from __future__ import annotations

from typing import List
import json
import logging
from pathlib import Path
from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from src.config import ROOT_DIR
from backend.schemas import (
    JobStatusResponse,
    ProofreadRequest,
    ResultsResponse,
    UploadResponse,
    ProtectedTermsRequest,
    PreferencesRequest,
    RagChatRequest,
    RagIndexRequest,
    RagModelResponse,
)
from backend.services import (
    create_job,
    get_job,
    get_job_dir,
    queue_job,
    get_all_jobs,
)

router = APIRouter()
backend_logger = logging.getLogger("backend")

# Whitelist of allowed download files to prevent directory traversal attacks
ALLOWED_DOWNLOADS = {
    "annotated_original.html": "10_final/annotated_original.html",
    "corrected_document.html": "10_final/corrected_document.html",
    "report.json": "10_final/report.json",
    "changes.md": "10_final/changes.md",
    "summary.csv": "10_final/summary.csv",
    "raw_text.txt": "01_raw/raw_text.txt",
    "filtered_text.txt": "02_filtered/filtered_text.txt",
    "normalized_text.txt": "03_preprocessed/normalized_text.txt",
    "pipeline.log": "logs/pipeline.log",
    "context_report.json": "report.json",
    "context_report.html": "report.html",
    "business_report.html": "business_report.html",
}



@router.post(
    "/upload",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a document for proofreading",
)
async def upload_document(file: UploadFile = File(...)) -> UploadResponse:
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename cannot be empty.",
        )

    suffix = Path(file.filename).suffix.lower()
    if suffix not in (".pdf", ".docx", ".txt"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file format '{suffix}'. Only PDF, DOCX, and TXT are supported.",
        )

    try:
        # Ensure data/input directory exists
        input_dir = ROOT_DIR / "data" / "input"
        input_dir.mkdir(parents=True, exist_ok=True)

        # Generate unique ID and save file to data/input
        import uuid
        job_id = str(uuid.uuid4().hex)
        safe_filename = f"{job_id}_{file.filename}"
        dest_path = input_dir / safe_filename

        with open(dest_path, "wb") as buffer:
            # Read and write chunks to handle large files efficiently
            while chunk := await file.read(1024 * 1024):
                buffer.write(chunk)

        # Create job entry
        job = create_job(file.filename, dest_path)
        backend_logger.info("Uploaded file %s successfully. Job ID: %s", file.filename, job["job_id"])
        
        return UploadResponse(job_id=job["job_id"], filename=file.filename)
    except Exception as exc:
        backend_logger.error("Failed to upload file %s: %s", file.filename, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process upload: {str(exc)}",
        )


@router.post(
    "/proofread",
    response_model=JobStatusResponse,
    summary="Queue a proofreading job for execution",
)
async def start_proofread(request: ProofreadRequest) -> JobStatusResponse:
    job = get_job(request.job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job with ID '{request.job_id}' not found.",
        )

    try:
        updated_job = queue_job(request.job_id)
        return JobStatusResponse(**updated_job)
    except Exception as exc:
        backend_logger.error("Failed to queue job %s: %s", request.job_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start proofreading: {str(exc)}",
        )


@router.get(
    "/status/{job_id}",
    response_model=JobStatusResponse,
    summary="Get status and live progress of a proofreading job",
)
async def get_status(job_id: str) -> JobStatusResponse:
    job = get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job with ID '{job_id}' not found.",
        )
    return JobStatusResponse(**job)


