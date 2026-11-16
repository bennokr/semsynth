"""Which language the text columns of a table are written in.

linked-codebook defines the protocol (which cells are asked, how many must agree); this module supplies the detector
it asks, ``py3langid``, and turns a detected tag into the Faker locale that MetaSyn uses for free text. ``py3langid``
is optional (extra ``language``): without it no language is detected and nothing else changes.
"""

from __future__ import annotations

import functools
import logging
from collections.abc import Callable
from typing import Any

LOGGER = logging.getLogger(__name__)

# Tags py3langid returns for text that has no language ("zxx") or that it declines to classify ("und").
_NO_LANGUAGE = frozenset({"zxx", "und"})

# Locales Faker has no ``xx_XX`` locale for, or where the language alone is ambiguous.
_PREFERRED_LOCALES = {"en": "en_US", "pt": "pt_PT", "zh": "zh_CN"}


def detector() -> Callable[[str], str | None] | None:
    """The language detector for linked-codebook's ``infer``, or ``None`` when ``py3langid`` is not installed."""

    try:
        from py3langid import langid
    except ImportError:
        LOGGER.info("py3langid is not installed; the language of text columns is not detected")
        return None
    return functools.partial(_detect, langid)


def _detect(langid: Any, text: str) -> str | None:
    tag, score = langid.classify(text)
    if tag in _NO_LANGUAGE or score <= langid.RAW_FLOOR:
        return None
    return str(tag).lower()


def faker_locale(tag: str | None) -> str | None:
    """The Faker locale for a BCP 47 language tag, or ``None`` when Faker has none for that language.

    ``nl`` gives ``nl_NL`` and ``en`` gives ``en_US``; a tag that already names a region (``nl-BE``) is used as is.
    """

    if not tag:
        return None
    from faker.config import AVAILABLE_LOCALES

    language, _, region = tag.replace("_", "-").partition("-")
    language = language.lower()
    if region and f"{language}_{region.upper()}" in AVAILABLE_LOCALES:
        return f"{language}_{region.upper()}"
    candidates = (_PREFERRED_LOCALES.get(language), f"{language}_{language.upper()}", language)
    found = next((name for name in candidates if name in AVAILABLE_LOCALES), None)
    if found is not None:
        return found
    return next((name for name in sorted(AVAILABLE_LOCALES) if name.startswith(f"{language}_")), None)


def apply_free_text_locales(frame: Any, codebook: Any) -> None:
    """Draw free text in the language the codebook records for the column (MetaSyn fits English otherwise)."""

    if codebook is None:
        return
    from faker import Faker
    from metasyn.distribution import FreeTextDistribution

    for var in frame.meta_vars:
        column = codebook.column(var.name)
        locale = faker_locale(column.get("language") if column else None)
        if locale and isinstance(var.distribution, FreeTextDistribution):
            var.distribution.locale = locale
            var.distribution.fake = Faker(locale=locale)
