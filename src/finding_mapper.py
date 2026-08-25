"""
finding_mapper.py
===================
Enriches the (untouched) report_generator output — 10_final/report.json —
with sentence_id / word-level highlight offsets, producing the finding
contract the review UI consumes:

  {finding_id, sentence_id, error_type, severity, original, suggestion,
   status, page_number, token_start, token_end, quality_score,
   source_element_id, source_bbox}

source_element_id/source_bbox are the Docling provenance anchor (copied
from the sentence lookup entry) that src/pdf_bbox_resolver.py uses to
resolve a real, region-scoped PDF bounding box -- this module itself never
computes or guesses PDF coordinates.

This module is purely additive and read-only with respect to how issues
are detected, validated or merged: it never re-derives a finding, it only
reshapes what report_generator already produced (Spell/Grammar/Validation
Agents and report_generator.py itself remain untouched).

It DOES add a second, independent quality gate on top of what already
passed ValidationAgent — findings that only swap a valid regional spelling
variant, that overlap a protected term ValidationAgent's char-offset check
happened to miss, or that operate on a dash/fragment artifact instead of
real sentence content, are rejected here before they ever reach the UI.
Rejected findings are kept in a companion file (not surfaced to the review
UI) purely for debugging/audit purposes.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.sentence_mapper import sentence_id_str
from src.spelling_standards import classify_variant_direction, should_reject_for_spelling_standard
from src.utils import save_json

# A "fragment" is content that isn't a real sentence/list-item: leftover
# punctuation glued to a word (extraction artifact, see page_text_builder's
# dash normalization), or too little actual text to carry meaning.
_FRAGMENT_LEADING_PUNCT_RE = re.compile(r"^[\-–—•·*]")
_HAS_LETTERS_RE = re.compile(r"[A-Za-z]{2,}")

# Only mechanical proofreading categories reach the review UI (spelling,
# grammar/tense agreement, punctuation). "style" (and anything else the
# agents might ever emit) is a wording/tone preference, not a mechanical
# error, and is explicitly out of scope for this tab -- see src/models.py
# IssueType for the full enum grammar_agent/spell_agent draw from.
_APPROVED_PROOFREADING_CATEGORIES = {"spelling", "grammar", "tense", "punctuation"}


def _looks_like_fragment(original: str, sentence_text: str) -> bool:
    original = (original or "").strip()
    sentence_text = (sentence_text or "").strip()

    if _FRAGMENT_LEADING_PUNCT_RE.match(original):
        return True
    if not _HAS_LETTERS_RE.search(sentence_text):
        return True
    # A "sentence" with fewer than 3 words is rarely enough context to
    # safely judge a spelling/grammar correction against.
    word_count = len(re.findall(r"[A-Za-z]+", sentence_text))
    if word_count < 3:
        return True
    return False


def _overlaps_protected_term(char_start: Optional[int], char_end: Optional[int],
                              protected_terms: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if char_start is None or char_end is None:
        return None
    for term in protected_terms:
        t_start, t_end = term.get("char_start"), term.get("char_end")
        if t_start is None or t_end is None:
            continue
        if char_start < t_end and char_end > t_start:
            return term
    return None


def _compute_quality_score(
    confidence: Optional[float],
    is_protected_hit: bool,
    is_regional_variant: bool,
    is_fragment: bool,
    agreement_count: int,
) -> int:
    """0-100 composite score. Findings that fail a hard gate never reach this
    (score is only informational for what *does* pass), but is still useful
    signal for the UI to sort/prioritize by."""
    score = 50.0
    if isinstance(confidence, (int, float)):
        conf = confidence if confidence <= 1.0 else confidence / 100.0
        score = conf * 100.0
    if agreement_count and agreement_count > 1:
        score += min(15, (agreement_count - 1) * 7)
    if is_protected_hit:
        score -= 40
    if is_regional_variant:
        score -= 40
    if is_fragment:
        score -= 30
    return max(0, min(100, round(score)))


from src.false_positive_rejection import FalsePositiveRejectionLayer


def build_findings(
    report_issues: List[Dict[str, Any]],
    lookup_index: Dict[str, Any],
    decisions: Optional[Dict[str, str]] = None,
    protected_terms: Optional[List[Dict[str, Any]]] = None,
    spelling_standard: str = "both",
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Returns (findings, auto_rejected). `findings` is what the review UI sees."""
    decisions = decisions or {}
    protected_terms = protected_terms or []
    findings: List[Dict[str, Any]] = []
    auto_rejected: List[Dict[str, Any]] = []
    rejection_layer = FalsePositiveRejectionLayer(protected_terms, spelling_standard=spelling_standard)

    for idx, issue in enumerate(report_issues):
        finding_id = f"ERR_{idx + 1:04d}"

        numeric_sentence_id = issue.get("sentence_id")
        sid = None
        if numeric_sentence_id is not None:
            try:
                sid = sentence_id_str(int(numeric_sentence_id))
            except (TypeError, ValueError):
                sid = None

        sentence_entry = (lookup_index.get(sid) or lookup_index.get(str(numeric_sentence_id))) if (sid or numeric_sentence_id is not None) else None
        sentence_text = (sentence_entry or {}).get("text") or issue.get("sentence_text") or ""
        page_number = (
            (sentence_entry or {}).get("page_number")
            or issue.get("page_number")
            or issue.get("page")
            or 1
        )
        source_element_id = (sentence_entry or {}).get("source_element_id")
        source_bbox = (sentence_entry or {}).get("source_bbox")

        original = issue.get("original_text") or issue.get("highlighted_text") or ""
        suggestion = issue.get("suggested_text") or issue.get("suggested_replacement") or ""

        token_start: Optional[int] = None
        token_end: Optional[int] = None
        if original and sentence_text:
            pos = sentence_text.find(original)
            if pos != -1:
                token_start, token_end = pos, pos + len(original)

        sentence_id_resolved = sid is not None or numeric_sentence_id is not None
        sentence_found_in_map = sentence_entry is not None or bool(sentence_text)
        page_number_valid = isinstance(page_number, (int, float)) and int(page_number) > 0
        original_found_in_sentence = bool(original) and bool(sentence_text) and original in sentence_text
        token_offsets_valid = (
            token_start is not None
            and token_end is not None
            and 0 <= token_start < token_end <= len(sentence_text)
        )
        grounding_verified = (
            sentence_id_resolved
            and sentence_found_in_map
            and page_number_valid
            and original_found_in_sentence
            and token_offsets_valid
        )

        status = decisions.get(finding_id) or decisions.get(str(idx + 1)) or decisions.get(str(idx)) or "pending"

        issue_type = issue.get("issue_type") or issue.get("category") or "grammar"
        if hasattr(issue_type, "value"):
            issue_type = issue_type.value

        confidence = issue.get("final_confidence")
        if not isinstance(confidence, (int, float)):
            confidence = issue.get("confidence")
        agreement_count = issue.get("agreement_count") or 1

        category = str(issue_type).lower()
        category_approved = category in _APPROVED_PROOFREADING_CATEGORIES

        # --- Quality gate: FalsePositiveRejectionLayer ---
        is_fp_rejected, fp_reject_reason, quality_score = rejection_layer.evaluate_candidate(
            original=original,
            suggestion=suggestion,
            sentence_text=sentence_text,
            issue_type=category,
            source=str(issue.get("source", "gramformer")),
            confidence=confidence,
            char_start=issue.get("char_start"),
            char_end=issue.get("char_end"),
        )

        gate_reject_reason = None
        if not category_approved:
            gate_reject_reason = f"out of proofreading scope (category: {category})"
        elif is_fp_rejected:
            gate_reject_reason = fp_reject_reason
        elif not grounding_verified:
            gate_reject_reason = "ungrounded sentence/page provenance"

        finding = {
            "finding_id": finding_id,
            "sentence_id": sid,
            "page_number": int(page_number),
            "error_type": category,
            "severity": issue.get("severity") or "medium",
            "original": original,
            "suggestion": suggestion,
            "status": status,
            "token_start": token_start,
            "token_end": token_end,
            "sentence_text": sentence_text,
            "reason": issue.get("reason") or issue.get("explanation") or "",
            "confidence": confidence,
            "quality_score": quality_score,
            "grounding_verified": grounding_verified,
            "source_element_id": source_element_id,
            "source_bbox": source_bbox,
        }

        if gate_reject_reason:
            finding["auto_reject_reason"] = gate_reject_reason
            auto_rejected.append(finding)
        else:
            findings.append(finding)

    return findings, auto_rejected


def save_findings(findings: List[Dict[str, Any]], output_path: Path) -> Path:
    save_json(findings, output_path)
    return output_path
