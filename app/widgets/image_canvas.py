"""
图像显示画布 - 支持标注边界框的绘制、拖动、边缘伸缩编辑及鼠标滚轮缩放
"""
from enum import IntEnum
from math import log2
from typing import Optional

import numpy as np
from PyQt5.QtCore import Qt, QRectF, QPointF, pyqtSignal
from PyQt5.QtGui import QPixmap, QImage, QPainter, QPen, QColor, QCursor, QWheelEvent
from PyQt5.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QGraphicsRectItem


HANDLE_SIZE = 6
ZOOM_FACTOR = 1.15
MIN_ZOOM = 0.05
MAX_ZOOM = 20.0


class ResizeHandle(IntEnum):
    """缩放手柄方向"""
    NONE = 0
    TOP_LEFT = 1
    TOP = 2
    TOP_RIGHT = 3
    RIGHT = 4
    BOTTOM_RIGHT = 5
    BOTTOM = 6
    BOTTOM_LEFT = 7
    LEFT = 8


CURSOR_MAP = {
    ResizeHandle.TOP_LEFT: Qt.SizeFDiagCursor,
    ResizeHandle.BOTTOM_RIGHT: Qt.SizeFDiagCursor,
    ResizeHandle.TOP_RIGHT: Qt.SizeBDiagCursor,
    ResizeHandle.BOTTOM_LEFT: Qt.SizeBDiagCursor,
    ResizeHandle.TOP: Qt.SizeVerCursor,
    ResizeHandle.BOTTOM: Qt.SizeVerCursor,
    ResizeHandle.LEFT: Qt.SizeHorCursor,
    ResizeHandle.RIGHT: Qt.SizeHorCursor,
}


