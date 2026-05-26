"""OCR engine using Tesseract with Pillow image preprocessing."""

import os
import statistics
import sys
import shutil
from pathlib import Path
from urllib.request import urlopen

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
        # Also set TESSDATA_PREFIX to system tessdata so get_languages works
        sys_td = Path(path).parent / "tessdata"
        if sys_td.is_dir():
            os.environ.setdefault("TESSDATA_PREFIX", str(sys_td))


_auto_configure_tesseract()

_TESSERACT_AVAILABLE = _find_tesseract() is not None


class _TesseractNotFoundError(RuntimeError):
    """Raised when Tesseract OCR is not installed."""

    def __init__(self):
        super().__init__(
            "未找到 Tesseract OCR 引擎，无法进行文字识别。\n\n"
            "请先安装 Tesseract OCR：\n"
            "  • Windows: winget install tesseract\n"
            "    或从 https://github.com/UB-Mannheim/tesseract/wiki 下载安装包\n"
            "    安装时请务必勾选 Chinese (Simplified) 语言包\n"
            "  • macOS: brew install tesseract tesseract-lang\n"
            "  • Linux: sudo apt install tesseract-ocr tesseract-ocr-eng tesseract-ocr-chi-sim\n\n"
            "安装完成后重新启动本程序即可。"
        )


# ── language pack management ──────────────────────────────────────────

_ocr_langs = "eng"
_user_tessdata: Path | None = None
_tessdata_config = ""  # extra config fragment for --tessdata-dir


def _download_lang(lang_code: str, dest_dir: Path) -> bool:
    """Download a .traineddata file from multiple mirrors."""
    mirrors = [
        f"https://raw.githubusercontent.com/tesseract-ocr/tessdata/main/{lang_code}.traineddata",
        f"https://ghproxy.net/https://raw.githubusercontent.com/tesseract-ocr/tessdata/main/{lang_code}.traineddata",
    ]
    data = None
    for url in mirrors:
        try:
            with urlopen(url, timeout=60) as resp:
                data = resp.read()
            break
        except Exception:
            continue

    if data is None:
        print(f"  Could not reach any mirror for {lang_code}.traineddata")
        print(f"  Please download manually from:")
        print(f"    {mirrors[0]}")
        print(f"  and save to: {dest_dir}")
        return False

    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / f"{lang_code}.traineddata"
    target.write_bytes(data)
    return True


def _init_languages():
    """Populate a user-local tessdata with all needed language packs.

    The Windows Tesseract tessdata under Program Files is read-only
    without admin, so we mirror everything into %APPDATA%/ai-translate/tessdata
    and pass --tessdata-dir to every Tesseract invocation.

    When Tesseract is not installed, this still creates the user tessdata
    directory so language packs can be pre-downloaded for later use.
    """
    global _ocr_langs, _user_tessdata, _tessdata_config

    appdata = os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))
    user_td = Path(appdata) / "ai-translate" / "tessdata"
    user_td.mkdir(parents=True, exist_ok=True)
    _user_tessdata = user_td
    _tessdata_config = f"--tessdata-dir {user_td}"

    # Copy system traineddata into user dir (avoid admin permissions later)
    if _TESSERACT_AVAILABLE:
        tess_cmd = pytesseract.pytesseract.tesseract_cmd
        if tess_cmd:
            sys_td = Path(tess_cmd).parent / "tessdata"
            if sys_td.is_dir():
                for src in sys_td.glob("*.traineddata"):
                    dst = user_td / src.name
                    if not dst.exists():
                        try:
                            dst.write_bytes(src.read_bytes())
                        except Exception:
                            pass

    # Enumerate installed languages from the user directory
    installed: set[str] = set()
    for f in user_td.glob("*.traineddata"):
        installed.add(f.stem)

    # Download missing language packs
    wanted = ["chi_sim", "jpn"]
    missing = [l for l in wanted if l not in installed]
    if missing:
        print("=" * 56)
        print("AI Translate — installing Tesseract language packs …")
        for lang in missing:
            print(f"  {lang}.traineddata —", end=" ")
            if _download_lang(lang, user_td):
                installed.add(lang)
                print("installed.")
            else:
                print("FAILED.")
        print("=" * 56)

    # Update TESSDATA_PREFIX so get_languages still works for scripts
    os.environ["TESSDATA_PREFIX"] = str(user_td)

    preferred = ["eng", "chi_sim", "jpn"]
    available = [l for l in preferred if l in installed]
    _ocr_langs = "+".join(available) if available else "eng"


_init_languages()


# ── OCR engine ────────────────────────────────────────────────────────

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
        """Return (text, font_px, first_word_x, first_word_y)."""
        img, scale = self._preprocess(image)
        text = self._do_ocr(img).strip()
        font_px, first_x, first_y = self._extract_layout(img, scale)
        return text, font_px, first_x, first_y

    def recognize_with_lines(self, image: Image.Image) -> tuple[str, int, list]:
        """Return (full_text, font_px, line_boxes)."""
        img, scale = self._preprocess(image)
        text = self._do_ocr(img).strip()
        font_px, line_boxes = self._extract_lines(img, scale)
        return text, font_px, line_boxes

    def _do_ocr(self, img: Image.Image) -> str:
        if not _TESSERACT_AVAILABLE:
            raise _TesseractNotFoundError()
        cfg = _tessdata_config + " --psm 6"
        try:
            return pytesseract.image_to_string(img, lang=_ocr_langs, config=cfg)
        except pytesseract.TesseractError:
            return pytesseract.image_to_string(img, lang="eng", config=cfg)

    def _image_to_data(self, img: Image.Image) -> dict | None:
        """Call pytesseract.image_to_data with available languages."""
        if not _TESSERACT_AVAILABLE:
            raise _TesseractNotFoundError()
        cfg = _tessdata_config + " --psm 6"
        try:
            return pytesseract.image_to_data(
                img, lang=_ocr_langs, config=cfg,
                output_type=pytesseract.Output.DICT,
            )
        except pytesseract.TesseractError:
            try:
                return pytesseract.image_to_data(
                    img, lang="eng", config=cfg,
                    output_type=pytesseract.Output.DICT,
                )
            except pytesseract.TesseractError:
                return None

    def _preprocess(self, image: Image.Image) -> tuple[Image.Image, float]:
        """Enhance image for better OCR accuracy."""
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
                if level == 5:
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
        """Return (font_px, line_boxes) where line_boxes = [(text, x, y, w, h), ...]."""
        data = self._image_to_data(img)
        if data is None:
            return 0, []

        try:
            heights = []
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

            groups: dict[tuple, list] = {}
            for w in words:
                key = (w["block_num"], w["par_num"], w["line_num"])
                groups.setdefault(key, []).append(w)

            line_boxes = []
            for _key, group in groups.items():
                line_text = " ".join(w["text"] for w in group)
                min_x = min(w["left"] for w in group)
                min_y = min(w["top"] for w in group)
                max_x = max(w["left"] + w["width"] for w in group)
                max_y = max(w["top"] + w["height"] for w in group)
                line_boxes.append((line_text, min_x, min_y,
                                   max_x - min_x, max_y - min_y))

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
