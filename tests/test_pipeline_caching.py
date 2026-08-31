import json
import shutil
import pytest
from pathlib import Path
import tempfile
from src.rag.cache_manager import DocumentCacheManager, compute_file_hash, CACHE_BASE_DIR
from backend.services import create_job, get_job, JOBS


def _reset_cache_dir(doc_hash: str) -> None:
    """These tests use fixed doc_hash values and write real files under the
    persistent CACHE_BASE_DIR (not a tmp_path) -- without cleanup, a stale
    cache_metadata.json from a previous run (with an old pipeline_version)
    leaks across runs and can make is_fully_processed() correctly (but
    confusingly, for a test) report False. Clearing first makes each run
    start from _ensure_metadata() writing a fresh, current-version file."""
    cache_dir = CACHE_BASE_DIR / doc_hash
    if cache_dir.exists():
        shutil.rmtree(cache_dir, ignore_errors=True)

def test_compute_file_hash():
    with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".txt") as tmp:
        tmp.write("Production Scale Test Document Content 12345")
        tmp_path = Path(tmp.name)
    
    try:
        h1 = compute_file_hash(tmp_path)
        h2 = compute_file_hash(tmp_path)
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex length
    finally:
        if tmp_path.exists():
            tmp_path.unlink()

def test_cache_manager_stage_tracking():
    doc_hash = "test_hash_1234567890abcdef1234567890abcdef"
    _reset_cache_dir(doc_hash)
    cache_mgr = DocumentCacheManager(doc_hash, "sample_doc.pdf")
    
    assert not cache_mgr.is_stage_completed("extraction")
    assert not cache_mgr.is_fully_processed()
    
    # Save artifact for extraction
    cache_mgr.save_artifact("01_raw/raw_text.txt", "Sample raw text")
    cache_mgr.save_artifact("01_extraction/extracted_document.json", {"pages": 10})
    cache_mgr.update_completed_stage("extraction")
    
    assert cache_mgr.is_stage_completed("extraction")
    
    # Test loading cached artifact
    loaded_raw = cache_mgr.load_artifact("01_raw/raw_text.txt")
    assert loaded_raw == "Sample raw text"
    
    loaded_extracted = cache_mgr.load_artifact("01_extraction/extracted_document.json")
    assert loaded_extracted == {"pages": 10}
    
    # Test invalidation
    cache_mgr.invalidate_stage("extraction")
    assert not cache_mgr.is_stage_completed("extraction")

def test_full_cache_hit_job_creation():
    doc_hash = "full_cache_hit_hash_00000000000000000000"
    _reset_cache_dir(doc_hash)
    cache_mgr = DocumentCacheManager(doc_hash, "test_enterprise.pdf")
    
    essential_stages = [
        "extraction", "chunks", "embeddings", "proofreading",
        "semantic_clusters", "claim_extraction", "chunk_reasoning",
        "cluster_reasoning", "claude_input", "claude_verification", "final_report"
    ]
    for stage in essential_stages:
        cache_mgr.save_artifact(f"mock_{stage}.json", {"status": "ok"})
        # Save mock file for map check
        artifacts = cache_mgr.metadata_path.parent
        for art in [
            "01_raw/raw_text.txt", "01_extraction/extracted_document.json",
            "06_chunks/document_chunks.json", "07_embeddings/vector_store_metadata.json",
            "10_final/report.json", "10_final/annotated_original.html", "10_final/corrected_document.html",
            "09_semantic_clusters/semantic_clusters.json", "10_claim_extraction/chunk_claims.json",
            "11_chunk_reasoning/chunk_reasoning.json", "12_cluster_reasoning/cluster_reasoning.json",
            "13_claude_input/claude_input.json", "14_claude_verification/claude_response.json",
            "15_final_report/final_report.json", "15_final_report/final_report.html"
        ]:
            cache_mgr.save_artifact(art, "dummy content")
        cache_mgr.update_completed_stage(stage)

    assert cache_mgr.is_fully_processed()


def test_stale_pipeline_version_invalidates_full_cache_hit():
    """A document processed under an older pipeline_version must never be
    served as a full cache hit, even if every stage's artifact files are
    still present on disk -- this is what stops a document re-uploaded
    after an image/entity-linking bugfix from silently reusing the buggy
    cached run."""
    from src.rag import cache_manager as cm

    doc_hash = "stale_version_hash_11111111111111111111"
    _reset_cache_dir(doc_hash)
    cache_mgr = DocumentCacheManager(doc_hash, "stale_doc.pdf")

    essential_stages = [
        "extraction", "chunks", "embeddings", "proofreading",
        "semantic_clusters", "claim_extraction", "chunk_reasoning",
        "cluster_reasoning", "claude_input", "claude_verification", "final_report"
    ]
    for art in [
        "01_raw/raw_text.txt", "01_extraction/extracted_document.json",
        "06_chunks/document_chunks.json", "07_embeddings/vector_store_metadata.json",
        "10_final/report.json", "10_final/annotated_original.html", "10_final/corrected_document.html",
        "09_semantic_clusters/semantic_clusters.json", "10_claim_extraction/chunk_claims.json",
        "11_chunk_reasoning/chunk_reasoning.json", "12_cluster_reasoning/cluster_reasoning.json",
        "13_claude_input/claude_input.json", "14_claude_verification/claude_response.json",
        "15_final_report/final_report.json", "15_final_report/final_report.html"
    ]:
        cache_mgr.save_artifact(art, "dummy content")
    for stage in essential_stages:
        cache_mgr.update_completed_stage(stage)

    assert cache_mgr.is_fully_processed(), "sanity check: freshly-stamped cache should be a full hit"

    # Simulate this cache having been written by an older pipeline version.
    meta = cache_mgr.get_metadata()
    meta["pipeline_version"] = "0.0.1-old"
    cache_mgr._write_json(cache_mgr.metadata_path, meta)
    cm.MEMORY_CACHE.pop(doc_hash, None)  # drop the in-memory copy so the stale file is actually re-read

    assert not cache_mgr.is_fully_processed(), "stale pipeline_version must force a cache miss / reprocessing"