class EditableRect(QGraphicsRectItem):
    """可拖拽 + 边缘伸缩的矩形框"""

    def __init__(self, rect: QRectF, color: QColor, label: str = "", tag: str = "",
                 image_bounds: QRectF = None):
        super().__init__(rect)
        self._color = color
        self._label = label
        self._tag = tag
        self._editing = False
        self._resize_handle = ResizeHandle.NONE
        self._drag_start_pos: Optional[QPointF] = None
        self._drag_start_rect: Optional[QRectF] = None
        self._bounds = image_bounds or QRectF(0, 0, 0, 0)  # 图片范围，用于限制越界

        self.setPen(QPen(color, 2))
        self.setBrush(QColor(color.red(), color.green(), color.blue(), 40))
        self.setAcceptHoverEvents(True)
        self.setZValue(10)
        self.setCacheMode(self.NoCache)  # 禁缓存避免拖拽残影
        self._update_flags()

    def boundingRect(self) -> QRectF:
        """扩展边界以包含拖拽手柄的绘制范围，避免残影"""
        r = self.rect()
        extra = HANDLE_SIZE / 2 + 1
        return r.adjusted(-extra, -extra, extra, extra)

    def _update_flags(self) -> None:
        """启/禁用可移动和几何变更标志，保留 hover 等其他标志"""
        self.setFlag(QGraphicsRectItem.ItemIsMovable, self._editing)
        self.setFlag(QGraphicsRectItem.ItemSendsGeometryChanges, self._editing)

    def set_bounds(self, bounds: QRectF) -> None:
        self._bounds = bounds

    @property
    def tag(self) -> str:
        return self._tag

    @property
    def label(self) -> str:
        return self._label

    @label.setter
    def label(self, value: str) -> None:
        self._label = value

    def set_editable(self, enabled: bool) -> None:
        self._editing = enabled
        if enabled:
            self.setPen(QPen(self._color, 3, Qt.DashLine))
        else:
            self.setPen(QPen(self._color, 2))
        self._update_flags()

    @property
    def is_editing(self) -> bool:
        return self._editing

    def _detect_handle(self, pos: QPointF) -> ResizeHandle:
        if not self._editing:
            return ResizeHandle.NONE
        r = self.rect()
        margin = HANDLE_SIZE

        corners = [
            (r.topLeft(), ResizeHandle.TOP_LEFT),
            (r.topRight(), ResizeHandle.TOP_RIGHT),
            (r.bottomLeft(), ResizeHandle.BOTTOM_LEFT),
            (r.bottomRight(), ResizeHandle.BOTTOM_RIGHT),
        ]
        for corner_pt, handle in corners:
            if (pos - corner_pt).manhattanLength() < margin:
                return handle

        if abs(pos.y() - r.top()) < margin and r.left() + margin < pos.x() < r.right() - margin:
            return ResizeHandle.TOP
        if abs(pos.y() - r.bottom()) < margin and r.left() + margin < pos.x() < r.right() - margin:
            return ResizeHandle.BOTTOM
        if abs(pos.x() - r.left()) < margin and r.top() + margin < pos.y() < r.bottom() - margin:
            return ResizeHandle.LEFT
        if abs(pos.x() - r.right()) < margin and r.top() + margin < pos.y() < r.bottom() - margin:
            return ResizeHandle.RIGHT

        return ResizeHandle.NONE

    def hoverMoveEvent(self, event) -> None:
        if not self._editing:
            super().hoverMoveEvent(event)
            return
        handle = self._detect_handle(event.pos())
        self.setCursor(QCursor(CURSOR_MAP.get(handle, Qt.ArrowCursor)))
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event) -> None:
        if not self._editing or event.button() != Qt.LeftButton:
            super().mousePressEvent(event)
            return
        self._resize_handle = self._detect_handle(event.pos())
        self._drag_start_pos = event.pos()
        self._drag_start_rect = QRectF(self.rect())
        if self._resize_handle != ResizeHandle.NONE:
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if not self._editing or self._resize_handle == ResizeHandle.NONE:
            super().mouseMoveEvent(event)
            return
        if self._drag_start_rect is None or self._drag_start_pos is None:
            return

        delta = event.pos() - self._drag_start_pos
        r = QRectF(self._drag_start_rect)
        h = self._resize_handle
        b = self._bounds  # 图片边界

        if h in (ResizeHandle.TOP_LEFT, ResizeHandle.LEFT, ResizeHandle.BOTTOM_LEFT):
            r.setLeft(min(r.left() + delta.x(), r.right() - 10))
        if h in (ResizeHandle.TOP_RIGHT, ResizeHandle.RIGHT, ResizeHandle.BOTTOM_RIGHT):
            r.setRight(max(r.right() + delta.x(), r.left() + 10))
        if h in (ResizeHandle.TOP_LEFT, ResizeHandle.TOP, ResizeHandle.TOP_RIGHT):
            r.setTop(min(r.top() + delta.y(), r.bottom() - 10))
        if h in (ResizeHandle.BOTTOM_LEFT, ResizeHandle.BOTTOM, ResizeHandle.BOTTOM_RIGHT):
            r.setBottom(max(r.bottom() + delta.y(), r.top() + 10))

        r = r.normalized()
        # === 限制不超出图片范围 ===
        if r.left() < 0:
            r.setLeft(0)
        if r.top() < 0:
            r.setTop(0)
        if b.width() > 0 and r.right() > b.width():
            r.setRight(b.width())
        if b.height() > 0 and r.bottom() > b.height():
            r.setBottom(b.height())

        self.prepareGeometryChange()
        self.setRect(r)
        self.scene().update()  # 强制刷新场景避免残影

    def mouseReleaseEvent(self, event) -> None:
        if self._resize_handle != ResizeHandle.NONE:
            self._resize_handle = ResizeHandle.NONE
            self._drag_start_pos = None
            self._drag_start_rect = None

            # 释放后再次约束位置
            self._clamp_to_bounds()
            event.accept()
        else:
            super().mouseReleaseEvent(event)
            self._clamp_to_bounds()

    def itemChange(self, change, value):
        """拦截移动，限制盒子不超出图片边界"""
        if change == self.ItemPositionChange and self._editing:
            new_pos = value
            bounds = self._bounds
            if bounds.width() > 0:
                r = self.rect()
                if new_pos.x() < -r.left():
                    new_pos.setX(-r.left())
                if new_pos.y() < -r.top():
                    new_pos.setY(-r.top())
                if new_pos.x() + r.right() > bounds.width():
                    new_pos.setX(bounds.width() - r.right())
                if new_pos.y() + r.bottom() > bounds.height():
                    new_pos.setY(bounds.height() - r.bottom())
            return new_pos
        return super().itemChange(change, value)

    def _clamp_to_bounds(self) -> None:
        """确保 rect 不超出图片边界"""
        r = self.rect()
        b = self._bounds
        if b.width() <= 0:
            return
        changed = False
        if r.left() < 0:
            r.setLeft(0); changed = True
        if r.top() < 0:
            r.setTop(0); changed = True
        if r.right() > b.width():
            r.setRight(b.width()); changed = True
        if r.bottom() > b.height():
            r.setBottom(b.height()); changed = True
        if changed:
            self.prepareGeometryChange()
            self.setRect(r)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        super().paint(painter, option, widget)
        if not self._editing:
            return
        r = self.rect()
        hs = HANDLE_SIZE
        painter.setPen(QPen(self._color, 1))
        painter.setBrush(Qt.NoBrush)
        corners = [r.topLeft(), r.topRight(), r.bottomLeft(), r.bottomRight()]
        for c in corners:
            painter.drawRect(QRectF(c.x() - hs / 2, c.y() - hs / 2, hs, hs))
        edges = [
            QPointF(r.center().x(), r.top()),
            QPointF(r.center().x(), r.bottom()),
            QPointF(r.left(), r.center().y()),
            QPointF(r.right(), r.center().y()),
        ]
        for e in edges:
            painter.drawRect(QRectF(e.x() - hs / 2, e.y() - hs / 2, hs, hs))


