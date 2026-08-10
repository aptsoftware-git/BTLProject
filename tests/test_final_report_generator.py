import json
import pytest
from pathlib import Path
from collections import Counter
from src.rag.final_report_generator import FinalReportGenerator, _get_publication_status

def test_publication_status():
    status_ready = _get_publication_status(Counter(), 1)
    assert status_ready["label"] == "Ready for Publication"

    status_minor = _get_publication_status(Counter({"Low": 5}), 5)
    assert status_minor["label"] == "Requires Minor Revision"

    status_review = _get_publication_status(Counter({"High": 2}), 2)
    assert status_review["label"] == "Compliance Review Recommended"

    status_major = _get_publication_status(Counter({"Critical": 1}), 1)
    assert status_major["label"] == "Requires Major Revision"

def test_final_report_generator_run(tmp_path):
    job_dir = tmp_path / "job_test_exec"
    claude_dir = job_dir / "14_claude_verification"
    claude_dir.mkdir(parents=True, exist_ok=True)
    chunks_dir = job_dir / "06_chunks"
    chunks_dir.mkdir(parents=True, exist_ok=True)

    # An Ambiguity Analysis finding must be grounded: its evidence quote
    # must be a real substring of the cited chunk's actual text (see
    # src/rag/ambiguity_grounding_gate.py).
    with open(chunks_dir / "document_chunks.json", "w", encoding="utf-8") as f:
        json.dump({"chunks": [{
            "metadata": {"chunk_id": "chunk_0001", "page_number": 3, "heading": "Delivery Timelines"},
            "text": "Deliverables will be completed promptly, per Section 3 of the agreement."
        }]}, f)

    claude_response = {
        "overall_document_risk": "Medium",
        "verified_findings": [
            {
                # In-scope, in-taxonomy, grounded finding -- must survive
                # every gate and reach the final report.
                "issue_id": "test_amb_001",
                "status": "confirmed",
                "business_category": "Missing / conflicting context",
                "severity": "High",
                "reason": "Vague deadline specified in contract section, with no defined date elsewhere in the document.",
                "recommendation": "Specify exact calendar date for deliverable.",
                "page": 3,
                "section": "Delivery Timelines",
                "quote": "Deliverables will be completed promptly.",
                "business_impact": "Causes ambiguity in contractual completion dates.",
                "evidence": [
                    {"chunk_id": "chunk_0001", "quote": "Deliverables will be completed promptly."}
                ]
            },
            {
                # Out-of-scope (Proofreading, not Ambiguity Analysis) --
                # must be rejected by the category taxonomy gate regardless
                # of what Claude labeled it, per
                # src/rag/ambiguity_taxonomy.py.
                "issue_id": "test_amb_002",
                "status": "confirmed",
                "business_category": "Grammar Issue",
                "severity": "Low",
                "reason": "Minor subject verb agreement error.",
                "recommendation": "Fix subject verb agreement.",
                "page": 1,
                "section": "Introduction",
                "quote": "The results of the test is conclusive.",
                "business_impact": "Minor phrasing issue.",
                "evidence": []
            }
        ],
        "recommendations": [
            "Reconcile delivery dates across Section 3.",
            "Fix subject verb agreement in Section 1."
        ]
    }

    with open(claude_dir / "claude_response.json", "w", encoding="utf-8") as f:
        json.dump(claude_response, f)

    generator = FinalReportGenerator()
    generator.run_generation(job_dir, "doc_test_123")

    report_dir = job_dir / "15_final_report"
    assert (report_dir / "final_report.json").exists()
    assert (report_dir / "executive_summary.md").exists()
    assert (report_dir / "final_report.md").exists()
    assert (report_dir / "final_report.html").exists()

    with open(report_dir / "final_report.json", "r", encoding="utf-8") as f:
        data = json.load(f)
        assert data["document_job_id"] == "doc_test_123"
        assert data["publication_status"]["label"] in [
            "Ready for Publication", "Requires Minor Revision", "Compliance Review Recommended", "Requires Major Revision", "Editorial Review Required"
        ]
        # Only the in-scope, grounded finding reaches the report; the
        # Grammar Issue finding is rejected as out of taxonomy scope.
        assert len(data["findings"]) == 1
        assert data["findings"][0]["category"] == "Missing / conflicting context"
        assert any(r.get("issue_id") == "test_amb_002" for r in data["rejected_findings"])
        assert "action_plan" in data
        assert "phase_1_immediate" in data["action_plan"]
        assert "validation_summary" in data

    with open(report_dir / "final_report.html", "r", encoding="utf-8") as f:
        html_content = f.read()
        assert "Enterprise Document Quality" in html_content

