"""半透明识别结果浮窗 — 拖拽 + 伸缩 + 自动隐藏"""
import numpy as np
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPixmap, QImage, QColor
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy

from app.widgets.drag_resize_mixin import DragResizeMixin


class ResultOverlay(DragResizeMixin, QWidget):
    """半透明识别结果浮窗 — 未锁定时可拖拽+伸缩，锁定后全透明"""

    _LABEL_COLORS = {
        "普通": "#f9e2af",
        "通行证": "#d38aaa",
        "赛季奇遇": "#fab387",
        "杂项": "#94e2d5",
        "异色": "#89b4fa",
        "奇异": "#a6e3a1",
        "混系": "#cba6f7",
        "污染": "#b4befe",
        "+魔攻": "#a6e3a1",
        "+魔防": "#a6e3a1",
        "+物攻": "#a6e3a1",
        "+物防": "#a6e3a1",
        "+速度": "#a6e3a1",
        "+生命": "#a6e3a1",
    }

    _DEFAULT_COLOR = "#a6e3a1"
    _HANDLE_R = 5
    _HANDLE_COLOR = QColor(137, 180, 250)

    _MIN_DRAG_W = 180
    _MIN_DRAG_H = 200

    def __init__(self, parent=None, hide_delay_ms: int = 3000):
        QWidget.__init__(self, parent)
        DragResizeMixin.__init__(
            self, min_w=self._MIN_DRAG_W, min_h=self._MIN_DRAG_H,
            bounds=self.screen().availableGeometry(),
        )

        self.setWindowFlags(
            Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setMinimumSize(self._MIN_DRAG_W, self._MIN_DRAG_H)
        self.resize(100, 300)

        self._locked = False
        self._result_showing = False   # 有检测结果时 True，点击可隐藏

        # 自动隐藏定时器
        self._hide_delay_ms = hide_delay_ms
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.setInterval(hide_delay_ms)
        self._hide_timer.timeout.connect(self.hide)

        self._init_ui()

    # ---- 重写 Mixin 条件 -----------------------------------------

    def _drag_allowed(self) -> bool:
        return not self._locked and not self._result_showing

    # ---- UI ------------------------------------------------------

    def _init_ui(self) -> None:
        self._container = QWidget(self)
        self._container.setObjectName("overlay_container")
        self._container.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._container.setStyleSheet(
            "QWidget#overlay_container { background-color: rgba(255,255,255,0.20); }"
        )
        self._container.setGeometry(0, 0, self.width(), self.height())

        root = QVBoxLayout(self._container)
        root.setContentsMargins(8, 6, 8, 6)
        root.setSpacing(4)

        self.attr_label = QLabel()
        self.attr_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.attr_label.setWordWrap(True)
        self.attr_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.attr_label.setStyleSheet("background: transparent;")
        self.attr_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        root.addWidget(self.attr_label, 0)

        bottom = QHBoxLayout()
        bottom.setContentsMargins(0, 0, 0, 0)
        bottom.setSpacing(0)
        bottom.addStretch(1)

        self.box_image = QLabel()
        self.box_image.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.box_image.setAlignment(Qt.AlignCenter)
        self.box_image.setScaledContents(False)
        self.box_image.setStyleSheet("background: transparent;")
        self.box_image.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        bottom.addWidget(self.box_image, 0)

        root.addLayout(bottom, 1)

    def resizeEvent(self, event) -> None:
        QWidget.resizeEvent(self, event)
        self._container.setGeometry(0, 0, self.width(), self.height())

    def paintEvent(self, event) -> None:
        QWidget.paintEvent(self, event)
        if not self._locked:
            DragResizeMixin.draw_resize_handles(self, self._HANDLE_R, self._HANDLE_COLOR)

    def _update_bg(self) -> None:
        alpha = 0 if self._locked else 51
        self._container.setStyleSheet(
            f"QWidget#overlay_container {{ background-color: rgba(255,255,255,{alpha}); }}"
        )

    # ---- 鼠标事件 → 委托 Mixin ------------------------------------

    def mousePressEvent(self, event) -> None:
        # 有检测结果时：点击隐藏浮窗
        if self._result_showing and event.button() == Qt.LeftButton:
            self._hide_timer.stop()
            self.hide()
            event.accept()
            return
        self._mix_mouse_press(event)

    def mouseMoveEvent(self, event) -> None:
        self._mix_mouse_move(event)

    def mouseReleaseEvent(self, event) -> None:
        self._mix_mouse_release(event)

    # ---- 显示逻辑 -------------------------------------------------

    def show_result(self, box: tuple, attrs: dict, roi_image: np.ndarray = None) -> None:
        parts = []
        for region in ("top", "middle", "bottom"):
            val = attrs.get(region)
            if val:
                parts.append(val)

        self._result_showing = bool(parts)

        if parts:
            html_parts = []
            for i, word in enumerate(parts):
                color = self._LABEL_COLORS.get(word, self._DEFAULT_COLOR)
                sep = ' <span style="color:rgba(166,173,200,0.5);">-</span> ' if i < len(parts) - 1 else ''
                html_parts.append(
                    f'<span style="color:{color}; font-weight:bold; font-size:16px;">{word}</span>{sep}'
                )
            self.attr_label.setText("".join(html_parts))
            self.attr_label.setVisible(True)
        else:
            self.attr_label.setText("")
            self.attr_label.setVisible(False)

        if roi_image is not None and roi_image.size > 0:
            self._show_cropped(roi_image)
        else:
            self.box_image.clear()

        self.show()
        self._reset_hide_timer()

    def _show_cropped(self, img: np.ndarray) -> None:
        try:
            lbl_h = self.box_image.height()
            if lbl_h <= 1:
                lbl_h = 200

            h, w = img.shape[:2]
            if len(img.shape) == 2:
                img = np.stack([img] * 3, axis=-1)
            elif img.shape[2] == 4:
                img = img[:, :, :3]

            scale = lbl_h / h
            new_w = max(1, int(w * scale))
            new_h = max(1, int(h * scale))

            qimg = QImage(img.data, w, h, img.strides[0], QImage.Format_RGB888)
            pixmap = QPixmap.fromImage(qimg).scaled(
                new_w, new_h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation,
            )
            self.box_image.setPixmap(pixmap)
            self.box_image.setFixedWidth(new_w)
        except Exception:
            pass

    def show_placeholder(self) -> None:
        self._result_showing = False
        self.attr_label.setText("")
        self.attr_label.setVisible(False)
        self.box_image.clear()
        self.show()
        self._reset_hide_timer()

    # ---- 锁定 -----------------------------------------------------

    def set_locked(self, locked: bool) -> None:
        self._locked = locked
        self._update_bg()
        if locked:
            self.setCursor(Qt.ArrowCursor)
            if self.isVisible():
                self._reset_hide_timer()
        else:
            self._hide_timer.stop()
        self.update()

    @property
    def is_locked(self) -> bool:
        return self._locked

    # ---- 自动隐藏 -------------------------------------------------

    def set_hide_delay(self, ms: int) -> None:
        self._hide_delay_ms = ms
        self._hide_timer.setInterval(ms)
        if self._hide_timer.isActive():
            self._reset_hide_timer()

    def _reset_hide_timer(self) -> None:
        self._hide_timer.stop()
        if self._locked and self._hide_delay_ms > 0:
            self._hide_timer.start()
