"""
test_proofreading_count_consistency.py
======================================
Verifies that proofreading findings flow end-to-end from raw issues ->
mapped findings -> backend API response -> frontend list state without
dropping non-pdf-grounded findings or applying artificial count truncations.
"""

import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from backend.app import app
from src.finding_mapper import build_findings, save_findings
from src.final_validation_layer import FinalValidationLayer, build_count_reconciliation, save_final_findings
from src.pdf_bbox_resolver import resolve_bboxes
from src.sentence_mapper import sentence_id_str


@pytest.fixture
def sample_findings_data(tmp_path):
    job_id = "test_count_consistency_job"
    job_dir = tmp_path / "data" / "output" / job_id
    final_dir = job_dir / "10_final"
    sentences_dir = job_dir / "04_sentences"
    final_dir.mkdir(parents=True, exist_ok=True)
    sentences_dir.mkdir(parents=True, exist_ok=True)

    # 1. Create a rich sentence lookup index with 20 sentences
    lookup_index = {}
    for i in range(1, 21):
        sid = sentence_id_str(i)
        lookup_index[sid] = {
            "sentence_id": sid,
            "page_number": (i // 5) + 1,
            "text": f"This is sentence number {i} with some text content for proofreading evaluation.",
            "source_element_id": f"elem_{i}",
            "source_bbox": {"l": 50, "t": 100 + i * 20, "r": 400, "b": 115 + i * 20, "coord_origin": "TOPLEFT"},
        }
    with open(sentences_dir / "sentence_lookup_index.json", "w", encoding="utf-8") as f:
        json.dump(lookup_index, f)

    # 2. Create 15 raw issues across various sentences
    raw_issues = []
    for i in range(1, 16):
        sid_num = i
        sid_str = sentence_id_str(sid_num)
        sent_text = lookup_index[sid_str]["text"]
        raw_issues.append({
            "sentence_id": sid_num,
            "page_number": (i // 5) + 1,
            "original_text": "sentence",
            "suggested_text": "statement",
            "issue_type": "spelling" if i % 2 == 0 else "grammar",
            "severity": "high" if i % 3 == 0 else "medium",
            "reason": f"Correction reason for issue {i}",
            "confidence": 0.95,
            "sentence_text": sent_text,
        })

    with open(final_dir / "report.json", "w", encoding="utf-8") as f:
        json.dump({"issues": raw_issues}, f)

    # 3. Map findings using finding_mapper
    findings, auto_rejected = build_findings(raw_issues, lookup_index)
    
    # 4. Mix of pdf_grounded (some with bbox, some without)
    # Simulate PDF bbox resolution where only some have physical PDF bboxes
    resolved_findings = []
    for idx, f in enumerate(findings):
        is_pdf_grounded = idx < 6  # simulate only first 6 resolving PDF canvas boxes
        resolved_findings.append({
            **f,
            "pdf_grounded": is_pdf_grounded,
            "bbox": {"x0": 50, "y0": 100, "x1": 150, "y1": 120} if is_pdf_grounded else None
        })

    save_findings(resolved_findings, final_dir / "mapped_findings.json")

    return {
        "job_id": job_id,
        "job_dir": job_dir,
        "raw_count": len(raw_issues),
        "passed_count": len(resolved_findings),
        "pdf_grounded_count": sum(1 for f in resolved_findings if f.get("pdf_grounded") is True),
        "sentence_grounded_count": sum(1 for f in resolved_findings if not f.get("pdf_grounded")),
        "resolved_findings": resolved_findings,
    }


def test_findings_data_flow_parity(sample_findings_data, monkeypatch):
    """
    Test that compares raw issue count, backend API count, and frontend
    card / count calculation, ensuring NO truncation down to 6.
    """
    job_id = sample_findings_data["job_id"]
    job_dir = sample_findings_data["job_dir"]
    raw_count = sample_findings_data["raw_count"]
    passed_count = sample_findings_data["passed_count"]

    assert raw_count == 15
    assert passed_count == 15

    # Mock backend get_job and get_job_dir to point to our test job
    import backend.routes as routes
    monkeypatch.setattr(routes, "get_job", lambda jid: {"job_id": jid, "status": "completed"} if jid == job_id else None)
    monkeypatch.setattr(routes, "get_job_dir", lambda jid: job_dir)

    client = TestClient(app)
    response = client.get(f"/api/documents/{job_id}/findings")
    assert response.status_code == 200

    data = response.json()
    api_findings = data.get("findings", [])
    
    # 1. API count must match mapped count exactly
    assert len(api_findings) == passed_count, f"Expected {passed_count} findings from API, got {len(api_findings)}"

    # 2. Frontend logic simulation (reproducing IssueCardList state)
    all_frontend_findings = [f for f in api_findings if f]
    total_ui_count = len(all_frontend_findings)
    
    accepted_count = sum(1 for f in all_frontend_findings if f.get("status") == "accepted")
    rejected_count = sum(1 for f in all_frontend_findings if f.get("status") == "rejected")
    pending_count = total_ui_count - accepted_count - rejected_count

    # Verify UI counts reflect the full findings array, NOT just the 6 PDF-grounded ones
    assert total_ui_count == passed_count == 15, "Frontend total count dropped findings!"
    assert pending_count == 15, "Pending count did not match total initial findings!"
    assert sample_findings_data["pdf_grounded_count"] == 6
    assert sample_findings_data["sentence_grounded_count"] == 9

    # Both PDF-grounded and Sentence-grounded findings must be preserved and rendered
    pdf_grounded_in_ui = [f for f in all_frontend_findings if f.get("pdf_grounded") is True]
    sentence_grounded_in_ui = [f for f in all_frontend_findings if not f.get("pdf_grounded")]

    assert len(pdf_grounded_in_ui) == 6
    assert len(sentence_grounded_in_ui) == 9


def test_final_findings_artifact_is_canonical_source_for_api(sample_findings_data, monkeypatch):
    """
    End-to-end: finding_mapper output -> FinalValidationLayer -> canonical
    10_final/final_findings.json -> /findings API. Once final_findings.json
    exists, the API must serve it (not mapped_findings.json), and every
    candidate that went into the validation layer must be accounted for
    across accepted + rejected + merged (count reconciliation).
    """
    job_id = sample_findings_data["job_id"]
    job_dir = sample_findings_data["job_dir"]
    final_dir = job_dir / "10_final"
    resolved_findings = sample_findings_data["resolved_findings"]

    save_findings([], final_dir / "auto_rejected_findings.json")

    layer = FinalValidationLayer()
    accepted, decision_log = layer.run(resolved_findings, [])
    save_final_findings(accepted, decision_log, final_dir)

    reconciliation = build_count_reconciliation(job_dir)
    assert reconciliation["is_reconciled"] is True, reconciliation["checks"]

    n_accepted = sum(1 for d in decision_log if d["decision"] == "accepted")
    n_rejected = sum(1 for d in decision_log if d["decision"] == "rejected")
    n_merged = sum(1 for d in decision_log if d["decision"] == "merged")
    assert n_accepted + n_rejected + n_merged == len(resolved_findings)
    assert len(accepted) == n_accepted

    import backend.routes as routes
    monkeypatch.setattr(routes, "get_job", lambda jid: {"job_id": jid, "status": "completed"} if jid == job_id else None)
    monkeypatch.setattr(routes, "get_job_dir", lambda jid: job_dir)

    client = TestClient(app)
    response = client.get(f"/api/documents/{job_id}/findings")
    assert response.status_code == 200
    api_findings = response.json()["findings"]

    # API must reflect the canonical (post-final-validation) artifact, not
    # the pre-final-validation mapped_findings.json count.
    assert len(api_findings) == len(accepted)
    assert {f["finding_id"] for f in api_findings} == {f["finding_id"] for f in accepted}
