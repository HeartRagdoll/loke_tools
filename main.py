"""
洛克工具
基于 YOLO11 的两阶段识别（盒子定位 + 属性识别）
"""
import ctypes
import os
import sys
import traceback
from pathlib import Path

# Windows 任务栏图标
if sys.platform == "win32":
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("RockTool.LockeTools.2_0")
    except Exception:
        pass

# 确保项目根目录在 sys.path 中
PROJECT_ROOT = Path(__file__).parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

def setup_env() -> None:
    """设置环境变量"""
    os.environ["OMP_NUM_THREADS"] = "1"
    os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"


def main() -> None:
    """程序入口"""
    setup_env()
    from app.utils.device import init_device
    from app.utils.logger import logger
    device_info = init_device()
    logger.info(f"设备检测: {device_info}")

    from PyQt5.QtWidgets import QApplication, QMessageBox
    from PyQt5.QtCore import Qt
    from PyQt5.QtGui import QIcon

    # 高DPI适配
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("洛克工具")
    app.setOrganizationName("RockTool")

    # 程序图标（窗口标题栏 & 任务栏）
    from app.utils.paths import get_app_root
    icon_path = get_app_root() / "icon.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    try:
        from app.main_window import MainWindow
        window = MainWindow()
        window.show()
    except Exception as e:
        err_msg = f"启动失败:\n{traceback.format_exc()}"
        QMessageBox.critical(None, "启动错误", err_msg)
        sys.exit(1)

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
