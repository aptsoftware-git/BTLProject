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
    and updates the current executing job status."""

    def emit(self, record: logging.LogRecord) -> None:
        global CURRENT_JOB_ID
        if not CURRENT_JOB_ID:
            return
        try:
            msg = record.getMessage()
            for stage_key, (percentage, stage_name) in STAGE_PROGRESS_MAP.items():
                if stage_key in msg:
                    job = JOBS.get(CURRENT_JOB_ID)
                    if job:
                        job["current_stage"] = stage_name
                        job["progress_percentage"] = percentage
                        if stage_key in ("Generating annotated HTML", "Generating reports", "Completed"):
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
        "progress_percentage": job["progress_percentage"],
        "created_at": job["created_at"],
        "completed_at": job["completed_at"],
        "error": job["error"],
        "file_path": job["file_path"],
        "result": job["result"],
    }
    
    # Preserve context analysis and granular progress fields in serialized metadata
    for key in [
        "proofreading_ready", "rag_ready", "context_analysis_ready", "comparative_analysis_ready",
        "context_analysis_status", "context_analysis_stage", "context_analysis_progress",
        "comparative_analysis_status", "comparative_analysis_stage", "comparative_analysis_progress",
        "context_analysis_issues_count", "context_analysis_est_time",
        "knowledge_objects_generated", "embeddings_completed", "index_progress",
        "memory_usage", "cpu_usage", "current_page", "total_pages",
        "current_batch", "total_batches", "estimated_remaining_time", "memory_safe_mode",
        "cache_info"
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
    metadata_path = get_job_dir(job_id) / "metadata.json"
    if not metadata_path.exists():
        return None
    try:
        with open(metadata_path, "r", encoding="utf-8") as f:
            job = json.load(f)
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

    job = {
        "job_id": job_id,
        "doc_hash": doc_hash,
        "filename": filename,
        "status": "uploaded",
        "current_stage": "Stage 1: Extraction",
        "progress_percentage": 0.0,
        "created_at": datetime.now().isoformat(),
        "completed_at": None,
        "error": None,
        "file_path": str(original_file_path),
        "result": None,
        "cache_info": cache_info,
    }

    # Check for full cache hit (Requirement 1 & Primary Objective)
    if cache_mgr.is_fully_processed():
        backend_logger.info("[FULL CACHE HIT] Document fingerprint %s... is fully processed. Reusing artifacts for job %s.", doc_hash[:10], job_id)
        cache_mgr.sync_to_job_dir(job_dir)
        
        proof_res = cache_mgr.load_artifact("10_final/report.json")
        
        job["status"] = "completed"
        job["current_stage"] = "Completed"
        job["progress_percentage"] = 100.0
        job["context_analysis_status"] = "completed"
        job["context_analysis_stage"] = "Completed"
        job["context_analysis_progress"] = 100.0
        job["completed_at"] = datetime.now().isoformat()
        job["result"] = proof_res or {"total_issues": 0, "status": "completed"}
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


def queue_job(job_id: str) -> Dict[str, Any]:
    """Queues a job for background processing if it is not already running or completed."""
    job = get_job(job_id)
    if not job:
        raise ValueError("Job not found")
        
    if job["status"] in ("completed", "pending", "processing"):
        return job

    job["status"] = "pending"
    job["current_stage"] = "Stage 1: Extraction"
    job["progress_percentage"] = 0.0
    job["error"] = None
    job["completed_at"] = None
    save_job_metadata(job_id)
    
    job_queue.put(job_id)
    return job


def run_context_analysis_inline(job_id: str, job_dir: Path) -> None:
    """Executes Context Analysis, Ambiguity Pipeline, Claude Verification, and Final Report synchronously."""
    job = get_job(job_id)
    if job:
        job["context_analysis_status"] = "running"
        job["context_analysis_stage"] = "Stage 5: RAG"
        job["context_analysis_progress"] = 55.0
        job["current_stage"] = "Stage 5: RAG"
        job["progress_percentage"] = 55.0
        save_job_metadata(job_id)

    from src.rag.contextual_analysis.pipeline import ContextAnalysisPipeline
    from src.config import load_preferences

    prefs = load_preferences()
    model_name = prefs.get("ollama", {}).get("model", "qwen2.5-coder:32b")

    consistency_pipeline = ContextAnalysisPipeline(model_name=model_name)
    consistency_pipeline.run_analysis(job_dir, job_id)

    if job:
        job["rag_ready"] = True
        job["rag_status"] = "completed"
        save_job_metadata(job_id)

    # Stage 6: Local LLM Ambiguity Detection
    if job:
        job["current_stage"] = "Stage 6: Local LLM Ambiguity Detection"
        job["progress_percentage"] = 68.0
        save_job_metadata(job_id)

    from src.rag.ambiguity_pipeline import AmbiguityPipeline
    ambiguity_pipeline = AmbiguityPipeline()
    ambiguity_pipeline.run_clustering(job_dir, job_id)
    backend_logger.info("Generated ambiguity semantic clusters for job %s", job_id)

    from src.rag.ambiguity_extractor import AmbiguityExtractor
    ambiguity_extractor = AmbiguityExtractor()
    ambiguity_extractor.run_extraction(job_dir, job_id)
    backend_logger.info("Generated ambiguity claims extraction index for job %s", job_id)

    from src.rag.ambiguity_chunk_analyzer import AmbiguityChunkAnalyzer
    chunk_analyzer = AmbiguityChunkAnalyzer()
    chunk_analyzer.run_analysis(job_dir, job_id)
    backend_logger.info("Generated ambiguity chunk-level analysis for job %s", job_id)

    from src.rag.ambiguity_cluster_analyzer import AmbiguityClusterAnalyzer
    cluster_analyzer = AmbiguityClusterAnalyzer()
    cluster_analyzer.run_analysis(job_dir, job_id)
    backend_logger.info("Generated ambiguity cluster-level analysis for job %s", job_id)

    # Stage 7: Claude Verification
    if job:
        job["current_stage"] = "Stage 7: Claude Verification"
        job["progress_percentage"] = 82.0
        save_job_metadata(job_id)

    from src.rag.claude_input_builder import ClaudeInputBuilder
    input_builder = ClaudeInputBuilder()
    input_builder.run_packaging(job_dir, job_id)

    from src.rag.claude.verification_service import ClaudeVerificationService
    verification_service = ClaudeVerificationService()
    verification_service.run_verification(job_dir, job_id)
    backend_logger.info("Generated Claude verification report for job %s", job_id)

    # Stage 9: Executive Compliance Report Generation
    if job:
        job["current_stage"] = "Stage 9: Executive Compliance Report Generation"
        job["progress_percentage"] = 90.0
        job["context_analysis_ready"] = True
        save_job_metadata(job_id)

    from src.rag.final_report_generator import FinalReportGenerator
    report_generator = FinalReportGenerator()
    report_generator.run_generation(job_dir, job_id)
    backend_logger.info("Generated final business compliance report for job %s", job_id)

    # Stage 10 & 11: Comparative Analysis & Executive Comparative Report Generation
    if job:
        job["current_stage"] = "Stage 10: Comparative Analysis"
        job["progress_percentage"] = 94.0
        job["comparative_analysis_status"] = "running"
        save_job_metadata(job_id)

    try:
        from src.comparative_analysis.service import ComparativeAnalysisService
        from src.comparative_analysis.models import ComparativeAnalysisRequest

        comp_service = ComparativeAnalysisService()
        comp_req = ComparativeAnalysisRequest(document_id=job_id)
        comp_resp = comp_service.run_analysis(comp_req)

        backend_logger.info("Generated Comparative Analysis and Executive Report for job %s (status: %s)", job_id, comp_resp.status)
        if job:
            job["comparative_analysis_status"] = comp_resp.status
            job["comparative_analysis_progress"] = 100.0
            job["comparative_analysis_ready"] = True
            job["current_stage"] = "Stage 11: Executive Comparative Analysis Report Generation"
            job["progress_percentage"] = 98.0
            save_job_metadata(job_id)
    except Exception as comp_err:
        backend_logger.error("Comparative Analysis execution failed for job %s: %s", job_id, comp_err, exc_info=True)
        if job:
            job["comparative_analysis_status"] = "failed"

    # Copy reports to 09_reports/
    try:
        import shutil
        reports_dir = job_dir / "09_reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        if (job_dir / "report.json").exists():
            shutil.copy2(job_dir / "report.json", reports_dir / "consistency_report.json")
        if (job_dir / "business_report.html").exists():
            shutil.copy2(job_dir / "business_report.html", reports_dir / "consistency_report.html")
        comp_report_src = job_dir / "comparative_analysis" / "comparative_report.html"
        if comp_report_src.exists():
            shutil.copy2(comp_report_src, reports_dir / "comparative_report.html")
    except Exception as copy_err:
        backend_logger.error("Failed to copy consistency reports to 09_reports: %s", copy_err)

    # Count issues
    issues_count = 0
    report_file = job_dir / "report.json"
    if report_file.exists():
        with open(report_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            issues_count = len(data.get("issues", []))

    if job:
        job["context_analysis_status"] = "completed"
        job["context_analysis_stage"] = "Completed"
        job["context_analysis_progress"] = 100.0
        job["context_analysis_issues_count"] = issues_count

    if job and "doc_hash" in job:
        cache_mgr = DocumentCacheManager(job["doc_hash"], job["filename"])
        cache_mgr.sync_from_job_dir(job_dir)


def background_worker() -> None:
    """Thread function that processes jobs sequentially to avoid resource contention."""
    global CURRENT_JOB_ID
    backend_logger = logging.getLogger("backend")
    backend_logger.info("Background proofreading worker thread started.")
    
    while True:
        try:
            job_id = job_queue.get()
            if job_id is None:
                break
                
            job = get_job(job_id)
            if not job:
                job_queue.task_done()
                continue
                
            backend_logger.info("Processing job %s (%s)", job_id, job["filename"])
            job["status"] = "processing"
            job["current_stage"] = "Stage 1: Extraction"
            job["progress_percentage"] = 5.0
            save_job_metadata(job_id)
            
            CURRENT_JOB_ID = job_id
            input_path = Path(job["file_path"])
            config = PipelineConfig()
            
            # Reset pipeline log handlers before run to prevent sharing file outputs across runs
            pipeline_logger = logging.getLogger("pipeline")
            for h in list(pipeline_logger.handlers):
                if isinstance(h, logging.FileHandler):
                    try:
                        h.close()
                    except Exception:
                        pass
                    pipeline_logger.removeHandler(h)
            # Re-attach progress tracking handler
            if progress_handler not in pipeline_logger.handlers:
                pipeline_logger.addHandler(progress_handler)

            try:
                with ProofreadingPipeline(config) as pipeline:
                    result = pipeline.run(input_path, run_id=job_id)
                    job["result"] = result
                    job["proofreading_ready"] = True
                    job["proofreading_status"] = "completed"
                    job["current_stage"] = "Proofreading Ready (Running RAG & Contextual Analysis in Background)"
                    job["progress_percentage"] = 50.0
                    save_job_metadata(job_id)
                    backend_logger.info("Proofreading phase finished for job %s. Results unlocked on UI. Proceeding to RAG & Ambiguity Pipeline...", job_id)
                    
                    try:
                        import shutil
                        job_dir = get_job_dir(job_id)
                        reports_dir = job_dir / "09_reports"
                        reports_dir.mkdir(parents=True, exist_ok=True)
                        
                        final_dir = job_dir / "10_final"
                        if (final_dir / "report.json").exists():
                            shutil.copy2(final_dir / "report.json", reports_dir / "proofreading_report.json")
                        if (final_dir / "annotated_original.html").exists():
                            shutil.copy2(final_dir / "annotated_original.html", reports_dir / "annotated.html")
                        if (final_dir / "corrected_document.html").exists():
                            shutil.copy2(final_dir / "corrected_document.html", reports_dir / "corrected.html")
                    except Exception as copy_err:
                        backend_logger.error("Failed to copy proofreading reports to 09_reports: %s", copy_err)

                # Run RAG -> Ambiguity Detection -> Claude Verification -> Final Report Generation
                job_dir = get_job_dir(job_id)
                run_context_analysis_inline(job_id, job_dir)

                # Mark Job Complete ONLY after all report files are successfully written
                job["status"] = "completed"
                job["current_stage"] = "Completed"
                job["progress_percentage"] = 100.0
                backend_logger.info("Job %s fully completed end-to-end successfully.", job_id)

            except Exception as e:
                import traceback
                error_trace = traceback.format_exc()
                job["status"] = "failed"
                job["current_stage"] = "Failed"
                job["error"] = f"{str(e)}\n{error_trace}"
                job["progress_percentage"] = 0.0
                backend_logger.error("Job %s failed: %s", job_id, e)
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


