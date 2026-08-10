"""
ambiguity_context_filter.py
==============================
Deterministic context-awareness guard for "Numerical inconsistency",
"Date / timeline inconsistency", and "Unit / measurement inconsistency"
findings.

These three categories are the ones most prone to false positives from
legitimate differences the audit called out explicitly: different
reporting periods (FY2023 vs FY2024), and unit/scale conversions (crore vs
million, lakh vs thousand) that are numerically equivalent once normalized.

This is a bounded heuristic, not full entity/metric resolution -- it only
catches the two most common, cheaply-verifiable false-positive patterns:
evidence items that reference different time periods, and evidence items
whose numbers are equivalent under a standard unit-scale conversion. It
never *adds* a finding; it only rejects candidates the LLM already flagged
when the evidence itself contradicts the claim of a conflict.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

_CONTEXT_SENSITIVE_CATEGORIES = frozenset({
    "Numerical inconsistency",
    "Date / timeline inconsistency",
    "Unit / measurement inconsistency",
})

# Matches FY2023, FY 23, FY-2024, 2023-24, Q1 2024, Q3FY23, or a bare
# 4-digit year -- broad enough to catch the common reporting-period phrasings
# without trying to be a full date parser.
_PERIOD_RE = re.compile(
    r"\bFY[\s-]?(\d{2,4})\b"
    r"|\bQ[1-4][\s-]?(?:FY)?[\s-]?(\d{2,4})\b"
    r"|\b((?:19|20)\d{2})[\s/-]((?:19|20)?\d{2})\b"
    r"|\b((?:19|20)\d{2})\b",
    re.IGNORECASE,
)


def _normalize_year(raw: str) -> str:
    raw = raw.strip()
    if len(raw) == 2:
        # "23" -> "2023" (assumes 2000s; good enough for a plausibility check)
        return "20" + raw
    return raw[-4:] if len(raw) > 4 else raw


def _extract_periods(text: str) -> set:
    periods = set()
    for m in _PERIOD_RE.finditer(text or ""):
        for g in m.groups():
            if g:
                periods.add(_normalize_year(g))
    return periods


# Scale words/abbreviations -> multiplier, for normalizing numbers before
# comparing them across evidence items (e.g. "1.2 crore" vs "12 million").
_SCALE_WORDS = {
    "crore": 10_000_000, "crores": 10_000_000, "cr": 10_000_000,
    "lakh": 100_000, "lakhs": 100_000, "lac": 100_000, "lacs": 100_000,
    "billion": 1_000_000_000, "bn": 1_000_000_000,
    "million": 1_000_000, "mn": 1_000_000,
    "thousand": 1_000, "k": 1_000,
}
_NUMBER_RE = re.compile(
    r"(?:[₹$€£]\s*)?([\d,]+(?:\.\d+)?)\s*(crore|crores|cr|lakh|lakhs|lac|lacs|billion|bn|million|mn|thousand|k)?\b",
    re.IGNORECASE,
)


def _extract_scaled_numbers(text: str) -> List[float]:
    values = []
    for m in _NUMBER_RE.finditer(text or ""):
        raw_num, scale_word = m.group(1), m.group(2)
        try:
            num = float(raw_num.replace(",", ""))
        except ValueError:
            continue
        if num == 0:
            continue
        multiplier = _SCALE_WORDS.get((scale_word or "").lower(), 1)
        values.append(num * multiplier)
    return values


def is_context_conflict_plausible(finding: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """Returns (plausible, reject_reason).

    Only evaluates findings in the three context-sensitive categories;
    everything else passes through unconditionally (plausible=True,
    reason=None). A finding is rejected as a likely false positive if its
    own evidence items reference clearly different reporting periods, or if
    their numeric values are equivalent once standard unit-scale
    conversions are applied.
    """
    category = finding.get("category") or finding.get("business_category")
    if category not in _CONTEXT_SENSITIVE_CATEGORIES:
        return True, None

    evidence_items: List[Dict[str, Any]] = list(finding.get("evidence") or [])
    quotes = [str(ev.get("quote") or "") for ev in evidence_items if ev.get("quote")]
    if len(quotes) < 2:
        # Nothing to cross-check between -- can't determine a false positive
        # from context alone, so let it through to LLM/grounding judgment.
        return True, None

    # 1. Different reporting periods referenced across evidence items.
    period_sets = [p for p in (_extract_periods(q) for q in quotes) if p]
    if len(period_sets) >= 2:
        common = set.intersection(*period_sets)
        if not common:
            return False, (
                "evidence items reference different reporting periods/dates "
                f"({[sorted(p) for p in period_sets]}) -- likely a legitimate "
                "period-over-period difference, not a conflict"
            )

    # 2. Numerically equivalent once unit/scale is normalized.
    all_values = []
    for q in quotes:
        all_values.extend(_extract_scaled_numbers(q))
    if len(all_values) >= 2:
        hi, lo = max(all_values), min(v for v in all_values if v > 0) if any(v > 0 for v in all_values) else 0
        if lo > 0:
            ratio = hi / lo
            if abs(ratio - 1.0) <= 0.02:
                return False, (
                    f"values ({lo:g} vs {hi:g}) are numerically equivalent within "
                    "2% once unit/scale conversion is applied -- not a real conflict"
                )

    return True, None
