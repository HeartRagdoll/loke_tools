"""
全局 QSS 样式
"""

MAIN_STYLE = """
/* 全局 */
* {
    font-family: "Microsoft YaHei", "SimHei", sans-serif;
    font-size: 13px;
}

QMainWindow {
    background-color: #1e1e2e;
}

QWidget {
    background-color: #1e1e2e;
    color: #cdd6f4;
}

/* 工具栏容器 */
QWidget#toolbar_container {
    background-color: #181825;
    border-bottom: 2px solid #313244;
}

QWidget#toolbar_container QPushButton {
    background-color: #89b4fa;
    color: #1e1e2e;
    border: none;
    border-radius: 6px;
    padding: 6px 8px;
    font-weight: bold;
    font-size: 13px;
    min-width: 80px;
}

QWidget#toolbar_container QPushButton:hover {
    background-color: #b4d0fb;
}

QWidget#toolbar_container QPushButton:pressed {
    background-color: #74a8f7;
}

QWidget#toolbar_container QPushButton[active="true"] {
    background-color: #f38ba8;
    color: #1e1e2e;
}

QWidget#toolbar_container QPushButton[active="true"]:hover {
    background-color: #f5a0b8;
}

QWidget#toolbar_container QPushButton:disabled {
    background-color: #45475a;
    color: #6c7086;
}

/* 下拉框 */
QComboBox {
    background-color: #313244;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 5px 10px;
    min-width: 140px;
    color: #cdd6f4;
}

QComboBox:hover {
    border-color: #89b4fa;
}

QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 24px;
    border-left: 1px solid #45475a;
    border-top-right-radius: 6px;
    border-bottom-right-radius: 6px;
}

QComboBox QAbstractItemView {
    background-color: #313244;
    border: 1px solid #45475a;
    color: #cdd6f4;
    selection-background-color: #89b4fa;
    selection-color: #1e1e2e;
}

/* 标签 */
QLabel {
    color: #cdd6f4;
    background: transparent;
}

QLabel#title {
    font-size: 15px;
    font-weight: bold;
    color: #89b4fa;
}

QLabel#result_title {
    font-size: 16px;
    font-weight: bold;
    color: #a6e3a1;
}

QLabel#attr_result {
    font-size: 14px;
    color: #f9e2af;
    padding: 4px 0;
}

/* 列表 */
QListWidget {
    background-color: #181825;
    border: 1px solid #313244;
    border-radius: 6px;
    color: #cdd6f4;
    outline: none;
}

QListWidget::item {
    padding: 8px 12px;
    border-bottom: 1px solid #313244;
}

QListWidget::item:selected {
    background-color: #89b4fa;
    color: #1e1e2e;
}

QListWidget::item:hover {
    background-color: #313244;
}

/* 滚动条 */
QScrollBar:vertical {
    background: #181825;
    width: 8px;
    border: none;
}

QScrollBar::handle:vertical {
    background: #45475a;
    border-radius: 4px;
    min-height: 30px;
}

QScrollBar::handle:vertical:hover {
    background: #585b70;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}

QScrollBar:horizontal {
    background: #181825;
    height: 8px;
    border: none;
}

QScrollBar::handle:horizontal {
    background: #45475a;
    border-radius: 4px;
    min-width: 30px;
}

QScrollBar::handle:horizontal:hover {
    background: #585b70;
}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
}

/* 分割线 */
QSplitter::handle {
    background-color: #313244;
    width: 2px;
}

/* 输入框 */
QLineEdit {
    background-color: #313244;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 6px 10px;
    color: #cdd6f4;
}

QLineEdit:focus {
    border-color: #89b4fa;
}

/* 面板 */
QWidget#panel {
    background-color: #181825;
    border: 1px solid #313244;
    border-radius: 8px;
    padding: 10px;
}

QGroupBox {
    background-color: #181825;
    border: 1px solid #313244;
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 16px;
    color: #cdd6f4;
    font-weight: bold;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: #89b4fa;
}
"""

DATASET_WINDOW_STYLE = """
/* 按钮 */
QPushButton {
    background-color: #45475a;
    color: #cdd6f4;
    border: none;
    border-radius: 5px;
    padding: 5px 14px;
    font-weight: bold;
}

QPushButton:hover {
    background-color: #585b70;
}

QPushButton:pressed {
    background-color: #313244;
}

QPushButton#primary_btn {
    background-color: #89b4fa;
    color: #1e1e2e;
    padding: 7px 20px;
    font-size: 14px;
}

QPushButton#primary_btn:hover {
    background-color: #b4d0fb;
}

QPushButton#danger_btn {
    background-color: #f38ba8;
    color: #1e1e2e;
}

QPushButton#danger_btn:hover {
    background-color: #f5a0b8;
}

QPushButton#success_btn {
    background-color: #a6e3a1;
    color: #1e1e2e;
    padding: 7px 20px;
    font-size: 14px;
}

QPushButton#success_btn:hover {
    background-color: #b9edb5;
}

QPushButton#success_btn:disabled {
    background-color: #45475a;
    color: #6c7086;
}

QPushButton#edit_btn {
    background-color: #fab387;
    color: #1e1e2e;
    padding: 4px 10px;
    font-size: 12px;
}

QPushButton#edit_btn:hover {
    background-color: #fbc49e;
}

QPushButton#edit_btn[editing="true"] {
    background-color: #a6e3a1;
}

/* 文本区域 */
QTextEdit {
    background-color: #181825;
    border: 1px solid #313244;
    border-radius: 6px;
    color: #cdd6f4;
    padding: 8px;
}

/* 进度条 */
QProgressBar {
    background-color: #313244;
    border: none;
    border-radius: 4px;
    height: 6px;
    text-align: center;
    color: transparent;
}

QProgressBar::chunk {
    background-color: #89b4fa;
    border-radius: 4px;
}
"""
