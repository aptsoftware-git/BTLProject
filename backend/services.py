from __future__ import annotations

import json
import logging
import queue
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from src.config import PipelineConfig, ROOT_DIR
from src.pipeline import ProofreadingPipeline

# Global in-memory storage for active jobs
JOBS: Dict[str, Dict[str, Any]] = {}
CURRENT_JOB_ID: Optional[str] = None
job_queue: queue.Queue[str] = queue.Queue()

# Map of stage log markers to UI progress stages & percentages (Proofreading Sub-steps: 5% - 48%)
STAGE_PROGRESS_MAP = {
    "Extracting document": (5.0, "Stage 1: Extracting Text"),
    "Analyzing layout": (10.0, "Stage 1: Analyzing Document Layout"),
    "Filtering": (15.0, "Stage 2: Filtering Content"),
    "Preprocessing": (20.0, "Stage 2: Preprocessing Text"),
    "Building paragraphs": (25.0, "Stage 2: Building Paragraphs"),
    "Sentence splitting": (30.0, "Stage 2: Splitting Sentences"),
    "Building protected terms": (35.0, "Stage 3: Building Protected Terms"),
    "Spell / grammar detection (LanguageTool + SymSpell)": (40.0, "Stage 4: Running Spell & Grammar Checks"),
    "Grammar review (local LLM)": (44.0, "Stage 4: Running LLM Grammar Review"),
    "Validation (protected-terms gate)": (46.0, "Stage 4: Validating Candidates"),
    "Semantic validation": (47.0, "Stage 4: Running Semantic Validation"),
    "Generating annotated HTML": (48.0, "Stage 4: Proofreading Ready"),
    "Generating reports": (49.0, "Stage 4: Proofreading Complete"),
    "Completed": (100.0, "Completed"),
}


class JobProgressHandler(logging.Handler):
    """Logging handler that listens to progress updates on the 'pipeline' logger
    and updates the current executing job status with granular stage readiness flags."""

    def emit(self, record: logging.LogRecord) -> None:
        global CURRENT_JOB_ID
        if not CURRENT_JOB_ID:
            return
        try:
            msg = record.getMessage()
            job = JOBS.get(CURRENT_JOB_ID)
            if not job:
                return

            for stage_key, (percentage, stage_name) in STAGE_PROGRESS_MAP.items():
                if stage_key in msg:
                    job["current_stage"] = stage_name
                    job["progress_percentage"] = percentage
                    
                    if stage_key in ("Sentence splitting", "Building protected terms"):
                        job["extraction_ready"] = True
                        job["document_viewer_ready"] = True
                    elif stage_key in ("Spell / grammar detection (LanguageTool + SymSpell)", "Grammar review (local LLM)"):
                        job["extraction_ready"] = True
                        job["spell_ready"] = True
                    elif stage_key in ("Validation (protected-terms gate)", "Semantic validation"):
                        job["extraction_ready"] = True
                        job["spell_ready"] = True
                        job["grammar_ready"] = True
                    elif stage_key in ("Generating annotated HTML", "Generating reports", "Completed"):
                        job["extraction_ready"] = True
                        job["spell_ready"] = True
                        job["grammar_ready"] = True
                        job["proofreading_ready"] = True
                        job["proofreading_status"] = "completed"
                    
                    save_job_metadata(CURRENT_JOB_ID)
                    break
        except Exception:
            pass


# Register progress tracking logging handler
logger = logging.getLogger("pipeline")
progress_handler = JobProgressHandler()
progress_handler.setLevel(logging.INFO)
logger.addHandler(progress_handler)
logger.setLevel(logging.INFO)

backend_logger = logging.getLogger("backend")



def get_job_dir(job_id: str) -> Path:
    """Return the output directory path for a given job ID."""
    return ROOT_DIR / "data" / "output" / job_id


