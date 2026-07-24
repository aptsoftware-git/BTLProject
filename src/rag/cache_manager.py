"""
cache_manager.py
================
Enterprise Persistent Document Cache Manager.
Computes SHA-256 document fingerprints, manages stage artifact persistence,
memory caching, incremental execution state, and recovery.
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from src.config import ROOT_DIR

logger = logging.getLogger("pipeline")
backend_logger = logging.getLogger("backend")

# Memory Cache for fast in-memory lookups
MEMORY_CACHE: Dict[str, Dict[str, Any]] = {}

CACHE_BASE_DIR = ROOT_DIR / "data" / "cache"

PIPELINE_VERSION = "2.0.0"
PROMPT_VERSION = "1.0.0"
EMBEDDING_MODEL_VERSION = "all-MiniLM-L6-v2"

STAGE_ARTIFACTS_MAP = {
    "extraction": ["01_raw/raw_text.txt", "01_extraction/extracted_document.json"],
    "filtered": ["02_filtered/filtered_text.txt"],
    "preprocessed": ["03_preprocessed/normalized_text.txt"],
    "sentences": ["04_sentences/sentences.json"],
    "protected_terms": ["05_protected_terms/protected_terms.json"],
    "chunks": ["06_chunks/document_chunks.json"],
    "embeddings": ["07_embeddings/vector_store_metadata.json"],
    "proofreading": ["10_final/report.json", "10_final/annotated_original.html", "10_final/corrected_document.html"],
    "context_analysis": ["07_context_analysis/report.json"],
    "semantic_clusters": ["09_semantic_clusters/semantic_clusters.json"],
    "claim_extraction": ["10_claim_extraction/chunk_claims.json"],
    "chunk_reasoning": ["11_chunk_reasoning/chunk_reasoning.json"],
    "cluster_reasoning": ["12_cluster_reasoning/cluster_reasoning.json"],
    "claude_input": ["13_claude_input/claude_input.json"],
    "claude_verification": ["14_claude_verification/claude_response.json"],
    "final_report": ["15_final_report/final_report.json", "15_final_report/final_report.html"]
}


def compute_file_hash(file_path: Path | str) -> str:
    """Computes SHA-256 hex digest of a document file."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found for hashing: {file_path}")
    
    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            sha256.update(chunk)
    return sha256.hexdigest()


