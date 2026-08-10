"""
ambiguity_grounding_gate.py
==============================
Programmatic evidence-grounding gate for Ambiguity Analysis findings.

The audit found that grounding for cross-chunk/cross-object findings rested
entirely on two successive LLM self-reports (the analysis call, then the
verification call) -- CitationValidator only checked that a cited chunk_id
existed, never that the quoted evidence text was real. This module adds the
missing programmatic check: every finding must cite at least one chunk_id
whose real, source text actually contains the quoted evidence (normalized
substring match) before it can be accepted. An LLM claiming a quote that
does not exist in the cited chunk is rejected here, unconditionally.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

_WS_RE = re.compile(r"\s+")


def _normalize(text: str) -> str:
    return _WS_RE.sub(" ", (text or "").strip()).lower()


def _quote_found_in_chunk(quote: str, chunk_text: str) -> bool:
    quote_n = _normalize(quote)
    chunk_n = _normalize(chunk_text)
    if not quote_n or not chunk_n:
        return False
    if quote_n in chunk_n:
        return True
    # Tolerate minor punctuation/quote-character drift (curly vs straight
    # quotes, trailing ellipses) by also checking the quote with leading/
    # trailing non-alphanumeric characters stripped.
    stripped = quote_n.strip(" .,;:'\"“”‘’…-")
    return bool(stripped) and stripped in chunk_n


def verify_evidence(
    finding: Dict[str, Any], chunk_map: Dict[str, Dict[str, Any]]
) -> Tuple[bool, Optional[str]]:
    """Returns (grounded, reject_reason).

    A finding is grounded only if it cites at least one evidence item whose
    quote is a real (normalized) substring of the actual text of the chunk
    it claims to come from. Evidence is gathered from the finding's
    `evidence` list (each `{chunk_id, quote}`), falling back to the
    finding's own top-level `chunk_id` + `highlighted_ambiguity`/
    `original_chunk` fields when no evidence list is present.
    """
    evidence_items: List[Dict[str, Any]] = list(finding.get("evidence") or [])

    if not evidence_items:
        fallback_chunk_id = finding.get("chunk_id")
        fallback_quote = finding.get("highlighted_ambiguity") or finding.get("quote")
        if fallback_chunk_id and fallback_quote:
            evidence_items = [{"chunk_id": fallback_chunk_id, "quote": fallback_quote}]

    if not evidence_items:
        return False, "no source location/evidence text provided"

    checked_any_valid_chunk = False
    for item in evidence_items:
        chunk_id = item.get("chunk_id")
        quote = item.get("quote")
        if not chunk_id or not quote:
            continue
        chunk_entry = chunk_map.get(chunk_id)
        if not chunk_entry:
            continue
        checked_any_valid_chunk = True
        chunk_text = chunk_entry.get("text") or ""
        if _quote_found_in_chunk(quote, chunk_text):
            return True, None

    if not checked_any_valid_chunk:
        return False, "cited chunk_id(s) not found in document chunk map"
    return False, "evidence quote does not appear verbatim in the cited source chunk"