def save_job_metadata(job_id: str) -> None:
    """Serialize job status metadata to data/output/{job_id}/metadata.json."""
    job = JOBS.get(job_id)
    if not job:
        return
    job_dir = get_job_dir(job_id)
    job_dir.mkdir(parents=True, exist_ok=True)
    metadata_path = job_dir / "metadata.json"
    
    # Create serializable copy
    metadata = {
        "job_id": job["job_id"],
        "filename": job["filename"],
        "status": job["status"],
        "current_stage": job["current_stage"],
        "progress_percentage": job.get("progress_percentage", 0.0),
        "overall_progress": job.get("overall_progress", 0),
        "created_at": job["created_at"],
        "completed_at": job.get("completed_at"),
        "error": job.get("error"),
        "file_path": job.get("file_path"),
        "result": job.get("result"),
        "stages": job.get("stages", []),
    }
    
    # Preserve context analysis and granular progress fields in serialized metadata
    for key in [
        "upload_ready", "document_viewer_ready", "extraction_ready", "spell_ready", "grammar_ready",
        "proofreading_ready", "rag_ready", "context_analysis_ready", "comparative_analysis_ready", "reports_ready",
        "context_analysis_status", "context_analysis_stage", "context_analysis_progress",
        "comparative_analysis_status", "comparative_analysis_stage", "comparative_analysis_progress",
        "context_analysis_issues_count", "context_analysis_est_time",
        "knowledge_objects_generated", "embeddings_completed", "index_progress",
        "memory_usage", "cpu_usage", "current_page", "total_pages",
        "current_batch", "total_batches", "estimated_remaining_time", "memory_safe_mode",
        "cache_info", "doc_hash"
    ]:
        if key in job:
            metadata[key] = job[key]

    try:
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
    except Exception as exc:
        logging.getLogger("backend").error("Failed to save metadata for job %s: %s", job_id, exc)


def load_job_metadata(job_id: str) -> Optional[Dict[str, Any]]:
    """Loads job status metadata from data/output/{job_id}/metadata.json if it exists."""
    job_dir = get_job_dir(job_id)
    metadata_path = job_dir / "metadata.json"
    if not metadata_path.exists():
        return None
    try:
        with open(metadata_path, "r", encoding="utf-8") as f:
            job = json.load(f)

            # Ensure stages list is present
            from src.stage_orchestrator import initialize_job_stages
            if "stages" not in job or not job["stages"]:
                job["stages"] = initialize_job_stages(job.get("created_at"))

            # Infer stage completion from artifacts if metadata lacks explicit status
            doc_json = job_dir / "structured_document.json"
            sentences_path = job_dir / "04_sentences" / "sentences.json"
            spell_path = job_dir / "06_spell" / "spell_candidates.json"
            report_path = job_dir / "10_final" / "report.json"
            ko_path = job_dir / "03_knowledge_objects" / "knowledge_objects.json"
            consistency_path = job_dir / "09_reports" / "consistency_report.html"
            comparative_path = job_dir / "09_reports" / "comparative_report.html"
            business_path = job_dir / "business_report.html"

            stage4_obj = next((s for s in job.get("stages", []) if s.get("stage_id") == "stage_4_grammar"), None)
            stage4_failed = (stage4_obj and stage4_obj.get("status") == "Failed") or job.get("proofreading_status") == "failed"

            if doc_json.exists() and sentences_path.exists():
                job["extraction_ready"] = True
                job["document_viewer_ready"] = True

            if spell_path.exists():
                job["spell_ready"] = True

            if report_path.exists() and not stage4_failed:
                job["grammar_ready"] = True
                job["proofreading_ready"] = True
                job["proofreading_status"] = "completed"
            elif stage4_failed:
                job["grammar_ready"] = False
                job["proofreading_ready"] = False
                job["proofreading_status"] = "failed"
                job["status"] = "failed"

            if ko_path.exists():
                job["rag_ready"] = True
                job["rag_status"] = "completed"

            if consistency_path.exists():
                job["context_analysis_ready"] = True
                job["context_analysis_status"] = "completed"

            if comparative_path.exists():
                job["comparative_analysis_ready"] = True
                job["comparative_analysis_status"] = "completed"

            if business_path.exists():
                job["reports_ready"] = True

            if (consistency_path.exists() or business_path.exists()) and job.get("status") in ("processing", "uploaded", "pending") and not stage4_failed:
                job["status"] = "completed"
                job["current_stage"] = "Completed"
                job["overall_progress"] = 100
                job["progress_percentage"] = 100.0
            elif stage4_failed:
                job["status"] = "failed"

            JOBS[job_id] = job
            return job
    except Exception as exc:
        logging.getLogger("backend").error("Failed to load metadata for job %s: %s", job_id, exc)
        return None


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    """Get a job's details from memory or from disk."""
    if job_id in JOBS:
        return JOBS[job_id]
    return load_job_metadata(job_id)


