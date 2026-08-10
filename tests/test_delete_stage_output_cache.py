"""
test_delete_stage_output_cache.py
====================================
Regression test for a CPU-performance bug: a plain "Rerun Proofreading"
(which only targets Stage 3 -- spell) was silently wiping Stage 6 (Context
Analysis) output folders too, because "stage_3_spell"/"stage_4_grammar" were
included in Stage 6's deletion trigger list in
backend/services.py:delete_stage_output_cache(). Stage 6's sub-pipelines
(ambiguity_extractor.py, ambiguity_chunk_analyzer.py,
ambiguity_cluster_analyzer.py, contextual_analysis/pipeline.py) only ever
read Stage 2 (extraction) and Stage 5 (RAG chunk) outputs as input -- never
anything from Stage 3/4 -- so this cascade forced a full redo of a
multi-hour pipeline on every proofreading-only rerun, for no reason.
"""

import shutil

import pytest

from backend.services import delete_stage_output_cache, get_job_dir, JOBS

_TEST_JOB_ID = "test_delete_stage_cache_scoping"


@pytest.fixture(autouse=True)
def _cleanup_real_job_dir():
    yield
    JOBS.pop(_TEST_JOB_ID, None)
    shutil.rmtree(get_job_dir(_TEST_JOB_ID), ignore_errors=True)


def _make_all_stage_folders(job_dir):
    for folder in [
        "06_spell", "07_grammar", "08_validation", "09_semantic", "10_final",
        "06_context_analysis", "07_semantic_clustering", "09_semantic_clusters",
        "10_claim_extraction", "11_chunk_reasoning", "12_cluster_reasoning",
        "13_claude_input", "14_claude_verification", "15_final_report",
    ]:
        (job_dir / folder).mkdir(parents=True, exist_ok=True)
        (job_dir / folder / "marker.json").write_text("{}", encoding="utf-8")


def test_stage3_rerun_does_not_wipe_context_analysis_outputs():
    job_dir = get_job_dir(_TEST_JOB_ID)
    _make_all_stage_folders(job_dir)

    delete_stage_output_cache(_TEST_JOB_ID, "stage_3_spell")

    # Stage 3/4 outputs ARE expected to be wiped -- proofreading is being rerun.
    assert not (job_dir / "06_spell").exists()
    assert not (job_dir / "07_grammar").exists()

    # Stage 6 (Context Analysis) outputs must survive: nothing in Stage 6
    # ever reads Stage 3/4 output, so a proofreading-only rerun can never
    # invalidate it.
    for folder in [
        "06_context_analysis", "07_semantic_clustering", "09_semantic_clusters",
        "10_claim_extraction", "11_chunk_reasoning", "12_cluster_reasoning",
        "13_claude_input", "14_claude_verification", "15_final_report",
    ]:
        assert (job_dir / folder).exists(), f"{folder} should NOT have been wiped by a Stage 3 rerun"


def test_stage6_rerun_still_wipes_its_own_outputs():
    job_dir = get_job_dir(_TEST_JOB_ID)
    _make_all_stage_folders(job_dir)

    delete_stage_output_cache(_TEST_JOB_ID, "stage_6_context")

    for folder in [
        "06_context_analysis", "07_semantic_clustering", "09_semantic_clusters",
        "10_claim_extraction", "11_chunk_reasoning", "12_cluster_reasoning",
        "13_claude_input", "14_claude_verification", "15_final_report",
    ]:
        assert not (job_dir / folder).exists()


def test_stage2_extraction_rerun_still_wipes_context_analysis_outputs():
    # Stage 2 IS a real Stage 6 dependency, so this cascade must remain.
    job_dir = get_job_dir(_TEST_JOB_ID)
    _make_all_stage_folders(job_dir)

    delete_stage_output_cache(_TEST_JOB_ID, "stage_2_extraction")

    assert not (job_dir / "06_context_analysis").exists()
    assert not (job_dir / "12_cluster_reasoning").exists()
