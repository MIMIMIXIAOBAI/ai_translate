"""Full-screen region selector with QRubberBand for click-and-drag selection."""

from PySide6.QtCore import Qt, QRect, QPoint, Signal
from PySide6.QtGui import QPainter, QColor, QPen, QBrush
from PySide6.QtWidgets import QWidget, QRubberBand, QApplication


class RegionSelector(QWidget):
    """Modal, full-screen widget for drag-to-select screen region.

    Uses a plain semi-transparent overlay — no screenshot capture — so there
    are no DPI scaling artifacts.  The user sees their real screen through the
    dimmed overlay and draws a rectangle over it.
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

        # Semi-transparent dim overlay — user sees real screen through it
        dim = QColor(0, 0, 0, 100)
        painter.fillRect(self.rect(), QBrush(dim))

        # Punch a clear hole for the selection rectangle
        if self._rubber_band.isVisible():
            r = self._rubber_band.geometry()
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(r, QBrush(Qt.GlobalColor.transparent))
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

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