from src.rag.cache_manager import DocumentCacheManager, compute_file_hash
from src.stage_orchestrator import initialize_job_stages, StageOrchestrator


def create_job(filename: str, original_file_path: Path, job_id: Optional[str] = None) -> Dict[str, Any]:
    """Initialize job details and write initial metadata with persistent SHA-256 caching."""
    if not job_id:
        job_id = str(uuid.uuid4().hex)

    job_dir = get_job_dir(job_id)
    job_dir.mkdir(parents=True, exist_ok=True)

    # Compute SHA-256 document fingerprint
    doc_hash = compute_file_hash(original_file_path)
    cache_mgr = DocumentCacheManager(doc_hash, filename)

    cache_info = {
        "cached": False,
        "reused_embeddings": False,
        "reused_chunks": False,
        "reused_artifacts": False,
        "estimated_time_saved_min": 0
    }

    created_at_iso = datetime.now().isoformat()
    stages = initialize_job_stages(created_at_iso)

    job = {
        "job_id": job_id,
        "doc_hash": doc_hash,
        "filename": filename,
        "status": "uploaded",
        "current_stage": "Document Uploaded",
        "progress_percentage": 12.5,
        "overall_progress": 12,
        "created_at": created_at_iso,
        "completed_at": None,
        "error": None,
        "file_path": str(original_file_path),
        "result": None,
        "cache_info": cache_info,
        "stages": stages,
        "upload_ready": True,
        "document_viewer_ready": False,
        "extraction_ready": False,
        "spell_ready": False,
        "grammar_ready": False,
        "proofreading_ready": False,
        "rag_ready": False,
        "context_analysis_ready": False,
        "comparative_analysis_ready": False,
        "reports_ready": False,
    }

    # Check for full cache hit (Requirement 1 & Primary Objective)
    if cache_mgr.is_fully_processed():
        backend_logger.info("[FULL CACHE HIT] Document fingerprint %s... is fully processed. Reusing artifacts for job %s.", doc_hash[:10], job_id)
        cache_mgr.sync_to_job_dir(job_dir)
        
        proof_res = cache_mgr.load_artifact("10_final/report.json")
        
        job["status"] = "completed"
        job["current_stage"] = "Completed"
        job["progress_percentage"] = 100.0
        job["overall_progress"] = 100
        job["context_analysis_status"] = "completed"
        job["context_analysis_stage"] = "Completed"
        job["context_analysis_progress"] = 100.0
        job["completed_at"] = datetime.now().isoformat()
        job["result"] = proof_res or {"total_issues": 0, "status": "completed"}
        job["document_viewer_ready"] = True
        job["extraction_ready"] = True
        job["spell_ready"] = True
        job["grammar_ready"] = True
        job["proofreading_ready"] = True
        job["rag_ready"] = True
        job["context_analysis_ready"] = True
        job["comparative_analysis_ready"] = True
        job["reports_ready"] = True

        for s in job["stages"]:
            s["status"] = "Completed"

        job["cache_info"] = {
            "cached": True,
            "reused_embeddings": True,
            "reused_chunks": True,
            "reused_artifacts": True,
            "estimated_time_saved_min": 18
        }

        JOBS[job_id] = job
        save_job_metadata(job_id)
        return job

    # Partial cache hit / new document: sync existing completed stages
    cache_mgr.sync_to_job_dir(job_dir)

    JOBS[job_id] = job
    save_job_metadata(job_id)
    return job


def queue_job(job_id: str, force: bool = False) -> Dict[str, Any]:
    """Queues a job for background stage orchestration if it is not already running or completed."""
    job = get_job(job_id)
    if not job:
        raise ValueError("Job not found")
        
    global CURRENT_JOB_ID
    # If the active worker thread is already executing this exact job, return it
    if not force and CURRENT_JOB_ID == job_id:
        return job

    # If the job is already finished, do not re-queue unless forced
    if not force and job.get("status") == "completed":
        return job

    job["status"] = "pending"
    job["current_stage"] = "Document Extraction"
    job["error"] = None
    job["completed_at"] = None
    save_job_metadata(job_id)
    
    job_queue.put(job_id)
    return job


