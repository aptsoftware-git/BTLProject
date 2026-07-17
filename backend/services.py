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

# Map of stage log markers to UI progress stages & percentages
STAGE_PROGRESS_MAP = {
    "Extracting document": (5.0, "Extracting Text"),
    "Analyzing layout": (12.0, "Analyzing Document Layout"),
    "Filtering": (18.0, "Filtering Content"),
    "Preprocessing": (25.0, "Preprocessing Text"),
    "Building paragraphs": (32.0, "Building Paragraphs"),
    "Sentence splitting": (40.0, "Splitting Sentences"),
    "Building protected terms": (48.0, "Building Protected Terms"),
    "Spell / grammar detection (LanguageTool + SymSpell)": (55.0, "Running Spell & Grammar Checks"),
    "Grammar review (local LLM)": (70.0, "Running LLM Grammar Review"),
    "Validation (protected-terms gate)": (80.0, "Validating Candidates"),
    "Semantic validation": (88.0, "Running Semantic Validation"),
    "Generating annotated HTML": (92.0, "Generating Annotated Documents"),
    "Generating reports": (97.0, "Generating Reports"),
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
        "context_analysis_status", "context_analysis_stage", "context_analysis_progress",
        "context_analysis_issues_count", "context_analysis_est_time",
        "knowledge_objects_generated", "embeddings_completed", "index_progress",
        "memory_usage", "cpu_usage", "current_page", "total_pages",
        "current_batch", "total_batches", "estimated_remaining_time", "memory_safe_mode"
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


def create_job(filename: str, original_file_path: Path) -> Dict[str, Any]:
    """Initialize job details and write initial metadata."""
    job_id = str(uuid.uuid4().hex)
    job = {
        "job_id": job_id,
        "filename": filename,
        "status": "uploaded",
        "current_stage": "Uploaded",
        "progress_percentage": 0.0,
        "created_at": datetime.now().isoformat(),
        "completed_at": None,
        "error": None,
        "file_path": str(original_file_path),
        "result": None,
    }
    JOBS[job_id] = job
    save_job_metadata(job_id)
    return job


def queue_job(job_id: str) -> Dict[str, Any]:
    """Queues a job for background processing if it is not already running."""
    job = get_job(job_id)
    if not job:
        raise ValueError("Job not found")
        
    if job["status"] in ("pending", "processing"):
        return job

    job["status"] = "pending"
    job["current_stage"] = "Queued"
    job["progress_percentage"] = 0.0
    job["error"] = None
    job["completed_at"] = None
    save_job_metadata(job_id)
    
    job_queue.put(job_id)
    return job


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
            job["current_stage"] = "Starting"
            job["progress_percentage"] = 0.0
            save_job_metadata(job_id)
            
            CURRENT_JOB_ID = job_id
            input_path = Path(job["file_path"])
            config = PipelineConfig()
            
            # Reset pipeline log handlers before run to prevent sharing file outputs across runs
            pipeline_logger = logging.getLogger("pipeline")
            pipeline_logger.handlers = [h for h in pipeline_logger.handlers if not isinstance(h, logging.FileHandler)]
            # Re-attach progress tracking handler
            if progress_handler not in pipeline_logger.handlers:
                pipeline_logger.addHandler(progress_handler)

            try:
                with ProofreadingPipeline(config) as pipeline:
                    result = pipeline.run(input_path, run_id=job_id)
                    job["status"] = "completed"
                    job["current_stage"] = "Completed"
                    job["progress_percentage"] = 100.0
                    job["result"] = result
                    backend_logger.info("Job %s completed successfully.", job_id)
                    
                    # Phase 6 Final: Copy reports to 09_reports/
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
                        backend_logger.info("Copied proofreading reports to 09_reports/ for job %s", job_id)
                    except Exception as copy_err:
                        backend_logger.error("Failed to copy proofreading reports to 09_reports: %s", copy_err)

                    # Trigger Context Analysis in background thread!
                    job_dir = get_job_dir(job_id)
                    run_context_analysis_bg(job_id, job_dir)

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
            job = get_job(job_id)
            if job:
                job["context_analysis_status"] = "running"
                job["context_analysis_stage"] = "Starting Context Analysis"
                job["context_analysis_progress"] = 0.0
                save_job_metadata(job_id)
            
            from src.rag.contextual_analysis.pipeline import ContextAnalysisPipeline
            from src.config import load_preferences
            
            # Load preferences
            prefs = load_preferences()
            model_name = prefs.get("ollama", {}).get("model", "qwen2.5-coder:32b")
            
            consistency_pipeline = ContextAnalysisPipeline(model_name=model_name)
            consistency_pipeline.run_analysis(job_dir, job_id)
            
            # Set completion status
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
                save_job_metadata(job_id)
                
            try:
                import shutil
                reports_dir = job_dir / "09_reports"
                reports_dir.mkdir(parents=True, exist_ok=True)
                if (job_dir / "report.json").exists():
                    shutil.copy2(job_dir / "report.json", reports_dir / "consistency_report.json")
                if (job_dir / "business_report.html").exists():
                    shutil.copy2(job_dir / "business_report.html", reports_dir / "consistency_report.html")
            except Exception as copy_err:
                logging.getLogger("backend").error("Failed to copy consistency reports to 09_reports: %s", copy_err)
                
        except Exception as e:
            import traceback
            logging.getLogger("backend").error("Context Analysis failed for job %s: %s\n%s", job_id, e, traceback.format_exc())
            job = get_job(job_id)
            if job:
                job["context_analysis_status"] = "failed"
                job["context_analysis_stage"] = f"Failed: {str(e)}"
                job["context_analysis_progress"] = 0.0
                save_job_metadata(job_id)
            
    threading.Thread(target=worker, daemon=True).start()

