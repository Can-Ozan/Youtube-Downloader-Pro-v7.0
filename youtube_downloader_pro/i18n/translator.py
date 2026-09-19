"""Central UTF-8 catalogs using English source messages as stable translation keys.

Like Qt source-text catalogs, identifiers and combo values remain untranslated.
Translated strings retain their source keys for in-place Qt retranslation.
"""

import ctypes
import json
import locale
import logging
import os
import re
import sys
from functools import lru_cache

from youtube_downloader_pro.utils.resources import resource_path

_language = "en"
log = logging.getLogger(__name__)


def system_language(locale_name: str | None = None) -> str:
    if locale_name is None:
        locale_name = os.environ.get("LC_ALL") or os.environ.get("LC_MESSAGES")
        if not locale_name and sys.platform == "win32":
            # Windows UI language, independent of regional number/date formatting.
            locale_name = locale.windows_locale.get(
                ctypes.windll.kernel32.GetUserDefaultUILanguage()
            )
        locale_name = locale_name or locale.getlocale()[0] or "en"
    return "tr" if locale_name.lower().startswith(("tr", "turkish")) else "en"


@lru_cache(maxsize=2)
def catalog(code: str) -> dict[str, str]:
    path = resource_path("youtube_downloader_pro", "i18n", f"{code}.json")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in value.items()
        ):
            raise ValueError("Translation catalog must map strings to strings")
        return value
    except (OSError, ValueError) as error:
        log.warning("Cannot load translation catalog %s: %s", code, error)
        return {}


def set_language(code: str) -> None:
    global _language
    _language = code if code in {"tr", "en"} else "en"


def language() -> str:
    return _language


class TranslatedText(str):
    """A string retaining its source key and values for later UI retranslation."""

    def __new__(cls, text, key, values):
        instance = super().__new__(cls, text)
        instance.key = key
        instance.values = values
        return instance


def tr(key: str, **values) -> str:
    if isinstance(key, TranslatedText):
        values = key.values | values
        key = key.key
    source_values = values
    values = {
        name: tr(value) if isinstance(value, TranslatedText) else value
        for name, value in values.items()
    }
    english = catalog("en").get(key, key)
    text = catalog(_language).get(key) or english
    if not values:
        return TranslatedText(text, key, source_values)
    try:
        return TranslatedText(text.format(**values), key, source_values)
    except (KeyError, ValueError, IndexError):
        try:
            return TranslatedText(english.format(**values), key, source_values)
        except (KeyError, ValueError, IndexError):
            return TranslatedText(english, key, source_values)


@lru_cache(maxsize=1)
def _message_patterns():
    patterns = []
    for key in catalog("en"):
        if "{" in key:
            escaped = re.escape(key)
            escaped = re.sub(r"\\\{(\w+)\\\}", r"(?P<\1>.+?)", escaped)
            patterns.append((re.compile("^" + escaped + "$", re.DOTALL), key))
    return patterns


def translate_message(message: str) -> str:
    """Present engine messages without placing language choices in business logic."""
    if isinstance(message, TranslatedText):
        return tr(message)
    if message in catalog("en"):
        return tr(message)
    for pattern, key in _message_patterns():
        if match := pattern.fullmatch(message):
            return tr(key, **match.groupdict())
    return message
