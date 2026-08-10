"""
test_final_report_generator_gates.py
=======================================
Integration test for FinalReportGenerator.run_generation()'s three hard
rejection gates (category taxonomy, evidence grounding, context-awareness),
wired in per the Ambiguity Analysis architecture change: a finding only
reaches the final report if it is (1) in the approved taxonomy, (2) has
evidence that verifiably exists in its cited source chunk, and (3) is not a
context-driven false positive (different period / equivalent unit).
"""

import json

import pytest

from src.rag.final_report_generator import FinalReportGenerator

CHUNKS = {
    "chunks": [
        {"metadata": {"chunk_id": "c1", "page_number": 3, "heading": "Financials"}, "text": "FY2024 revenue was $50 million."},
        {"metadata": {"chunk_id": "c2", "page_number": 4, "heading": "Financials"}, "text": "FY2024 revenue was $10 million, a shortfall versus target."},
        {"metadata": {"chunk_id": "c3", "page_number": 5, "heading": "Style"}, "text": "The libary was enviroment friendly."},
    ]
}


@pytest.fixture
def job_dir(tmp_path):
    (tmp_path / "14_claude_verification").mkdir(parents=True)
    (tmp_path / "06_chunks").mkdir(parents=True)
    (tmp_path / "06_chunks" / "document_chunks.json").write_text(json.dumps(CHUNKS), encoding="utf-8")
    return tmp_path


def _write_claude_response(job_dir, verified_findings):
    payload = {"overall_document_risk": "Medium", "verified_findings": verified_findings}
    (job_dir / "14_claude_verification" / "claude_response.json").write_text(json.dumps(payload), encoding="utf-8")


def test_grounded_in_taxonomy_finding_is_accepted(job_dir):
    _write_claude_response(job_dir, [{
        "issue_id": "f1", "status": "confirmed", "severity": "High",
        "business_category": "Numerical Inconsistency",
        "chunk_id": "c1", "page": 3, "section": "Financials",
        "original_chunk": "FY2024 revenue was $50 million.",
        "highlighted_ambiguity": "FY2024 revenue was $50 million",
        "reason": "Revenue figures conflict", "confidence": 0.9,
        "evidence": [
            {"chunk_id": "c1", "quote": "FY2024 revenue was $50 million"},
            {"chunk_id": "c2", "quote": "FY2024 revenue was $10 million"},
        ],
    }])

    FinalReportGenerator().run_generation(job_dir, "testdoc", force_regenerate=True)
    result = json.loads((job_dir / "15_final_report" / "final_report.json").read_text(encoding="utf-8"))

    assert len(result["findings"]) == 1
    assert result["findings"][0]["category"] == "Numerical inconsistency"
    assert result["rejected_findings"] == []


def test_grammar_category_finding_is_rejected(job_dir):
    _write_claude_response(job_dir, [{
        "issue_id": "f2", "status": "confirmed", "severity": "Low",
        "business_category": "Grammar Issue",
        "chunk_id": "c3", "page": 5, "section": "Style",
        "original_chunk": "The libary was enviroment friendly.",
        "highlighted_ambiguity": "libary",
        "reason": "Misspelling", "confidence": 0.9,
        "evidence": [{"chunk_id": "c3", "quote": "libary"}],
    }])

    FinalReportGenerator().run_generation(job_dir, "testdoc", force_regenerate=True)
    result = json.loads((job_dir / "15_final_report" / "final_report.json").read_text(encoding="utf-8"))

    assert result["findings"] == []
    assert len(result["rejected_findings"]) == 1
    assert "not in the approved Ambiguity Analysis taxonomy" in result["rejected_findings"][0]["reject_reason"]


def test_hallucinated_evidence_finding_is_rejected(job_dir):
    _write_claude_response(job_dir, [{
        "issue_id": "f3", "status": "confirmed", "severity": "Medium",
        "business_category": "Numerical Inconsistency",
        "chunk_id": "c1", "page": 3, "section": "Financials",
        "original_chunk": "fabricated",
        "highlighted_ambiguity": "fabricated quote not in source",
        "reason": "hallucinated", "confidence": 0.9,
        "evidence": [{"chunk_id": "c1", "quote": "this text does not exist in chunk c1 at all"}],
    }])

    FinalReportGenerator().run_generation(job_dir, "testdoc", force_regenerate=True)
    result = json.loads((job_dir / "15_final_report" / "final_report.json").read_text(encoding="utf-8"))

    assert result["findings"] == []
    assert len(result["rejected_findings"]) == 1
    assert "ungrounded evidence" in result["rejected_findings"][0]["reject_reason"]


def test_claude_own_rejection_still_excluded_from_findings(job_dir):
    _write_claude_response(job_dir, [{
        "issue_id": "f4", "status": "rejected",
        "business_category": "Numerical Inconsistency",
        "chunk_id": "c1", "reason": "not material",
    }])

    FinalReportGenerator().run_generation(job_dir, "testdoc", force_regenerate=True)
    result = json.loads((job_dir / "15_final_report" / "final_report.json").read_text(encoding="utf-8"))

    assert result["findings"] == []
    assert len(result["rejected_findings"]) == 1
