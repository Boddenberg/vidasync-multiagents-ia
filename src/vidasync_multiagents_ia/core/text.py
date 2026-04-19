"""Text normalization helpers shared across services.

Centralizes the NFKD + ASCII fold + whitespace-collapse pipeline that was
previously reimplemented in more than a dozen call sites.
"""
from __future__ import annotations

import re
import unicodedata

_WHITESPACE_RE = re.compile(r"\s+")


def strip_accents(value: str) -> str:
    """Return ``value`` with diacritics removed via NFKD + ASCII fold."""
    normalized = unicodedata.normalize("NFKD", value)
    return normalized.encode("ascii", "ignore").decode("ascii")


def normalize_pt_text(
    value: str,
    *,
    lower: bool = True,
    strip: bool = True,
    collapse_whitespace: bool = True,
) -> str:
    """NFKD-fold Portuguese text for case-insensitive matching.

    Applies (in order): optional strip, optional lowercase, ASCII fold, and
    optional whitespace collapse. Defaults match the most common usage.
    """
    result = value.strip() if strip else value
    if lower:
        result = result.lower()
    result = strip_accents(result)
    if collapse_whitespace:
        result = _WHITESPACE_RE.sub(" ", result).strip()
    return result