def delete_stage_output_cache(job_id: str, stage_id: str = "all") -> None:
    """Removes cached output files for specified stage(s) to ensure fresh execution."""
    job_dir = get_job_dir(job_id)
    import shutil

    sid = str(stage_id).lower()

    # Stage 2: Extraction
    if sid in ("all", "stage_2_extraction", "extraction", "2"):
        (job_dir / "structured_document.json").unlink(missing_ok=True)
        for folder in ["01_raw", "02_filtered", "03_preprocessed", "04_sentences", "05_protected_terms"]:
            shutil.rmtree(job_dir / folder, ignore_errors=True)

    # Stage 3: Spell
    if sid in ("all", "stage_2_extraction", "extraction", "2", "stage_3_spell", "spell", "3"):
        shutil.rmtree(job_dir / "06_spell", ignore_errors=True)

    # Stage 4: Grammar
    if sid in ("all", "stage_2_extraction", "extraction", "2", "stage_3_spell", "spell", "3", "stage_4_grammar", "grammar", "4"):
        (job_dir / "report.json").unlink(missing_ok=True)
        (job_dir / "annotated_original.html").unlink(missing_ok=True)
        (job_dir / "corrected_document.html").unlink(missing_ok=True)
        (job_dir / "09_reports" / "report.json").unlink(missing_ok=True)
        (job_dir / "09_reports" / "proofreading_report.json").unlink(missing_ok=True)
        for folder in ["07_grammar", "08_validation", "09_semantic"]:
            shutil.rmtree(job_dir / folder, ignore_errors=True)

        dec_path = job_dir / "10_final" / "decisions.json"
        dec_content = dec_path.read_text(encoding="utf-8") if dec_path.exists() else None
        shutil.rmtree(job_dir / "10_final", ignore_errors=True)
        if dec_content:
            (job_dir / "10_final").mkdir(parents=True, exist_ok=True)
            (job_dir / "10_final" / "decisions.json").write_text(dec_content, encoding="utf-8")

    # Stage 5: RAG
    if sid in ("all", "stage_2_extraction", "extraction", "2", "stage_5_rag", "rag", "5"):
        (job_dir / "document_chunks.json").unlink(missing_ok=True)
        for folder in ["03_knowledge_objects", "06_chunks"]:
            shutil.rmtree(job_dir / folder, ignore_errors=True)

    # Stage 6: Context Analysis. Depends only on Stage 2 (extraction) and
    # Stage 5 (RAG chunks) inputs -- none of ambiguity_extractor.py,
    # ambiguity_chunk_analyzer.py, ambiguity_cluster_analyzer.py, or
    # contextual_analysis/pipeline.py ever read Stage 3/4 output folders
    # (06_spell/07_grammar/08_validation/09_semantic/10_final). Previously
    # "stage_3_spell"/"stage_4_grammar" were included here too, so a plain
    # "Rerun Proofreading" (which only targets Stage 3) silently wiped and
    # forced a full redo of this multi-hour Stage 6 pipeline every time --
    # removed since proofreading changes can never invalidate this stage's
    # inputs.
    if sid in ("all", "stage_2_extraction", "extraction", "2", "stage_6_context", "context", "6"):
        (job_dir / "report.json").unlink(missing_ok=True)
        (job_dir / "business_report.html").unlink(missing_ok=True)
        (job_dir / "09_reports" / "consistency_report.html").unlink(missing_ok=True)
        (job_dir / "09_reports" / "consistency_report.json").unlink(missing_ok=True)
        for folder in ["06_context_analysis", "07_semantic_clustering", "09_semantic_clusters", "10_claim_extraction", "11_chunk_reasoning", "12_cluster_reasoning", "13_claude_input", "14_claude_verification", "15_final_report"]:
            shutil.rmtree(job_dir / folder, ignore_errors=True)

    # Stage 7: Comparative Analysis
    if sid in ("all", "stage_2_extraction", "extraction", "2", "stage_6_context", "context", "6", "stage_7_comparative", "comparative", "7"):
        shutil.rmtree(job_dir / "comparative_analysis", ignore_errors=True)
        (job_dir / "09_reports" / "comparative_report.html").unlink(missing_ok=True)

    # Stage 8: Executive Reports
    if sid in ("all", "stage_2_extraction", "extraction", "2", "stage_4_grammar", "grammar", "4", "stage_6_context", "context", "6", "stage_7_comparative", "comparative", "7", "stage_8_reports", "reports", "8"):
        (job_dir / "business_report.html").unlink(missing_ok=True)
        (job_dir / "09_reports" / "final_report.html").unlink(missing_ok=True)
        (job_dir / "15_final_report" / "final_report.json").unlink(missing_ok=True)
        (job_dir / "15_final_report" / "final_report.html").unlink(missing_ok=True)


