"""AI Translate — screen region OCR + translation desktop app.

Hotkey Ctrl+Shift+T or system tray → select a screen region → OCR → translate → overlay.
"""

import json
import sys
from pathlib import Path

import mss
from PIL import Image
import keyboard

from PySide6.QtCore import Qt, Signal, QObject, QRect, QTimer, QThread
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
    """A brief, auto-dismissing toast message."""

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


class _TranslateThread(QThread):
    """Runs OCR + translation in a background thread."""
    finished = Signal(str, str, QRect, int, float)
    error = Signal(str)

    def __init__(self, img: Image.Image, rect: QRect, dpr: float):
        super().__init__()
        self._img = img
        self._rect = rect
        self._dpr = dpr

    def run(self):
        try:
            ocr = OcrEngine()
            text, font_px = ocr.recognize_with_size(self._img)
            if not text:
                self.error.emit("未识别到文字")
                return
            translator = Translator()
            translated = translator.translate(text)
            if not translated:
                self.error.emit("翻译结果为空")
                return
            self.finished.emit(text, translated, self._rect, font_px, self._dpr)
        except Exception as e:
            self.error.emit(str(e))


class App:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)

        with open(CONFIG_PATH, encoding="utf-8") as f:
            self.config = json.load(f)

        self._overlay: TranslationOverlay | None = None
        self._selector: RegionSelector | None = None
        self._thread: _TranslateThread | None = None

        self._setup_tray()
        self._setup_hotkey()

    def _setup_tray(self):
        self.tray = QSystemTrayIcon()
        self.tray.setIcon(_make_tray_icon())
        self.tray.setToolTip("AI Translate — Ctrl+Shift+T")

        menu = QMenu()
        select_action = menu.addAction("框选翻译\tCtrl+Shift+T")
        select_action.triggered.connect(self.start_selection)
        menu.addSeparator()
        quit_action = menu.addAction("退出")
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

    # ── selection pipeline ───────────────────────────────────────────

    def start_selection(self):
        if self._selector is not None:
            return

        self._dismiss_overlay()
        self._selector = RegionSelector()
        QTimer.singleShot(50, self._run_selector_loop)

    def _run_selector_loop(self):
        from PySide6.QtCore import QEventLoop
        selector = self._selector
        loop = QEventLoop()
        selector.selection_done.connect(loop.quit)
        selector.destroyed.connect(loop.quit)
        selector.show()
        selector.raise_()
        selector.activateWindow()
        loop.exec()

        if selector.accepted and selector.selected_rect is not None:
            self._process_region(selector)
        self._selector = None

    def _process_region(self, selector: RegionSelector):
        """Capture the selected region and start OCR + translate in background."""
        physical = selector.physical_rect()
        logical = selector.selected_rect

        with mss.MSS() as sct:
            monitor = {
                "left": physical.x(), "top": physical.y(),
                "width": max(1, physical.width()),
                "height": max(1, physical.height()),
            }
            grabbed = sct.grab(monitor)

        img = Image.frombytes("RGB", (grabbed.width, grabbed.height), grabbed.rgb)

        # Show progress toast
        self._toast = _InfoToast("正在翻译...")
        self._toast.show()

        # Start background thread
        dpr = selector.dpr
        self._thread = _TranslateThread(img, logical, dpr)
        self._thread.finished.connect(self._on_translation_done)
        self._thread.error.connect(self._on_translation_error)
        self._thread.finished.connect(lambda: setattr(self, '_thread', None))
        self._thread.error.connect(lambda: setattr(self, '_thread', None))
        self._thread.start()

    def _on_translation_done(self, original: str, translated: str, logical_rect: QRect,
                            font_size_px: int = 0, dpr: float = 1.0):
        if self._toast:
            self._toast.close()
            self._toast = None
        self._overlay = TranslationOverlay(
            logical_rect, original, translated, font_size_px, dpr)

    def _on_translation_error(self, msg: str):
        if self._toast:
            self._toast.close()
            self._toast = None
        self._show_info(f"翻译失败: {msg}")

    # ── overlay management ──────────────────────────────────────────

    def _dismiss_overlay(self):
        try:
            if self._overlay is not None:
                self._overlay.close()
        except RuntimeError:
            pass
        self._overlay = None

    def _show_info(self, message: str):
        toast = _InfoToast(message)
        toast.show()
        QTimer.singleShot(3000, toast.close)

    def _shutdown(self):
        self._dismiss_overlay()
        if self._thread and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(2000)
        try:
            keyboard.unhook_all()
        except Exception:
            pass
        self.app.quit()

    def run(self):
        self.app.exec()


if __name__ == "__main__":
    App().run()
