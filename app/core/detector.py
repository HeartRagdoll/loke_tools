"""
YOLO 检测器封装 - 支持盒子检测和属性识别两阶段检测
"""
import threading
from pathlib import Path
from typing import Optional, Callable

import numpy as np

from app.utils.logger import logger
from app.utils.config import ConfigManager


class YOLODetector:
    """YOLO 检测器，封装模型加载与推理"""

    def __init__(self, model_path: str = ""):
        self._model = None
        self._model_path = ""
        self._lock = threading.Lock()
        if model_path:
            self.load(model_path)

    def load(self, model_path: str) -> bool:
        """加载模型"""
        with self._lock:
            try:
                from ultralytics import YOLO
                path = Path(model_path)
                if not path.exists():
                    logger.error(f"模型文件不存在: {model_path}")
                    return False
                self._model = YOLO(str(path))
                self._model_path = model_path
                logger.info(f"模型加载成功: {model_path}")
                return True
            except Exception as e:
                logger.error(f"模型加载失败: {e}")
                self._model = None
                return False

    def predict(self, image: np.ndarray, conf: float = 0.25, **kwargs):
        """对图像进行推理，返回 ultralytics Results 对象列表"""
        with self._lock:
            if self._model is None:
                logger.error("模型未加载")
                return None
            try:
                results = self._model.predict(
                    image, conf=conf, verbose=False, **kwargs
                )
                return results
            except Exception as e:
                logger.error(f"推理失败: {e}")
                return None

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    @property
    def model_path(self) -> str:
        return self._model_path

    @staticmethod
    def extract_boxes(results) -> list:
        """从 Results 中提取边界框列表 [(x1,y1,x2,y2,conf,cls), ...]"""
        boxes = []
        if results is None:
            return boxes
        for r in results:
            if r.boxes is None:
                continue
            try:
                xyxy = r.boxes.xyxy.cpu().numpy() if hasattr(r.boxes.xyxy, 'cpu') else np.array(r.boxes.xyxy)
                conf = r.boxes.conf.cpu().numpy() if hasattr(r.boxes.conf, 'cpu') else np.array(r.boxes.conf)
                cls = r.boxes.cls.cpu().numpy() if hasattr(r.boxes.cls, 'cpu') else np.array(r.boxes.cls)
                for i in range(len(xyxy)):
                    boxes.append((
                        int(xyxy[i][0]), int(xyxy[i][1]),
                        int(xyxy[i][2]), int(xyxy[i][3]),
                        float(conf[i]), int(cls[i])
                    ))
            except Exception:
                pass
        return boxes

    @staticmethod
    def get_best_box(results):
        """获取置信度最高的盒子"""
        boxes = YOLODetector.extract_boxes(results)
        if not boxes:
            return None
        boxes.sort(key=lambda b: (b[2] - b[0]) * (b[3] - b[1]), reverse=True)
        return boxes[0]


class TwoStageDetector:
    """两阶段检测器：先用盒子模型找位置，再用属性模型识别三个区域"""

    def __init__(self, box_conf: float = 0.8, attr_conf: float = 0.8):
        self.box_detector = YOLODetector()
        self.attr_detector = YOLODetector()
        self.box_conf = box_conf
        self.attr_conf = attr_conf
        self._running = False
        self._on_result: Optional[Callable] = None

    def load_box_model(self, path: str) -> bool:
        return self.box_detector.load(path)

    def load_attr_model(self, path: str) -> bool:
        return self.attr_detector.load(path)

    @property
    def is_running(self) -> bool:
        return self._running

    def set_callback(self, callback: Optional[Callable]) -> None:
        """设置结果回调 callback(box, attrs_result)"""
        self._on_result = callback

    def process_image(self, image: np.ndarray) -> tuple:
        """
        对图像进行两阶段识别
        返回: (result, roi_image)
        result: {"box": (x1,y1,x2,y2), "attrs": {"top": label, "middle": label, "bottom": label}}
        roi_image: 裁剪的盒子区域 numpy 数组，或 None
        """
        result = {"box": None, "attrs": {}}
        roi = None

        if not self.box_detector.is_loaded:
            return result, roi

        # 粗定位：盒子检测
        box_results = self.box_detector.predict(image, conf=self.box_conf)
        best_box = YOLODetector.get_best_box(box_results)
        if best_box is None:
            return result, roi

        x1, y1, x2, y2 = best_box[:4]
        result["box"] = (x1, y1, x2, y2)

        # 裁剪盒子区域
        h, w = image.shape[:2]
        x1c = max(0, x1)
        y1c = max(0, y1)
        x2c = min(w, x2)
        y2c = min(h, y2)
        if x2c <= x1c or y2c <= y1c:
            return result, roi
        roi = image[y1c:y2c, x1c:x2c].copy()

        if not self.attr_detector.is_loaded:
            return result, roi

        # 细粒度识别：识别盒子内部三个区域的属性
        attr_results = self.attr_detector.predict(roi, conf=self.attr_conf)
        boxes_with_labels = []
        for r in attr_results:
            if r.boxes is None:
                continue
            try:
                xyxy = r.boxes.xyxy.cpu().numpy() if hasattr(r.boxes.xyxy, 'cpu') else np.array(r.boxes.xyxy)
                conf = r.boxes.conf.cpu().numpy() if hasattr(r.boxes.conf, 'cpu') else np.array(r.boxes.conf)
                cls = r.boxes.cls.cpu().numpy() if hasattr(r.boxes.cls, 'cpu') else np.array(r.boxes.cls)
                names = self.attr_detector._model.names if self.attr_detector._model else {}
                for i in range(len(xyxy)):
                    class_id = int(cls[i])
                    label = names.get(class_id, f"class_{class_id}")
                    boxes_with_labels.append((
                        float(xyxy[i][0]), float(xyxy[i][1]),
                        float(xyxy[i][2]), float(xyxy[i][3]),
                        float(conf[i]), label
                    ))
            except Exception:
                pass

        # 按中心 y 坐标从上到下排序，最多 3 个，直接按位置赋值
        if boxes_with_labels:
            boxes_with_labels.sort(key=lambda bx: (bx[1] + bx[3]) / 2)
            sorted_labels = [bx[5] for bx in boxes_with_labels]
            result["attrs"]["top"] = sorted_labels[0] if len(sorted_labels) > 0 else None
            result["attrs"]["middle"] = sorted_labels[1] if len(sorted_labels) > 1 else None
            result["attrs"]["bottom"] = sorted_labels[2] if len(sorted_labels) > 2 else None

        return result, roi
