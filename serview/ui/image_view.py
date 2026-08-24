"""The image display: zooming, panning, pixel probing and crop selection."""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap, QWheelEvent
from PySide6.QtWidgets import (
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
    QRubberBand,
)

ZOOM_STEPS = (0.05, 0.1, 0.125, 0.25, 0.33, 0.5, 0.66, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0, 16.0)


def numpy_to_qimage(image: np.ndarray) -> QImage:
    """Convert an 8 bit greyscale or RGB array into a QImage (data is copied)."""
    if image.dtype != np.uint8:
        raise ValueError("only 8 bit images can be displayed")
    image = np.ascontiguousarray(image)
    height, width = image.shape[:2]
    if image.ndim == 2:
        qimage = QImage(image.data, width, height, width, QImage.Format_Grayscale8)
    else:
        qimage = QImage(image.data, width, height, 3 * width, QImage.Format_RGB888)
    return qimage.copy()


class ImageView(QGraphicsView):
    """Displays one frame with zoom, pan and an optional selection box."""

    zoom_changed = Signal(float)
    cursor_moved = Signal(int, int)          # image coordinates, (-1, -1) when outside
    selection_changed = Signal(QRect)        # in image coordinates
    double_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._item = QGraphicsPixmapItem()
        self._item.setTransformationMode(Qt.FastTransformation)
        self._scene.addItem(self._item)

        self.setBackgroundBrush(QColor(32, 32, 34))
        self.setRenderHints(QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setMouseTracking(True)
        self.setFrameShape(QGraphicsView.NoFrame)

        self._zoom = 1.0
        self._fit = True
        self._image_size = (0, 0)
        self._selection_mode = False
        self._rubber_band: QRubberBand | None = None
        self._rubber_origin = QPoint()
        self._selection_item = QGraphicsRectItem()
        pen = QPen(QColor(255, 200, 0), 0, Qt.DashLine)
        pen.setCosmetic(True)
        self._selection_item.setPen(pen)
        self._selection_item.setVisible(False)
        self._scene.addItem(self._selection_item)

    # -- content ---------------------------------------------------------
    def set_image(self, image: np.ndarray | None) -> None:
        if image is None:
            self._item.setPixmap(QPixmap())
            self._image_size = (0, 0)
            return
        pixmap = QPixmap.fromImage(numpy_to_qimage(image))
        first = self._image_size != (pixmap.width(), pixmap.height())
        self._item.setPixmap(pixmap)
        self._image_size = (pixmap.width(), pixmap.height())
        self._scene.setSceneRect(QRectF(pixmap.rect()))
        if first and self._fit:
            self.zoom_to_fit()

    @property
    def image_size(self) -> tuple[int, int]:
        return self._image_size

    @property
    def has_image(self) -> bool:
        return self._image_size != (0, 0)

    # -- zooming ----------------------------------------------------------
    @property
    def zoom(self) -> float:
        return self._zoom

    def set_zoom(self, factor: float, keep_fit: bool = False) -> None:
        factor = max(ZOOM_STEPS[0], min(ZOOM_STEPS[-1], factor))
        self._zoom = factor
        if not keep_fit:
            self._fit = False
        self.resetTransform()
        self.scale(factor, factor)
        # Nearest neighbour above 100% so individual pixels stay crisp.
        self._item.setTransformationMode(
            Qt.FastTransformation if factor >= 1.0 else Qt.SmoothTransformation
        )
        self.zoom_changed.emit(factor)

    def zoom_in(self) -> None:
        for step in ZOOM_STEPS:
            if step > self._zoom + 1e-6:
                self.set_zoom(step)
                return

    def zoom_out(self) -> None:
        for step in reversed(ZOOM_STEPS):
            if step < self._zoom - 1e-6:
                self.set_zoom(step)
                return

    def zoom_to_fit(self) -> None:
        if not self.has_image:
            return
        self._fit = True
        width, height = self._image_size
        available = self.viewport().size()
        factor = min(available.width() / width, available.height() / height)
        self.set_zoom(factor, keep_fit=True)
        self.centerOn(self._item)

    @property
    def fit_enabled(self) -> bool:
        return self._fit

    def enable_fit(self) -> None:
        """Re-arm fit-to-window for the next image that is loaded."""
        self._fit = True

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._fit:
            self.zoom_to_fit()

    def wheelEvent(self, event: QWheelEvent) -> None:
        if event.angleDelta().y() > 0:
            self.zoom_in()
        else:
            self.zoom_out()
        event.accept()

    # -- selection --------------------------------------------------------
    def set_selection_mode(self, enabled: bool) -> None:
        self._selection_mode = enabled
        self.setDragMode(QGraphicsView.NoDrag if enabled else QGraphicsView.ScrollHandDrag)
        self.setCursor(Qt.CrossCursor if enabled else Qt.ArrowCursor)

    def set_selection(self, rect: QRect | None) -> None:
        if rect is None or rect.isEmpty():
            self._selection_item.setVisible(False)
            return
        self._selection_item.setRect(QRectF(rect))
        self._selection_item.setVisible(True)

    def _image_position(self, view_pos: QPoint) -> QPointF:
        return self.mapToScene(view_pos)

    def mousePressEvent(self, event) -> None:
        if self._selection_mode and event.button() == Qt.LeftButton:
            self._rubber_origin = event.position().toPoint()
            if self._rubber_band is None:
                self._rubber_band = QRubberBand(QRubberBand.Rectangle, self.viewport())
            self._rubber_band.setGeometry(QRect(self._rubber_origin, self._rubber_origin))
            self._rubber_band.show()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        position = event.position().toPoint()
        if self._rubber_band is not None and self._rubber_band.isVisible():
            self._rubber_band.setGeometry(QRect(self._rubber_origin, position).normalized())
        if self.has_image:
            scene_pos = self._image_position(position)
            x, y = int(scene_pos.x()), int(scene_pos.y())
            width, height = self._image_size
            if 0 <= x < width and 0 <= y < height:
                self.cursor_moved.emit(x, y)
            else:
                self.cursor_moved.emit(-1, -1)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._rubber_band is not None and self._rubber_band.isVisible():
            self._rubber_band.hide()
            rect = QRect(self._rubber_origin, event.position().toPoint()).normalized()
            top_left = self._image_position(rect.topLeft())
            bottom_right = self._image_position(rect.bottomRight())
            width, height = self._image_size
            x0 = max(0, min(width - 1, int(top_left.x())))
            y0 = max(0, min(height - 1, int(top_left.y())))
            x1 = max(0, min(width, int(bottom_right.x())))
            y1 = max(0, min(height, int(bottom_right.y())))
            selection = QRect(x0, y0, max(1, x1 - x0), max(1, y1 - y0))
            if selection.width() > 3 and selection.height() > 3:
                self.set_selection(selection)
                self.selection_changed.emit(selection)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        self.double_clicked.emit()
        super().mouseDoubleClickEvent(event)

    def leaveEvent(self, event) -> None:
        self.cursor_moved.emit(-1, -1)
        super().leaveEvent(event)
