"""
屏幕捕获模块 - 支持全屏截图和区域截图
"""
import threading
import time
from typing import Optional, Callable

import numpy as np
from PIL import ImageGrab

from app.utils.config import ConfigManager


class ScreenCapture:
    """屏幕捕获器 — 支持全屏或指定区域"""

    def __init__(self):
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._interval: float = 1.0
        self._callback: Optional[Callable] = None
        self._config = ConfigManager()

    def set_callback(self, callback: Callable[[np.ndarray], None]) -> None:
        """设置截图回调，每捕获一帧调用一次"""
        self._callback = callback

    def set_interval(self, seconds: float) -> None:
        self._interval = max(0.1, seconds)

    @property
    def is_running(self) -> bool:
        return self._running

    def capture_once(self) -> Optional[np.ndarray]:
        """单次截图（全屏或按 capture_region 裁剪），返回 RGB numpy array"""
        try:
            region = self._config.capture_region
            if region and all(k in region for k in ("x", "y", "w", "h")):
                bbox = (
                    region["x"], region["y"],
                    region["x"] + region["w"], region["y"] + region["h"],
                )
                img = ImageGrab.grab(bbox=bbox, all_screens=True)
            else:
                img = ImageGrab.grab(all_screens=True)
            return np.array(img.convert("RGB"))
        except Exception as e:
            from app.utils.logger import logger
            logger.error(f"截图失败: {e}")
            return None

    def start(self) -> None:
        """开始持续截图（后台线程）"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """停止截图"""
        self._running = False

    def _capture_loop(self) -> None:
        from app.utils.logger import logger
        while self._running:
            t0 = time.time()
            try:
                img = self.capture_once()
                if img is not None and self._callback:
                    self._callback(img)
            except Exception as e:
                logger.error(f"截图循环异常: {e}")
            elapsed = time.time() - t0
            sleep_time = max(0, self._interval - elapsed)
            if sleep_time > 0 and self._running:
                time.sleep(sleep_time)