class ImageCanvas(QGraphicsView):
    """图像画布 — 滚轮缩放 + 标注编辑

    设计要点：
      - 场景坐标等于图像像素坐标（x: 0~w, y: 0~h）
      - 初始缩放采用 cover-fit：以较大比例填满视口，无黑边
      - 不随窗口尺寸变化而自动重缩放，避免选框坐标偏移
      - 鼠标滚轮以当前鼠标位置为锚点缩放
    """

    rect_changed = pyqtSignal(str, tuple)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.SmoothPixmapTransform)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setMouseTracking(True)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setStyleSheet(
            "background-color: #11111b; border: 1px solid #313244; border-radius: 6px;"
        )

        self._pixmap_item: Optional[QGraphicsPixmapItem] = None
        self._rects: dict = {}
        self._image_size: tuple = (0, 0)
        self._current_zoom = 1.0

    # ---- 属性 ----

    @property
    def image_bounds(self) -> QRectF:
        return QRectF(0, 0, self._image_size[0], self._image_size[1])

    # ---- 图片加载 ----

    def set_image(self, image: np.ndarray) -> None:
        """设置显示图像，采用 cover-fit 铺满视口"""
        try:
            h, w, c = image.shape
            self._image_size = (w, h)
            bytes_per_line = 3 * w
            qimg = QImage(image.data, w, h, bytes_per_line, QImage.Format_RGB888)
            pixmap = QPixmap.fromImage(qimg)
            self._scene.clear()
            self._rects.clear()

            self._pixmap_item = QGraphicsPixmapItem(pixmap)
            self._scene.addItem(self._pixmap_item)
            self._scene.setSceneRect(0, 0, w, h)

            self._apply_cover_fit()
        except Exception as e:
            from app.utils.logger import logger
            logger.error(f"图像显示失败: {e}")

    def _apply_cover_fit(self) -> None:
        """contain-fit：以较小比例缩放，确保图片完整可见（不裁剪），窄图不高倍放大"""
        iw, ih = self._image_size
        if iw <= 0 or ih <= 0:
            return
        vp = self.viewport()
        if vp is None:
            return
        vw, vh = vp.width(), vp.height()
        if vw <= 0 or vh <= 0:
            return

        scale = min(vw / iw, vh / ih)  # contain：较小比例保证完整显示
        self.resetTransform()
        self.scale(scale, scale)
        self._current_zoom = scale
        self.centerOn(self._scene.sceneRect().center())

    # ---- 矩形框操作 ----

    def add_rect(self, tag: str, x1: int, y1: int, x2: int, y2: int,
                 label: str = "", color: QColor = None, editable: bool = False) -> EditableRect:
        """添加边界框（自动限制在图片范围内）"""
        w_img, h_img = self._image_size
        x1 = max(0, min(x1, w_img))
        y1 = max(0, min(y1, h_img))
        x2 = max(0, min(x2, w_img))
        y2 = max(0, min(y2, h_img))

        if color is None:
            colors_map = {
                "box": QColor(137, 180, 250),
                "top": QColor(243, 139, 168),
                "middle": QColor(249, 226, 175),
                "bottom": QColor(166, 227, 161),
            }
            color = colors_map.get(tag, QColor(137, 180, 250))

        rect = QRectF(x1, y1, x2 - x1, y2 - y1)
        item = EditableRect(rect, color, label, tag, self.image_bounds)
        item.set_editable(editable)
        self._scene.addItem(item)
        self._rects[tag] = item
        return item

    def remove_rect(self, tag: str) -> None:
        if tag in self._rects:
            self._scene.removeItem(self._rects[tag])
            del self._rects[tag]

    def clear_rects(self) -> None:
        for tag in list(self._rects.keys()):
            self.remove_rect(tag)

    def clear_attr_rects(self) -> None:
        """只清除属性区域框（top/middle/bottom），保留 box"""
        for tag in ("top", "middle", "bottom"):
            self.remove_rect(tag)

    def get_rect(self, tag: str) -> Optional[tuple]:
        item = self._rects.get(tag)
        if item is None:
            return None
        r = item.rect()
        p = item.pos()  # 拖拽移动后 pos() 会变，必须加上
        return (int(p.x() + r.x()), int(p.y() + r.y()),
                int(p.x() + r.x() + r.width()), int(p.y() + r.y() + r.height()))

    def get_all_rects(self) -> dict:
        return {tag: self.get_rect(tag) for tag in self._rects}

    # ---- 编辑模式 ----

    def set_all_editable(self, enabled: bool) -> None:
        for item in self._rects.values():
            item.set_editable(enabled)
        self.setDragMode(QGraphicsView.NoDrag if enabled else QGraphicsView.ScrollHandDrag)

    def set_edit_mode(self, tag: str, editing: bool) -> None:
        item = self._rects.get(tag)
        if item:
            item.set_editable(editing)
            self.setDragMode(QGraphicsView.NoDrag if editing else QGraphicsView.ScrollHandDrag)

    def disable_all_editing(self) -> None:
        self.set_all_editable(False)

    # ---- 缩放 ----

    def wheelEvent(self, event: QWheelEvent) -> None:
        """滚轮缩放 — 以鼠标位置为锚点"""
        factor = ZOOM_FACTOR if event.angleDelta().y() > 0 else 1.0 / ZOOM_FACTOR
        new_zoom = self._current_zoom * factor

        if MIN_ZOOM <= new_zoom <= MAX_ZOOM:
            self._current_zoom = new_zoom
            self.scale(factor, factor)
        event.accept()

    # 移除 resizeEvent —— 不再随窗口尺寸变化自动缩放，避免选框坐标漂移