def retry_job_stage(job_id: str, stage_id: str = "all") -> Dict[str, Any]:
    """Resets a failed or specific stage and its downstream dependencies to pending and triggers background re-execution."""
    job = get_job(job_id)
    if not job:
        raise ValueError(f"Job '{job_id}' not found.")

    sid = str(stage_id).lower()
    delete_stage_output_cache(job_id, stage_id)

    if "stages" not in job or not job["stages"]:
        job["stages"] = initialize_job_stages(job.get("created_at"))

    stage_index_map = {
        "stage_1_upload": 0, "upload": 0, "1": 0,
        "stage_2_extraction": 1, "extraction": 1, "2": 1,
        "stage_3_spell": 2, "spell": 2, "3": 2,
        "stage_4_grammar": 3, "grammar": 3, "4": 3,
        "stage_5_rag": 4, "rag": 4, "5": 4,
        "stage_6_context": 5, "context": 5, "6": 5,
        "stage_7_comparative": 6, "comparative": 6, "7": 6,
        "stage_8_reports": 7, "reports": 7, "8": 7,
    }

    target_idx = stage_index_map.get(sid, None)

    for idx, s in enumerate(job["stages"]):
        if sid == "all" or target_idx is None or idx >= target_idx or s["stage_id"] == stage_id or s["name"].lower() == sid:
            s["status"] = "Pending"
            s["errors"] = None

    if target_idx is not None:
        if target_idx <= 1:
            job["extraction_ready"] = False
            job["document_viewer_ready"] = False
        if target_idx <= 2:
            job["spell_ready"] = False
        if target_idx <= 3:
            job["grammar_ready"] = False
            job["proofreading_ready"] = False
            job["proofreading_status"] = "pending"
        if target_idx <= 4:
            job["rag_ready"] = False
            job["rag_status"] = "pending"
        if target_idx <= 5:
            job["context_analysis_ready"] = False
            job["context_analysis_status"] = "pending"
        if target_idx <= 6:
            job["comparative_analysis_ready"] = False
            job["comparative_analysis_status"] = "pending"
        if target_idx <= 7:
            job["reports_ready"] = False

    job["status"] = "pending"
    job["error"] = None
    save_job_metadata(job_id)

    queue_job(job_id, force=True)
    return job


def rerun_proofreading_job(job_id: str) -> Dict[str, Any]:
    """Re-runs proofreading pipeline (Stage 3 & Stage 4) preserving extraction & RAG."""
    return retry_job_stage(job_id, stage_id="stage_3_spell")


def validate_job_outputs(job_id: str) -> Dict[str, Any]:
    """Validates presence and integrity of stage output artifacts for a document job."""
    job = get_job(job_id)
    if not job:
        raise ValueError(f"Job '{job_id}' not found.")

    job_dir = get_job_dir(job_id)

    stage_artifacts = {
        "stage_1_upload": ["01_document", "metadata.json"],
        "stage_2_extraction": ["structured_document.json", "04_sentences/sentences.json", "03_preprocessed/normalized_text.txt"],
        "stage_3_spell": ["06_spell/spell_candidates.json"],
        "stage_4_grammar": ["07_grammar/grammar_candidates.json", "10_final/report.json"],
        "stage_5_rag": ["03_knowledge_objects/knowledge_objects.json"],
        "stage_6_context": ["09_reports/consistency_report.html"],
        "stage_7_comparative": ["comparative_analysis/comparative_report.html"],
        "stage_8_reports": ["business_report.html"]
    }

    missing_outputs = []
    existing_outputs = []
    stage_statuses = {}
    highest_completed = 1
    recommended_recovery = 1

    for stage_key, files in stage_artifacts.items():
        stage_num = int(stage_key.split("_")[1])
        all_exist = True
        for f in files:
            path = job_dir / f
            if path.exists() and (path.is_dir() or path.stat().st_size > 0):
                existing_outputs.append(f)
            else:
                all_exist = False
                missing_outputs.append(f)

        stage_statuses[stage_key] = all_exist
        if all_exist:
            highest_completed = max(highest_completed, stage_num)
        elif recommended_recovery == 1:
            recommended_recovery = stage_num

    # Special check for proofreading report
    report_missing = not (job_dir / "10_final" / "report.json").exists() and not (job_dir / "report.json").exists()

    return {
        "job_id": job_id,
        "filename": job.get("filename"),
        "status": job.get("status"),
        "highest_completed_stage": highest_completed,
        "recommended_recovery_stage": recommended_recovery if report_missing or missing_outputs else 8,
        "missing_outputs": list(set(missing_outputs)),
        "existing_outputs": list(set(existing_outputs)),
        "is_valid": len(missing_outputs) == 0,
        "stage_statuses": stage_statuses
    }


