"""Full-screen region selector with QRubberBand for click-and-drag selection."""

import io
from PIL import Image
import mss
from PySide6.QtCore import Qt, QRect, QPoint, Signal
from PySide6.QtGui import QPixmap, QPainter, QColor, QBrush, QPen
from PySide6.QtWidgets import QWidget, QRubberBand, QApplication


class RegionSelector(QWidget):
    """Modal, full-screen widget for drag-to-select screen region.

    Captures the entire desktop background and dims it so the user can draw
    a selection rectangle.  The widget uses logical (device-independent) Qt
    coordinates; mss captures are done in physical pixels via DPR conversion.
    """

    selection_done = Signal(QRect)

    def __init__(self):
        super().__init__()
        self._origin = QPoint()
        self._rubber_band = QRubberBand(QRubberBand.Shape.Rectangle, self)
        self.selected_rect: QRect | None = None
        self._accepted = False
        self._dpr: float = 1.0

        self._init_ui()
        self._capture_background()

    @property
    def accepted(self) -> bool:
        return self._accepted

    @property
    def dpr(self) -> float:
        return self._dpr

    def _init_ui(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.virtualGeometry()
            self._dpr = screen.devicePixelRatio()
        else:
            geo = QRect(0, 0, 1920, 1080)
        self.setGeometry(geo)
        self.setCursor(Qt.CursorShape.CrossCursor)

    def _capture_background(self):
        """Capture the full desktop via mss at physical resolution and scale to
        widget logical size so the display is pixel-perfect at any DPI."""
        geo = self.geometry()  # logical coords
        dpr = self._dpr
        with mss.MSS() as sct:
            monitor = {
                "left": int(geo.x() * dpr),
                "top": int(geo.y() * dpr),
                "width": int(geo.width() * dpr),
                "height": int(geo.height() * dpr),
            }
            grabbed = sct.grab(monitor)
        img = Image.frombytes("RGB", (grabbed.width, grabbed.height), grabbed.rgb)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        raw = QPixmap()
        raw.loadFromData(buf.getvalue())
        # Scale physical-resolution pixmap to widget logical size → 1:1 display
        self._bg_pixmap = raw.scaled(
            geo.size(),
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

    def physical_rect(self) -> QRect:
        """Convert the selected logical-coord rect to physical (mss) coordinates."""
        if self.selected_rect is None:
            return QRect()
        r = self.selected_rect
        return QRect(
            int(r.x() * self._dpr),
            int(r.y() * self._dpr),
            int(r.width() * self._dpr),
            int(r.height() * self._dpr),
        )

    def paintEvent(self, event):
        painter = QPainter(self)

        if self._bg_pixmap:
            painter.drawPixmap(self.rect(), self._bg_pixmap)

        # Dim overlay
        painter.fillRect(self.rect(), QBrush(QColor(0, 0, 0, 100)))

        # Punch a clear hole for the selection rectangle
        if self._rubber_band.isVisible():
            r = self._rubber_band.geometry()
            if self._bg_pixmap:
                painter.drawPixmap(r, self._bg_pixmap, r)
            pen = QPen(QColor("#89b4fa"), 2)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(r)

        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._origin = event.position().toPoint()
            self._rubber_band.setGeometry(QRect(self._origin, self._origin))
            self._rubber_band.show()

    def mouseMoveEvent(self, event):
        if self._rubber_band.isVisible():
            rect = QRect(self._origin, event.position().toPoint()).normalized()
            self._rubber_band.setGeometry(rect)
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            rect = QRect(self._origin, event.position().toPoint()).normalized()
            if rect.width() > 10 and rect.height() > 10:
                self._accepted = True
                self.selected_rect = rect
                self.selection_done.emit(rect)
            self.close()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
