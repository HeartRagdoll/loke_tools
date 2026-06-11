"""
配置管理器 - 负责读写 config.json
"""
import json
from pathlib import Path
from typing import Any, Optional

from app.utils.paths import get_config_path


class ConfigManager:
    """全局配置单例"""

    _instance: Optional["ConfigManager"] = None
    _config: dict = {}

    def __new__(cls) -> "ConfigManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load()
        return cls._instance

    @property
    def config_path(self) -> Path:
        return get_config_path()

    def _load(self) -> None:
        try:
            path = self.config_path
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    self._config = json.load(f)
            else:
                self._config = {}
                self._save()
        except Exception:
            self._config = {}
            self._save()

    def _save(self) -> None:
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self._config, f, ensure_ascii=False, indent=4)
        except Exception:
            pass

    def get(self, key: str, default: Any = None) -> Any:
        return self._config.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._config[key] = value
        self._save()

    @property
    def default_box_label(self) -> str:
        return self.get("default_box_label", "box")

    @property
    def attr_labels(self) -> dict:
        return self.get("attr_labels", {
            "top": [],
            "middle": [],
            "bottom": [],
        })

    @attr_labels.setter
    def attr_labels(self, value: dict) -> None:
        self.set("attr_labels", value)

    @property
    def detect_interval_ms(self) -> int:
        return self.get("detect_interval_ms", 1000)

    @detect_interval_ms.setter
    def detect_interval_ms(self, value: int) -> None:
        self.set("detect_interval_ms", value)

    @property
    def hide_interval_ms(self) -> int:
        return self.get("hide_interval_ms", 10000)

    @hide_interval_ms.setter
    def hide_interval_ms(self, value: int) -> None:
        self.set("hide_interval_ms", value)

    @property
    def last_model_box(self) -> str:
        return self.get("last_model_box", "")

    @last_model_box.setter
    def last_model_box(self, value: str) -> None:
        self.set("last_model_box", value)

    @property
    def last_model_attr(self) -> str:
        return self.get("last_model_attr", "")

    @last_model_attr.setter
    def last_model_attr(self, value: str) -> None:
        self.set("last_model_attr", value)

    # ---- 检测阈值 ----

    @property
    def box_conf_threshold(self) -> float:
        return self.get("box_conf_threshold", 0.8)

    @box_conf_threshold.setter
    def box_conf_threshold(self, value: float) -> None:
        self.set("box_conf_threshold", value)

    @property
    def attr_conf_threshold(self) -> float:
        return self.get("attr_conf_threshold", 0.8)

    @attr_conf_threshold.setter
    def attr_conf_threshold(self, value: float) -> None:
        self.set("attr_conf_threshold", value)

    # ---- 浮窗显示 ----

    @property
    def overlay_font_size(self) -> int:
        """浮窗结果文字大小，单位 px"""
        return self.get("overlay_font_size", 16)

    @overlay_font_size.setter
    def overlay_font_size(self, value: int) -> None:
        self.set("overlay_font_size", value)

    # ---- 上次标注位置（像素坐标） ----

    def get_last_rects(self) -> dict:
        return self.get("last_rects", {"box": None, "attr": None})

    def set_last_rects(self, box: dict = None, attr: dict = None) -> None:
        self.set("last_rects", {"box": box, "attr": attr})

    def reset_last_rects(self) -> None:
        self.set("last_rects", {"box": None, "attr": None})

    @property
    def window_geometry(self) -> dict:
        return self.get("window_geometry", {
            "main": {"x": 613, "y": 38, "width": 473, "height": 80},
            "dataset": {"x": 355, "y": 175, "width": 1200, "height": 750},
        })

    @window_geometry.setter
    def window_geometry(self, value: dict) -> None:
        self.set("window_geometry", value)

    # ---- 浮窗位置与锁定状态 ----

    @property
    def overlay_geometry(self) -> dict:
        return self.get("overlay_geometry", {
            "x": 1700, "y": 150, "w": 210, "h": 315, "locked": True,
        })

    @overlay_geometry.setter
    def overlay_geometry(self, value: dict) -> None:
        self.set("overlay_geometry", value)

    # ---- 截屏识别区域（屏幕坐标） ----

    @property
    def capture_region(self) -> dict:
        """截屏区域，None 表示全屏；dict: {x, y, w, h}"""
        return self.get("capture_region", {
            "x": 295, "y": -1, "w": 1400, "h": 1080,
        })

    @capture_region.setter
    def capture_region(self, value: dict) -> None:
        self.set("capture_region", value)