def safe_load_candidates(file_path: Path) -> List[dict]:
    """Safely loads candidate JSON files, automatically repairing truncated trailing JSON if needed."""
    if not file_path.exists():
        return []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read().strip()
        if not content:
            return []
        try:
            res = json.loads(content)
            return res if isinstance(res, list) else []
        except json.JSONDecodeError:
            # Try auto-repair by finding the last complete object bracket '}'
            last_brace = content.rfind("}")
            if last_brace != -1:
                repaired = content[:last_brace+1] + "\n]"
                try:
                    res = json.loads(repaired)
                    return res if isinstance(res, list) else []
                except Exception:
                    pass
            return []
    except Exception as exc:
        logging.getLogger("backend").warning("Could not parse candidates file %s: %s", file_path, exc)
        return []


def regenerate_proofreading_report(job_id: str) -> Dict[str, Any]:
    """Deprecated standalone report-rebuild path.

    This used to reconstruct 10_final/report.json directly from existing
    spell/grammar artifacts without going through finding_mapper, which left
    10_final/mapped_findings.json - the file the Review UI actually reads -
    stale or absent. There must be exactly one supported way to regenerate
    proofreading output; redirect to the canonical rerun-proofreading
    workflow (Stage 3 -> Stage 4 -> finding_mapper) instead of maintaining a
    second, divergent code path.
    """
    job = get_job(job_id)
    if not job:
        raise ValueError(f"Job '{job_id}' not found.")

    backend_logger = logging.getLogger("backend")
    backend_logger.info(
        "[JOB %s] regenerate_proofreading_report is deprecated; redirecting to rerun_proofreading_job",
        job_id[:7]
    )
    return rerun_proofreading_job(job_id)


def rerun_stage(job_id: str, stage_number: int | str) -> Dict[str, Any]:
    """Reruns ONLY a single stage for job_id using existing artifacts."""
    return retry_job_stage(job_id, stage_id=str(stage_number))


def rerun_from_stage(job_id: str, stage_number: int | str) -> Dict[str, Any]:
    """Skips preceding completed stages and reruns pipeline from stage_number onwards."""
    return retry_job_stage(job_id, stage_id=str(stage_number))


def repair_job(job_id: str) -> Dict[str, Any]:
    """Validates outputs and automatically repairs missing artifacts or regenerates reports."""
    validation = validate_job_outputs(job_id)
    job_dir = get_job_dir(job_id)
    
    if "10_final/report.json" in validation.get("missing_outputs", []):
        spell_exists = (job_dir / "06_spell" / "spell_candidates.json").exists()
        sent_exists = (job_dir / "04_sentences" / "sentences.json").exists()
        if spell_exists and sent_exists:
            return regenerate_proofreading_report(job_id)

    rec_stage = validation.get("recommended_recovery_stage", 4)
    return rerun_from_stage(job_id, rec_stage)


def run_context_analysis_inline(job_id: str, job_dir: Path) -> None:
    """Helper to execute stages 6, 7, and 8 with forced re-generation."""
    orchestrator = StageOrchestrator(job_id, job_dir, Path(get_job(job_id)["file_path"]))
    orchestrator.run_stage_6_context(force_regenerate=True)
    orchestrator.run_stage_7_comparative(force_regenerate=True)
    orchestrator.run_stage_8_reports(force_regenerate=True)


