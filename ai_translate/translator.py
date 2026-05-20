"""Translation wrapper supporting multiple backends with proxy support."""

import json
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "config.json"


def _load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


class Translator:
    def __init__(self, target_lang: str | None = None):
        config = _load_config()
        if target_lang is None:
            target_lang = config.get("target_language", "zh-CN")
        self.target_lang = target_lang
        self._service = config.get("translation_service", "auto")
        self._proxies = None
        if config.get("proxy"):
            self._proxies = {"http": config["proxy"], "https": config["proxy"]}

    def translate(self, text: str) -> str:
        """Translate text to target language using available backends."""
        if not text or not text.strip():
            return ""

        if self._service == "auto":
            return self._auto_translate(text)
        else:
            return self._translate_with(self._service, text)

    def _auto_translate(self, text: str) -> str:
        """Try backends in order: MyMemory → Google (if accessible) → LibreTranslate."""
        for service in ["mymemory", "google", "libre"]:
            try:
                result = self._translate_with(service, text)
                if result and result != text:
                    return result
            except Exception:
                continue
        raise RuntimeError(
            "All translation backends failed. "
            "Check your network connection or set 'proxy' in config.json."
        )

    def _translate_with(self, service: str, text: str) -> str:
        from deep_translator import (
            MyMemoryTranslator,
            GoogleTranslator,
            LibreTranslator,
        )

        params = {"target": self.target_lang}
        if self._proxies:
            params["proxies"] = self._proxies

        if service == "mymemory":
            # MyMemory uses full language names, not codes
            source_lang = self._to_mymemory_lang("en")
            target_lang = self._to_mymemory_lang(self.target_lang)
            return MyMemoryTranslator(
                source=source_lang, target=target_lang
            ).translate(text)
        elif service == "google":
            params["source"] = "auto"
            return GoogleTranslator(**params).translate(text)
        elif service == "libre":
            params["source"] = "auto"
            return LibreTranslator(**params).translate(text)
        else:
            raise ValueError(f"Unknown translation service: {service}")

    @staticmethod
    def _to_mymemory_lang(code: str) -> str:
        """Map a language code (e.g. 'en', 'zh-CN') to MyMemory's full name."""
        mapping = {
            "en": "english",
            "zh-CN": "chinese simplified",
            "zh-TW": "chinese traditional",
            "ja": "japanese",
            "ko": "korean",
            "fr": "french",
            "de": "german",
            "es": "spanish",
            "pt": "portuguese",
            "it": "italian",
            "ru": "russian",
            "ar": "arabic",
            "th": "thai",
            "vi": "vietnamese",
        }
        return mapping.get(code, code)