@router.get(
    "/results/{job_id}",
    response_model=ResultsResponse,
    summary="Get full proofreading results for a completed job",
)
async def get_results(job_id: str) -> ResultsResponse:
    job = get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job with ID '{job_id}' not found.",
        )

    if job["status"] == "failed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Job failed with error: {job.get('error')}",
        )

    if job["status"] != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Job is currently in state '{job['status']}'. Results are only available for completed jobs.",
        )

    job_dir = get_job_dir(job_id)
    
    # 1. Load Issues
    issues = []
    report_path = job_dir / "10_final" / "report.json"
    if report_path.exists():
        try:
            with open(report_path, "r", encoding="utf-8") as f:
                report_data = json.load(f)
                issues = report_data.get("issues", [])
        except Exception as exc:
            backend_logger.warning("Error reading report.json for job %s: %s", job_id, exc)

    # 2. Load Protected Terms
    protected_terms = []
    pt_path = job_dir / "05_protected_terms" / "protected_terms.json"
    if pt_path.exists():
        try:
            with open(pt_path, "r", encoding="utf-8") as f:
                protected_terms = json.load(f)
        except Exception as exc:
            backend_logger.warning("Error reading protected_terms.json for job %s: %s", job_id, exc)

    # 3. Load HTMLs
    annotated_html = ""
    annotated_path = job_dir / "10_final" / "annotated_original.html"
    if annotated_path.exists():
        try:
            annotated_html = annotated_path.read_text(encoding="utf-8")
        except Exception as exc:
            backend_logger.warning("Error reading annotated_original.html for job %s: %s", job_id, exc)

    corrected_html = ""
    corrected_path = job_dir / "10_final" / "corrected_document.html"
    if corrected_path.exists():
        try:
            corrected_html = corrected_path.read_text(encoding="utf-8")
        except Exception as exc:
            backend_logger.warning("Error reading corrected_document.html for job %s: %s", job_id, exc)

    # 4. Load Markdown and CSV Reports
    reports = {}
    changes_path = job_dir / "10_final" / "changes.md"
    if changes_path.exists():
        try:
            reports["changes.md"] = changes_path.read_text(encoding="utf-8")
        except Exception as exc:
            backend_logger.warning("Error reading changes.md for job %s: %s", job_id, exc)

    summary_path = job_dir / "10_final" / "summary.csv"
    if summary_path.exists():
        try:
            reports["summary.csv"] = summary_path.read_text(encoding="utf-8")
        except Exception as exc:
            backend_logger.warning("Error reading summary.csv for job %s: %s", job_id, exc)

    raw_text = ""
    raw_text_path = job_dir / "03_preprocessed" / "normalized_text.txt"
    if raw_text_path.exists():
        try:
            raw_text = raw_text_path.read_text(encoding="utf-8")
        except Exception as exc:
            backend_logger.warning("Error reading normalized_text.txt for job %s: %s", job_id, exc)

    return ResultsResponse(
        job_id=job_id,
        status=job["status"],
        statistics=job.get("result") or {},
        issues=issues,
        protected_terms=protected_terms,
        annotated_html=annotated_html,
        corrected_html=corrected_html,
        reports=reports,
        raw_text=raw_text,
    )


@router.get(
    "/download/{job_id}/{file}",
    summary="Download a specific output file generated by the pipeline",
)
async def download_file(job_id: str, file: str) -> FileResponse:
    job = get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job with ID '{job_id}' not found.",
        )

    if file not in ALLOWED_DOWNLOADS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File download for '{file}' is not permitted.",
        )

    job_dir = get_job_dir(job_id)
    subpath = ALLOWED_DOWNLOADS[file]
    target_path = job_dir / subpath

    if not target_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Requested file '{file}' has not been generated for this job.",
        )

    # Determine media type / headers
    media_type = "application/octet-stream"
    if file.endswith(".html"):
        media_type = "text/html"
    elif file.endswith(".json"):
        media_type = "application/json"
    elif file.endswith(".md"):
        media_type = "text/markdown"
    elif file.endswith(".csv"):
        media_type = "text/csv"
    elif file.endswith(".txt") or file.endswith(".log"):
        media_type = "text/plain"

    return FileResponse(
        path=target_path,
        media_type=media_type,
        filename=file,
    )


