"""UI translations only. Never translate save fields, asset IDs or file formats.

Catalogs live beside this module (also in the compiled distribution). English
source messages are the keys. Unknown locales and missing/bad messages fall
back to English, so a translation cannot prevent the editor from opening.
"""
from __future__ import annotations

import json
import locale
import os
import sys
from functools import lru_cache
from pathlib import Path
from string import Formatter

LANGUAGES = {
    'en': 'English',
    'fr': 'Français',
    'de': 'Deutsch',
    'ru': 'Русский',
    'ja': '日本語',
    'es-419': 'Español (Latinoamérica)',
}
_language = 'en'


def normalize_language(value: str | None) -> str:
    tag = str(value or '').replace('_', '-').lower().split('-')[0]
    return 'es-419' if tag == 'es' else tag if tag in LANGUAGES else 'en'


def system_language() -> str:
    try:
        if os.name == 'nt':
            import ctypes
            name = locale.windows_locale.get(ctypes.windll.kernel32.GetUserDefaultUILanguage())
        else:
            name = locale.getlocale()[0]
        return normalize_language(name)
    except (AttributeError, OSError, ValueError):
        return 'en'


def set_language(language: str) -> str:
    global _language
    _language = normalize_language(language)
    return _language


def get_language() -> str:
    return _language


def fields(text: str) -> tuple:
    """Placeholder names, conversions and format specs must survive translation."""
    return tuple(sorted((name, spec, conversion or '') for _, name, spec, conversion
                        in Formatter().parse(text) if name is not None))


@lru_cache(maxsize=None)
def catalog(language: str) -> dict[str, str]:
    if language == 'en':
        return {}
    bases = [Path(__file__).resolve().parent]
    if getattr(sys, '_MEIPASS', None):
        bases.insert(0, Path(sys._MEIPASS))
    for base in bases:
        try:
            data = json.loads((base / 'locales' / f'{language}.json').read_text(encoding='utf-8'))
            valid = {}
            for key, value in data.items():
                try:
                    if isinstance(value, str) and value.strip() and fields(key) == fields(value):
                        valid[key] = value
                except ValueError:
                    # One broken translation must not disable the other entries.
                    continue
            return valid
        except (OSError, ValueError, AttributeError, TypeError):
            continue
    return {}


def translate_for(language: str, message: str, **values) -> str:
    translated = catalog(normalize_language(language)).get(message, message)
    if not values:
        return translated
    try:
        return translated.format(**values)
    except (KeyError, IndexError, ValueError):
        return message.format(**values)


def tr(message: str, **values) -> str:
    return translate_for(_language, message, **values)
