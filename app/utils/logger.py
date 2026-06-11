"""
日志模块 - 统一的日志管理
"""
import logging
import sys

from app.utils.paths import get_logs_dir


def setup_logger(name: str = "RockTool") -> logging.Logger:
    """配置并返回日志器"""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    # 控制台输出
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_fmt = logging.Formatter(
        "[%(asctime)s] %(levelname)s - %(message)s", datefmt="%H:%M:%S"
    )
    console_handler.setFormatter(console_fmt)
    logger.addHandler(console_handler)

    # 文件输出
    log_dir = get_logs_dir()
    log_dir.mkdir(exist_ok=True)
    file_handler = logging.FileHandler(
        log_dir / "app.log", encoding="utf-8", mode="a"
    )
    file_handler.setLevel(logging.DEBUG)
    file_fmt = logging.Formatter(
        "[%(asctime)s] %(levelname)s [%(name)s] %(message)s"
    )
    file_handler.setFormatter(file_fmt)
    logger.addHandler(file_handler)

    return logger


logger = setup_logger()
