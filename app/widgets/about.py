"""关于弹窗"""
from PyQt5.QtCore import Qt as QtCore
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton,
)


class AboutDialog(QDialog):
    """洛克工具 - 关于弹窗"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("关于 - 洛克工具")
        self.setFixedSize(440, 360)
        self.setWindowFlags(self.windowFlags() & ~QtCore.WindowContextHelpButtonHint)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 24, 30, 24)
        layout.setSpacing(10)

        title = QLabel("洛克工具 - 盒子识别")
        title.setAlignment(QtCore.AlignCenter)
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        title.setFixedHeight(40)
        layout.addWidget(title)

        version = QLabel("版本信息: 2.0")
        version.setAlignment(QtCore.AlignCenter)
        version.setStyleSheet("font-size: 13px; color: #6c7086;")
        layout.addWidget(version)

        sep = QLabel("")
        sep.setFixedHeight(8)
        layout.addWidget(sep)

        lines = [
            ("B站账号: 布心-偶猫", True),       # 可选复制
            ("", False),
            ("本软件完全免费，只是为了方便自己刷盒子懒得一直盯着。", False),
            ("如果帮助到你了,记得给UP点个赞哦。", False),
            ("", False),
            ("UP创建了自己的交流群: 1101212530", True),  # 可选复制
            ("", False),
            ("后续还会继续优化，有问题也可以进行反馈哦。", False),
        ]
        for text, copyable in lines:
            if not text:
                layout.addSpacing(8)
                continue
            lbl = QLabel(text)
            lbl.setAlignment(QtCore.AlignCenter)
            if text.startswith("交流群"):
                lbl.setStyleSheet("font-size: 13px; color: #89b4fa; font-weight: bold;")
            elif text.startswith("UP") or text.startswith("B站"):
                lbl.setStyleSheet("font-size: 13px; color: #f9e2af;")
            elif text.startswith("本软件"):
                lbl.setStyleSheet("font-size: 12px; color: #a6adc8;")
            else:
                lbl.setStyleSheet("font-size: 12px; color: #a6adc8;")

            if copyable:
                lbl.setTextInteractionFlags(QtCore.TextSelectableByMouse)
                lbl.setToolTip("选中后 Ctrl+C 即可复制")

            layout.addWidget(lbl)

        layout.addStretch()

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton("关闭")
        close_btn.setObjectName("primary_btn")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)
