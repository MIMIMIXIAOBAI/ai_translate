"""OCR engine using Tesseract with Pillow image preprocessing."""

import statistics
import sys
import shutil
from pathlib import Path

from PIL import Image, ImageFilter, ImageEnhance
import pytesseract


def _find_tesseract() -> str | None:
    """Auto-detect Tesseract installation on various platforms."""
    found = shutil.which("tesseract")
    if found:
        return found

    if sys.platform == "win32":
        candidates = [
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        ]
        import os
        local = os.environ.get("LOCALAPPDATA", "")
        if local:
            candidates.append(Path(local) / "Programs" / "Tesseract-OCR" / "tesseract.exe")
        for p in candidates:
            if Path(str(p)).exists():
                return str(p)
    return None


def _auto_configure_tesseract():
    path = _find_tesseract()
    if path:
        pytesseract.pytesseract.tesseract_cmd = path


_auto_configure_tesseract()


class OcrEngine:
    def recognize(self, image: Image.Image) -> str:
        """Extract text from a PIL Image via Tesseract OCR with preprocessing."""
        img, _ = self._preprocess(image)
        return self._do_ocr(img).strip()

    def recognize_with_size(self, image: Image.Image) -> tuple[str, int]:
        """Return (text, estimated_font_height_in_physical_pixels)."""
        text, font_px, _first_x, _first_y = self.recognize_with_layout(image)
        return text, font_px

    def recognize_with_layout(self, image: Image.Image) -> tuple[str, int, int, int]:
        """Return (text, font_px, first_word_x, first_word_y).

        Coordinates are in the original image's pixel space, adjusted for
        any preprocessing scale factor.
        """
        img, scale = self._preprocess(image)
        text = self._do_ocr(img).strip()
        font_px, first_x, first_y = self._extract_layout(img, scale)
        return text, font_px, first_x, first_y

    def recognize_with_lines(self, image: Image.Image) -> tuple[str, int, list]:
        """Return (full_text, font_px, line_boxes).

        line_boxes is a list of (line_text, x, y, w, h) in original image pixels,
        sorted by vertical then horizontal position.
        """
        img, scale = self._preprocess(image)
        text = self._do_ocr(img).strip()
        font_px, line_boxes = self._extract_lines(img, scale)
        return text, font_px, line_boxes

    def _image_to_data(self, img: Image.Image) -> dict | None:
        """Call pytesseract.image_to_data with language fallback chain."""
        for langs in ("eng+chi_sim+jpn", "eng+chi_sim", "eng+jpn", "eng"):
            try:
                return pytesseract.image_to_data(
                    img, lang=langs, config="--psm 6",
                    output_type=pytesseract.Output.DICT,
                )
            except pytesseract.TesseractError:
                continue
        return None

    def _do_ocr(self, img: Image.Image) -> str:
        for langs in ("eng+chi_sim+jpn", "eng+chi_sim", "eng+jpn", "eng"):
            try:
                return pytesseract.image_to_string(img, lang=langs, config="--psm 6")
            except pytesseract.TesseractError:
                continue
        return ""

    def _preprocess(self, image: Image.Image) -> tuple[Image.Image, float]:
        """Enhance image for better OCR accuracy.

        Returns (preprocessed_image, scale_factor).
        """
        img = image.convert("L")  # grayscale

        scale = 1.0
        w, h = img.size
        if w < 300 or h < 100:
            scale = max(2.0, min(4.0, 300.0 / min(w, 1)))
            img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(2.0)

        img = img.filter(ImageFilter.SHARPEN)

        return img, scale

    def _extract_layout(self, img: Image.Image, scale: float) -> tuple[int, int, int]:
        """Return (font_height_px, first_word_x, first_word_y) in original image coords."""
        data = self._image_to_data(img)
        if data is None:
            return 0, 0, 0

        try:
            heights = []
            first_x = first_y = 0
            found_first = False
            for i, level in enumerate(data["level"]):
                if level == 5:  # word level
                    h_val = data["height"][i]
                    if h_val > 0:
                        heights.append(h_val)
                        if not found_first:
                            first_x = data["left"][i]
                            first_y = data["top"][i]
                            found_first = True

            font_px = int(statistics.median(heights)) if heights else 0

            if scale > 1.0:
                font_px = int(font_px / scale)
                first_x = int(first_x / scale)
                first_y = int(first_y / scale)

            return font_px, first_x, first_y
        except Exception:
            return 0, 0, 0

    def _extract_lines(self, img: Image.Image, scale: float) -> tuple[int, list]:
        """Return (font_px, line_boxes) where line_boxes = [(text, x, y, w, h), ...].

        Groups word-level Tesseract data into lines and computes per-line
        bounding boxes in original image coordinates.
        """
        data = self._image_to_data(img)
        if data is None:
            return 0, []

        try:
            heights = []
            # Collect all valid words with their spatial metadata
            words = []
            for i, level in enumerate(data["level"]):
                if level == 5:
                    h_val = data["height"][i]
                    w_val = data["width"][i]
                    word_text = (data["text"][i] or "").strip()
                    if h_val > 0 and w_val > 0 and word_text:
                        heights.append(h_val)
                        words.append({
                            "text": word_text,
                            "left": data["left"][i],
                            "top": data["top"][i],
                            "width": w_val,
                            "height": h_val,
                            "line_num": data["line_num"][i],
                            "block_num": data["block_num"][i],
                            "par_num": data["par_num"][i],
                        })

            if not words:
                return 0, []

            font_px = int(statistics.median(heights)) if heights else 0

            # Group words by (block_num, par_num, line_num)
            groups: dict[tuple, list] = {}
            for w in words:
                key = (w["block_num"], w["par_num"], w["line_num"])
                groups.setdefault(key, []).append(w)

            # Compute per-line bounding box
            line_boxes = []
            for _key, group in groups.items():
                line_text = " ".join(w["text"] for w in group)
                min_x = min(w["left"] for w in group)
                min_y = min(w["top"] for w in group)
                max_x = max(w["left"] + w["width"] for w in group)
                max_y = max(w["top"] + w["height"] for w in group)
                line_boxes.append((line_text, min_x, min_y,
                                   max_x - min_x, max_y - min_y))

            # Sort by vertical then horizontal position
            line_boxes.sort(key=lambda b: (b[2], b[1]))

            if scale > 1.0:
                font_px = int(font_px / scale)
                line_boxes = [
                    (t, int(x / scale), int(y / scale),
                     int(w / scale), int(h / scale))
                    for t, x, y, w, h in line_boxes
                ]

            return font_px, line_boxes
        except Exception:
            return 0, []
