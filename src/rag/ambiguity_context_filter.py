"""
ambiguity_context_filter.py
==============================
Deterministic context-awareness guard and programmatic ambiguity validator
for Ambiguity Analysis findings.

Enforces:
1. Rejection of false positive numerical/unit/date conflicts caused by reporting period differences or unit conversions.
2. Rejection of standalone factual statements (e.g., "Operating segments include Engineering...") that lack a genuine conflicting interpretation.
3. Rejection of boilerplate headings, titles, contact info, standalone section titles.
4. Rejection of style advice, writing criticism, grammar suggestions, subjective rewrites, and placeholder text leakage.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

_CONTEXT_SENSITIVE_CATEGORIES = frozenset({
    "Numerical inconsistency",
    "Date / timeline inconsistency",
    "Unit / measurement inconsistency",
})

# Matches FY2023, FY 23, FY-2024, 2023-24, Q1 2024, Q3FY23, or a bare 4-digit year
_PERIOD_RE = re.compile(
    r"\bFY[\s-]?(\d{2,4})\b"
    r"|\bQ[1-4][\s-]?(?:FY)?[\s-]?(\d{2,4})\b"
    r"|\b((?:19|20)\d{2})[\s/-]((?:19|20)?\d{2})\b"
    r"|\b((?:19|20)\d{2})\b",
    re.IGNORECASE,
)

# Scale words/abbreviations -> multiplier
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

# Patterns for boilerplate headings, section titles, contact info
BOILERPLATE_PATTERNS = {
    "OUR VISION", "OUR MISSION", "VISION", "MISSION", "PROJECTS", "OVERVIEW",
    "STRENGTHS", "CONTENT", "DOCUMENT", "SECTION", "OUR HERITAGE", "TABLE OF CONTENTS",
    "CONTENTS PAGE", "INDEX PAGE", "CHAIRMAN'S MESSAGE", "CORPORATE PHILOSOPHY",
    "ACKNOWLEDGEMENTS", "FORWARD LOOKING STATEMENTS", "COMPANY PROFILE", "CONTACT",
    "CONTACT US", "INDUSTRY", "HEADQUARTERS", "BOARD & KEY LEADERSHIP",
    "BOARD AND KEY LEADERSHIP", "KEY LEADERSHIP", "WEBSITE", "EMAIL", "ADDRESS",
    "ABOUT US", "EXECUTIVE SUMMARY", "INTRODUCTION", "FINANCIAL PERFORMANCE",
    "SERVICES", "PRODUCTS", "LEADERSHIP", "MANAGEMENT", "CORPORATE INFORMATION",
    "REGISTERED OFFICE", "FINANCIAL ASSETS", "NET DEBT", "TOTAL EQUITY", "SENSITIVITY ANALYSIS",
    "FIXED RATE INSTRUMENTS", "VARIABLE RATE INSTRUMENTS", "OUR GOVERNANCE COMMITMENT",
    "EDUCATION AND SKILL DEVELOPMENT", "GROWTH", "TABLE 1", "APPENDIX"
}

# Style criticism & prompt leakage terms
STYLE_CRITICISM_TERMS = [
    "rephrase", "rephrased", "passive voice", "grammatical", "spelling typo",
    "stylistic choice", "writing quality", "readability suggestion", "purely stylistic",
    "subjective preference", "undefined term", "vague wording", "vague qualifier"
]

PLACEHOLDER_LEAKAGE_TERMS = [
    "chunk analysis", "sample content", "placeholder", "lorem ipsum",
    "unrelated to the provided text", "from the given text", "claims made in this chunk",
    "no direct evidence", "the claims and entities"
]


def _normalize_year(raw: str) -> str:
    raw = raw.strip()
    if len(raw) == 2:
        return "20" + raw
    return raw[-4:] if len(raw) > 4 else raw


def _extract_periods(text: str) -> set:
    periods = set()
    for m in _PERIOD_RE.finditer(text or ""):
        for g in m.groups():
            if g:
                periods.add(_normalize_year(g))
    return periods


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

    Rejects false positive numerical/unit/date conflicts caused by reporting period
    differences or unit-scale conversions.
    """
    category = finding.get("category") or finding.get("business_category")
    if category not in _CONTEXT_SENSITIVE_CATEGORIES:
        return True, None

    evidence_items: List[Dict[str, Any]] = list(finding.get("evidence") or [])
    quotes = [str(ev.get("quote") or "") for ev in evidence_items if ev.get("quote")]
    if len(quotes) < 2:
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