@router.get(
    "/documents",
    summary="Get all documents list",
)
async def list_documents():
    jobs = get_all_jobs()
    docs = []
    for j in jobs:
        suffix = Path(j["filename"]).suffix.replace(".", "").upper()
        size_str = "0.0 MB"
        if j.get("file_path"):
            p = Path(j["file_path"])
            if p.exists():
                size_str = f"{(p.stat().st_size / 1024 / 1024):.1f} MB"
        
        uploaded_label = "Uploaded recently"
        if j.get("created_at"):
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(j["created_at"])
                uploaded_label = f"Uploaded {dt.strftime('%b %d, %Y')}"
            except Exception:
                pass
                
        docs.append({
            "id": j["job_id"],
            "filename": j["filename"],
            "fileType": suffix,
            "uploadedLabel": uploaded_label,
            "size": size_str,
            "status": j["status"],
        })
    return docs


@router.get(
    "/stats",
    summary="Get summary stats for dashboard",
)
async def get_stats():
    jobs = get_all_jobs()
    completed = [j for j in jobs if j["status"] == "completed"]
    
    avg_score = 86
    if completed:
        scores = []
        for j in completed:
            issues = []
            job_dir = get_job_dir(j["job_id"])
            report_path = job_dir / "10_final" / "report.json"
            if report_path.exists():
                try:
                    with open(report_path, "r", encoding="utf-8") as f:
                        issues = json.load(f).get("issues", [])
                except Exception:
                    pass
            scores.append(max(45, 100 - len(issues)))
        avg_score = int(sum(scores) / len(scores))
    
    resolved_today = 0
    for j in completed:
        job_dir = get_job_dir(j["job_id"])
        report_path = job_dir / "10_final" / "report.json"
        if report_path.exists():
            try:
                with open(report_path, "r", encoding="utf-8") as f:
                    issues = json.load(f).get("issues", [])
                    resolved_today += len(issues)
            except Exception:
                pass
                
    docs_today = 0
    from datetime import datetime
    start_of_today = datetime.now().date()
    for j in jobs:
        try:
            created_dt = datetime.fromisoformat(j["created_at"]).date()
            if created_dt == start_of_today:
                docs_today += 1
        except Exception:
            pass
            
    return {
        "totalDocuments": len(jobs),
        "grammarAccuracy": avg_score,
        "issuesResolvedToday": resolved_today,
        "documentsToday": docs_today
    }


@router.get(
    "/system-status",
    summary="Get statuses of services",
)
async def get_system_status():
    return [
        {"name": "Backend", "online": True},
        {"name": "LLM (Ollama)", "online": True},
        {"name": "LanguageTool", "online": True},
        {"name": "SymSpell", "online": True}
    ]


@router.post(
    "/documents",
    summary="Upload and start analysis on a document",
)
async def upload_and_start_document(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="Filename cannot be empty.",
        )

    suffix = Path(file.filename).suffix.lower()
    if suffix not in (".pdf", ".docx", ".txt"):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format '{suffix}'. Only PDF, DOCX, and TXT are supported.",
        )

    try:
        input_dir = ROOT_DIR / "data" / "input"
        input_dir.mkdir(parents=True, exist_ok=True)

        import uuid
        job_id = str(uuid.uuid4().hex)
        safe_filename = f"{job_id}_{file.filename}"
        dest_path = input_dir / safe_filename

        with open(dest_path, "wb") as buffer:
            while chunk := await file.read(1024 * 1024):
                buffer.write(chunk)

        # Create job
        job = create_job(file.filename, dest_path)
        # Queue job
        queue_job(job["job_id"])
        
        # Calculate size string
        size_str = f"{(dest_path.stat().st_size / 1024 / 1024):.1f} MB"
        
        return {
            "id": job["job_id"],
            "filename": job["filename"],
            "fileType": suffix.replace(".", "").upper(),
            "uploadedLabel": "Uploaded just now",
            "size": size_str,
            "status": "pending"
        }
    except Exception as exc:
        raise HTTPException(
            status_code=505,
            detail=f"Failed to process upload: {str(exc)}",
        )


