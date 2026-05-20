"""Transparent, stay-on-top overlay displaying translated text at original positions."""

import json
from pathlib import Path

from PySide6.QtCore import Qt, QRect, QRectF
from PySide6.QtGui import (
    QPainter, QColor, QFont, QPen, QBrush,
    QTextDocument, QFontMetrics,
)
from PySide6.QtWidgets import QWidget

CONFIG_PATH = Path(__file__).parent / "config.json"


class TranslationOverlay(QWidget):
    """Overlay that renders each translated line at its original text position.

    Parameters
    ----------
    rect: QRect
        Logical geometry matching the selected region.
    lines_data: list[tuple[str, int, int, int, int]]
        Each tuple is (translated_text, x, y, w, h) in logical pixels.
    is_dark_bg: bool
        If True the original background is dark → use light text.
    """

    def __init__(
        self,
        rect: QRect,
        lines_data: list,
        is_dark_bg: bool = True,
    ):
        super().__init__()
        self._region = rect
        self._lines_data = lines_data  # [(text, x, y, w, h), ...] in logical px
        self._is_dark_bg = is_dark_bg

        with open(CONFIG_PATH, encoding="utf-8") as f:
            config = json.load(f)
        ov = config["overlay"]

        self._bg_color = QColor(ov["background_color"])
        self._bg_color.setAlphaF(ov["background_opacity"])
        self._padding = ov["padding"]
        self._border_radius = ov["border_radius"]
        self._min_font_size = ov["min_font_size"]

        self._text_color = QColor("#ffffff")

        self._init_ui()

    def _init_ui(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        x = max(0, self._region.x())
        y = max(0, self._region.y())
        w = max(60, self._region.width())
        h = max(40, self._region.height())
        self.setGeometry(x, y, w, h)
        self.show()

    def _font_for_line(self, line_h: int, text: str, available_w: int) -> QFont:
        """Create a font that fits *text* inside *available_w* at the given line height."""
        px = max(self._min_font_size, min(line_h, 48))
        font = QFont("Microsoft YaHei")
        font.setPixelSize(px)

        fm = QFontMetrics(font)
        if fm.horizontalAdvance(text) <= available_w:
            return font

        for px in range(px - 1, self._min_font_size - 1, -1):
            font.setPixelSize(px)
            fm = QFontMetrics(font)
            if fm.horizontalAdvance(text) <= available_w:
                return font
        return font

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Full-region background
        painter.setBrush(QBrush(self._bg_color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(self.rect(), self._border_radius, self._border_radius)

        if not self._lines_data:
            painter.end()
            return

        painter.setPen(QPen(self._text_color))

        for text, lx, ly, _lw, lh in self._lines_data:
            available_w = max(20, self.width() - lx - self._padding)
            font = self._font_for_line(lh, text, available_w)
            painter.setFont(font)

            doc = QTextDocument()
            doc.setDefaultFont(font)
            doc.setPlainText(text)
            doc.setTextWidth(available_w)

            painter.save()
            painter.translate(lx, ly)
            clip = QRectF(0, 0, available_w,
                          max(20, self.height() - ly - self._padding))
            doc.drawContents(painter, clip)
            painter.restore()

        painter.end()

    def mousePressEvent(self, event):
        self.close()
