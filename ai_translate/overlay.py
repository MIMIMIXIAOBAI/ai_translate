"""Transparent, stay-on-top overlay displaying translated text."""

import json
from pathlib import Path

from PySide6.QtCore import Qt, QRect, QPoint
from PySide6.QtGui import (
    QPainter, QColor, QFont, QPen, QBrush, QFontMetrics,
    QTextDocument, QAbstractTextDocumentLayout,
)
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QApplication

CONFIG_PATH = Path(__file__).parent / "config.json"


class TranslationOverlay(QWidget):
    def __init__(self, rect: QRect, original: str, translated: str):
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
        self._font_size = ov["font_size"]
        self._min_font_size = ov["min_font_size"]
        self._max_w_ratio = ov["max_width_ratio"]
        self._max_h_ratio = ov["max_height_ratio"]
        self._padding = ov["padding"]
        self._border_radius = ov["border_radius"]

        self._init_ui()

    def _init_ui(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        # Size overlay to fit within screen bounds with some margin
        screen = QApplication.primaryScreen()
        if screen:
            screen_geom = screen.availableGeometry()
            max_w = int(screen_geom.width() * self._max_w_ratio)
            max_h = int(screen_geom.height() * self._max_h_ratio)
        else:
            max_w, max_h = 1200, 800

        text_w, text_h = self._calc_text_size(max_w)
        w = min(text_w + self._padding * 2, max_w)
        h = min(text_h + self._padding * 2, max_h)

        # Position near the top-left of the original region, clamped to screen
        x = max(0, self._region.x())
        y = max(0, self._region.y())
        self.setGeometry(x, y, w, h)
        self.show()

    def _calc_text_size(self, max_w: int) -> tuple[int, int]:
        """Calculate required size for the translated text."""
        doc = QTextDocument()
        doc.setDefaultFont(QFont("Microsoft YaHei", self._font_size))
        doc.setPlainText(self.translated_text)
        doc.setTextWidth(max_w - self._padding * 2)
        size = doc.documentLayout().documentSize()
        return int(size.width()), int(size.height())

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Rounded rect background
        painter.setBrush(QBrush(self._bg_color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(self.rect(), self._border_radius, self._border_radius)

        # Translated text
        painter.setPen(QPen(self._text_color))
        font = QFont("Microsoft YaHei", self._font_size)
        painter.setFont(font)

        text_rect = self.rect().adjusted(
            self._padding, self._padding, -self._padding, -self._padding
        )

        doc = QTextDocument()
        doc.setDefaultFont(font)
        doc.setPlainText(self.translated_text)
        doc.setTextWidth(text_rect.width())
        painter.translate(text_rect.topLeft())
        doc.drawContents(painter)

    def mousePressEvent(self, event):
        self.close()