@router.get(
    "/documents/{job_id}",
    summary="Get details of a document/job",
)
async def get_document(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=404,
            detail=f"Job with ID '{job_id}' not found.",
        )
    
    suffix = Path(job["filename"]).suffix.replace(".", "").upper()
    size_str = "0.0 MB"
    if job.get("file_path"):
        p = Path(job["file_path"])
        if p.exists():
            size_str = f"{(p.stat().st_size / 1024 / 1024):.1f} MB"

    uploaded_label = "Uploaded recently"
    if job.get("created_at"):
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(job["created_at"])
            uploaded_label = f"Uploaded {dt.strftime('%b %d, %Y')}"
        except Exception:
            pass

    response_data = {
        "id": job["job_id"],
        "filename": job["filename"],
        "fileType": suffix,
        "uploadedLabel": uploaded_label,
        "size": size_str,
        "status": job["status"],
        "current_stage": job.get("current_stage"),
        "progress_percentage": job.get("progress_percentage"),
        "error": job.get("error"),
        "issues": [],
        "protected_terms": [],
        "annotated_html": "",
        "corrected_html": "",
        "reports": {},
        "raw_text": "",
        "statistics": job.get("result") or {},
        "context_analysis_status": job.get("context_analysis_status", "pending"),
        "context_analysis_stage": job.get("context_analysis_stage", ""),
        "context_analysis_progress": job.get("context_analysis_progress", 0.0),
        "context_analysis_issues_count": job.get("context_analysis_issues_count", 0),
        "context_analysis_est_time": job.get("context_analysis_est_time", "N/A"),
        "knowledge_objects_generated": job.get("knowledge_objects_generated", 0),
        "embeddings_completed": job.get("embeddings_completed", 0),
        "index_progress": job.get("index_progress", 0),
        "memory_usage": job.get("memory_usage", "N/A"),
        "cpu_usage": job.get("cpu_usage", "N/A"),
        "current_page": job.get("current_page", 0),
        "total_pages": job.get("total_pages", 0),
        "current_batch": job.get("current_batch", 0),
        "total_batches": job.get("total_batches", 0),
        "estimated_remaining_time": job.get("estimated_remaining_time", "N/A"),
        "memory_safe_mode": job.get("memory_safe_mode", True),
    }

    if job["status"] == "completed":
        job_dir = get_job_dir(job_id)
        
        # Load Issues
        issues = []
        report_path = job_dir / "10_final" / "report.json"
        if report_path.exists():
            try:
                with open(report_path, "r", encoding="utf-8") as f:
                    report_data = json.load(f)
                    issues = report_data.get("issues", [])
            except Exception as exc:
                backend_logger.warning("Error reading report.json for job %s: %s", job_id, exc)
        response_data["issues"] = issues

        # Load Protected Terms
        protected_terms = []
        pt_path = job_dir / "05_protected_terms" / "protected_terms.json"
        if pt_path.exists():
            try:
                with open(pt_path, "r", encoding="utf-8") as f:
                    protected_terms = json.load(f)
            except Exception as exc:
                backend_logger.warning("Error reading protected_terms.json for job %s: %s", job_id, exc)
        response_data["protected_terms"] = protected_terms

        # Load HTMLs
        annotated_html = ""
        annotated_path = job_dir / "10_final" / "annotated_original.html"
        if annotated_path.exists():
            try:
                annotated_html = annotated_path.read_text(encoding="utf-8")
            except Exception as exc:
                backend_logger.warning("Error reading annotated_original.html for job %s: %s", job_id, exc)
        response_data["annotated_html"] = annotated_html

        corrected_html = ""
        corrected_path = job_dir / "10_final" / "corrected_document.html"
        if corrected_path.exists():
            try:
                corrected_html = corrected_path.read_text(encoding="utf-8")
            except Exception as exc:
                backend_logger.warning("Error reading corrected_document.html for job %s: %s", job_id, exc)
        response_data["corrected_html"] = corrected_html

        # Load Reports
        reports = {}
        changes_path = job_dir / "10_final" / "changes.md"
        if changes_path.exists():
            try:
                reports["changes.md"] = changes_path.read_text(encoding="utf-8")
            except Exception as exc:
                backend_logger.warning("Error reading changes.md for job %s: %s", job_id, exc)

        summary_path = job_dir / "10_final" / "summary.csv"
        if summary_path.exists():
            try:
                reports["summary.csv"] = summary_path.read_text(encoding="utf-8")
            except Exception as exc:
                backend_logger.warning("Error reading summary.csv for job %s: %s", job_id, exc)
        response_data["reports"] = reports

        # Load raw_text
        raw_text = ""
        raw_text_path = job_dir / "03_preprocessed" / "normalized_text.txt"
        if raw_text_path.exists():
            try:
                raw_text = raw_text_path.read_text(encoding="utf-8")
            except Exception as exc:
                backend_logger.warning("Error reading normalized_text.txt for job %s: %s", job_id, exc)
        response_data["raw_text"] = raw_text

    return response_data


