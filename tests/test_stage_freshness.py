"""
test_stage_freshness.py
=========================
Regression tests for the Stage 3 -> Stage 4 staleness/dependency-gating bug:
a report.json generated before Stage 3 produced its real spell_candidates.json
was being treated as a valid cache hit forever, even after Stage 3 was
successfully rerun. See job cff0427c29e541d496d067247fba5c52 for the original
repro (08_validation/accepted.json + 10_final/report.json written 36 minutes
*before* 06_spell/spell_candidates.json).
"""

import os
import shutil
import time

import pytest

from src.stage_orchestrator import StageOrchestrator, _artifact_is_stale
from backend.services import create_job, get_job, get_job_dir, JOBS

# backend.services.get_job_dir() always resolves to the real data/output/
# directory (it is not parametrized by tmp_path), and create_job()/get_job()
# persist metadata.json there as a side effect. Every job_id used by this
# file is cleaned up automatically so test runs never leave ghost job
# folders behind in the real data/output/ directory.
_TEST_JOB_IDS = [
    "test_stage4_blocked_missing",
    "test_stage4_blocked_failed",
    "test_stage4_stale_report",
    "test_stage3_blocked_missing",
    "test_stage3_blocked_failed",
]


@pytest.fixture(autouse=True)
def _cleanup_real_job_dirs():
    yield
    for job_id in _TEST_JOB_IDS:
        JOBS.pop(job_id, None)
        shutil.rmtree(get_job_dir(job_id), ignore_errors=True)


def _touch(path, content="x", mtime=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    if mtime is not None:
        os.utime(path, (mtime, mtime))


# ---------------------------------------------------------------------------
# _artifact_is_stale
# ---------------------------------------------------------------------------

def test_artifact_is_stale_when_output_missing(tmp_path):
    output = tmp_path / "out.json"
    input_ = tmp_path / "in.json"
    _touch(input_)
    assert _artifact_is_stale(output, input_) is True


def test_artifact_is_stale_when_output_empty(tmp_path):
    output = tmp_path / "out.json"
    output.write_text("", encoding="utf-8")
    input_ = tmp_path / "in.json"
    _touch(input_)
    assert _artifact_is_stale(output, input_) is True


def test_artifact_is_stale_reproduces_original_bug(tmp_path):
    """report.json written before spell_candidates.json must be flagged stale."""
    report = tmp_path / "10_final" / "report.json"
    spell = tmp_path / "06_spell" / "spell_candidates.json"

    now = time.time()
    _touch(report, "{}", mtime=now - 2000)   # 13:56 equivalent
    _touch(spell, "[]", mtime=now)           # 14:32 equivalent, 36 min later

    assert _artifact_is_stale(report, spell) is True


def test_artifact_is_stale_false_when_output_newer(tmp_path):
    spell = tmp_path / "06_spell" / "spell_candidates.json"
    report = tmp_path / "10_final" / "report.json"

    now = time.time()
    _touch(spell, "[]", mtime=now - 2000)
    _touch(report, "{}", mtime=now)

    assert _artifact_is_stale(report, spell) is False


# ---------------------------------------------------------------------------
# Stage gating: Stage 4 must never run/cache-hit against missing/failed
# Stage 3 output. Stage 3 must never run/cache-hit against missing/failed
# Stage 2 output.
# ---------------------------------------------------------------------------

def _make_job(tmp_path, job_id):
    dummy_file = tmp_path / "sample.pdf"
    dummy_file.write_text("dummy", encoding="utf-8")
    job_dir = tmp_path / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    create_job("sample.pdf", dummy_file, job_id=job_id)
    return job_dir, dummy_file


def test_stage4_blocked_when_spell_output_missing(tmp_path):
    job_id = "test_stage4_blocked_missing"
    job_dir, dummy_file = _make_job(tmp_path, job_id)

    orchestrator = StageOrchestrator(job_id, job_dir, dummy_file)
    orchestrator.run_stage_4_grammar()

    job = get_job(job_id)
    stage4 = next(s for s in job["stages"] if s["stage_id"] == "stage_4_grammar")
    assert stage4["status"] == "Blocked"
    assert "Stage 3" in stage4["errors"]
    # Must not have been reported as a successful/completed run.
    assert job.get("grammar_ready") is not True


def test_stage4_blocked_when_stage3_failed(tmp_path):
    job_id = "test_stage4_blocked_failed"
    job_dir, dummy_file = _make_job(tmp_path, job_id)

    orchestrator = StageOrchestrator(job_id, job_dir, dummy_file)
    orchestrator.update_stage_state("stage_3_spell", "Failed", errors="simulated failure")

    orchestrator.run_stage_4_grammar()

    job = get_job(job_id)
    stage4 = next(s for s in job["stages"] if s["stage_id"] == "stage_4_grammar")
    assert stage4["status"] == "Blocked"


def test_stage4_does_not_cache_hit_stale_report(tmp_path):
    """The exact original bug: an existing, non-empty report.json must not be
    treated as 'Completed' if it predates the current spell_candidates.json."""
    job_id = "test_stage4_stale_report"
    job_dir, dummy_file = _make_job(tmp_path, job_id)

    now = time.time()
    _touch(job_dir / "10_final" / "report.json", '{"total_issues": 0, "issues": []}', mtime=now - 2000)
    _touch(job_dir / "06_spell" / "spell_candidates.json", "[]", mtime=now)

    orchestrator = StageOrchestrator(job_id, job_dir, dummy_file)
    orchestrator.run_stage_4_grammar()

    job = get_job(job_id)
    stage4 = next(s for s in job["stages"] if s["stage_id"] == "stage_4_grammar")
    # Must not silently cache-hit as "Completed, duration 0.0" against stale output.
    assert not (stage4["status"] == "Completed" and stage4.get("duration") == 0.0)


def test_stage3_blocked_when_sentences_missing(tmp_path):
    job_id = "test_stage3_blocked_missing"
    job_dir, dummy_file = _make_job(tmp_path, job_id)

    orchestrator = StageOrchestrator(job_id, job_dir, dummy_file)
    orchestrator.run_stage_3_spell()

    job = get_job(job_id)
    stage3 = next(s for s in job["stages"] if s["stage_id"] == "stage_3_spell")
    assert stage3["status"] == "Blocked"
    assert "Stage 2" in stage3["errors"]


def test_stage3_blocked_when_stage2_failed(tmp_path):
    job_id = "test_stage3_blocked_failed"
    job_dir, dummy_file = _make_job(tmp_path, job_id)

    orchestrator = StageOrchestrator(job_id, job_dir, dummy_file)
    orchestrator.update_stage_state("stage_2_extraction", "Failed", errors="simulated failure")

    orchestrator.run_stage_3_spell()

    job = get_job(job_id)
    stage3 = next(s for s in job["stages"] if s["stage_id"] == "stage_3_spell")
    assert stage3["status"] == "Blocked"
