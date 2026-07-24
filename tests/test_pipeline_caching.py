import json
import pytest
from pathlib import Path
import tempfile
from src.rag.cache_manager import DocumentCacheManager, compute_file_hash, CACHE_BASE_DIR
from backend.services import create_job, get_job, JOBS

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
