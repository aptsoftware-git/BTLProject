"""
final_validation_layer.py
==========================
Generic Final Validation Layer -- the last gate before a finding reaches
the UI/API.

Sits directly after finding_mapper.build_findings() (mapping + the first
false-positive gate + PDF bbox resolution have already run) and
independently re-examines EVERY finding it is handed -- both the ones
finding_mapper accepted so far and the ones it already auto-rejected.
Passing an earlier stage's filter is never treated as automatic
acceptance here: each finding is re-scored from scratch against a fixed
set of generic checks (sentence/context evidence, PDF/source-text
evidence, broken sentence boundaries, OCR/layout/whitespace artefacts,
protected entities/terms, duplicate/overlapping findings, British vs
American spelling consistency, confidence & evidence quality).

Every candidate that passes through this layer ends with exactly one
decision -- "accepted" | "rejected" | "merged" -- plus a stable,
machine-readable reason code. The full per-candidate log
(`run()`'s second return value) is the audit trail; `run()`'s first
return value (`accepted`) is the only data that should ever reach the
canonical final-findings artifact (10_final/final_findings.json).

Nothing downstream (mapping counts, the /findings API, or the review UI)
should read 10_final/mapped_findings.json directly once this layer has
produced 10_final/final_findings.json -- see stage_orchestrator.py's end
of Stage 4 and backend/routes.py's `_findings_with_live_status`.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.false_positive_rejection import FalsePositiveRejectionLayer
from src.spelling_standards import classify_variant_direction, should_reject_for_spelling_standard
from src.utils import load_json, save_json


# ---------------------------------------------------------------------------
# Reason codes -- stable strings so tests/tooling can match on them without
# parsing prose. Rejection/merge reasons are prefixed with a fixed code and
# may carry a ":"-separated detail (e.g. the upstream reason, or the id of
# the finding a duplicate was merged into).
# ---------------------------------------------------------------------------
class Reason:
    OK = "OK"
    UPSTREAM_REJECTED = "UPSTREAM_REJECTED"
    NO_EVIDENCE_ORIGINAL_OR_SUGGESTION = "NO_EVIDENCE_ORIGINAL_OR_SUGGESTION"
    NO_SENTENCE_CONTEXT = "NO_SENTENCE_CONTEXT"
    BROKEN_SENTENCE_BOUNDARY = "BROKEN_SENTENCE_BOUNDARY"
    OCR_OR_LAYOUT_ARTIFACT = "OCR_OR_LAYOUT_ARTIFACT"
    WHITESPACE_ARTIFACT = "WHITESPACE_ARTIFACT"
    PROTECTED_ENTITY_OR_TERM = "PROTECTED_ENTITY_OR_TERM"
    LANGUAGE_VARIANT_INCONSISTENT = "LANGUAGE_VARIANT_INCONSISTENT"
    UNCERTAIN_APOSTROPHE_SUGGESTION = "UNCERTAIN_APOSTROPHE_SUGGESTION"
    CAPITALIZATION_FROM_BROKEN_TEXT = "CAPITALIZATION_FROM_BROKEN_TEXT"
    NO_PDF_OR_SOURCE_EVIDENCE = "NO_PDF_OR_SOURCE_EVIDENCE"
    LOW_CONFIDENCE_EVIDENCE = "LOW_CONFIDENCE_EVIDENCE"
    DUPLICATE_FINDING = "DUPLICATE_FINDING"
    OVERLAPPING_FINDING = "OVERLAPPING_FINDING"


_APOSTROPHE_CHARS = "'’ʼ`"
_CONTROL_ARTIFACT_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f�]")
# Mojibake left behind by a UTF-8 file mis-decoded as Latin-1/CP1252
# (typical OCR/PDF-extraction artefact), e.g. "donâ€™t" or "Ã©cole".
_MOJIBAKE_RE = re.compile(r"[ÃÂ][€™¦¢œ]|â€[™œ¦]")
_MULTI_WS_RE = re.compile(r"\s{2,}")
# Trailing hyphenation break left by column/line-wrap extraction, e.g. "envi-"
_HYPHEN_BREAK_RE = re.compile(r"[A-Za-z]-\s*$")
_LEADING_FRAGMENT_RE = re.compile(r"^[\-–—•·*»«]")
_LETTERS_RE = re.compile(r"[A-Za-z]{2,}")

DEFAULT_MIN_CONFIDENCE = 0.5
DEFAULT_MIN_QUALITY = 40
DEFAULT_MIN_APOSTROPHE_CONFIDENCE = 0.85


def _norm_conf(value: Optional[float]) -> Optional[float]:
    if not isinstance(value, (int, float)):
        return None
    return value / 100.0 if value > 1.0 else float(value)


def _looks_like_ocr_or_layout_artifact(original: str, suggestion: str, sentence_text: str) -> bool:
    combined = f"{original} {suggestion} {sentence_text}"
    if _CONTROL_ARTIFACT_RE.search(combined):
        return True
    if _MOJIBAKE_RE.search(combined):
        return True
    if _HYPHEN_BREAK_RE.search(original or ""):
        return True
    stripped = (original or "").strip()
    if stripped and len(stripped) <= 1 and not stripped.isalpha():
        return True
    return False


def _has_whitespace_artifact(original: str, suggestion: str) -> bool:
    if _MULTI_WS_RE.search(original or "") or _MULTI_WS_RE.search(suggestion or ""):
        return True
    if (original or "") != (original or "").strip():
        return True
    if (suggestion or "") != (suggestion or "").strip():
        return True
    return False


def _is_apostrophe_only_change(original: str, suggestion: str) -> bool:
    def strip_apos(s: str) -> str:
        return "".join(c for c in s if c not in _APOSTROPHE_CHARS)

    o, s = (original or "").lower(), (suggestion or "").lower()
    if not o or not s or o == s:
        return False
    has_apostrophe = any(c in _APOSTROPHE_CHARS for c in o) or any(c in _APOSTROPHE_CHARS for c in s)
    return has_apostrophe and strip_apos(o) == strip_apos(s)


def _is_capitalization_only(original: str, suggestion: str) -> bool:
    return bool(original) and bool(suggestion) and original != suggestion and original.lower() == suggestion.lower()


def _broken_sentence_boundary(original: str, sentence_text: str) -> bool:
    original = (original or "").strip()
    sentence_text = (sentence_text or "").strip()

    if _LEADING_FRAGMENT_RE.match(original):
        return True
    if not _LETTERS_RE.search(sentence_text):
        return True
    if len(re.findall(r"[A-Za-z]+", sentence_text)) < 3:
        return True
    # A sentence that doesn't open on an uppercase letter, a digit, or
    # punctuation is very likely a slice of a larger sentence carved out by
    # a broken split (extraction artefact), not a real sentence boundary.
    first = sentence_text[0]
    if first.isalpha() and not first.isupper():
        return True
    return False


def _finding_key(finding: Dict[str, Any]) -> Tuple[Any, str, str]:
    return (
        finding.get("sentence_id"),
        (finding.get("original") or "").strip().lower(),
        (finding.get("suggestion") or "").strip().lower(),
    )


def _spans_overlap(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    if a.get("sentence_id") != b.get("sentence_id"):
        return False
    a_s, a_e = a.get("token_start"), a.get("token_end")
    b_s, b_e = b.get("token_start"), b.get("token_end")
    if a_s is None or a_e is None or b_s is None or b_e is None:
        return False
    return a_s < b_e and a_e > b_s


class FinalValidationLayer:
    """Generic last-gate validator. Stateless aside from configured thresholds."""

    def __init__(
        self,
        protected_terms: Optional[List[Dict[str, Any]]] = None,
        spelling_standard: str = "both",
        min_confidence: float = DEFAULT_MIN_CONFIDENCE,
        min_quality: float = DEFAULT_MIN_QUALITY,
        min_apostrophe_confidence: float = DEFAULT_MIN_APOSTROPHE_CONFIDENCE,
    ) -> None:
        self.spelling_standard = spelling_standard
        self.min_confidence = min_confidence
        self.min_quality = min_quality
        self.min_apostrophe_confidence = min_apostrophe_confidence
        self.rejection_layer = FalsePositiveRejectionLayer(protected_terms, spelling_standard=spelling_standard)

    def _evaluate_single(self, finding: Dict[str, Any]) -> Tuple[str, str]:
        """Returns (decision, reason) for one finding, ignoring duplicates/overlaps
        (those are resolved across the whole batch in `run`)."""
        original = finding.get("original") or ""
        suggestion = finding.get("suggestion") or ""
        sentence_text = finding.get("sentence_text") or ""
        confidence = _norm_conf(finding.get("confidence"))
        quality_score = finding.get("quality_score")

        if not original or not suggestion:
            return "rejected", Reason.NO_EVIDENCE_ORIGINAL_OR_SUGGESTION
        if not sentence_text:
            return "rejected", Reason.NO_SENTENCE_CONTEXT
        if _broken_sentence_boundary(original, sentence_text):
            return "rejected", Reason.BROKEN_SENTENCE_BOUNDARY
        if _looks_like_ocr_or_layout_artifact(original, suggestion, sentence_text):
            return "rejected", Reason.OCR_OR_LAYOUT_ARTIFACT
        if _has_whitespace_artifact(original, suggestion):
            return "rejected", Reason.WHITESPACE_ARTIFACT

        entity_reason = self.rejection_layer.is_protected_entity_or_proper_noun(original, suggestion)
        if entity_reason:
            return "rejected", f"{Reason.PROTECTED_ENTITY_OR_TERM}:{entity_reason}"

        if FalsePositiveRejectionLayer.is_british_american_swap(original, suggestion):
            if should_reject_for_spelling_standard(original, suggestion, self.spelling_standard):
                direction = classify_variant_direction(original, suggestion)
                return "rejected", f"{Reason.LANGUAGE_VARIANT_INCONSISTENT}:{direction}"

        if _is_capitalization_only(original, suggestion) and not sentence_text.startswith(original):
            return "rejected", Reason.CAPITALIZATION_FROM_BROKEN_TEXT

        if _is_apostrophe_only_change(original, suggestion):
            conf = confidence if confidence is not None else 0.0
            if conf < self.min_apostrophe_confidence:
                return "rejected", Reason.UNCERTAIN_APOSTROPHE_SUGGESTION

        # Authoritative grounding: either the token was verified against the
        # real PDF page text (pdf_grounded, see src/pdf_bbox_resolver.py) or
        # against the source sentence text (grounding_verified, see
        # src/finding_mapper.py's original_found_in_sentence check). A bare
        # `source_bbox` is only carried-through Docling element provenance
        # (never itself checked against the finding's `original` text) and
        # must never be treated as evidence on its own -- doing so let
        # stale/hallucinated candidates through as long as *some* bbox
        # metadata existed, regardless of whether the reported token was
        # ever actually found anywhere.
        grounding_verified = bool(finding.get("grounding_verified"))
        pdf_grounded = bool(finding.get("pdf_grounded"))
        if not grounding_verified and not pdf_grounded:
            return "rejected", Reason.NO_PDF_OR_SOURCE_EVIDENCE

        if confidence is not None and confidence < self.min_confidence:
            return "rejected", Reason.LOW_CONFIDENCE_EVIDENCE
        if isinstance(quality_score, (int, float)) and quality_score < self.min_quality:
            return "rejected", Reason.LOW_CONFIDENCE_EVIDENCE

        return "accepted", Reason.OK

    def run(
        self,
        findings: List[Dict[str, Any]],
        auto_rejected: Optional[List[Dict[str, Any]]] = None,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        findings      -- candidates finding_mapper.build_findings() accepted so far.
        auto_rejected -- candidates finding_mapper already rejected; re-logged
                          here (decision carried over) so every candidate that
                          ever existed shows up exactly once in the decision log.

        Returns (accepted, decision_log):
          accepted      -- finding dicts with decision == "accepted"; this is
                            the only list that should be written to
                            10_final/final_findings.json.
          decision_log  -- one entry per candidate ever seen by this layer:
                            {finding_id, sentence_id, original, suggestion,
                             error_type, decision, reason, stage}.
        """
        auto_rejected = auto_rejected or []
        decision_log: List[Dict[str, Any]] = []

        def log(f: Dict[str, Any], decision: str, reason: str) -> None:
            decision_log.append({
                "finding_id": f.get("finding_id"),
                "sentence_id": f.get("sentence_id"),
                "original": f.get("original"),
                "suggestion": f.get("suggestion"),
                "error_type": f.get("error_type"),
                "decision": decision,
                "reason": reason,
                "stage": "final_validation",
            })

        for f in auto_rejected:
            log(f, "rejected", f"{Reason.UPSTREAM_REJECTED}:{f.get('auto_reject_reason')}")

        kept: List[Dict[str, Any]] = []
        seen_keys: Dict[Tuple[Any, str, str], Dict[str, Any]] = {}

        for f in findings:
            decision, reason = self._evaluate_single(f)
            if decision != "accepted":
                log(f, decision, reason)
                continue

            key = _finding_key(f)
            duplicate_of = seen_keys.get(key)
            if duplicate_of is not None:
                log(f, "merged", f"{Reason.DUPLICATE_FINDING}:{duplicate_of.get('finding_id')}")
                continue

            overlap_of = next((k for k in kept if _spans_overlap(k, f)), None)
            if overlap_of is not None:
                log(f, "merged", f"{Reason.OVERLAPPING_FINDING}:{overlap_of.get('finding_id')}")
                continue

            seen_keys[key] = f
            kept.append(f)
            log(f, "accepted", Reason.OK)

        return kept, decision_log


