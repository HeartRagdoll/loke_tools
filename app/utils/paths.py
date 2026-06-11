"""
应用路径解析 — 兼容开发环境与 PyInstaller 打包后的 exe

- 开发环境：`__file__` 正常可用，根目录为项目根
- exe 环境：`sys.frozen=True`，可写资源在 exe 同级目录
"""
import sys
from pathlib import Path


def get_app_root() -> Path:
    """获取应用根目录（可写资源所在位置）

    - 开发环境：app/utils/paths.py 向上 3 级 = 项目根 (loke_tools/)
    - exe 环境：sys.executable 所在目录（exe 同级）
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent.parent.parent


def get_models_dir() -> Path:
    """模型目录"""
    return get_app_root() / "models"


def get_data_dir() -> Path:
    """数据集目录"""
    return get_app_root() / "data"


def get_logs_dir() -> Path:
    """日志目录"""
    return get_app_root() / "logs"


def get_config_path() -> Path:
    """config.json 路径"""
    return get_app_root() / "config.json"