def background_worker() -> None:
    """Thread function that processes jobs sequentially stage by stage via StageOrchestrator."""
    global CURRENT_JOB_ID
    backend_logger = logging.getLogger("backend")
    backend_logger.info("Background stage orchestration worker thread started.")

    while True:
        try:
            job_id = job_queue.get()
            if job_id is None:
                break

            job = get_job(job_id)
            if not job:
                job_queue.task_done()
                continue

            backend_logger.info("[JOB %s] START Processing pipeline for (%s)", job_id[:7], job.get("filename"))
            CURRENT_JOB_ID = job_id
            job_dir = get_job_dir(job_id)
            input_path = Path(job["file_path"])

            try:
                orchestrator = StageOrchestrator(job_id, job_dir, input_path)
                orchestrator.execute_all_stages()
            except Exception as e:
                import traceback
                error_trace = traceback.format_exc()
                job["status"] = "failed"
                job["current_stage"] = "Failed"
                job["error"] = f"{str(e)}\n{error_trace}"
                backend_logger.error("[JOB %s] FAILED background worker: %s", job_id[:7], e)
            finally:
                job["completed_at"] = datetime.now().isoformat()
                save_job_metadata(job_id)
                CURRENT_JOB_ID = None
                job_queue.task_done()
        except Exception as exc:
            backend_logger.critical("Critical error in background worker loop: %s", exc)
            time.sleep(2)


# Start worker thread
worker_thread = threading.Thread(target=background_worker, daemon=True)
worker_thread.start()


def delete_job(job_id: str) -> None:
    """Deletes job directory and removes job from memory."""
    import shutil
    if job_id in JOBS:
        del JOBS[job_id]
    job_dir = get_job_dir(job_id)
    if job_dir.exists():
        shutil.rmtree(job_dir, ignore_errors=True)


def recover_stuck_jobs_on_startup():
    """Discovers jobs that were left in 'processing' or 'pending' state when server started
    and marks them as 'recoverable' (awaiting user action), without automatically triggering execution."""
    try:
        time.sleep(1)
        all_jobs = get_all_jobs()
        for j in all_jobs:
            job_id = j.get("job_id")
            if not job_id or len(job_id) < 20 or job_id.startswith("test_"):
                continue
            if j.get("status") in ("processing", "pending") and job_id != CURRENT_JOB_ID:
                logging.getLogger("backend").info("[RECOVERY CHECKPOINT] Discovered recoverable job %s. Marking recoverable (awaiting user action).", job_id[:7])
                j["status"] = "recoverable"
                j["current_stage"] = "Recoverable Checkpoint Detected (Awaiting User Action)"
                save_job_metadata(job_id)
    except Exception as exc:
        logging.getLogger("backend").error("Failed startup recoverable job discovery: %s", exc)


# Startup job discovery enabled (marks recoverable, waits for user action)
threading.Thread(target=recover_stuck_jobs_on_startup, daemon=True).start()


def get_all_jobs() -> list[Dict[str, Any]]:
    """Scan the output directory and load metadata for all jobs."""
    output_dir = ROOT_DIR / "data" / "output"
    if not output_dir.exists():
        return []

    all_jobs = []
    for child in output_dir.iterdir():
        if child.is_dir():
            job_id = child.name
            job = get_job(job_id)
            if job:
                all_jobs.append(job)

    # Sort by created_at desc
    all_jobs.sort(key=lambda j: j.get("created_at", ""), reverse=True)
    return all_jobs


def run_context_analysis_bg(job_id: str, job_dir: Path) -> None:
    def worker():
        try:
            delete_stage_output_cache(job_id, "all")
            run_context_analysis_inline(job_id, job_dir)
        except Exception as e:
            import traceback
            logging.getLogger("backend").error("Context Analysis background trigger failed for job %s: %s\n%s", job_id, e, traceback.format_exc())
            job = get_job(job_id)
            if job:
                job["context_analysis_status"] = "failed"
                job["context_analysis_stage"] = f"Failed: {str(e)}"
                save_job_metadata(job_id)

    threading.Thread(target=worker, daemon=True).start()




