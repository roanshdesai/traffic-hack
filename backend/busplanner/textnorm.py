"""Deterministic text normalisation used for matching.

These functions only remove differences in case, spacing and punctuation.
They never expand abbreviations or correct spelling: anything that needs a
judgement call is left unmatched and reported for human review.
"""

from __future__ import annotations

import math
import re
import unicodedata

_NON_ALNUM = re.compile(r"[^0-9A-Z]+")


def _fold(value: str) -> str:
    text = unicodedata.normalize("NFKC", value or "").upper().replace("&", " AND ")
    return text


def code_key(value: str) -> str:
    """Key for route numbers and stop codes: ``"534-a "`` -> ``"534A"``."""
    return _NON_ALNUM.sub("", _fold(value))


def name_key(value: str) -> str:
    """Key for stop names: case-folded, punctuation and repeated spaces collapsed."""
    return _NON_ALNUM.sub(" ", _fold(value)).strip()


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))
