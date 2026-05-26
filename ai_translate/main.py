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


def _sample_brightness(img: Image.Image) -> float:
    """Return average perceived brightness (0–255) of an RGB PIL Image."""
    small = img.resize((8, 8), Image.LANCZOS)
    total = 0.0
    count = 0
    for pixel in small.getdata():
        if isinstance(pixel, int):
            total += pixel
        else:
            r, g, b = pixel[0], pixel[1], pixel[2]
            total += 0.299 * r + 0.587 * g + 0.114 * b
        count += 1
    return total / max(count, 1)


class _TranslateThread(QThread):
    """Runs OCR + translation in a background thread.

    Emits finished(QRect, list, bool) where list is [(text, x, y, w, h), ...]
    in logical coordinates, and bool is whether the background is dark.
    """

    finished = Signal(QRect, object, bool)
    error = Signal(str)

    def __init__(self, img: Image.Image, rect: QRect, dpr: float):
        super().__init__()
        self._img = img
        self._rect = rect
        self._dpr = dpr

    def run(self):
        try:
            ocr = OcrEngine()
            full_text, _font_px, line_boxes = ocr.recognize_with_lines(self._img)

            is_dark_bg = _sample_brightness(self._img) < 128
            dpr = self._dpr

            if line_boxes:
                # Translate full text in one request (avoids Baidu QPS limits)
                combined_text = "\n".join(lb[0] for lb in line_boxes)
                try:
                    translated_full = Translator().translate(combined_text)
                except Exception:
                    translated_full = ""
                if not translated_full:
                    translated_full = combined_text

                # Try to split back to per-line translations
                translated_parts = [p.strip() for p in translated_full.split("\n")]
                parts = [p for p in translated_parts if p]

                translated_lines = []
                if len(parts) == len(line_boxes):
                    # Perfect match — pair each translated part with its line position
                    for i, (orig_text, x, y, w, h) in enumerate(line_boxes):
                        translated_lines.append((
                            parts[i],
                            max(0, int(x / dpr)),
                            max(0, int(y / dpr)),
                            max(8, int(w / dpr)),
                            max(8, int(h / dpr)),
                        ))
                else:
                    # Line count mismatch — batch translation lost line structure.
                    # Fall back to translating each line individually with a small
                    # delay between calls to respect API rate limits (e.g. Baidu QPS).
                    translator = Translator()
                    for i, (orig_text, x, y, w, h) in enumerate(line_boxes):
                        line_text = orig_text.strip()
                        if not line_text:
                            continue
                        try:
                            if i > 0:
                                QThread.msleep(600)  # ~1 QPS ceiling
                            translated = translator.translate(line_text)
                        except Exception:
                            translated = line_text  # show original as fallback
                        if not translated:
                            translated = line_text
                        translated_lines.append((
                            translated,
                            max(0, int(x / dpr)),
                            max(0, int(y / dpr)),
                            max(8, int(w / dpr)),
                            max(8, int(h / dpr)),
                        ))

                self.finished.emit(self._rect, translated_lines, is_dark_bg)
            else:
                # Fallback: no line boxes found, translate entire block
                text = full_text or ocr.recognize(self._img).strip()
                if not text:
                    self.error.emit("未识别到文字")
                    return
                try:
                    translated = Translator().translate(text)
                except Exception:
                    translated = ""
                if not translated:
                    self.error.emit("翻译结果为空")
                    return
                translated_lines = [(translated, 8, 8,
                                     max(40, self._img.width // 2),
                                     max(20, self._img.height // 2))]
                self.finished.emit(self._rect, translated_lines, is_dark_bg)

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

        try:
            if selector.accepted and selector.selected_rect is not None:
                self._process_region(selector)
        except Exception as e:
            self._show_info(f"处理失败: {e}")
        finally:
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

        self._toast = _InfoToast("正在翻译...")
        self._toast.show()

        dpr = selector.dpr
        self._thread = _TranslateThread(img, logical, dpr)
        self._thread.finished.connect(self._on_translation_done)
        self._thread.error.connect(self._on_translation_error)
        self._thread.finished.connect(lambda: setattr(self, '_thread', None))
        self._thread.error.connect(lambda: setattr(self, '_thread', None))
        self._thread.start()

    def _on_translation_done(self, logical_rect: QRect, lines_data: list,
                             is_dark_bg: bool):
        if self._toast:
            self._toast.close()
            self._toast = None
        self._overlay = TranslationOverlay(logical_rect, lines_data, is_dark_bg)

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
