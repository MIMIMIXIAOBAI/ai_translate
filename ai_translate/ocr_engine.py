"""OCR engine using Tesseract with Pillow image preprocessing."""

import sys
import shutil
from pathlib import Path

from PIL import Image, ImageFilter, ImageEnhance
import pytesseract


def _find_tesseract() -> str | None:
    """Auto-detect Tesseract installation on various platforms."""
    # Check PATH first
    found = shutil.which("tesseract")
    if found:
        return found

    if sys.platform == "win32":
        candidates = [
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        ]
        # Also check user-local install
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
        img = self._preprocess(image)
        try:
            text = pytesseract.image_to_string(img, lang="eng+chi_sim", config="--psm 6")
        except pytesseract.TesseractError:
            # Retry with English only if combined lang data missing
            text = pytesseract.image_to_string(img, lang="eng", config="--psm 6")
        return text.strip()

    def _preprocess(self, image: Image.Image) -> Image.Image:
        """Enhance image for better OCR accuracy."""
        img = image.convert("L")  # grayscale

        # Upscale small images for better recognition
        w, h = img.size
        if w < 300 or h < 100:
            scale = max(2, min(4, 300 // min(w, 1)))
            img = img.resize((w * scale, h * scale), Image.LANCZOS)

        # Increase contrast
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(2.0)

        # Sharpen
        img = img.filter(ImageFilter.SHARPEN)

        return img
