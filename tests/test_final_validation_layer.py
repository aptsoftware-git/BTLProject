"""
test_final_validation_layer.py
================================
Regression tests for src/final_validation_layer.py -- the generic final
gate that sits between finding_mapper's output and the canonical
10_final/final_findings.json artifact.

Covers:
  * genuine errors surviving to "accepted"
  * each individual false-positive rule rejecting the right candidate with
    the right machine-readable reason code
  * duplicate / overlapping findings resolving to "merged"
  * every candidate handed to the layer getting exactly one decision
  * count reconciliation across the finding_mapper -> final_validation link
"""

import json

import pytest

from src.final_validation_layer import (
    FinalValidationLayer,
    Reason,
    build_count_reconciliation,
    save_final_findings,
)
from src.utils import save_json


GOOD_SENTENCE = "The company will recieve the shipment next week without delay."


def make_finding(**overrides):
    base = {
        "finding_id": "ERR_0001",
        "sentence_id": "S0001",
        "page_number": 1,
        "error_type": "spelling",
        "severity": "medium",
        "original": "recieve",
        "suggestion": "receive",
        "status": "pending",
        "token_start": 15,
        "token_end": 22,
        "sentence_text": GOOD_SENTENCE,
        "reason": "Spelling correction",
        "confidence": 0.9,
        "quality_score": 90,
        "grounding_verified": True,
        "source_element_id": "elem_1",
        "source_bbox": {"l": 10, "t": 10, "r": 100, "b": 20, "coord_origin": "TOPLEFT"},
        "pdf_grounded": True,
        "bbox": {"x0": 10, "y0": 10, "x1": 100, "y1": 20},
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Genuine errors -> accepted
# ---------------------------------------------------------------------------

def test_genuine_spelling_error_is_accepted():
    layer = FinalValidationLayer()
    accepted, log = layer.run([make_finding()], [])
    assert len(accepted) == 1
    assert log[0]["decision"] == "accepted"
    assert log[0]["reason"] == Reason.OK


def test_genuine_grammar_sva_error_is_accepted():
    layer = FinalValidationLayer()
    finding = make_finding(
        finding_id="ERR_0002",
        error_type="grammar",
        original="are",
        suggestion="is",
        sentence_text="The project team are confident about the revised delivery schedule.",
        token_start=17,
        token_end=20,
        confidence=0.85,
        quality_score=85,
    )
    accepted, log = layer.run([finding], [])
    assert len(accepted) == 1
    assert log[0]["decision"] == "accepted"


def test_upstream_auto_rejected_is_carried_over_not_silently_dropped():
    layer = FinalValidationLayer()
    rejected_upstream = make_finding(finding_id="ERR_0003", auto_reject_reason="out of proofreading scope (category: style)")
    accepted, log = layer.run([], [rejected_upstream])
    assert accepted == []
    assert len(log) == 1
    assert log[0]["decision"] == "rejected"
    assert log[0]["reason"].startswith(Reason.UPSTREAM_REJECTED)


# ---------------------------------------------------------------------------
# False positives -> rejected, each with the expected reason code
# ---------------------------------------------------------------------------

def test_ocr_hyphen_break_artifact_is_rejected():
    layer = FinalValidationLayer()
    finding = make_finding(original="envi-", suggestion="environment", sentence_text="The envi- ronment report covers Q1 operations fully.")
    accepted, log = layer.run([finding], [])
    assert accepted == []
    assert log[0]["reason"] == Reason.OCR_OR_LAYOUT_ARTIFACT


def test_mojibake_artifact_is_rejected():
    layer = FinalValidationLayer()
    finding = make_finding(
        original="donâ€™t",
        suggestion="don't",
        sentence_text="Employees donâ€™t need to submit forms twice this quarter.",
    )
    accepted, log = layer.run([finding], [])
    assert accepted == []
    assert log[0]["reason"] == Reason.OCR_OR_LAYOUT_ARTIFACT


def test_whitespace_artifact_is_rejected():
    layer = FinalValidationLayer()
    finding = make_finding(original="wo  rd", suggestion="word", sentence_text="This is a wo  rd spacing artefact in the extracted text.")
    accepted, log = layer.run([finding], [])
    assert accepted == []
    assert log[0]["reason"] == Reason.WHITESPACE_ARTIFACT


def test_capitalization_from_broken_text_is_rejected():
    layer = FinalValidationLayer()
    # `original` does not occur at the very start of `sentence_text`, so a
    # pure case-only change here indicates the "sentence" is actually a
    # broken/partial slice, not a genuine sentence-start capitalization fix.
    finding = make_finding(
        error_type="grammar",
        original="the",
        suggestion="The",
        sentence_text="Reports indicate that the project remains on schedule for now.",
    )
    accepted, log = layer.run([finding], [])
    assert accepted == []
    assert log[0]["reason"] == Reason.CAPITALIZATION_FROM_BROKEN_TEXT


def test_uncertain_apostrophe_suggestion_is_rejected_at_low_confidence():
    layer = FinalValidationLayer()
    finding = make_finding(
        error_type="punctuation",
        original="its",
        suggestion="it's",
        sentence_text="The company values its employees and their long term growth.",
        confidence=0.55,
        quality_score=55,
    )
    accepted, log = layer.run([finding], [])
    assert accepted == []
    assert log[0]["reason"] == Reason.UNCERTAIN_APOSTROPHE_SUGGESTION


def test_uncertain_apostrophe_suggestion_accepted_at_high_confidence():
    layer = FinalValidationLayer()
    finding = make_finding(
        error_type="punctuation",
        original="its",
        suggestion="it's",
        sentence_text="The company values its employees and their long term growth.",
        confidence=0.95,
        quality_score=95,
    )
    accepted, log = layer.run([finding], [])
    assert len(accepted) == 1


def test_protected_entity_is_rejected():
    layer = FinalValidationLayer()
    finding = make_finding(
        original="Fichtner",
        suggestion="Fitchner",
        sentence_text="Fichtner served as the independent engineer for the project.",
    )
    accepted, log = layer.run([finding], [])
    assert accepted == []
    assert log[0]["reason"].startswith(Reason.PROTECTED_ENTITY_OR_TERM)


def test_british_american_variant_rejected_when_standard_is_both():
    layer = FinalValidationLayer(spelling_standard="both")
    finding = make_finding(
        original="colour",
        suggestion="color",
        sentence_text="The brochure uses colour schemes consistent with the brand guide.",
    )
    accepted, log = layer.run([finding], [])
    assert accepted == []
    assert log[0]["reason"].startswith(Reason.LANGUAGE_VARIANT_INCONSISTENT)


def test_british_american_variant_accepted_when_standard_allows_direction():
    layer = FinalValidationLayer(spelling_standard="en-US")
    finding = make_finding(
        original="colour",
        suggestion="color",
        sentence_text="The brochure uses colour schemes consistent with the brand guide.",
    )
    accepted, log = layer.run([finding], [])
    assert len(accepted) == 1


def test_no_pdf_or_source_evidence_is_rejected():
    layer = FinalValidationLayer()
    finding = make_finding(grounding_verified=False, pdf_grounded=False, source_bbox=None, bbox=None)
    accepted, log = layer.run([finding], [])
    assert accepted == []
    assert log[0]["reason"] == Reason.NO_PDF_OR_SOURCE_EVIDENCE


def test_low_confidence_evidence_is_rejected():
    layer = FinalValidationLayer(min_confidence=0.5)
    finding = make_finding(confidence=0.2, quality_score=20)
    accepted, log = layer.run([finding], [])
    assert accepted == []
    assert log[0]["reason"] == Reason.LOW_CONFIDENCE_EVIDENCE


def test_no_sentence_context_is_rejected():
    layer = FinalValidationLayer()
    finding = make_finding(sentence_text="")
    accepted, log = layer.run([finding], [])
    assert accepted == []
    assert log[0]["reason"] == Reason.NO_SENTENCE_CONTEXT


def test_broken_sentence_boundary_is_rejected():
    layer = FinalValidationLayer()
    finding = make_finding(original="-item", suggestion="item", sentence_text="-item continues from previous bullet fragment")
    accepted, log = layer.run([finding], [])
    assert accepted == []
    assert log[0]["reason"] == Reason.BROKEN_SENTENCE_BOUNDARY


# ---------------------------------------------------------------------------
# Duplicate / overlap resolution -> merged
# ---------------------------------------------------------------------------

def test_exact_duplicate_finding_is_merged_not_dropped_silently():
    layer = FinalValidationLayer()
    first = make_finding(finding_id="ERR_0001")
    duplicate = make_finding(finding_id="ERR_0001_dup")
    accepted, log = layer.run([first, duplicate], [])
    assert len(accepted) == 1
    assert accepted[0]["finding_id"] == "ERR_0001"
    decisions = {d["finding_id"]: d for d in log}
    assert decisions["ERR_0001_dup"]["decision"] == "merged"
    assert decisions["ERR_0001_dup"]["reason"] == f"{Reason.DUPLICATE_FINDING}:ERR_0001"


def test_overlapping_span_finding_is_merged():
    layer = FinalValidationLayer()
    first = make_finding(finding_id="ERR_0010", original="recieve", suggestion="receive", token_start=15, token_end=22)
    overlapping = make_finding(
        finding_id="ERR_0011",
        original="recieved",
        suggestion="received",
        token_start=15,
        token_end=24,
    )
    accepted, log = layer.run([first, overlapping], [])
    assert len(accepted) == 1
    decisions = {d["finding_id"]: d for d in log}
    assert decisions["ERR_0011"]["decision"] == "merged"
    assert decisions["ERR_0011"]["reason"].startswith(Reason.OVERLAPPING_FINDING)


def test_every_candidate_gets_exactly_one_decision():
    layer = FinalValidationLayer()
    findings = [
        make_finding(finding_id="ERR_0001"),
        make_finding(finding_id="ERR_0002", original="colour", suggestion="color", sentence_text="The colour palette follows brand guidelines closely."),
    ]
    auto_rejected = [make_finding(finding_id="ERR_0099", auto_reject_reason="out of proofreading scope (category: style)")]
    accepted, log = layer.run(findings, auto_rejected)
    seen_ids = {d["finding_id"] for d in log}
    assert seen_ids == {"ERR_0001", "ERR_0002", "ERR_0099"}
    assert all(d["decision"] in ("accepted", "rejected", "merged") for d in log)
    assert len(log) == len(findings) + len(auto_rejected)


# ---------------------------------------------------------------------------
# Count reconciliation
# ---------------------------------------------------------------------------

def test_count_reconciliation_passes_on_consistent_job_dir(tmp_path):
    job_dir = tmp_path / "job"
    final_dir = job_dir / "10_final"
    final_dir.mkdir(parents=True)

    report_issues = [{"sentence_id": i} for i in range(5)]
    save_json({"issues": report_issues}, final_dir / "report.json")

    mapped = [make_finding(finding_id=f"ERR_{i:04d}") for i in range(3)]
    auto_rejected = [make_finding(finding_id=f"ERR_{i:04d}", auto_reject_reason="x") for i in range(3, 5)]
    save_json(mapped, final_dir / "mapped_findings.json")
    save_json(auto_rejected, final_dir / "auto_rejected_findings.json")

    layer = FinalValidationLayer()
    accepted, log = layer.run(mapped, auto_rejected)
    save_final_findings(accepted, log, final_dir)

    result = build_count_reconciliation(job_dir)
    assert result["is_reconciled"] is True
    for check in result["checks"]:
        assert check["passed"], check


def test_count_reconciliation_flags_mismatch(tmp_path):
    job_dir = tmp_path / "job"
    final_dir = job_dir / "10_final"
    final_dir.mkdir(parents=True)

    save_json({"issues": [{"sentence_id": i} for i in range(5)]}, final_dir / "report.json")
    # Deliberately inconsistent: mapping claims only 2 total candidates, not 5.
    save_json([make_finding(finding_id="ERR_0000")], final_dir / "mapped_findings.json")
    save_json([make_finding(finding_id="ERR_0001", auto_reject_reason="x")], final_dir / "auto_rejected_findings.json")

    result = build_count_reconciliation(job_dir)
    assert result["is_reconciled"] is False
    mismatch = next(c for c in result["checks"] if c["name"] == "mapping_accounts_for_all_report_issues")
    assert mismatch["passed"] is False
