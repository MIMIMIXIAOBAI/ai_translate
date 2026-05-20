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
        """Return (text, estimated_font_height_in_physical_pixels).

        The font height is estimated from Tesseract word bounding boxes and
        adjusted for the preprocessing scale factor so it matches the original
        image scale.
        """
        img, scale = self._preprocess(image)
        text = self._do_ocr(img).strip()
        raw_height = self._estimate_font_height(img)
        font_px = int(raw_height / scale) if scale > 1.0 else raw_height
        return text, font_px

    def _do_ocr(self, img: Image.Image) -> str:
        try:
            text = pytesseract.image_to_string(img, lang="eng+chi_sim", config="--psm 6")
        except pytesseract.TesseractError:
            text = pytesseract.image_to_string(img, lang="eng", config="--psm 6")
        return text

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

    def _estimate_font_height(self, img: Image.Image) -> int:
        """Estimate median character height (px) from Tesseract word boxes."""
        try:
            data = pytesseract.image_to_data(
                img, lang="eng", config="--psm 6",
                output_type=pytesseract.Output.DICT,
            )
            heights = []
            for i, level in enumerate(data["level"]):
                if level == 5:  # word level
                    h_val = data["height"][i]
                    if h_val > 0:
                        heights.append(h_val)
            if heights:
                return int(statistics.median(heights))
        except Exception:
            pass
        return 0