def save_final_findings(accepted: List[Dict[str, Any]], decision_log: List[Dict[str, Any]], final_dir: Path) -> None:
    save_json(accepted, final_dir / "final_findings.json")
    save_json(decision_log, final_dir / "final_validation_log.json")


# ---------------------------------------------------------------------------
# Count reconciliation
# ---------------------------------------------------------------------------
def build_count_reconciliation(job_dir: Path) -> Dict[str, Any]:
    """
    Reads every count-relevant artifact this pipeline persists and returns a
    stage-by-stage funnel plus a set of exact-equality checks for the links
    that are structurally guaranteed never to drop a candidate silently.

    Two of the checks below (`mapping_accounts_for_all_report_issues` and
    `final_validation_accounts_for_all_mapped_candidates`) are exact
    invariants: both finding_mapper.build_findings() and
    FinalValidationLayer.run() iterate their *entire* input and place every
    item into exactly one output bucket, so input_count must always equal
    the sum of the output buckets. The earlier stages (spell filter,
    context validation, semantic validation, merge/dedup) are reported as
    an informational funnel: grammar candidates are re-derived by
    Gramformer per targeted sentence rather than filtered 1:1, and
    MergeAgent intentionally *consolidates* multiple raw candidates into
    one finding (not a rejection), so a raw-candidate-count == final-count
    equality does not hold, and is not the correct definition of "nothing
    disappeared" for those stages -- disappearance there is instead
    verified by construction (every stage's own accepted+rejected lists
    are read directly from the same call that produced them).
    """
    final_dir = job_dir / "10_final"

    def count(path: Path) -> Optional[int]:
        if not path.exists():
            return None
        data = load_json(path)
        if isinstance(data, dict) and "issues" in data:
            data = data["issues"]
        return len(data) if isinstance(data, list) else None

    funnel = {
        "raw_spell_candidates": count(job_dir / "06_spell" / "spell_candidates.json"),
        "initial_filter_accepted_spell": count(job_dir / "06_spell" / "filtered_spell_candidates.json"),
        "initial_filter_rejected_spell": count(job_dir / "06_spell" / "rejected_spell_candidates.json"),
        "raw_grammar_candidates_seed": count(job_dir / "07_grammar" / "grammar_candidates.json"),
        "context_validation_accepted": count(job_dir / "08_validation" / "accepted.json"),
        "context_validation_rejected": count(job_dir / "08_validation" / "rejected.json"),
        "semantic_validation_rejected": count(job_dir / "09_semantic" / "semantic_failed.json"),
        "dedup_low_confidence_rejected": count(final_dir / "rejected.json"),
        "final_findings_pre_mapping": count(final_dir / "report.json"),
        "mapping_accepted": count(final_dir / "mapped_findings.json"),
        "mapping_auto_rejected": count(final_dir / "auto_rejected_findings.json"),
    }

    final_findings_count = count(final_dir / "final_findings.json")
    decision_log = load_json(final_dir / "final_validation_log.json") if (final_dir / "final_validation_log.json").exists() else []
    final_rejected_count = sum(1 for d in decision_log if d.get("decision") == "rejected")
    final_merged_count = sum(1 for d in decision_log if d.get("decision") == "merged")
    final_accepted_count = sum(1 for d in decision_log if d.get("decision") == "accepted")

    funnel["final_accepted"] = final_findings_count
    funnel["final_rejected"] = final_rejected_count
    funnel["final_merged"] = final_merged_count

    checks = []

    if funnel["mapping_accepted"] is not None and funnel["mapping_auto_rejected"] is not None and funnel["final_findings_pre_mapping"] is not None:
        lhs = funnel["mapping_accepted"] + funnel["mapping_auto_rejected"]
        checks.append({
            "name": "mapping_accounts_for_all_report_issues",
            "passed": lhs == funnel["final_findings_pre_mapping"],
            "detail": f"mapping_accepted({funnel['mapping_accepted']}) + mapping_auto_rejected({funnel['mapping_auto_rejected']}) == final_findings_pre_mapping({funnel['final_findings_pre_mapping']})",
        })

    if funnel["mapping_accepted"] is not None and funnel["mapping_auto_rejected"] is not None:
        total_into_final_validation = funnel["mapping_accepted"] + funnel["mapping_auto_rejected"]
        total_out = final_accepted_count + final_rejected_count + final_merged_count
        checks.append({
            "name": "final_validation_accounts_for_all_mapped_candidates",
            "passed": total_into_final_validation == total_out,
            "detail": f"mapping output({total_into_final_validation}) == final accepted+rejected+merged({total_out})",
        })

    if funnel["raw_spell_candidates"] is not None and funnel["initial_filter_accepted_spell"] is not None and funnel["initial_filter_rejected_spell"] is not None:
        checks.append({
            "name": "spell_initial_filter_accounts_for_all_raw_spell_candidates",
            "passed": funnel["raw_spell_candidates"] == funnel["initial_filter_accepted_spell"] + funnel["initial_filter_rejected_spell"],
            "detail": f"raw({funnel['raw_spell_candidates']}) == filtered_accepted({funnel['initial_filter_accepted_spell']}) + filtered_rejected({funnel['initial_filter_rejected_spell']})",
        })

    if funnel["context_validation_accepted"] is not None and funnel["context_validation_rejected"] is not None:
        # Not compared against an upstream raw count (Gramformer re-derives
        # grammar candidates per targeted sentence rather than filtering a
        # fixed input 1:1) -- recorded for visibility only, no equality claim.
        pass

    is_reconciled = bool(checks) and all(c["passed"] for c in checks)

    result = {
        "funnel": funnel,
        "checks": checks,
        "is_reconciled": is_reconciled,
    }
    save_json(result, final_dir / "count_reconciliation.json")
    return result
