"""截屏识别区域编辑器 — 可拖拽+伸缩的矩形框"""
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPainter, QPen, QColor
from PyQt5.QtWidgets import QWidget, QPushButton, QHBoxLayout

from app.widgets.drag_resize_mixin import DragResizeMixin


class RegionEditor(DragResizeMixin, QWidget):
    """截屏识别区域编辑浮窗 — 蓝色边框半透明矩形

    用法:
        editor = RegionEditor(capture_region, overlay)
        editor.confirmed.connect(on_confirm)
        editor.cancelled.connect(on_cancel)
        editor.show()
    """

    confirmed = pyqtSignal(dict)
    cancelled = pyqtSignal()

    _MIN_DRAG_W = 60
    _MIN_DRAG_H = 90   # 预留按钮栏高度
    _HANDLE_R = 5
    _BAR_H = 36
    _BORDER_COLOR = QColor(137, 180, 250)
    _FILL_COLOR = QColor(137, 180, 250, 30)

    def __init__(self, region: dict = None, overlay: QWidget = None):
        QWidget.__init__(self)

        # 使用全屏 geometry（含任务栏），确保区域可覆盖整个屏幕
        screen_geo = self.screen().geometry()
        DragResizeMixin.__init__(
            self, min_w=self._MIN_DRAG_W, min_h=self._MIN_DRAG_H,
            bounds=screen_geo,
        )

        self.setWindowFlags(
            Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setMinimumSize(self._MIN_DRAG_W, self._MIN_DRAG_H)

        self._overlay = overlay

        if region and all(k in region for k in ("x", "y", "w", "h")):
            self.setGeometry(
              region.get("x", 295), 
              region.get("y", -1), 
              region.get("w", 1400), 
              region.get("h", 1080)
            )
        else:
            dw = int(screen_geo.width() * 0.6)
            dh = int(screen_geo.height() * 0.6)
            dx = screen_geo.left() + (screen_geo.width() - dw) // 2
            dy = screen_geo.top() + (screen_geo.height() - dh) // 2
            self.setGeometry(dx, dy, dw, dh)

        self.drag_move_callback = self._check_overlap
        self._init_ui()

    # ---- UI -------------------------------------------------------

    def _init_ui(self) -> None:
        # 按钮栏 — 置于区域内部，顶部居中偏下
        self._bar = QWidget(self)
        self._bar.setStyleSheet("background: rgba(24,24,37,220); border-radius: 6px;")
        bar_layout = QHBoxLayout(self._bar)
        bar_layout.setContentsMargins(10, 4, 10, 4)
        bar_layout.setSpacing(6)

        self._status_label = QPushButton("重叠：请调整位置")
        self._status_label.setEnabled(False)
        self._status_label.setStyleSheet(
            "QPushButton { background: transparent; color: #f38ba8; font-weight: bold; font-size: 11px; }"
        )
        bar_layout.addWidget(self._status_label)
        bar_layout.addStretch()

        self._confirm_btn = QPushButton("确定")
        self._confirm_btn.setStyleSheet(
            "QPushButton { background: #a6e3a1; color: #1e1e2e; border-radius: 4px; "
            "padding: 3px 14px; font-weight: bold; font-size: 12px; }"
            "QPushButton:hover { background: #b9edb5; }"
            "QPushButton:disabled { background: #45475a; color: #6c7086; }"
        )
        self._confirm_btn.clicked.connect(self._on_confirm)
        bar_layout.addWidget(self._confirm_btn)

        self._cancel_btn = QPushButton("取消")
        self._cancel_btn.setStyleSheet(
            "QPushButton { background: #f38ba8; color: #1e1e2e; border-radius: 4px; "
            "padding: 3px 14px; font-weight: bold; font-size: 12px; }"
            "QPushButton:hover { background: #f5a0b8; }"
        )
        self._cancel_btn.clicked.connect(self._on_cancel)
        bar_layout.addWidget(self._cancel_btn)

        self._update_bar_geometry()

    def resizeEvent(self, event) -> None:
        QWidget.resizeEvent(self, event)
        self._update_bar_geometry()

    def _update_bar_geometry(self) -> None:
        bar_w = 260
        x = (self.width() - bar_w) // 2
        y = 8  # 顶部边下方
        self._bar.setGeometry(x, y, min(bar_w, self.width() - 12), self._BAR_H)

    def showEvent(self, event) -> None:
        QWidget.showEvent(self, event)
        self._check_overlap()

    # ---- 重叠检测 -------------------------------------------------

    def _check_overlap(self) -> None:
        if self._overlay is None or not self._overlay.isVisible():
            self._confirm_btn.setEnabled(True)
            self._status_label.setVisible(False)
            return

        overlapped = self.geometry().intersects(self._overlay.geometry())
        self._confirm_btn.setEnabled(not overlapped)
        self._status_label.setVisible(overlapped)

    # ---- 确定 / 取消 -----------------------------------------------

    def _on_confirm(self) -> None:
        g = self.geometry()
        self.confirmed.emit({"x": g.x(), "y": g.y(), "w": g.width(), "h": g.height()})
        self.close()

    def _on_cancel(self) -> None:
        self.cancelled.emit()
        self.close()

    # ---- 绘制 -----------------------------------------------------

    def paintEvent(self, event) -> None:
        QWidget.paintEvent(self, event)
        w, h = self.width(), self.height()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        painter.setBrush(self._FILL_COLOR)
        painter.setPen(Qt.NoPen)
        painter.drawRect(0, 0, w - 1, h - 1)

        painter.setPen(QPen(self._BORDER_COLOR, 2))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(1, 1, w - 3, h - 3)

        painter.end()
        DragResizeMixin.draw_resize_handles(self, self._HANDLE_R, self._BORDER_COLOR)

    # ---- 鼠标事件 → 委托 Mixin ------------------------------------

    def mousePressEvent(self, event) -> None:
        self._mix_mouse_press(event)

    def mouseMoveEvent(self, event) -> None:
        self._mix_mouse_move(event)

    def mouseReleaseEvent(self, event) -> None:
        self._mix_mouse_release(event)