def is_evidence_relevant_to_claim(finding: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """Checks if cited evidence items are topically relevant to the claim/title of the finding.

    Rejects mismatched findings where evidence quotes belong to a completely different topic
    (e.g., claim about Management/Audit Committee, but evidence quotes talk about Foreign Exchange / Interest Rate Risk).
    """
    title = (finding.get("title") or "").lower()
    explanation = (finding.get("claude_explanation") or finding.get("reason") or finding.get("explanation") or "").lower()
    evidence_items = list(finding.get("evidence") or [])

    if not evidence_items or not title:
        return True, None

    claim_text = f"{title} {explanation}"

    # Extract key domain nouns (> 3 chars, excluding generic stop words)
    words = re.findall(r"\b[a-z]{4,}\b", claim_text)
    stop_words = {
        "this", "that", "with", "from", "have", "been", "where", "which", "there", "their", "about",
        "would", "could", "should", "section", "document", "finding", "report", "issue", "conflict",
        "contradiction", "inconsistency", "mismatch", "between", "statement", "passage", "text"
    }
    subject_keywords = set(w for w in words if w not in stop_words)

    if not subject_keywords:
        return True, None

    # Check if at least one evidence quote contains at least one subject keyword
    relevant_count = 0
    for ev in evidence_items:
        q = str(ev.get("quote") or "").lower()
        if not q:
            continue
        if any(kw in q for kw in subject_keywords):
            relevant_count += 1

    if evidence_items and relevant_count == 0:
        return False, (
            f"mismatched evidence: cited quotes do not relate to claim subject '{title}'"
        )

    return True, None


def is_genuine_ambiguity(finding: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """Evaluates if a candidate finding represents a genuine document ambiguity.

    Enforces:
    - Pronoun / entity-reference ambiguity single-quote retention.
    - Terminology inconsistency validation (requires same entity/concept context).
    - Mismatched evidence rejection.
    - Rejection of style advice, writing criticism, boilerplate headings, prompt leakage.
    """
    if not isinstance(finding, dict):
        return False, "invalid finding object structure"

    category = finding.get("category") or finding.get("business_category") or ""
    quote = (finding.get("highlighted_ambiguity") or finding.get("quote") or finding.get("suspected_text") or "").strip()
    title = (finding.get("title") or "").strip()
    explanation = (finding.get("claude_explanation") or finding.get("reason") or finding.get("explanation") or "").strip()
    section = (finding.get("section_heading") or finding.get("section") or "").strip()

    full_text = f"{title} {quote} {explanation} {section}".lower()

    # 1. Placeholder & system leakage check
    if any(p in full_text for p in PLACEHOLDER_LEAKAGE_TERMS):
        return False, "finding contains internal prompt leakage or placeholder text"

    # 2. Style advice & writing criticism check
    if any(s in full_text for s in STYLE_CRITICISM_TERMS):
        return False, "finding represents writing style advice, grammar preference, or subjective rewrite, not a document ambiguity"

    # 3. Boilerplate heading & title check
    q_clean = quote.upper()
    t_clean = title.upper()
    if q_clean in BOILERPLATE_PATTERNS or t_clean in BOILERPLATE_PATTERNS:
        return False, "boilerplate heading, section title, or standalone label cannot be flagged as an ambiguity"

    # 4. Mismatched evidence check
    rel_ok, rel_reason = is_evidence_relevant_to_claim(finding)
    if not rel_ok:
        return False, rel_reason

    # 5. Pronoun / Entity-reference ambiguity validation (single-quote valid)
    if category == "Pronoun / entity-reference ambiguity":
        pronoun_terms = ["he", "she", "they", "it", "his", "her", "herself", "himself", "itself", "themselves", "this", "these", "entity", "pronoun", "antecedent", "referent", "mismatch", "gender"]
        if any(p in full_text for p in pronoun_terms):
            return True, None

    # 6. Terminology inconsistency validation (requires same entity/concept context)
    if category == "Terminology inconsistency":
        term_context_kw = ["same", "concept", "entity", "naming", "variant", "refer", "inconsistent", "differs", "varies", "across"]
        if not any(kw in full_text for kw in term_context_kw):
            return False, "terminology difference lacks contextual evidence that terms refer to the same entity/concept"

    # 7. Standalone factual statement check
    evidence_items = list(finding.get("evidence") or [])
    has_conflict_keywords = any(
        kw in full_text for kw in [
            "conflict", "contradict", "mismatch", "inconsist", "differ", "discrepancy",
            "unclear", "ambiguous", "opposite", "varies", "clash", "versus", "vs",
            "vague", "missing", "lack", "omitted", "absence", "no defined", "timeline",
            "error", "incorrect", "wrong", "incongruity"
        ]
    )

    if len(evidence_items) <= 1 and not has_conflict_keywords:
        return False, (
            "factual statement alone is not an ambiguity; requires conflicting evidence "
            "or an explicit inconsistency between document passages"
        )

    return True, None
