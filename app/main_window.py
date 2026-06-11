"""
主窗口 - 横向工具栏 + 半透明识别结果浮窗
"""
from pathlib import Path
from typing import Optional

import numpy as np
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QMainWindow, QPushButton, QWidget,
    QLabel, QMessageBox,
    QApplication,
    QHBoxLayout, QVBoxLayout,
)

from app.core.detector import TwoStageDetector
from app.utils.paths import get_models_dir
from app.core.capture import ScreenCapture
from app.utils.config import ConfigManager
from app.utils.logger import logger
from app.widgets.styles import MAIN_STYLE
from app.widgets.result_overlay import ResultOverlay
from app.widgets.detect_thread import DetectThread


class MainWindow(QMainWindow):
    """主窗口 — 横向工具栏 + 浮窗结果显示"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("洛克工具 - 盒子识别 2.0")
        self.setWindowFlags(
            Qt.WindowStaysOnTopHint
            | Qt.WindowMinimizeButtonHint
            | Qt.WindowCloseButtonHint
        )
        self.setMinimumWidth(420)
        self.setFixedHeight(90)

        self._config = ConfigManager()
        self._detector = TwoStageDetector(
            box_conf=self._config.box_conf_threshold,
            attr_conf=self._config.attr_conf_threshold,
        )
        self._capture = ScreenCapture()
        self._detecting = False
        self._detect_thread: Optional[DetectThread] = None
        self._dataset_window = None
        self._overlay: Optional[ResultOverlay] = None

        self._init_ui()
        self._load_last_model()
        self._restore_geometry()
        self._init_overlay()

    def _init_ui(self) -> None:
        self.setStyleSheet(MAIN_STYLE)

        # 中央 widget 使用垂直布局：工具栏 + 状态标签
        central = QWidget()
        central.setObjectName("toolbar_container")
        central.setStyleSheet("""
            QWidget#toolbar_container {
                background-color: #181825;
                border-bottom: 2px solid #313244;
                padding: 2px 10px;
            }
        """)
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 4, 10, 4)
        root.setSpacing(2)

        # ---- 工具栏行 ----
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        # 识别按钮
        self.detect_btn = QPushButton("开始识别")
        self.detect_btn.setProperty("active", False)
        self.detect_btn.setToolTip("开始/停止持续截屏识别")
        self.detect_btn.clicked.connect(self._toggle_detect)
        toolbar.addWidget(self.detect_btn)

        # 设置按钮
        self.settings_btn = QPushButton("设置")
        self.settings_btn.setToolTip("选择/导入模型")
        self.settings_btn.clicked.connect(self._open_settings)
        toolbar.addWidget(self.settings_btn)

        # 弹性空间 — 把右侧按钮推到右边
        toolbar.addStretch()

        # 关于按钮
        self.about_btn = QPushButton("关于")
        self.about_btn.setToolTip("软件信息 & 联系方式")
        self.about_btn.clicked.connect(self._show_about)
        self.about_btn.setFixedWidth(60)
        toolbar.addWidget(self.about_btn)

        # 锁定/解锁按钮
        self.lock_btn = QPushButton("锁定浮窗")
        self.lock_btn.setToolTip("锁定后浮窗不可拖动，仅能通过此按钮解锁")
        self.lock_btn.clicked.connect(self._toggle_lock_overlay)
        toolbar.addWidget(self.lock_btn)

        root.addLayout(toolbar)

        # ---- 状态标签 ----
        self._status_label = QLabel("等待开始...")
        self._status_label.setStyleSheet(
            "color: #a6e3a1; font-size: 11px; padding-left: 2px;"
        )
        root.addWidget(self._status_label)

        self.setCentralWidget(central)

    def _init_overlay(self) -> None:
        """初始化浮窗：创建 → 恢复位置 → 启动时显示空白面板"""
        if self._overlay is not None:
            return
        self._overlay = ResultOverlay(
            hide_delay_ms=self._config.hide_interval_ms)

        # 恢复上次保存的位置
        geo = self._config.overlay_geometry
        saved_x = geo.get("x", 1700)
        saved_y = geo.get("y", 150)
        saved_w = geo.get("w", 210)
        saved_h = geo.get("h", 315)
        was_locked = geo.get("locked", False)

        if saved_x is not None and saved_y is not None:
            if saved_w is not None and saved_h is not None:
                self._overlay.resize(saved_w, saved_h)
            self._overlay.move(saved_x, saved_y)
            if was_locked:
                self._overlay.set_locked(True)
                self.lock_btn.setText("解锁浮窗")
                self.lock_btn.setProperty("active", True)
                self.lock_btn.style().unpolish(self.lock_btn)
                self.lock_btn.style().polish(self.lock_btn)
        else:
            # 首次使用：默认屏幕右上区域
            screen = QApplication.primaryScreen()
            if screen:
                avail = screen.availableGeometry()
                self._overlay.move(avail.right() - 520, avail.top() + 100)

        # 启动时：锁定状态下不显示，解锁时显示
        if not self._overlay.is_locked:
            self._overlay.show_placeholder()
        # 拖拽结束后保存位置
        self._overlay.drag_finished = self._save_overlay_position

    def _load_last_model(self) -> None:
        """从配置加载上次使用的盒子模型和属性模型，更新状态文本"""
        box_ok = self._load_model_by_dir(
            self._config.last_model_box,
            get_models_dir() / "box",
            self._detector.load_box_model,
            "盒子",
        )
        attr_ok = self._load_model_by_dir(
            self._config.last_model_attr,
            get_models_dir() / "attr",
            self._detector.load_attr_model,
            "属性",
        )
        lines = []
        lines.append("盒子模型: " + (f"已加载 {self._config.last_model_box}" if box_ok else "未加载"))
        lines.append("属性模型: " + (f"已加载 {self._config.last_model_attr}" if attr_ok else "未加载"))
        self._status_label.setText("\n".join(lines))

    @staticmethod
    def _load_model_by_dir(model_name: str, model_dir: Path, loader, tag: str) -> bool:
        """从指定目录加载模型，支持子目录查找。返回是否加载成功。"""
        if not model_name:
            return False
        model_path = model_dir / model_name
        if not model_path.exists():
            matches = list(model_dir.rglob(model_name))
            if matches:
                model_path = matches[0]
            else:
                logger.error(f"{tag}模型未找到: {model_name}")
                return False
        loader(str(model_path))
        return True

    def _toggle_detect(self) -> None:
        if self._detecting:
            self._stop_detect()
        else:
            self._start_detect()

    def _start_detect(self) -> None:
        if not self._detector.box_detector.is_loaded:
            QMessageBox.warning(self, "提示", "请先在设置中加载模型")
            return

        self._init_overlay()

        self._detecting = True
        self.detect_btn.setText("停止识别")
        self.detect_btn.setProperty("active", True)
        self.detect_btn.style().unpolish(self.detect_btn)
        self.detect_btn.style().polish(self.detect_btn)

        # 取消工具栏置顶：避免全屏游戏鼠标显现
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowStaysOnTopHint)
        # 最小化主窗口：避免遮挡游戏窗口
        self.showMinimized()

        # 自动锁定浮窗（先锁定再显示，确保自动隐藏定时器启动）
        self._overlay.set_locked(True)
        self._overlay.show_placeholder()
        self.lock_btn.setText("解锁浮窗")
        self.lock_btn.setProperty("active", True)
        self.lock_btn.style().unpolish(self.lock_btn)
        self.lock_btn.style().polish(self.lock_btn)

        self._detect_thread = DetectThread(self._detector)
        self._detect_thread.result_ready.connect(self._on_result)
        self._detect_thread.start()

        self._capture.set_callback(self._on_frame)
        self._capture.set_interval(self._config.detect_interval_ms / 1000.0)
        self._capture.start()

        self._status_label.setText("识别中...")
        logger.info("开始识别")

    def _stop_detect(self) -> None:
        self._detecting = False
        self.detect_btn.setText("开始识别")
        self.detect_btn.setProperty("active", False)
        self.detect_btn.style().unpolish(self.detect_btn)
        self.detect_btn.style().polish(self.detect_btn)

        # setWindowFlags 会重建原生窗口导致位置重置，先保存位置
        saved_pos = self.pos()
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        self.show()
        self.move(saved_pos)

        self._capture.stop()
        if self._detect_thread:
            self._detect_thread.stop()
            self._detect_thread.wait(1000)
            self._detect_thread = None

        if self._overlay:
            self._overlay.hide()

        self._status_label.setText("等待开始...")
        logger.info("停止识别")

    def _refresh_model_status(self) -> None:
        """刷新状态标签中模型加载信息（不重新加载模型）"""
        box_ok = self._detector.box_detector.is_loaded
        attr_ok = self._detector.attr_detector.is_loaded
        lines = [
            "盒子模型: " + (f"已加载 {self._config.last_model_box}" if box_ok else "未加载"),
            "属性模型: " + (f"已加载 {self._config.last_model_attr}" if attr_ok else "未加载"),
        ]
        self._status_label.setText("\n".join(lines))

    def _on_frame(self, image: np.ndarray) -> None:
        if self._detect_thread:
            self._detect_thread.image = image

    def _on_result(self, result: dict, roi_image: np.ndarray = None) -> None:
        """处理检测结果 — 仅在检测到目标时更新浮窗（无结果时不重置自动隐藏定时器）"""
        if self._overlay is None:
            return

        if result.get("box"):
            self._overlay.show_result(
                result["box"],
                result.get("attrs", {}),
                roi_image,
            )
            
    def _toggle_lock_overlay(self) -> None:
        if self._overlay is None:
            return
        if self._overlay.is_locked:
            self._overlay.set_locked(False)
            self.lock_btn.setText("锁定浮窗")
            self.lock_btn.setProperty("active", False)
            # 解锁后确保浮窗可见
            if not self._overlay.isVisible():
                self._overlay.show_placeholder()
        else:
            self._overlay.set_locked(True)
            self.lock_btn.setText("解锁浮窗")
            self.lock_btn.setProperty("active", True)
        self.lock_btn.style().unpolish(self.lock_btn)
        self.lock_btn.style().polish(self.lock_btn)
        self._save_overlay_position()

    def _save_overlay_position(self) -> None:
        """保存浮窗位置/大小/锁定状态到配置"""
        if self._overlay is None:
            return
        pos = self._overlay.pos()
        sz = self._overlay.size()
        self._config.overlay_geometry = {
            "x": pos.x(),
            "y": pos.y(),
            "w": sz.width(),
            "h": sz.height(),
            "locked": self._overlay.is_locked,
        }

    def _show_about(self) -> None:
        """关于弹窗"""
        from app.widgets.about import AboutDialog
        AboutDialog(self).exec_()

    def _open_dataset_window(self) -> None:
        if self._detecting:
            self._stop_detect()
        from app.dataset_window import DatasetWindow
        if self._dataset_window is None:
            self._dataset_window = DatasetWindow(main_window=self)
        self._dataset_window.show()
        self._dataset_window.raise_()

    def _open_settings(self) -> None:
        if self._detecting:
            self._stop_detect()
        from app.settings_window import SettingsWindow
        dialog = SettingsWindow(config=self._config, overlay=self._overlay,
                                capture=self._capture, detector=self._detector, parent=self)
        if dialog.exec_() == SettingsWindow.Accepted:
            model_path = dialog.selected_model_box
            if model_path:
                self._detector.load_box_model(model_path)
                self._config.last_model_box = Path(model_path).name
            attr_path = dialog.selected_model_attr
            if attr_path:
                self._detector.load_attr_model(attr_path)
                self._config.last_model_attr = Path(attr_path).name

        if dialog._want_dataset:
            self._open_dataset_window()

        # 刷新主窗口模型加载状态
        self._refresh_model_status()

    def _restore_geometry(self) -> None:
        geo = self._config.window_geometry.get("main")
        if isinstance(geo, dict):
            try:
                x = geo.get("x", 615)
                y = geo.get("y", 40)
                w = geo.get("width", 473)
                self.resize(w, self.height())
                self.move(x, y)
            except Exception:
                pass

    def _save_window_geometry(self) -> None:
        """保存主窗口位置/宽度到配置"""
        g = self.geometry()
        geo = self._config.window_geometry.copy()
        geo["main"] = {"x": g.x(), "y": g.y(), "width": g.width(), "height": g.height()}
        self._config.window_geometry = geo

    def moveEvent(self, event) -> None:
        """窗口移动后自动保存位置"""
        super().moveEvent(event)
        self._save_window_geometry()

    def resizeEvent(self, event) -> None:
        """窗口宽度变化后自动保存"""
        super().resizeEvent(event)
        self._save_window_geometry()

    def closeEvent(self, event) -> None:
        """关闭窗口时保存配置"""
        if self._detecting:
            self._stop_detect()
        if self._dataset_window:
            self._dataset_window.close()
        self._save_overlay_position()
        self._save_window_geometry()
        event.accept()
