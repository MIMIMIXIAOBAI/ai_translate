"""AI Translate — screen region OCR + translation desktop app.

Hotkey Ctrl+Shift+T or system tray → select a screen region → OCR → translate → overlay.
"""

import json
import sys
from pathlib import Path

import mss
from PIL import Image
import keyboard

from PySide6.QtCore import Qt, Signal, QObject, QRect, QTimer
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QFont, QPen, QBrush
from PySide6.QtWidgets import (
    QApplication, QSystemTrayIcon, QMenu, QWidget,
)

from region_selector import RegionSelector
from ocr_engine import OcrEngine
from translator import Translator
from overlay import TranslationOverlay

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.json"


def _make_tray_icon() -> QIcon:
    """Draw a simple '译' tray icon."""
    pix = QPixmap(64, 64)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor("#89b4fa"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(4, 4, 56, 56, 14, 14)
    painter.setPen(QColor("#1e1e2e"))
    font = QFont("Microsoft YaHei", 30, QFont.Weight.Bold)
    painter.setFont(font)
    painter.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, "译")
    painter.end()
    return QIcon(pix)


class HotkeyBridge(QObject):
    triggered = Signal()


class _InfoToast(QWidget):
    """A brief, auto-dismissing toast message in the center of the screen."""

    def __init__(self, message: str):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self._msg = message
        self.resize(420, 64)
        center = QApplication.primaryScreen().availableGeometry().center()
        self.move(center.x() - 210, center.y() - 32)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QBrush(QColor(30, 30, 46, 230)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(self.rect(), 10, 10)
        p.setPen(QPen(QColor("#cdd6f4")))
        font = QFont("Microsoft YaHei", 12)
        p.setFont(font)
        p.drawText(self.rect().adjusted(16, 12, -16, -12),
                   Qt.AlignmentFlag.AlignCenter, self._msg)
        p.end()

    def mousePressEvent(self, event):
        self.close()


class App:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)

        with open(CONFIG_PATH, encoding="utf-8") as f:
            self.config = json.load(f)

        self.ocr = OcrEngine()
        self.translator = Translator()
        self._overlay: TranslationOverlay | None = None
        self._selector: RegionSelector | None = None

        self._setup_tray()
        self._setup_hotkey()

    def _setup_tray(self):
        self.tray = QSystemTrayIcon()
        self.tray.setIcon(_make_tray_icon())
        self.tray.setToolTip("AI Translate — Ctrl+Shift+T")

        menu = QMenu()
        select_action = menu.addAction("Select Region\tCtrl+Shift+T")
        select_action.triggered.connect(self.start_selection)
        menu.addSeparator()
        quit_action = menu.addAction("Quit")
        quit_action.triggered.connect(self._shutdown)
        self.tray.setContextMenu(menu)
        self.tray.show()

    def _setup_hotkey(self):
        hotkey = self.config.get("hotkey", "ctrl+shift+t")
        try:
            self._hotkey_bridge = HotkeyBridge()
            self._hotkey_bridge.triggered.connect(self.start_selection)
            keyboard.add_hotkey(hotkey, lambda: self._hotkey_bridge.triggered.emit())
        except Exception:
            print(f"Warning: Could not register hotkey '{hotkey}'. "
                  "Use the tray icon to activate.")

    def start_selection(self):
        """Begin the select → OCR → translate → overlay pipeline."""
        if self._selector is not None:
            return  # already selecting

        self._dismiss_overlay()
        self._selector = RegionSelector()
        # Use a local event loop to block until selection completes
        QTimer.singleShot(0, self._run_selector_loop)

    def _run_selector_loop(self):
        from PySide6.QtCore import QEventLoop
        selector = self._selector
        loop = QEventLoop()
        selector.selection_done.connect(loop.quit)
        selector.destroyed.connect(loop.quit)
        selector.show()
        loop.exec()

        if selector.accepted and selector.selected_rect is not None:
            rect = selector.selected_rect
            self._process_region(rect)
        self._selector = None

    def _process_region(self, rect: QRect):
        """Capture, OCR, translate, and display overlay for the selected region."""
        try:
            # Capture the selected screen region
            with mss.mss() as sct:
                monitor = {
                    "left": rect.x(), "top": rect.y(),
                    "width": rect.width(), "height": rect.height(),
                }
                grabbed = sct.grab(monitor)

            img = Image.frombytes(
                "RGBA", (grabbed.width, grabbed.height),
                grabbed.pixels, "raw", "BGRA",
            ).convert("RGB")

            # OCR
            text = self.ocr.recognize(img)
            if not text:
                self._show_info("No text detected in the selected region.")
                return

            # Translate
            translated = self.translator.translate(text)
            if not translated:
                self._show_info("Translation returned empty.")
                return

            # Show overlay
            self._overlay = TranslationOverlay(rect, text, translated)

        except Exception as e:
            self._show_info(f"Error: {e}")

    def _dismiss_overlay(self):
        if self._overlay and self._overlay.isVisible():
            self._overlay.close()
        self._overlay = None

    def _show_info(self, message: str):
        toast = _InfoToast(message)
        toast.show()
        QTimer.singleShot(3000, toast.close)

    def _shutdown(self):
        self._dismiss_overlay()
        try:
            keyboard.unhook_all()
        except Exception:
            pass
        self.app.quit()

    def run(self):
        self.app.exec()


if __name__ == "__main__":
    App().run()
