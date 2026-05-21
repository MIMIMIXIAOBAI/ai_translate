"""Translation wrapper supporting Baidu, MyMemory, Google, and LibreTranslate."""

import hashlib
import json
import random
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

CONFIG_PATH = Path(__file__).parent / "config.json"


def _load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def _baidu_translate(text: str, target_lang: str = "zh",
                     appid: str = "", key: str = "",
                     proxies: dict | None = None) -> str:
    """Translate via Baidu Translation API (requires appid + key)."""
    # Language code mapping for Baidu
    baidu_lang = {
        "zh-CN": "zh", "zh": "zh",
        "en": "en",
        "ja": "jp", "jp": "jp",
        "ko": "kor",
        "fr": "fr", "de": "de", "es": "es",
        "pt": "pt", "it": "it", "ru": "ru",
        "ar": "ara", "th": "th", "vi": "vie",
    }
    to_lang = baidu_lang.get(target_lang, target_lang)

    salt = str(random.randint(32768, 65536))
    sign_str = appid + text + salt + key
    sign = hashlib.md5(sign_str.encode("utf-8")).hexdigest()

    params = {
        "q": text,
        "from": "auto",
        "to": to_lang,
        "appid": appid,
        "salt": salt,
        "sign": sign,
    }
    url = "https://fanyi-api.baidu.com/api/trans/vip/translate"
    data = urlencode(params).encode("utf-8")

    req = Request(url, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urlopen(req, timeout=15) as resp:
        result = json.loads(resp.read().decode("utf-8"))

    if "trans_result" in result:
        parts = [item["dst"] for item in result["trans_result"]]
        return "".join(parts)
    elif "error_code" in result:
        code = result["error_code"]
        msg = result.get("error_msg", "unknown")
        raise RuntimeError(f"Baidu API error {code}: {msg}")
    else:
        raise RuntimeError(f"Baidu API unexpected response: {result}")


class Translator:
    def __init__(self, target_lang: str | None = None):
        config = _load_config()
        if target_lang is None:
            target_lang = config.get("target_language", "zh-CN")
        self.target_lang = target_lang
        self._service = config.get("translation_service", "auto")

        # Baidu credentials
        self._baidu_appid = config.get("baidu_appid", "")
        self._baidu_key = config.get("baidu_key", "")

        self._proxies = None
        if config.get("proxy"):
            self._proxies = {"http": config["proxy"], "https": config["proxy"]}

    def translate(self, text: str) -> str:
        """Translate text to target language."""
        if not text or not text.strip():
            return ""

        # Baidu takes priority when credentials are configured
        if self._service == "baidu" and self._baidu_appid and self._baidu_key:
            return _baidu_translate(
                text, self.target_lang,
                self._baidu_appid, self._baidu_key,
                self._proxies,
            )

        if self._service == "auto":
            # Try Baidu first if credentials exist, then fall back
            if self._baidu_appid and self._baidu_key:
                try:
                    return _baidu_translate(
                        text, self.target_lang,
                        self._baidu_appid, self._baidu_key,
                        self._proxies,
                    )
                except Exception:
                    pass
            # Fall back to legacy backends
            return self._auto_translate(text)
        elif self._service == "baidu":
            raise RuntimeError(
                "Baidu translation requires baidu_appid and baidu_key in config.json"
            )
        else:
            return self._translate_with(self._service, text)

    def _auto_translate(self, text: str) -> str:
        """Try backends in order: Baidu → MyMemory → Google → LibreTranslate."""
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
