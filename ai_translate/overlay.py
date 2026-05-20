"""Transparent, stay-on-top overlay displaying translated text."""

import json
from pathlib import Path

from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import (
    QPainter, QColor, QFont, QPen, QBrush,
    QTextDocument, QFontMetrics,
)
from PySide6.QtWidgets import QWidget, QApplication

CONFIG_PATH = Path(__file__).parent / "config.json"


class TranslationOverlay(QWidget):
    def __init__(
        self,
        rect: QRect,
        original: str,
        translated: str,
        font_size_px: int = 0,
        dpr: float = 1.0,
    ):
        super().__init__()
        self.original_text = original
        self.translated_text = translated
        self._region = rect

        with open(CONFIG_PATH, encoding="utf-8") as f:
            config = json.load(f)
        ov = config["overlay"]

        self._bg_color = QColor(ov["background_color"])
        self._bg_color.setAlphaF(ov["background_opacity"])
        self._text_color = QColor(ov["text_color"])
        self._padding = ov["padding"]
        self._border_radius = ov["border_radius"]

        # Determine font size: prefer estimated size, fall back to config
        if font_size_px > 0 and dpr > 0:
            logical_px = max(8, int(font_size_px / dpr))
        else:
            logical_px = ov["font_size"]
        self._font = QFont("Microsoft YaHei")
        self._font.setPixelSize(logical_px)

        self._min_font_size = ov["min_font_size"]

        self._init_ui()

    def _init_ui(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        # Size to match the original selected region exactly
        x = max(0, self._region.x())
        y = max(0, self._region.y())
        w = max(60, self._region.width())
        h = max(40, self._region.height())
        self.setGeometry(x, y, w, h)
        self.show()

    def _effective_font(self) -> QFont:
        """Return a font that fits the text within the overlay width.

        Starts from the estimated font size and shrinks until the text fits.
        """
        fm = QFontMetrics(self._font)
        available_w = self.width() - self._padding * 2
        text_w = max(fm.horizontalAdvance(self.translated_text),
                     fm.horizontalAdvance("A") * 20)

        if text_w <= available_w:
            return self._font

        # Text too wide — shrink font until it fits (but not below minimum)
        font = QFont(self._font)
        for px in range(self._font.pixelSize() - 1, self._min_font_size - 1, -1):
            font.setPixelSize(px)
            fm = QFontMetrics(font)
            text_w = fm.horizontalAdvance(self.translated_text)
            if text_w <= available_w:
                return font
        return font

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Background
        painter.setBrush(QBrush(self._bg_color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(self.rect(), self._border_radius, self._border_radius)

        # Determine best-fit font
        font = self._effective_font()
        painter.setFont(font)
        painter.setPen(QPen(self._text_color))

        text_rect = self.rect().adjusted(
            self._padding, self._padding, -self._padding, -self._padding
        )

        # Use QTextDocument for word-wrapping
        doc = QTextDocument()
        doc.setDefaultFont(font)
        doc.setPlainText(self.translated_text)
        doc.setTextWidth(text_rect.width())

        # Vertically center the text block
        doc_size = doc.documentLayout().documentSize()
        y_offset = max(0, (text_rect.height() - doc_size.height()) / 2)
        painter.translate(text_rect.left(), text_rect.top() + y_offset)
        doc.drawContents(painter)

        painter.end()

    def mousePressEvent(self, event):
        self.close()