class DocumentCacheManager:
    """
    Manages persistent and in-memory document processing artifacts keyed by SHA-256 hash.
    """

    def __init__(self, doc_hash: str, original_filename: str = "unknown"):
        self.doc_hash = doc_hash
        self.original_filename = original_filename
        self.cache_dir = CACHE_BASE_DIR / doc_hash
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_path = self.cache_dir / "cache_metadata.json"
        self._ensure_metadata()

    def _ensure_metadata(self) -> None:
        if not self.metadata_path.exists():
            metadata = {
                "doc_hash": self.doc_hash,
                "original_filename": self.original_filename,
                "created_at": datetime.now().isoformat(),
                "last_updated": datetime.now().isoformat(),
                "pipeline_version": PIPELINE_VERSION,
                "prompt_version": PROMPT_VERSION,
                "embedding_model_version": EMBEDDING_MODEL_VERSION,
                "completed_stages": []
            }
            self._write_json(self.metadata_path, metadata)

    def get_metadata(self) -> Dict[str, Any]:
        if self.doc_hash in MEMORY_CACHE and "metadata" in MEMORY_CACHE[self.doc_hash]:
            return MEMORY_CACHE[self.doc_hash]["metadata"]
        
        if self.metadata_path.exists():
            try:
                with open(self.metadata_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                    MEMORY_CACHE.setdefault(self.doc_hash, {})["metadata"] = meta
                    return meta
            except Exception as e:
                logger.error(f"Error reading cache metadata for {self.doc_hash}: {e}")
        return {}

    def update_completed_stage(self, stage_name: str) -> None:
        meta = self.get_metadata()
        completed = set(meta.get("completed_stages", []))
        completed.add(stage_name)
        meta["completed_stages"] = list(completed)
        meta["last_updated"] = datetime.now().isoformat()
        MEMORY_CACHE.setdefault(self.doc_hash, {})["metadata"] = meta
        self._write_json(self.metadata_path, meta)
        logger.info(f"[CACHE RECORDED] Document {self.doc_hash[:10]}... completed stage: {stage_name}")

    def is_stage_completed(self, stage_name: str) -> bool:
        meta = self.get_metadata()
        if stage_name in meta.get("completed_stages", []):
            # Verify actual artifact files exist on disk
            artifacts = STAGE_ARTIFACTS_MAP.get(stage_name, [])
            for rel_path in artifacts:
                full_path = self.cache_dir / rel_path
                if not full_path.exists() or full_path.stat().st_size == 0:
                    return False
            return True
        return False

    def is_fully_processed(self) -> bool:
        essential_stages = [
            "extraction", "chunks", "embeddings", "proofreading",
            "semantic_clusters", "claim_extraction", "chunk_reasoning",
            "cluster_reasoning", "claude_input", "claude_verification", "final_report"
        ]
        return all(self.is_stage_completed(stage) for stage in essential_stages)

    def invalidate_stage(self, stage_name: str) -> None:
        meta = self.get_metadata()
        completed = [s for s in meta.get("completed_stages", []) if s != stage_name]
        meta["completed_stages"] = completed
        meta["last_updated"] = datetime.now().isoformat()
        MEMORY_CACHE.setdefault(self.doc_hash, {})["metadata"] = meta
        self._write_json(self.metadata_path, meta)
        
        # Remove physical artifacts for invalidated stage
        artifacts = STAGE_ARTIFACTS_MAP.get(stage_name, [])
        for rel_path in artifacts:
            full_path = self.cache_dir / rel_path
            if full_path.exists():
                try:
                    full_path.unlink()
                except Exception:
                    pass

    def save_artifact(self, rel_path: str, content: str | bytes | dict | list) -> Path:
        target_path = self.cache_dir / rel_path
        target_path.parent.mkdir(parents=True, exist_ok=True)

        if isinstance(content, (dict, list)):
            self._write_json(target_path, content)
        elif isinstance(content, str):
            with open(target_path, "w", encoding="utf-8") as f:
                f.write(content)
        elif isinstance(content, bytes):
            with open(target_path, "wb") as f:
                f.write(content)
        
        # Store in memory cache
        MEMORY_CACHE.setdefault(self.doc_hash, {})[rel_path] = content
        return target_path

    def load_artifact(self, rel_path: str) -> Optional[Any]:
        # Check memory cache first
        if self.doc_hash in MEMORY_CACHE and rel_path in MEMORY_CACHE[self.doc_hash]:
            return MEMORY_CACHE[self.doc_hash][rel_path]

        target_path = self.cache_dir / rel_path
        if not target_path.exists() or target_path.stat().st_size == 0:
            return None

        try:
            if rel_path.endswith(".json"):
                with open(target_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    MEMORY_CACHE.setdefault(self.doc_hash, {})[rel_path] = data
                    return data
            elif rel_path.endswith((".txt", ".md", ".html")):
                with open(target_path, "r", encoding="utf-8") as f:
                    text = f.read()
                    MEMORY_CACHE.setdefault(self.doc_hash, {})[rel_path] = text
                    return text
            else:
                with open(target_path, "rb") as f:
                    b_data = f.read()
                    MEMORY_CACHE.setdefault(self.doc_hash, {})[rel_path] = b_data
                    return b_data
        except Exception as e:
            logger.error(f"Error loading cached artifact {rel_path} for {self.doc_hash}: {e}")
            return None

    def sync_to_job_dir(self, job_dir: Path) -> None:
        """
        Synchronizes all cached artifacts into a specific job directory so all backend API endpoints and UI links work seamlessly.
        Uses fast directory tree copy or hardlinking.
        """
        job_dir.mkdir(parents=True, exist_ok=True)
        for item in self.cache_dir.iterdir():
            if item.name == "cache_metadata.json":
                continue
            dest = job_dir / item.name
            if item.is_dir():
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(item, dest)
            else:
                shutil.copy2(item, dest)

    def sync_from_job_dir(self, job_dir: Path) -> None:
        """
        Synchronizes generated artifacts from a job directory back into the persistent SHA-256 cache.
        """
        if not job_dir.exists():
            return
        
        for item in job_dir.iterdir():
            if item.name in ["metadata.json", "pipeline.log"]:
                continue
            dest = self.cache_dir / item.name
            if item.is_dir():
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(item, dest)
            else:
                shutil.copy2(item, dest)

        # Infer completed stages
        for stage_name, artifacts in STAGE_ARTIFACTS_MAP.items():
            if all((self.cache_dir / a).exists() and (self.cache_dir / a).stat().st_size > 0 for a in artifacts):
                self.update_completed_stage(stage_name)

    @staticmethod
    def _write_json(path: Path, data: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