@router.delete(
    "/documents/{job_id}",
    summary="Delete a document and its data",
)
async def delete_document(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=404,
            detail=f"Job with ID '{job_id}' not found.",
        )
    
    # 1. Delete original input file if it exists
    if job.get("file_path"):
        try:
            p = Path(job["file_path"])
            if p.exists():
                p.unlink()
        except Exception as e:
            backend_logger.warning("Error deleting original file: %s", e)
            
    # 2. Delete job directory in output
    try:
        import shutil
        job_dir = get_job_dir(job_id)
        if job_dir.exists():
            shutil.rmtree(job_dir)
    except Exception as e:
        backend_logger.warning("Error deleting output directory: %s", e)
        
    # 3. Delete from in-memory store
    from backend.services import JOBS
    if job_id in JOBS:
        del JOBS[job_id]
        
    return {"status": "success", "message": f"Document {job_id} deleted."}


@router.get(
    "/notifications",
    summary="Get recent notifications",
)
async def get_notifications():
    return [
        {"id": 1, "text": "Grammar review engine is fully online.", "time": "Just now"},
        {"id": 2, "text": "LanguageTool dictionary loaded successfully.", "time": "5m ago"},
        {"id": 3, "text": "Symspell spelling checks initialized.", "time": "10m ago"}
    ]


@router.get(
    "/settings/protected-terms",
    summary="Get custom whitelisted protected terms",
)
async def get_protected_terms_setting():
    path = ROOT_DIR / "data" / "protected_terms_whitelist.json"
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            backend_logger.warning("Error reading protected_terms_whitelist.json: %s", e)
    return []


