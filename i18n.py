# i18n.py
import json
import os
from config import DEFAULT_LANG, SUPPORTED_LANGS, resource_path

LOCALES_DIR = resource_path("locales")


class I18n:
    def __init__(self, lang: str = DEFAULT_LANG):
        self.lang = lang if lang in SUPPORTED_LANGS else DEFAULT_LANG
        self._data = {}
        self._load(self.lang)

    def _load(self, lang: str):
        path = os.path.join(LOCALES_DIR, f"{lang}.json")
        with open(path, "r", encoding="utf-8") as f:
            self._data = json.load(f)

    def set_lang(self, lang: str):
        if lang in SUPPORTED_LANGS:
            self.lang = lang
            self._load(lang)

    def t(self, key: str, **kwargs) -> str:
        text = self._data.get(key, key)
        if kwargs:
            try:
                text = text.format(**kwargs)
            except Exception:
                pass
        return text


i18n = I18n()