"""
YOLO 训练封装 — 监控线程实现可靠中断停止
"""
import threading
import time
from pathlib import Path
from typing import Optional, Callable

from app.utils.logger import logger
from app.utils.device import get_device


class YOLOTrainer:
    """YOLO 模型训练器

    训练在后台线程执行。另起一个监控线程高频检查停止请求，
    直接操作 ultralytics trainer 对象，避免被 model.train() 阻塞。
    """

    def __init__(self):
        self._training = False
        self._stop_event = threading.Event()
        self._model = None          # YOLO 实例（在主训练线程中赋值）
        self._on_progress: Optional[Callable] = None
        self._on_done: Optional[Callable] = None

    # ---- 公开接口 -------------------------------------------------

    @property
    def is_training(self) -> bool:
        return self._training

    def set_callbacks(
        self,
        on_progress: Optional[Callable[[str], None]] = None,
        on_done: Optional[Callable[[bool, str], None]] = None,
    ) -> None:
        self._on_progress = on_progress
        self._on_done = on_done

    def stop(self) -> None:
        if self._training:
            self._stop_event.set()
            self._emit("已请求停止训练，等待本轮 epoch 完成...")

    def train(
        self,
        data_yaml: str,
        model_type: str,
        model_dir: str,
        model_name: str = "",
        epochs: int = 100,
        imgsz: int = 640,
        batch: int = 16,
        lr0: float = 0.003,
        optimizer: str = "auto",
        pretrained: str = "yolo11n.pt",
    ) -> Optional[threading.Thread]:
        """启动训练线程"""
        if self._training:
            logger.warning("已有训练任务运行中")
            return None

        self._stop_event.clear()
        self._training = True
        thread = threading.Thread(
            target=self._train_thread,
            args=(data_yaml, model_type, model_dir, model_name,
                  epochs, imgsz, batch, lr0, optimizer, pretrained),
            daemon=True,
        )
        thread.start()
        return thread

    # ---- 内部 -----------------------------------------------------

    def _emit(self, msg: str) -> None:
        if self._on_progress:
            try:
                self._on_progress(msg)
            except Exception:
                pass

    def _train_thread(
        self,
        data_yaml: str,
        model_type: str,
        model_dir: str,
        model_name: str,
        epochs: int,
        imgsz: int,
        batch: int,
        lr0: float,
        optimizer: str,
        pretrained: str,
    ) -> None:
        """训练主线程 — 加载模型 → 启动监控 → 训练 → 后处理"""
        try:
            from ultralytics import YOLO

            self._emit("正在加载预训练模型...")
            self._model = YOLO(pretrained)

            # 启动监控线程：训练线程阻塞于 model.train()，监控线程独立运作
            monitor = threading.Thread(
                target=self._monitor_loop, daemon=True)
            monitor.start()

            out_path = Path(model_dir) / model_name
            self._emit(f"开始训练 epochs={epochs} batch={batch}...")

            self._model.train(
                data=data_yaml,
                epochs=epochs,
                imgsz=imgsz,
                batch=batch,
                device=get_device(),
                lr0=lr0,
                optimizer=optimizer,
                project=str(Path(model_dir)),
                name=model_name,
                exist_ok=False,
                verbose=False,
            )

            # 等待监控线程结束
            monitor.join(timeout=2)

            # 后处理
            final_path = self._cleanup_model_output(str(out_path))

            if self._stop_event.is_set():
                self._done(True, f"训练已停止，模型: {final_path}")
            else:
                self._done(True, f"训练完成，模型: {final_path}")

        except Exception as e:
            logger.error(f"训练失败: {e}")
            self._done(False, f"训练失败: {e}")
        finally:
            self._model = None
            self._training = False

    def _monitor_loop(self) -> None:
        """监控线程：高频检查停止事件，直接与 trainer 交互"""
        # 等待 trainer 对象初始化（model.train() 内部会创建）
        for _ in range(100):  # 最多等 10 秒
            if self._model is not None and hasattr(self._model, 'trainer') and self._model.trainer:
                break
            time.sleep(0.1)

        # 持续监控停止请求
        while not self._stop_event.is_set():
            try:
                trainer = self._model.trainer
                if trainer and getattr(trainer, 'stopped', False):
                    break  # 训练已自然结束
            except Exception:
                pass
            time.sleep(0.2)

        # 收到停止信号 → 通知 trainer
        if self._stop_event.is_set():
            try:
                trainer = self._model.trainer
                if trainer:
                    trainer.stop_training = True
                    if hasattr(trainer, 'stop'):
                        trainer.stop()
                    self._emit("已在当前 epoch 结束后中断训练")
            except Exception as e:
                logger.error(f"停止训练时出错: {e}")

    def _done(self, success: bool, msg: str) -> None:
        if self._on_done:
            try:
                self._on_done(success, msg)
            except Exception:
                pass

    # ---- 后处理 ---------------------------------------------------

    @staticmethod
    def _cleanup_model_output(out_dir: str) -> str:
        """复制 best.pt 到上级目录，清理 weights/，保留训练图表"""
        import shutil

        out_path = Path(out_dir)
        weights_dir = out_path / "weights"
        best_pt = weights_dir / "best.pt"
        final_path = out_path.parent / f"{out_path.name}.pt"

        try:
            if best_pt.exists():
                if final_path.exists():
                    final_path.unlink()
                shutil.copy2(str(best_pt), str(final_path))
                logger.info(f"best.pt → {final_path}")
            else:
                logger.warning(f"best.pt 不存在: {best_pt}")

            if weights_dir.exists():
                shutil.rmtree(weights_dir)

            logger.info(f"模型后处理完成: {final_path} (图表保留在 {out_dir})")
            return str(final_path)
        except Exception as e:
            logger.error(f"模型后处理失败: {e}")
            return str(out_dir)
