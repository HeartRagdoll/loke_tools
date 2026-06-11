"""后台检测线程 — 避免阻塞 UI"""
from typing import Optional

import numpy as np
from PyQt5.QtCore import QThread, pyqtSignal

from app.core.detector import TwoStageDetector
from app.utils.logger import logger


class DetectThread(QThread):
    """后台检测线程，避免阻塞 UI"""
    result_ready = pyqtSignal(dict, object)  # result dict + roi_image ndarray

    def __init__(self, detector: TwoStageDetector):
        super().__init__()
        self.detector = detector
        self.image: Optional[np.ndarray] = None
        self._running = True

    def run(self) -> None:
        while self._running:
            if self.image is not None:
                img = self.image.copy()
                self.image = None
                try:
                    result, roi = self.detector.process_image(img)
                    self.result_ready.emit(result, roi)
                except Exception as e:
                    logger.error(f"检测异常: {e}")
            self.msleep(50)

    def stop(self) -> None:
        self._running = False
