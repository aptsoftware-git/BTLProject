"""
test_stage_recovery.py
======================
Tests stage-level recovery, output validation, report regeneration, and repair logic.

IMPORTANT: backend.services.get_job_dir() always resolves to the real
data/output/{job_id} directory (it is not parametrized by tmp_path), so every
job_id used here is a disposable, clearly-named synthetic job that is created
fresh and torn down after each test. These tests previously hardcoded the
real production job ID "cff0427c29e541d496d067247fba5c52" and called
regenerate_proofreading_report()/repair_job() directly against it, which
mutated/deleted real user data (10_final/report.json, 08_validation/*) on
every test run. Never reintroduce a real job ID here.
"""

import json
import shutil
from pathlib import Path

import pytest

from backend.services import (
    validate_job_outputs,
    regenerate_proofreading_report,
    rerun_stage,
    rerun_from_stage,
    repair_job,
    safe_load_candidates,
    create_job,
    get_job,
    get_job_dir,
    JOBS,
)

TEST_JOB_ID = "test_recovery_synthetic_job"


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    JOBS.pop(TEST_JOB_ID, None)
    shutil.rmtree(get_job_dir(TEST_JOB_ID), ignore_errors=True)


def _make_synthetic_job_with_spell_candidates():
    """Creates a disposable job with a real Stage 2 + Stage 3 output on disk
    so Stage 4 (report regeneration) has valid, non-empty input to work from."""
    job_dir = get_job_dir(TEST_JOB_ID)
    shutil.rmtree(job_dir, ignore_errors=True)
    dummy_file = job_dir / "uploaded.pdf"
    dummy_file.parent.mkdir(parents=True, exist_ok=True)
    dummy_file.write_text("dummy", encoding="utf-8")

    create_job("sample.pdf", dummy_file, job_id=TEST_JOB_ID)

    sentences = [
        {
            "sentence_id": 1, "paragraph_id": 1, "page": 1,
            "text": "This is a test sentance.",
            "start_offset": 0, "end_offset": 25,
            "doc_char_start": 0, "doc_char_end": 25,
        },
    ]
    (job_dir / "04_sentences").mkdir(parents=True, exist_ok=True)
    (job_dir / "04_sentences" / "sentences.json").write_text(json.dumps(sentences), encoding="utf-8")

    (job_dir / "03_preprocessed").mkdir(parents=True, exist_ok=True)
    (job_dir / "03_preprocessed" / "normalized_text.txt").write_text(sentences[0]["text"], encoding="utf-8")

    spell_candidates = [
        {
            "sentence_id": 1, "char_start": 10, "char_end": 19,
            "original_text": "sentance", "suggested_text": "sentence",
            "issue_type": "spelling", "source": "languagetool", "reason": "Spelling",
            "confidence": 0.9, "page_number": 1, "bbox": None,
        }
    ]
    (job_dir / "06_spell").mkdir(parents=True, exist_ok=True)
    (job_dir / "06_spell" / "spell_candidates.json").write_text(json.dumps(spell_candidates), encoding="utf-8")

    return job_dir


def test_validate_job_outputs_on_synthetic_job():
    _make_synthetic_job_with_spell_candidates()
    val = validate_job_outputs(TEST_JOB_ID)
    assert val["job_id"] == TEST_JOB_ID
    assert "highest_completed_stage" in val
    assert isinstance(val["missing_outputs"], list)
    assert isinstance(val["existing_outputs"], list)


def test_safe_load_candidates_repair(tmp_path):
    # Test valid JSON
    f_valid = tmp_path / "valid.json"
    f_valid.write_text(json.dumps([{"sentence_id": 1, "original_text": "foo"}]), encoding="utf-8")
    assert len(safe_load_candidates(f_valid)) == 1

    # Test truncated trailing JSON
    f_trunc = tmp_path / "trunc.json"
    f_trunc.write_text('[{"sentence_id": 1, "original_text": "foo"}, {"sentence_id": 2, "original_text":', encoding="utf-8")
    repaired = safe_load_candidates(f_trunc)
    assert len(repaired) == 1
    assert repaired[0]["sentence_id"] == 1


def test_regenerate_proofreading_report_redirects_to_canonical_rerun(monkeypatch):
    """regenerate_proofreading_report must no longer be an independent
    report-rebuild path that can leave 10_final/mapped_findings.json stale.
    It must delegate to the single canonical rerun-proofreading workflow
    (rerun_proofreading_job), which reruns Stage 3 -> Stage 4 ->
    finding_mapper end-to-end instead of only rewriting report.json."""
    _make_synthetic_job_with_spell_candidates()

    calls = []

    def _fake_rerun_proofreading_job(job_id):
        calls.append(job_id)
        return {"job_id": job_id, "status": "pending", "redirected": True}

    import backend.services as services_module
    monkeypatch.setattr(services_module, "rerun_proofreading_job", _fake_rerun_proofreading_job)

    res = regenerate_proofreading_report(TEST_JOB_ID)

    assert calls == [TEST_JOB_ID]
    assert res.get("redirected") is True


def test_regenerate_proofreading_report_missing_job_raises():
    with pytest.raises(ValueError, match="not found"):
        regenerate_proofreading_report("job_that_does_not_exist_synthetic")


def test_repair_job_synthetic(monkeypatch):
    """repair_job(), when 10_final/report.json is missing, now goes through
    regenerate_proofreading_report() -> rerun_proofreading_job() ->
    retry_job_stage() -> queue_job(), which pushes onto the real background
    job queue and would actually run Docling/spell/grammar against the fake
    dummy PDF here. Stub rerun_proofreading_job so this stays a fast,
    in-process unit test instead of kicking off real async pipeline work
    that outlives the test and races the cleanup fixture."""
    _make_synthetic_job_with_spell_candidates()

    calls = []
    import backend.services as services_module
    monkeypatch.setattr(
        services_module, "rerun_proofreading_job",
        lambda job_id: calls.append(job_id) or {"job_id": job_id, "status": "pending"}
    )

    res = repair_job(TEST_JOB_ID)
    assert res is not None
    assert calls == [TEST_JOB_ID]
