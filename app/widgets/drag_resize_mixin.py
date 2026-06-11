"""可拖拽+伸缩的 QWidget 基类 Mixin — 屏幕坐标通用模板

用法:
    class MyWindow(DragResizeMixin, QWidget):
        def __init__(self):
            QWidget.__init__(self)
            DragResizeMixin.__init__(self, min_w=200, min_h=150,
                                     bounds=screen_geo)

        def _drag_allowed(self) -> bool:
            return not self._locked

        def paintEvent(self, event): ...  # 绘制节点、边框等

    属性:
        drag_finished: Callable | None  移动/伸缩结束回调
        drag_move_callback: Callable | None  每次移动/伸缩后回调

    子类可重写:
        _drag_allowed()  → bool  是否允许拖拽
        _resize_allowed() → bool 是否允许伸缩（默认同 _drag_allowed）
"""

from PyQt5.QtCore import Qt, QPoint, QRect
from PyQt5.QtGui import QPainter, QPen, QColor
from PyQt5.QtWidgets import QWidget


class DragResizeMixin:
    """QWidget 屏幕坐标拖拽+伸缩 Mixin

    使用要求：
      - 宿主必须是 QWidget（含 setWindowFlags FramelessWindowHint）
      - 必须在 host.__init__ 中显式调用 DragResizeMixin.__init__(self, ...)
      - 宿主可重写 _drag_allowed / _resize_allowed 控制启禁
      - 宿主应在 paintEvent 中绘制 8 个伸缩节点以提示用户

    提供:
      - 鼠标拖拽移动窗口
      - 8 方向边缘伸缩
      - bounds 边界限制（屏幕坐标 QRect），防止移出屏幕
      - drag_finished 回调
      - drag_move_callback 每次移动/伸缩回调（用于重叠检测等）
    """

    def __init__(self, min_w: int = 60, min_h: int = 60,
                 edge_margin: int = 6, bounds: QRect = None):
        if hasattr(self, "_mix_drag_initialized"):
            return
        self._mix_drag_initialized = True

        self._mix_min_w = min_w
        self._mix_min_h = min_h
        self._mix_edge_margin = edge_margin
        self._mix_bounds = bounds          # None = 不限制

        self._mix_dragging = False
        self._mix_resizing = False
        self._mix_resize_edge = ""
        self._mix_drag_start = QPoint()
        self._mix_geom_start = None

        # 启用鼠标追踪：悬停时触发 mouseMoveEvent 以改变光标
        self.setMouseTracking(True)

        self.drag_finished = None          # Callable[[], None]
        self.drag_move_callback = None     # Callable[[], None]

    # ---- 子类可重写 -----------------------------------------------

    def _drag_allowed(self) -> bool:
        """子类可重写：当前是否允许拖拽移动"""
        return True

    def _resize_allowed(self) -> bool:
        """子类可重写：当前是否允许边缘伸缩（默认同拖拽）"""
        return self._drag_allowed()

    def set_bounds(self, rect: QRect = None) -> None:
        """设置拖拽/伸缩的边界范围（屏幕坐标），None 表示不限"""
        self._mix_bounds = rect

    @staticmethod
    def draw_resize_handles(
        widget: QWidget, handle_r: int = 5,
        handle_pen: QColor = QColor(137, 180, 250),
        handle_brush: QColor = QColor(24, 24, 37, 200),
    ) -> None:
        """静态工具：在 widget 上绘制 8 个伸缩节点"""
        w, h = widget.width(), widget.height()
        r = handle_r
        painter = QPainter(widget)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(handle_pen, 1))
        painter.setBrush(handle_brush)
        points = [
            (r, r), (w - r, r), (r, h - r), (w - r, h - r),
            (w // 2, r), (w - r, h // 2), (w // 2, h - r), (r, h // 2),
        ]
        for px, py in points:
            painter.drawEllipse(QPoint(px, py), r, r)
        painter.end()

    # ---- 内部 -----------------------------------------------------

    _MIX_CURSORS = {
        "n": Qt.SizeVerCursor, "s": Qt.SizeVerCursor,
        "e": Qt.SizeHorCursor, "w": Qt.SizeHorCursor,
        "ne": Qt.SizeBDiagCursor, "sw": Qt.SizeBDiagCursor,
        "nw": Qt.SizeFDiagCursor, "se": Qt.SizeFDiagCursor,
    }

    def _mix_hit_test(self, pos: QPoint) -> str:
        x, y = pos.x(), pos.y()
        w, h = self.width(), self.height()
        m = self._mix_edge_margin
        top = y < m
        bottom = y > h - m
        left = x < m
        right = x > w - m
        if top and left:    return "nw"
        if top and right:   return "ne"
        if bottom and left: return "sw"
        if bottom and right: return "se"
        if top:             return "n"
        if bottom:          return "s"
        if left:            return "w"
        if right:           return "e"
        return ""

    def _mix_mouse_press(self, event) -> None:
        if event.button() != Qt.LeftButton or not self._drag_allowed():
            return
        edge = self._mix_hit_test(event.pos())
        if edge and self._resize_allowed():
            self._mix_resizing = True
            self._mix_resize_edge = edge
            self._mix_drag_start = event.globalPos()
            self._mix_geom_start = self.geometry()
        else:
            self._mix_dragging = True
            self._mix_drag_start = event.globalPos() - self.frameGeometry().topLeft()
        event.accept()

    def _mix_mouse_move(self, event) -> None:
        if not self._drag_allowed():
            return
        if self._mix_resizing:
            delta = event.globalPos() - self._mix_drag_start
            g = self._mix_geom_start
            e = self._mix_resize_edge
            x, y = g.x(), g.y()
            w, h = g.width(), g.height()
            if "e" in e:
                w = max(self._mix_min_w, g.width() + delta.x())
            if "s" in e:
                h = max(self._mix_min_h, g.height() + delta.y())
            if "w" in e:
                nw = max(self._mix_min_w, g.width() - delta.x())
                x = g.x() + g.width() - nw
                w = nw
            if "n" in e:
                nh = max(self._mix_min_h, g.height() - delta.y())
                y = g.y() + g.height() - nh
                h = nh
            self.setGeometry(x, y, w, h)
            self._mix_clamp_to_bounds()
            self._mix_call_move_callback()
        elif self._mix_dragging and event.buttons() & Qt.LeftButton:
            self.move(event.globalPos() - self._mix_drag_start)
            self._mix_clamp_to_bounds()
            self._mix_call_move_callback()
        else:
            edge = self._mix_hit_test(event.pos())
            self.setCursor(self._MIX_CURSORS.get(edge, Qt.ArrowCursor))

    def _mix_mouse_release(self, event) -> None:
        self._mix_dragging = False
        self._mix_resizing = False
        self._mix_resize_edge = ""
        self.setCursor(Qt.ArrowCursor)
        self._mix_clamp_to_bounds()
        if self.drag_finished:
            self.drag_finished()

    def _mix_clamp_to_bounds(self) -> None:
        """将窗口钳制在 bounds 范围内"""
        if self._mix_bounds is None:
            return
        g = self.geometry()
        b = self._mix_bounds
        x, y = g.x(), g.y()
        w, h = g.width(), g.height()

        # 不超出左/上边界
        if x < b.left():
            x = b.left()
        if y < b.top():
            y = b.top()
        # 不超出右/下边界
        if x + w > b.right():
            x = b.right() - w
        if y + h > b.bottom():
            y = b.bottom() - h

        if x != g.x() or y != g.y():
            self.move(x, y)

    def _mix_call_move_callback(self) -> None:
        if self.drag_move_callback:
            self.drag_move_callback()