@router.post(
    "/settings/protected-terms",
    summary="Save custom whitelisted protected terms",
)
async def save_protected_terms_setting(request: ProtectedTermsRequest):
    path = ROOT_DIR / "data" / "protected_terms_whitelist.json"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(request.terms, f, indent=2, ensure_ascii=False)
        return {"status": "success", "message": "Protected terms updated."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save protected terms: {str(e)}")


@router.get(
    "/settings/preferences",
    summary="Get user preference settings",
)
async def get_preferences_setting():
    path = ROOT_DIR / "data" / "preferences.json"
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            backend_logger.warning("Error reading preferences.json: %s", e)
    
    from src.config import PipelineConfig
    cfg = PipelineConfig()
    return {
        "ollama_host": cfg.ollama.host,
        "ollama_model": cfg.ollama.model,
        "languagetool_language": cfg.languagetool.language,
        "confidence_threshold": 40,
    }


@router.post(
    "/settings/preferences",
    summary="Save user preference settings",
)
async def save_preferences_setting(request: PreferencesRequest):
    path = ROOT_DIR / "data" / "preferences.json"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(request.preferences, f, indent=2, ensure_ascii=False)
        return {"status": "success", "message": "Preferences updated."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save preferences: {str(e)}")


@router.get(
    "/settings/system-info",
    summary="Get system info",
)
async def get_system_info():
    import sys
    import platform
    from src.config import PipelineConfig
    cfg = PipelineConfig()
    
    import requests
    ollama_status = "Offline"
    try:
        res = requests.get(cfg.ollama.host, timeout=2)
        if res.status_code == 200:
            ollama_status = "Online"
    except Exception:
        pass

    return {
        "os": platform.system(),
        "os_version": platform.version(),
        "python_version": sys.version.split()[0],
        "ollama_status": ollama_status,
        "ollama_host": cfg.ollama.host,
        "active_model": cfg.ollama.model,
    }


@router.post("/log-error")
async def log_error(payload: dict):
    backend_logger.error(f"====== FRONTEND RUNTIME ERROR ======\n{json.dumps(payload, indent=2)}\n====================================")
    return {"status": "success"}


# =====================================================================
# RAG ENDPOINTS (Phase 6)
# =====================================================================

_chat_service = None

def get_chat_service():
    global _chat_service
    if _chat_service is None:
        from src.rag.chat_service import ChatService
        _chat_service = ChatService()
    return _chat_service


@router.post("/rag/chat", summary="Query the AI Document Assistant")
async def rag_chat(request: RagChatRequest):
    try:
        service = get_chat_service()
        response = service.answer_question(
            document_id=request.document_id,
            question=request.question,
            model_id=request.selected_model,
            history_depth=request.conversation_history_depth
        )
        return response
    except Exception as e:
        import traceback
        backend_logger.error(f"Error in RAG chat: {e}\n{traceback.format_exc()}")
        raise HTTPException(
            status_code=500,
            detail=f"Chat generation failed: {str(e)}"
        )


@router.post("/rag/index", summary="Index a document for RAG search manually")
async def index_document_rag(request: RagIndexRequest):
    from src.rag.index_manager import IndexManager
    from backend.services import get_job, get_job_dir
    
    job = get_job(request.document_id)
    if not job:
        raise HTTPException(status_code=404, detail="Document job not found")
        
    job_dir = get_job_dir(request.document_id)
    chunks_file = job_dir / "document_chunks.json"
    if not chunks_file.exists():
        raise HTTPException(status_code=400, detail="No chunks generated for this document yet.")
        
    try:
        import json
        from src.rag.chunk_schema import ChunkMetadata, DocumentChunk
        from src.rag.document_schema import BoundingBox
        with open(chunks_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        chunks = []
        for c in data.get("chunks", []):
            meta_data = c.get("metadata", {})
            bboxes = [BoundingBox(**bbox_data) for bbox_data in meta_data.get("bounding_boxes", []) if bbox_data]
            meta = ChunkMetadata(
                chunk_id=meta_data.get("chunk_id"),
                document_id=meta_data.get("document_id"),
                page_number=meta_data.get("page_number"),
                chunk_type=meta_data.get("chunk_type"),
                heading=meta_data.get("heading"),
                section=meta_data.get("section"),
                hierarchy_path=meta_data.get("hierarchy_path", []),
                source_element_ids=meta_data.get("source_element_ids", []),
                word_count=meta_data.get("word_count"),
                token_estimate=meta_data.get("token_estimate"),
                bounding_boxes=bboxes,
                image_id=meta_data.get("image_id"),
                table_id=meta_data.get("table_id")
              )
            chunks.append(DocumentChunk(content=c.get("content"), metadata=meta))
            
        index_manager = IndexManager.from_config()
        success = index_manager.index_document(request.document_id, chunks)
        if success:
            return {"status": "success", "message": "Document indexed successfully."}
        else:
            raise HTTPException(status_code=500, detail="Indexing failed.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to index: {str(e)}")


@router.get("/rag/models", response_model=List[RagModelResponse], summary="Get available RAG models")
async def get_rag_models() -> List[RagModelResponse]:
    from src.rag.llm import get_available_models, DEFAULT_MODEL_ID
    models = get_available_models()
    return [
        RagModelResponse(
            id=m.id,
            display_name=m.display_name,
            description=m.description,
            recommended=(m.id == DEFAULT_MODEL_ID)
        ) for m in models
    ]


@router.get("/rag/history/{document_id}", summary="Get chat history for a document")
async def get_rag_history(document_id: str):
    service = get_chat_service()
    history = service.memory.get_history(document_id, depth=50)
    return {"document_id": document_id, "history": history}


@router.delete("/rag/history/{document_id}", summary="Clear chat history for a document")
async def delete_rag_history(document_id: str):
    service = get_chat_service()
    service.memory.clear_history(document_id)
    return {"status": "success", "message": f"History cleared for document {document_id}"}


@router.post("/rag/history/{document_id}/clear", summary="Clear chat history for a document")
async def clear_rag_history_post(document_id: str):
    service = get_chat_service()
    service.memory.clear_history(document_id)
    return {"status": "success", "message": f"History cleared for document {document_id}"}


@router.get("/rag/stats/{document_id}", summary="Get RAG statistics for a document")
async def get_rag_stats(document_id: str):
    from backend.services import get_job_dir
    import json
    import re
    job_dir = get_job_dir(document_id)
    chunks_file = job_dir / "06_chunks" / "document_chunks.json"
    if not chunks_file.exists():
        chunks_file = job_dir / "document_chunks.json"
        
    if not chunks_file.exists():
        return {
            "chunks": 0, "tables": 0, "images": 0, "pages": 0, "ocr": 0,
            "embeddings": 0, "vision_processed": 0, "processing_time": 0.0,
            "inspection_report_url": f"/outputs/{document_id}/inspection_report.html"
        }
    try:
        with open(chunks_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        chunks = data.get("chunks", [])
        
        # Read embedding summary if available
        emb_file = job_dir / "07_embeddings" / "embedding_summary.json"
        embeddings_count = len(chunks)
        ocr_count = 0
        vision_processed = 0
        if emb_file.exists():
            try:
                with open(emb_file, "r", encoding="utf-8") as ef:
                    ef_data = json.load(ef)
                    embeddings_count = ef_data.get("total_chunks", len(chunks))
                    ocr_count = ef_data.get("ocr_chunks", 0)
                    # Vision processed count is the number of image descriptions generated
                    vision_processed = ef_data.get("image_chunks", 0)
            except Exception:
                pass
                
        tables = sum(1 for c in chunks if c.get("metadata", {}).get("chunk_type") == "table")
        images = sum(1 for c in chunks if c.get("metadata", {}).get("chunk_type") == "image")
        pages = max([c.get("metadata", {}).get("page_number", 1) for c in chunks]) if chunks else 1
        
        processing_time = 0.0
        readme_file = job_dir / "README.md"
        if readme_file.exists():
            try:
                readme_text = readme_file.read_text(encoding="utf-8")
                match = re.search(r'Processing Time:\s*([\d\.]+)', readme_text)
                if match:
                    processing_time = float(match.group(1))
            except Exception:
                pass
                
        return {
            "chunks": len(chunks),
            "tables": tables,
            "images": images,
            "pages": pages,
            "ocr": ocr_count,
            "embeddings": embeddings_count,
            "vision_processed": vision_processed,
            "processing_time": processing_time,
            "inspection_report_url": f"/outputs/{document_id}/inspection_report.html"
        }
    except Exception:
        return {
            "chunks": 0, "tables": 0, "images": 0, "pages": 0, "ocr": 0,
            "embeddings": 0, "vision_processed": 0, "processing_time": 0.0,
            "inspection_report_url": f"/outputs/{document_id}/inspection_report.html"
        }


@router.post("/context-analysis/run/{job_id}", summary="Run Contextual Consistency Analysis")
async def run_context_analysis(job_id: str):
    from backend.services import get_job, get_job_dir, run_context_analysis_bg
    
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    job_dir = get_job_dir(job_id)
    try:
        run_context_analysis_bg(job_id, job_dir)
        return {"status": "running", "message": "Contextual Consistency Analysis started in background."}
    except Exception as e:
        import traceback
        backend_logger.error(f"Error running context analysis background thread: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/context-analysis/report/{job_id}", summary="Get Contextual Consistency Report")
async def get_context_analysis_report(job_id: str):
    from backend.services import get_job_dir
    job_dir = get_job_dir(job_id)
    report_file = job_dir / "report.json"
    if not report_file.exists():
        raise HTTPException(
            status_code=404, 
            detail="No Context Analysis has been generated for this document."
        )
    try:
        with open(report_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read report: {str(e)}")






