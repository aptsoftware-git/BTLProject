"""
spelling_standards.py
=======================
Configurable British/American English spelling-variant awareness.

Loads data/british_american_spellings.json (a curated pairs list) plus a
small set of regular suffix-swap rules (-ise/-ize, -our/-or, -re/-er,
-ll/-l) so a much wider set of regional spelling variants than any fixed
pairs list can be recognised.

`spelling_standard` preference values:
  "both"   (default) - never flag a correction that only swaps regional
             spelling; both British and American spellings are valid.
  "en-US"  - British -> American corrections are allowed through;
             American -> British corrections are rejected.
  "en-GB"  - the reverse of "en-US".
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from src.config import ROOT_DIR

_DATA_PATH = ROOT_DIR / "data" / "british_american_spellings.json"

_SUFFIX_RULES = [
    ("ise", "ize"), ("ised", "ized"), ("ising", "izing"), ("isation", "ization"),
    ("our", "or"), ("ours", "ors"), ("oured", "ored"), ("ouring", "oring"),
    ("re", "er"),
    ("lled", "led"), ("lling", "ling"), ("ller", "ler"),
]


def _load_pairs() -> dict:
    gb_to_us: dict[str, str] = {}
    if _DATA_PATH.exists():
        try:
            with open(_DATA_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            for gb, us in data.get("pairs", []):
                gb_to_us[gb.lower()] = us.lower()
        except Exception:
            pass
    return gb_to_us


_GB_TO_US = _load_pairs()
_US_TO_GB = {v: k for k, v in _GB_TO_US.items()}


def _suffix_variant_match(orig: str, sug: str) -> bool:
    """Regex-free heuristic: catches regional suffix swaps not in the curated list."""
    for gb_suffix, us_suffix in _SUFFIX_RULES:
        if orig.endswith(gb_suffix) and sug.endswith(us_suffix) and orig[: -len(gb_suffix)] == sug[: -len(us_suffix)]:
            if len(orig) - len(gb_suffix) >= 3:  # avoid matching tiny/unrelated words
                return True
        if orig.endswith(us_suffix) and sug.endswith(gb_suffix) and orig[: -len(us_suffix)] == sug[: -len(gb_suffix)]:
            if len(orig) - len(us_suffix) >= 3:
                return True
    return False


def classify_variant_direction(original: str, suggestion: str) -> Optional[str]:
    """
    Returns "gb_to_us" if `original` is the British spelling and `suggestion`
    the American one, "us_to_gb" for the reverse, or None if this isn't a
    recognised regional-spelling pair at all.
    """
    orig = (original or "").strip().lower()
    sug = (suggestion or "").strip().lower()
    if not orig or not sug or orig == sug:
        return None

    if _GB_TO_US.get(orig) == sug:
        return "gb_to_us"
    if _US_TO_GB.get(orig) == sug:
        return "us_to_gb"
    if _suffix_variant_match(orig, sug):
        # Suffix heuristic can't always tell direction reliably; use the
        # curated list's coverage of the given original word if present,
        # otherwise default to reporting a GB->US style swap (the common
        # case for -ise/-our/-re corrections a US-locale checker proposes).
        if orig in _GB_TO_US or orig.endswith(("ise", "ised", "ising", "isation", "our", "ours", "oured", "ouring", "re")):
            return "gb_to_us"
        return "us_to_gb"
    return None


def is_regional_variant(original: str, suggestion: str) -> bool:
    return classify_variant_direction(original, suggestion) is not None


def should_reject_for_spelling_standard(original: str, suggestion: str, standard: str = "both") -> bool:
    """
    True if this candidate correction should be rejected because it only
    swaps a valid regional spelling for another valid regional spelling,
    given the configured `standard` ("both" | "en-US" | "en-GB").
    """
    direction = classify_variant_direction(original, suggestion)
    if direction is None:
        return False
    standard = (standard or "both").lower()
    if standard == "both":
        return True
    if standard in ("en-us", "us", "american"):
        # Allow GB->US corrections through; reject US->GB.
        return direction == "us_to_gb"
    if standard in ("en-gb", "gb", "british"):
        return direction == "gb_to_us"
    return True
