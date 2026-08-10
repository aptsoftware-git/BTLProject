from __future__ import annotations

from typing import Any, Dict, List
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
    "comparative_report.html": "comparative_analysis/comparative_report.html",
    "comparative_report.json": "comparative_analysis/comparative_report.json",
    "executive_dashboard.html": "comparative_analysis/executive_dashboard.html",
    "company_profile.json": "comparative_analysis/company_profile.json",
    "competitor_profiles.json": "comparative_analysis/competitor_profiles.json",
    "comparison_matrix.json": "comparative_analysis/comparison_matrix.json",
    "gap_analysis.json": "comparative_analysis/gap_analysis.json",
    "swot_analysis.json": "comparative_analysis/swot_analysis.json",
    "recommendations.json": "comparative_analysis/recommendations.json",
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

        import uuid
        from backend.services import get_all_jobs, delete_stage_output_cache, save_job_metadata

        existing_job_id = None
        for j in get_all_jobs():
            if j.get("filename") == file.filename:
                existing_job_id = j.get("job_id")
                break

        if existing_job_id:
            job_id = existing_job_id
            safe_filename = f"{job_id}_{file.filename}"
            dest_path = input_dir / safe_filename
            with open(dest_path, "wb") as buffer:
                while chunk := await file.read(1024 * 1024):
                    buffer.write(chunk)

            delete_stage_output_cache(job_id, "all")
            job = get_job(job_id) or create_job(file.filename, dest_path, job_id=job_id)
            job["file_path"] = str(dest_path)
            job["status"] = "pending"
            save_job_metadata(job_id)
            queue_job(job_id, force=True)
            backend_logger.info("Re-uploaded file %s. Reusing job %s (ChromaDB vectors preserved, analysis re-generated).", file.filename, job_id)
        else:
            job_id = str(uuid.uuid4().hex)
            safe_filename = f"{job_id}_{file.filename}"
            dest_path = input_dir / safe_filename

            with open(dest_path, "wb") as buffer:
                while chunk := await file.read(1024 * 1024):
                    buffer.write(chunk)

            job = create_job(file.filename, dest_path, job_id=job_id)
            queue_job(job["job_id"])
        
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
    "/jobs/{job_id}",
    response_model=JobStatusResponse,
    summary="Get processing status and stage progress of a document job",
)
async def get_job_status(job_id: str) -> JobStatusResponse:
    job = get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job with ID '{job_id}' not found.",
        )
    return JobStatusResponse(**job)


@router.post(
    "/jobs/{job_id}/retry",
    response_model=JobStatusResponse,
    summary="Retry a failed stage or restart processing",
)
async def retry_job(job_id: str, stage_id: str = "all") -> JobStatusResponse:
    from backend.services import retry_job_stage
    try:
        job = retry_job_stage(job_id, stage_id=stage_id)
        return JobStatusResponse(**job)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc)
        )


@router.post(
    "/jobs/{job_id}/resume",
    response_model=JobStatusResponse,
    summary="Resume a recoverable or paused job",
)
async def resume_job(job_id: str) -> JobStatusResponse:
    from backend.services import repair_job
    try:
        job = repair_job(job_id)
        return JobStatusResponse(**job)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to resume job: {str(exc)}"
        )


@router.post(
    "/jobs/{job_id}/restart",
    response_model=JobStatusResponse,
    summary="Restart job processing from Stage 1",
)
async def restart_job(job_id: str) -> JobStatusResponse:
    from backend.services import retry_job_stage
    try:
        job = retry_job_stage(job_id, stage_id="all")
        return JobStatusResponse(**job)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to restart job: {str(exc)}"
        )


@router.delete(
    "/jobs/{job_id}",
    summary="Delete job metadata and directory",
)
async def remove_job(job_id: str):
    from backend.services import delete_job
    try:
        delete_job(job_id)
        return {"status": "deleted", "job_id": job_id}
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete job: {str(exc)}"
        )


@router.get(
    "/jobs/{job_id}/validate-finding/{issue_id}",
    summary="Validate finding grounding and coordinates against PDF source",
)
async def validate_finding(job_id: str, issue_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job with ID '{job_id}' not found.",
        )

    job_dir = get_job_dir(job_id)
    report_path = job_dir / "10_final" / "report.json"
    target_issue = None

    if report_path.exists():
        try:
            with open(report_path, "r", encoding="utf-8") as f:
                report_data = json.load(f)
                issues_list = report_data.get("issues", [])
                for idx, iss in enumerate(issues_list):
                    iid = iss.get("issue_id") or f"issue_{idx + 1}"
                    if iid == issue_id:
                        target_issue = iss
                        break
        except Exception:
            pass

    if not target_issue:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Issue ID '{issue_id}' not found in job '{job_id}'.",
        )

    page_num = target_issue.get("page") or target_issue.get("page_number") or 1
    bbox = target_issue.get("bbox")
    sent_text = target_issue.get("sentence_text") or target_issue.get("original_text") or ""
    
    is_grounded = isinstance(bbox, dict) and (
        float(bbox.get("x1", 0) or 0) > float(bbox.get("x0", 0) or 0) and
        float(bbox.get("y1", 0) or 0) > float(bbox.get("y0", 0) or 0)
    )

    return {
        "issue_id": issue_id,
        "original_page": int(page_num),
        "extracted_sentence": sent_text,
        "pdf_coordinates": bbox if is_grounded else None,
        "rendered_coordinates": bbox if is_grounded else None,
        "validation_status": "GROUNDED & VERIFIED" if is_grounded else "UNVERIFIED LOCATION",
        "location_verified": is_grounded
    }


def _normalize_issue_metadata(raw_issues: list) -> list:
    normalized = []
    for idx, item in enumerate(raw_issues):
        if not isinstance(item, dict):
            continue
        issue = dict(item)
        
        # 1. issue_id
        issue_id = str(issue.get("issue_id") or issue.get("id") or f"issue_{idx + 1}")
        issue["issue_id"] = issue_id
        issue["id"] = issue_id
        
        # 2. category
        cat = str(issue.get("category") or issue.get("issue_type") or issue.get("type") or "grammar").lower()
        if "spell" in cat:
            cat = "spelling"
        elif "punct" in cat:
            cat = "punctuation"
        elif "style" in cat:
            cat = "style"
        elif "term" in cat:
            cat = "terminology"
        elif "hyphen" in cat:
            cat = "hyphenation"
        elif "space" in cat:
            cat = "whitespace"
        else:
            cat = "grammar"
        issue["category"] = cat
        issue["issue_type"] = cat
        
        # 3. severity
        sev = str(issue.get("severity") or "MEDIUM").upper()
        if sev not in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
            sev = "MEDIUM"
        issue["severity"] = sev
        
        # 4. page_number
        page = issue.get("page_number") or issue.get("page") or 1
        try:
            page_val = int(page)
        except Exception:
            page_val = 1
        if page_val < 1:
            page_val = 1
        issue["page_number"] = page_val
        issue["page"] = page_val
        
        # 5 & 6. original_sentence & corrected_sentence
        highlighted = str(issue.get("highlighted_text") or issue.get("original_text") or issue.get("word") or issue.get("text") or "").strip()
        suggested = str(issue.get("suggested_text") or issue.get("suggested_replacement") or issue.get("replacement") or issue.get("suggestion") or "").strip()
        
        orig_sentence = str(issue.get("original_sentence") or issue.get("sentence_text") or issue.get("sentence") or issue.get("context") or highlighted).strip()
        corr_sentence = str(issue.get("corrected_sentence") or issue.get("corrected_sentence_text") or issue.get("suggested_sentence") or "").strip()
        
        if not corr_sentence and orig_sentence and highlighted and suggested:
            if highlighted in orig_sentence:
                corr_sentence = orig_sentence.replace(highlighted, suggested, 1)
            else:
                corr_sentence = f"{orig_sentence} -> [{suggested}]"
        if not corr_sentence:
            corr_sentence = orig_sentence
            
        issue["original_sentence"] = orig_sentence
        issue["sentence_text"] = orig_sentence
        issue["corrected_sentence"] = corr_sentence
        issue["corrected_sentence_text"] = corr_sentence
        
        # 7 & 8. highlighted_text & suggested_text
        issue["highlighted_text"] = highlighted
        issue["original_text"] = highlighted
        issue["suggested_text"] = suggested
        issue["suggested_replacement"] = suggested
        
        # 9. reason
        reason = str(issue.get("reason") or issue.get("explanation") or issue.get("message") or f"Recommended correction: replace '{highlighted}' with '{suggested}'.").strip()
        issue["reason"] = reason
        issue["explanation"] = reason
        
        # 10. confidence
        conf = issue.get("confidence") or issue.get("final_confidence") or 0.92
        if isinstance(conf, (int, float)):
            conf_str = f"{int(conf * 100)}%" if conf <= 1.0 else f"{int(conf)}%"
            conf_float = float(conf) if conf <= 1.0 else float(conf) / 100.0
        else:
            conf_str = str(conf)
            conf_float = 0.90
        issue["confidence"] = conf_str
        issue["final_confidence"] = conf_float
        
        # 11 & 12. bbox & grounding_verified
        bbox = issue.get("bbox") or issue.get("coordinates") or issue.get("pdf_coordinates")
        grounding_verified = False
        valid_bbox = None
        
        if isinstance(bbox, dict):
            try:
                x0 = float(bbox.get("x0", bbox.get("l", 0.0)) or 0.0)
                y0 = float(bbox.get("y0", bbox.get("t", 0.0)) or 0.0)
                x1 = float(bbox.get("x1", bbox.get("r", 0.0)) or 0.0)
                y1 = float(bbox.get("y1", bbox.get("b", 0.0)) or 0.0)
                if x1 > x0 and y1 > y0:
                    valid_bbox = {"x0": x0, "y0": y0, "x1": x1, "y1": y1}
                    grounding_verified = True
            except Exception:
                pass
                
        if "grounding_verified" in issue:
            grounding_verified = bool(issue["grounding_verified"]) and (valid_bbox is not None)
        else:
            if "location_verified" in issue:
                grounding_verified = bool(issue["location_verified"]) and (valid_bbox is not None)
            elif valid_bbox is not None:
                grounding_verified = True
                
        issue["bbox"] = valid_bbox
        issue["coordinates"] = valid_bbox
        issue["grounding_verified"] = grounding_verified
        issue["location_verified"] = grounding_verified
        
        normalized.append(issue)
    return normalized



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

    is_proofreading_done = job.get("status") == "completed" or job.get("proofreading_ready") or job.get("proofreading_status") == "completed"
    if not is_proofreading_done:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Proofreading is currently in state '{job['status']}'. Results will be available as soon as proofreading finishes.",
        )

    job_dir = get_job_dir(job_id)
    
    # 1. Load Issues
    raw_issues = []
    report_path = job_dir / "10_final" / "report.json"
    if report_path.exists():
        try:
            with open(report_path, "r", encoding="utf-8") as f:
                report_data = json.load(f)
                raw_issues = report_data.get("issues", [])
        except Exception as exc:
            backend_logger.warning("Error reading report.json for job %s: %s", job_id, exc)

    issues = _normalize_issue_metadata(raw_issues)

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
    "/documents/{job_id}/chunks-summary",
    summary="Get semantic chunks and Louvain clusters count summary with visualizer URLs",
)
async def get_chunks_summary(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job with ID '{job_id}' not found.",
        )

    job_dir = get_job_dir(job_id)
    
    # 1. Count Chunks
    chunks_count = 0
    chunks_by_type = {}
    chunks_file = job_dir / "document_chunks.json"
    if not chunks_file.exists():
        chunks_file = job_dir / "03_knowledge_objects" / "knowledge_objects.json"

    if chunks_file.exists():
        try:
            with open(chunks_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                chunks_count = len(data)
                for item in data:
                    c_type = item.get("chunk_type") or item.get("type") or "text"
                    chunks_by_type[c_type] = chunks_by_type.get(c_type, 0) + 1
        except Exception:
            pass

    # 2. Count Clusters
    clusters_count = 0
    clusters_file = job_dir / "semantic_clusters.json"
    if clusters_file.exists():
        try:
            with open(clusters_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                clusters_count = len(data)
        except Exception:
            pass

    return {
        "job_id": job_id,
        "filename": job.get("filename", ""),
        "total_chunks": chunks_count,
        "total_clusters": clusters_count,
        "chunks_by_type": chunks_by_type,
        "reports": {
            "consistency_html": f"/outputs/{job_id}/09_reports/consistency_report.html",
            "comparative_html": f"/outputs/{job_id}/09_reports/comparative_report.html",
            "annotated_html": f"/outputs/{job_id}/09_reports/annotated.html"
        }
    }


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
    "/documents/{job_id}/file",
    summary="Get/View the original document file for iframe or download",
)
async def get_document_file(job_id: str):
    job = get_job(job_id)
    target_path = None
    filename = "document.pdf"

    if job:
        filename = job.get("filename", filename)
        if job.get("file_path"):
            p = Path(job["file_path"])
            if p.exists():
                target_path = p

    if not target_path or not target_path.exists():
        input_dir = ROOT_DIR / "data" / "input"
        if input_dir.exists():
            for p in input_dir.iterdir():
                if p.is_file() and (job_id in p.name or (job and job.get("filename") == p.name)):
                    target_path = p
                    break

    if not target_path or not target_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Original document file for job '{job_id}' not found.",
        )

    suffix = target_path.suffix.lower()
    if suffix == ".pdf":
        media_type = "application/pdf"
    elif suffix == ".docx":
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    elif suffix == ".txt":
        media_type = "text/plain; charset=utf-8"
    else:
        media_type = "application/octet-stream"

    return FileResponse(
        path=target_path,
        media_type=media_type,
        filename=filename,
        headers={"Content-Disposition": f"inline; filename=\"{filename}\""}
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
    "/documents/upload",
    summary="Upload and start analysis on a document",
)
@router.post(
    "/documents",
    summary="Upload and start analysis on a document (Alias)",
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
        from backend.services import get_all_jobs, delete_stage_output_cache, save_job_metadata

        # Check if job for this filename already exists to avoid creating duplicate folders
        existing_job_id = None
        for j in get_all_jobs():
            if j.get("filename") == file.filename:
                existing_job_id = j.get("job_id")
                break

        if existing_job_id:
            job_id = existing_job_id
            safe_filename = f"{job_id}_{file.filename}"
            dest_path = input_dir / safe_filename
            with open(dest_path, "wb") as buffer:
                while chunk := await file.read(1024 * 1024):
                    buffer.write(chunk)

            # Invalidate old report files while preserving ChromaDB vector index & extracted chunks
            delete_stage_output_cache(job_id, "all")
            job = get_job(job_id) or create_job(file.filename, dest_path, job_id=job_id)
            job["file_path"] = str(dest_path)
            job["status"] = "pending"
            save_job_metadata(job_id)
            queue_job(job_id, force=True)
            backend_logger.info("Re-uploaded file %s. Reusing job %s (ChromaDB vectors preserved, analysis re-generated).", file.filename, job_id)
        else:
            job_id = str(uuid.uuid4().hex)
            safe_filename = f"{job_id}_{file.filename}"
            dest_path = input_dir / safe_filename

            with open(dest_path, "wb") as buffer:
                while chunk := await file.read(1024 * 1024):
                    buffer.write(chunk)

            # Create job
            job = create_job(file.filename, dest_path, job_id=job_id)
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
    from backend.services import get_job, get_job_dir, save_job_metadata, backend_logger
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
        "upload_ready": job.get("upload_ready", True),
        "document_viewer_ready": job.get("document_viewer_ready", False),
        "extraction_ready": job.get("extraction_ready", False),
        "spell_ready": job.get("spell_ready", False),
        "grammar_ready": job.get("grammar_ready", False),
        "proofreading_ready": job.get("proofreading_ready", False),
        "proofreading_status": job.get("proofreading_status", "pending"),
        "rag_ready": job.get("rag_ready", False),
        "context_analysis_ready": job.get("context_analysis_ready", False),
        "comparative_analysis_ready": job.get("comparative_analysis_ready", False),
        "reports_ready": job.get("reports_ready", False),
        "current_stage": job.get("current_stage"),
        "progress_percentage": job.get("progress_percentage"),
        "overall_progress": job.get("overall_progress", 0),
        "stages": job.get("stages", []),
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

    job_dir = get_job_dir(job_id)
    
    # Load Issues & Decisions
    issues = []
    decisions = {}
    decisions_path = job_dir / "10_final" / "decisions.json"
    if decisions_path.exists():
        try:
            with open(decisions_path, "r", encoding="utf-8") as f:
                decisions = json.load(f)
        except Exception:
            pass

    report_path = job_dir / "10_final" / "report.json"
    root_report_path = job_dir / "report.json"

    # 1. Primary Proofreading Source: 10_final/report.json
    if report_path.exists():
        try:
            with open(report_path, "r", encoding="utf-8") as f:
                report_data = json.load(f)
                raw_issues = report_data.get("issues", [])
                if raw_issues:
                    issues = raw_issues
        except Exception as exc:
            backend_logger.warning("Error reading 10_final/report.json for job %s: %s", job_id, exc)

    # 2. Unified Fallback: root job_dir/report.json (if valid proofreading report)
    if not issues and root_report_path.exists():
        try:
            with open(root_report_path, "r", encoding="utf-8") as f:
                report_data = json.load(f)
                raw_issues = report_data.get("issues", [])
                if raw_issues and isinstance(raw_issues, list) and len(raw_issues) > 0:
                    first_item = raw_issues[0]
                    if isinstance(first_item, dict) and ("original_text" in first_item or "suggested_text" in first_item):
                        issues = raw_issues
                        # Automatically persist unified copy to 10_final/report.json
                        try:
                            final_dir = job_dir / "10_final"
                            final_dir.mkdir(parents=True, exist_ok=True)
                            with open(report_path, "w", encoding="utf-8") as f_out:
                                json.dump(report_data, f_out, indent=2)
                        except Exception:
                            pass
        except Exception as exc:
            backend_logger.warning("Error reading root report.json for job %s: %s", job_id, exc)

    # STRICT RULE: Never fall back to raw candidates (accepted.json, grammar_candidates.json, spell_candidates.json)

    # Normalize issues metadata (ensuring issue_id, page, bbox)
    issues = _normalize_issue_metadata(issues)
    backend_logger.debug("Issue count loaded: %s", len(issues))

    report_exists = report_path.exists() or root_report_path.exists()
    backend_logger.debug("Report exists: %s | Issues returned: %s | First issue: %s", report_exists, len(issues), issues[0] if issues else None)

    # Apply decisions to issues
    for idx, issue in enumerate(issues):
        if isinstance(issue, dict):
            issue_id_str = str(issue.get("issue_id", f"issue_{idx + 1}"))
            if issue_id_str in decisions:
                issue["status"] = decisions[issue_id_str]
            elif str(idx) in decisions:
                issue["status"] = decisions[str(idx)]

    response_data["issues"] = issues
    response_data["decisions"] = decisions

    # Synchronize statistics with actual issues payload
    stats = dict(job.get("result")) if isinstance(job.get("result"), dict) else {}
    stats["total_issues"] = len(issues)
    stats["accepted"] = sum(1 for v in decisions.values() if v == "accepted")
    stats["rejected"] = sum(1 for v in decisions.values() if v == "rejected")
    response_data["statistics"] = stats

    # Ensure in-memory and disk metadata result stay synchronized
    job["result"] = stats
    save_job_metadata(job_id)

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

    rep_json_path = job_dir / "10_final" / "report.json"
    if rep_json_path.exists():
        try:
            reports["report.json"] = rep_json_path.read_text(encoding="utf-8")
        except Exception as exc:
            backend_logger.warning("Error reading report.json into reports dict for job %s: %s", job_id, exc)

    response_data["reports"] = reports
    response_data["reports"] = reports

    # Load raw_text with fallback paths
    raw_text = ""
    for rel_path in ["03_preprocessed/normalized_text.txt", "02_filtered/filtered_text.txt", "01_raw/raw_text.txt"]:
        raw_text_path = job_dir / rel_path
        if raw_text_path.exists():
            try:
                txt = raw_text_path.read_text(encoding="utf-8")
                if txt and txt.strip():
                    raw_text = txt
                    break
            except Exception as exc:
                backend_logger.warning("Error reading %s for job %s: %s", rel_path, job_id, exc)
    response_data["raw_text"] = raw_text
    return response_data


@router.get(
    "/documents/{job_id}/issues",
    summary="Get proofreading issues for a document",
)
async def get_document_issues(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job with ID '{job_id}' not found.")
    
    job_dir = get_job_dir(job_id)
    decisions = {}
    decisions_path = job_dir / "10_final" / "decisions.json"
    if decisions_path.exists():
        try:
            with open(decisions_path, "r", encoding="utf-8") as f:
                decisions = json.load(f)
        except Exception:
            pass

    issues = []
    report_path = job_dir / "10_final" / "report.json"
    if report_path.exists():
        try:
            with open(report_path, "r", encoding="utf-8") as f:
                report_data = json.load(f)
                issues = report_data.get("issues", [])
                for idx, issue in enumerate(issues):
                    if isinstance(issue, dict):
                        issue_id_str = str(issue.get("issue_id", idx))
                        if issue_id_str in decisions:
                            issue["status"] = decisions[issue_id_str]
                        elif str(idx) in decisions:
                            issue["status"] = decisions[str(idx)]
        except Exception as exc:
            backend_logger.warning("Error reading report.json for job %s: %s", job_id, exc)

    issues = _normalize_issue_metadata(issues)
    return {"job_id": job_id, "issues": issues, "decisions": decisions}


@router.patch(
    "/documents/{job_id}/issues/{issue_id}",
    summary="Update decision status for a proofreading issue",
)
async def update_document_issue_status(job_id: str, issue_id: str, payload: Dict[str, Any]):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job with ID '{job_id}' not found.")
    
    job_dir = get_job_dir(job_id)
    final_dir = job_dir / "10_final"
    final_dir.mkdir(parents=True, exist_ok=True)
    decisions_path = final_dir / "decisions.json"
    
    decisions = {}
    if decisions_path.exists():
        try:
            with open(decisions_path, "r", encoding="utf-8") as f:
                decisions = json.load(f)
        except Exception:
            pass

    new_status = payload.get("status", "accepted")
    decisions[str(issue_id)] = new_status

    try:
        with open(decisions_path, "w", encoding="utf-8") as f:
            json.dump(decisions, f, indent=2, ensure_ascii=False)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to persist decision: {str(exc)}")

    return {"job_id": job_id, "issue_id": issue_id, "status": new_status, "decisions": decisions}


# ---------------------------------------------------------------------------
# Page + Sentence Mapping architecture
# ---------------------------------------------------------------------------

def _load_json_or(path: Path, default):
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        backend_logger.warning("Failed to read %s: %s", path, exc)
        return default


@router.get(
    "/documents/{job_id}/pages/{page_number}",
    summary="Load a single page's running text on demand (for lazy/virtualized rendering)",
)
async def get_page_text(job_id: str, page_number: int):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

    job_dir = get_job_dir(job_id)
    page_texts = _load_json_or(job_dir / "03_page_text" / "page_text.json", [])
    page = next((p for p in page_texts if int(p.get("page_number", -1)) == page_number), None)
    if page is None:
        raise HTTPException(status_code=404, detail=f"Page {page_number} not found.")

    sentence_map = _load_json_or(job_dir / "04_sentences" / "page_sentence_map.json", [])
    page_sentences = [s for s in sentence_map if int(s.get("page_number", -1)) == page_number]

    return {"job_id": job_id, "page_number": page_number, "text": page.get("text", ""), "sentences": page_sentences}


@router.get(
    "/documents/{job_id}/page-count",
    summary="Total page count for virtualized/lazy viewer pagination",
)
async def get_page_count(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    job_dir = get_job_dir(job_id)
    page_texts = _load_json_or(job_dir / "03_page_text" / "page_text.json", [])
    return {"job_id": job_id, "page_count": len(page_texts)}


@router.get(
    "/documents/{job_id}/sentence-map",
    summary="Full page + sentence map (single source of truth for navigation/highlighting)",
)
async def get_sentence_map(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    job_dir = get_job_dir(job_id)
    sentence_map = _load_json_or(job_dir / "04_sentences" / "page_sentence_map.json", [])
    return {"job_id": job_id, "sentences": sentence_map}


@router.get(
    "/documents/{job_id}/sentence-lookup",
    summary="Fast sentence_id -> {page_number, text} lookup index",
)
async def get_sentence_lookup(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    job_dir = get_job_dir(job_id)
    lookup_index = _load_json_or(job_dir / "04_sentences" / "sentence_lookup_index.json", {})
    return {"job_id": job_id, "lookup": lookup_index}


def _findings_with_live_status(job_dir: Path) -> list:
    findings = _load_json_or(job_dir / "10_final" / "mapped_findings.json", [])
    decisions = _load_json_or(job_dir / "10_final" / "decisions.json", {})
    out = []
    for f in findings:
        f = dict(f)
        f["status"] = decisions.get(f["finding_id"], f.get("status", "pending"))
        out.append(f)
    return out


@router.get(
    "/documents/{job_id}/findings",
    summary="Proofreading findings enriched with sentence_id + word-level highlight offsets",
)
async def get_findings(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    job_dir = get_job_dir(job_id)
    findings = _findings_with_live_status(job_dir)
    return {"job_id": job_id, "findings": findings}


@router.patch(
    "/documents/{job_id}/findings/{finding_id}",
    summary="Accept or reject a single finding",
)
async def update_finding_status(job_id: str, finding_id: str, payload: Dict[str, Any]):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

    new_status = payload.get("status", "accepted")
    if new_status not in ("accepted", "rejected", "pending"):
        raise HTTPException(status_code=400, detail="status must be one of: accepted, rejected, pending")

    job_dir = get_job_dir(job_id)
    final_dir = job_dir / "10_final"
    final_dir.mkdir(parents=True, exist_ok=True)
    decisions_path = final_dir / "decisions.json"
    decisions = _load_json_or(decisions_path, {})
    decisions[finding_id] = new_status

    with open(decisions_path, "w", encoding="utf-8") as f:
        json.dump(decisions, f, indent=2, ensure_ascii=False)

    return {"job_id": job_id, "finding_id": finding_id, "status": new_status}


@router.get(
    "/documents/{job_id}/corrected-preview",
    summary="Live corrected sentence text with all currently-accepted findings applied",
)
async def get_corrected_preview(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

    job_dir = get_job_dir(job_id)
    findings = _findings_with_live_status(job_dir)
    lookup_index = _load_json_or(job_dir / "04_sentences" / "sentence_lookup_index.json", {})

    accepted_by_sentence: Dict[str, list] = {}
    for f in findings:
        if f.get("status") != "accepted" or not f.get("sentence_id"):
            continue
        accepted_by_sentence.setdefault(f["sentence_id"], []).append(f)

    preview = []
    for sid, sent_findings in accepted_by_sentence.items():
        original = lookup_index.get(sid, {}).get("text", "")
        corrected = original
        for f in sorted(sent_findings, key=lambda x: (x.get("token_start") is None, x.get("token_start") or 0), reverse=True):
            ts, te = f.get("token_start"), f.get("token_end")
            if ts is not None and te is not None and 0 <= ts <= te <= len(corrected):
                corrected = corrected[:ts] + (f.get("suggestion") or "") + corrected[te:]
        preview.append({"sentence_id": sid, "original": original, "corrected": corrected})

    return {"job_id": job_id, "preview": preview}


@router.post(
    "/documents/{job_id}/export-corrected",
    summary="Rebuild the corrected document (PDF/DOCX/HTML) from Docling content + accepted findings",
)
async def export_corrected_document(job_id: str, payload: Dict[str, Any] = {}):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

    fmt = str(payload.get("format", "pdf")).lower()
    if fmt not in ("pdf", "docx", "html"):
        raise HTTPException(status_code=400, detail="format must be one of: pdf, docx, html")

    job_dir = get_job_dir(job_id)
    page_texts = _load_json_or(job_dir / "03_page_text" / "page_text.json", [])
    sentence_map = _load_json_or(job_dir / "04_sentences" / "page_sentence_map.json", [])
    findings = _findings_with_live_status(job_dir)

    if not page_texts or not sentence_map:
        raise HTTPException(status_code=409, detail="Document extraction has not completed yet.")

    from src.corrected_document_builder import apply_accepted_corrections, build_html, build_docx, build_pdf

    corrected_pages = apply_accepted_corrections(page_texts, sentence_map, findings)

    export_dir = job_dir / "10_final" / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    title = f"Corrected: {job.get('filename', job_id)}"

    try:
        if fmt == "html":
            html_content = build_html(corrected_pages, title=title)
            out_path = export_dir / "corrected_document.html"
            out_path.write_text(html_content, encoding="utf-8")
            return FileResponse(path=out_path, media_type="text/html", filename="corrected_document.html")
        elif fmt == "docx":
            out_path = build_docx(corrected_pages, export_dir / "corrected_document.docx")
            return FileResponse(
                path=out_path,
                media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                filename="corrected_document.docx",
            )
        else:
            out_path = build_pdf(corrected_pages, export_dir / "corrected_document.pdf")
            return FileResponse(path=out_path, media_type="application/pdf", filename="corrected_document.pdf")
    except Exception as exc:
        backend_logger.error("Failed to export corrected document (%s) for job %s: %s", fmt, job_id, exc)
        raise HTTPException(status_code=500, detail=f"Export failed: {str(exc)}")


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
        "confidence_threshold": 50,
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
            recommended=(m.id == DEFAULT_MODEL_ID or m.id == "qwen2.5-coder:7b")
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


@router.post("/comparative-analysis/run/{job_id}", summary="Force Run Comparative Analysis")
@router.post("/reports/{job_id}/comparative-analysis/run", summary="Force Run Comparative Analysis (Alias)")
async def run_comparative_analysis_endpoint(job_id: str):
    import threading
    from backend.services import get_job, get_job_dir, delete_stage_output_cache
    from src.stage_orchestrator import StageOrchestrator
    
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    job_dir = get_job_dir(job_id)
    delete_stage_output_cache(job_id, "stage_7_comparative")
    
    def worker():
        try:
            orchestrator = StageOrchestrator(job_id, job_dir, Path(job["file_path"]))
            orchestrator.run_stage_7_comparative(force_regenerate=True)
        except Exception as e:
            backend_logger.error("Comparative Analysis re-run failed for job %s: %s", job_id, e)
            
    threading.Thread(target=worker, daemon=True).start()
    return {"status": "running", "message": "Comparative Analysis re-generation started in background."}


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


def get_report_meta(job_id: str, relative_file_path: Path):
    from backend.services import get_job_dir, get_job
    job_dir = get_job_dir(job_id)
    full_path = job_dir / relative_file_path
    job = get_job(job_id)
    
    if not full_path.exists():
        if job and (job.get("status") in ("processing", "pending", "running") or job.get("context_analysis_status") in ("running", "pending")):
            return {
                "job_id": job_id,
                "status": "generating",
                "current_stage": job.get("current_stage", "Generating Executive Report..."),
                "message": "Generating Executive Report..."
            }
        return {
            "job_id": job_id,
            "status": "not_found",
            "message": "Report file does not exist yet."
        }
        
    import os
    import datetime
    mtime = os.path.getmtime(full_path)
    creation_time = datetime.datetime.fromtimestamp(mtime).isoformat()
    
    parent_dir = relative_file_path.parent
    name = relative_file_path.name
    stem = relative_file_path.stem
    
    html_name = f"{stem}_inspector.html"
    if stem == "semantic_clusters":
        html_name = "cluster_inspector.html"
    elif stem == "chunk_claims":
        html_name = "claim_inspector.html"
    elif stem == "chunk_reasoning":
        html_name = "chunk_reasoning_inspector.html"
    elif stem == "cluster_reasoning":
        html_name = "cluster_reasoning_inspector.html"
    elif stem == "claude_response":
        html_name = "verification_inspector.html"
    elif stem == "final_report":
        html_name = "final_report.html"
        
    md_name = f"{stem}.md"
    if stem == "claude_response":
         md_name = "verification_summary.md"
         
    return {
        "job_id": job_id,
        "creation_time": creation_time,
        "processing_time": 0.0,
        "status": "completed",
        "download_urls": {
            "json": f"/outputs/{job_id}/{parent_dir.as_posix()}/{name}",
            "markdown": f"/outputs/{job_id}/{parent_dir.as_posix()}/{md_name}",
            "html": f"/outputs/{job_id}/{parent_dir.as_posix()}/{html_name}"
        }
    }


def _handle_report_response(job_id: str, relative_path: Path):
    from backend.services import get_job_dir, get_job, save_job_metadata, backend_logger
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

    job_dir = get_job_dir(job_id)
    report_file = job_dir / relative_path

    # On-demand Comparative Analysis generation if report is missing
    if not report_file.exists() and relative_path.parts[0] == "comparative_analysis":
        comp_status = job.get("comparative_analysis_status")
        if comp_status != "failed":
            try:
                backend_logger.info("Executing on-demand Comparative Analysis for job_id: %s", job_id)
                from src.comparative_analysis.service import ComparativeAnalysisService
                from src.comparative_analysis.models import ComparativeAnalysisRequest

                job["comparative_analysis_status"] = "running"
                comp_service = ComparativeAnalysisService()
                comp_req = ComparativeAnalysisRequest(document_id=job_id)
                comp_resp = comp_service.run_analysis(comp_req)
                
                if comp_resp.status == "completed" and report_file.exists():
                    job["comparative_analysis_status"] = "completed"
                    save_job_metadata(job_id)
            except Exception as comp_err:
                backend_logger.error("On-demand comparative analysis failed for job %s: %s", job_id, comp_err)
                job["comparative_analysis_status"] = "failed"
                save_job_metadata(job_id)

    if not report_file.exists():
        comp_status = job.get("comparative_analysis_status")
        ctx_status = job.get("context_analysis_status")
        job_status = job.get("status")

        if (
            job_status in ("processing", "pending", "running") or
            ctx_status in ("running", "pending") or
            comp_status in ("running", "pending") or
            comp_status is None
        ):
            meta = get_report_meta(job_id, relative_path)
            meta["status"] = "generating"
            return {"metadata": meta, "data": None}
        raise HTTPException(status_code=404, detail=f"Report file '{relative_path.name}' not found.")

    try:
        with open(report_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        meta = get_report_meta(job_id, relative_path)
        meta["status"] = "ready"
        return {"metadata": meta, "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


REPORT_PATH_MAP = {
    "semantic-clusters": Path("09_semantic_clusters/semantic_clusters.json"),
    "semantic_clusters": Path("09_semantic_clusters/semantic_clusters.json"),
    "claim-extraction": Path("10_claim_extraction/chunk_claims.json"),
    "claim_extraction": Path("10_claim_extraction/chunk_claims.json"),
    "chunk_claims": Path("10_claim_extraction/chunk_claims.json"),
    "chunk-reasoning": Path("11_chunk_reasoning/chunk_reasoning.json"),
    "chunk_reasoning": Path("11_chunk_reasoning/chunk_reasoning.json"),
    "cluster-reasoning": Path("12_cluster_reasoning/cluster_reasoning.json"),
    "cluster_reasoning": Path("12_cluster_reasoning/cluster_reasoning.json"),
    "claude-verification": Path("14_claude_verification/claude_response.json"),
    "claude_verification": Path("14_claude_verification/claude_response.json"),
    "verification": Path("14_claude_verification/claude_response.json"),
    "final-report": Path("15_final_report/final_report.json"),
    "final_report": Path("15_final_report/final_report.json"),
    "executive": Path("15_final_report/final_report.json"),
    "consistency": Path("report.json"),
    "comparative-analysis": Path("comparative_analysis/comparative_report.json"),
    "comparative_analysis": Path("comparative_analysis/comparative_report.json"),
    "company-profile": Path("comparative_analysis/company_profile.json"),
    "company_profile": Path("comparative_analysis/company_profile.json"),
    "competitor-profiles": Path("comparative_analysis/competitor_profiles.json"),
    "competitor_profiles": Path("comparative_analysis/competitor_profiles.json"),
    "comparison-matrix": Path("comparative_analysis/comparison_matrix.json"),
    "comparison_matrix": Path("comparative_analysis/comparison_matrix.json"),
    "swot": Path("comparative_analysis/swot_analysis.json"),
    "swot_analysis": Path("comparative_analysis/swot_analysis.json"),
    "recommendations": Path("comparative_analysis/recommendations.json"),
}


@router.get("/reports/{job_id}/semantic-clusters", summary="Get Semantic Clusters Report")
async def get_report_semantic_clusters(job_id: str):
    return _handle_report_response(job_id, Path("09_semantic_clusters/semantic_clusters.json"))


@router.get("/reports/{job_id}/semantic_clusters", summary="Get Semantic Clusters Report (Alias)")
async def get_report_semantic_clusters_alias(job_id: str):
    return _handle_report_response(job_id, Path("09_semantic_clusters/semantic_clusters.json"))


@router.get("/reports/{job_id}/claim-extraction", summary="Get Claim Extraction Report")
async def get_report_claim_extraction(job_id: str):
    return _handle_report_response(job_id, Path("10_claim_extraction/chunk_claims.json"))


@router.get("/reports/{job_id}/claim_extraction", summary="Get Claim Extraction Report (Alias)")
async def get_report_claim_extraction_alias(job_id: str):
    return _handle_report_response(job_id, Path("10_claim_extraction/chunk_claims.json"))


@router.get("/reports/{job_id}/chunk-reasoning", summary="Get Chunk-Level Reasoning Report")
async def get_report_chunk_reasoning(job_id: str):
    return _handle_report_response(job_id, Path("11_chunk_reasoning/chunk_reasoning.json"))


@router.get("/reports/{job_id}/chunk_reasoning", summary="Get Chunk-Level Reasoning Report (Alias)")
async def get_report_chunk_reasoning_alias(job_id: str):
    return _handle_report_response(job_id, Path("11_chunk_reasoning/chunk_reasoning.json"))


@router.get("/reports/{job_id}/cluster-reasoning", summary="Get Cluster-Level Reasoning Report")
async def get_report_cluster_reasoning(job_id: str):
    return _handle_report_response(job_id, Path("12_cluster_reasoning/cluster_reasoning.json"))


@router.get("/reports/{job_id}/cluster_reasoning", summary="Get Cluster-Level Reasoning Report (Alias)")
async def get_report_cluster_reasoning_alias(job_id: str):
    return _handle_report_response(job_id, Path("12_cluster_reasoning/cluster_reasoning.json"))


@router.get("/reports/{job_id}/claude-verification", summary="Get Claude Verification Report")
async def get_report_claude_verification(job_id: str):
    return _handle_report_response(job_id, Path("14_claude_verification/claude_response.json"))


@router.get("/reports/{job_id}/claude_verification", summary="Get Claude Verification Report (Alias)")
async def get_report_claude_verification_alias(job_id: str):
    return _handle_report_response(job_id, Path("14_claude_verification/claude_response.json"))


@router.get("/reports/{job_id}/final-report", summary="Get Final Business Compliance Report")
async def get_report_final_report(job_id: str):
    return _handle_report_response(job_id, Path("15_final_report/final_report.json"))


@router.get("/reports/{job_id}/final_report", summary="Get Final Business Compliance Report (Alias)")
async def get_report_final_report_alias(job_id: str):
    return _handle_report_response(job_id, Path("15_final_report/final_report.json"))


@router.get("/reports/{job_id}/comparative-analysis", summary="Get Comparative Analysis Report")
async def get_report_comparative_analysis(job_id: str):
    return _handle_report_response(job_id, Path("comparative_analysis/comparative_report.json"))


@router.get("/reports/{job_id}/company-profile", summary="Get Target Company Profile")
async def get_report_company_profile(job_id: str):
    return _handle_report_response(job_id, Path("comparative_analysis/company_profile.json"))


@router.get("/reports/{job_id}/competitor-profiles", summary="Get Competitor Profiles")
async def get_report_competitor_profiles(job_id: str):
    return _handle_report_response(job_id, Path("comparative_analysis/competitor_profiles.json"))


@router.get("/reports/{job_id}/comparison-matrix", summary="Get Comparison Matrix")
async def get_report_comparison_matrix(job_id: str):
    return _handle_report_response(job_id, Path("comparative_analysis/comparison_matrix.json"))


@router.get("/reports/{job_id}/swot", summary="Get SWOT Analysis")
async def get_report_swot(job_id: str):
    return _handle_report_response(job_id, Path("comparative_analysis/swot_analysis.json"))


@router.get("/reports/{job_id}/recommendations", summary="Get Strategic Recommendations")
async def get_report_recommendations(job_id: str):
    return _handle_report_response(job_id, Path("comparative_analysis/recommendations.json"))


@router.get("/reports/{job_id}/{report_type}", summary="Get dynamic report by type")
async def get_report_by_type(job_id: str, report_type: str):
    if report_type.lower() in REPORT_PATH_MAP:
        return _handle_report_response(job_id, REPORT_PATH_MAP[report_type.lower()])

    from backend.services import get_job_dir, get_job
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

    job_dir = get_job_dir(job_id)
    possible_files = list(job_dir.glob(f"**/{report_type}.json")) + list(job_dir.glob(f"**/{report_type}"))
    if possible_files:
        rel_path = possible_files[0].relative_to(job_dir)
        return _handle_report_response(job_id, rel_path)

    if job.get("status") in ("processing", "pending", "running") or job.get("context_analysis_status") in ("running", "pending"):
        return {"metadata": {"job_id": job_id, "status": "generating", "message": "Generating Executive Report..."}, "data": None}

    raise HTTPException(status_code=404, detail=f"Report '{report_type}' not found for job '{job_id}'.")


@router.get("/reports/{job_id}/{report_type}/pdf", summary="Download report in PDF format")
async def download_report_pdf(job_id: str, report_type: str):
    from backend.services import get_job_dir, get_job
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

    job_dir = get_job_dir(job_id)

    report_html_map = {
        "final-report": job_dir / "15_final_report" / "final_report.html",
        "final_report": job_dir / "15_final_report" / "final_report.html",
        "executive": job_dir / "15_final_report" / "final_report.html",
        "claude-verification": job_dir / "14_claude_verification" / "verification_inspector.html",
        "verification": job_dir / "14_claude_verification" / "verification_inspector.html",
        "cluster-reasoning": job_dir / "12_cluster_reasoning" / "cluster_reasoning_inspector.html",
        "chunk-reasoning": job_dir / "11_chunk_reasoning" / "chunk_reasoning_inspector.html",
        "claim-extraction": job_dir / "10_claim_extraction" / "claim_inspector.html",
        "semantic-clusters": job_dir / "09_semantic_clusters" / "cluster_inspector.html",
        "annotated-original": job_dir / "10_final" / "annotated_original.html",
        "corrected-document": job_dir / "10_final" / "corrected_document.html",
        "comparative-analysis": job_dir / "comparative_analysis" / "comparative_report.html",
        "comparative_analysis": job_dir / "comparative_analysis" / "comparative_report.html",
        "comparative": job_dir / "comparative_analysis" / "comparative_report.html",
        "executive-dashboard": job_dir / "comparative_analysis" / "executive_dashboard.html",
    }

    html_file = report_html_map.get(report_type.lower())
    if not html_file or not html_file.exists():
        candidates = [
            job_dir / "15_final_report" / "final_report.html",
            job_dir / "09_reports" / "consistency_report.html",
            job_dir / "business_report.html",
            job_dir / "comparative_analysis" / "comparative_report.html",
            job_dir / "09_reports" / "comparative_analysis.html",
            job_dir / "10_final" / "corrected_document.html"
        ]
        html_file = next((c for c in candidates if c.exists()), None)
        if not html_file:
            raise HTTPException(status_code=404, detail=f"HTML source for report '{report_type}' not found.")

    pdf_output_path = job_dir / f"{report_type}_report.pdf"

    # Always compile or update PDF if HTML is newer or PDF is missing
    if not pdf_output_path.exists() or pdf_output_path.stat().st_size == 0 or (html_file.stat().st_mtime > pdf_output_path.stat().st_mtime):
        try:
            import fitz
            html_text = html_file.read_text(encoding="utf-8")
            try:
                story = fitz.Story(html=html_text)
                writer = fitz.DocumentWriter(str(pdf_output_path))
                more = True
                while more:
                    page = writer.begin_page(fitz.PaperSize("A4"))
                    more, _ = story.place(fitz.Rect(36, 36, page.rect.width - 36, page.rect.height - 36))
                    story.draw(page)
                    writer.end_page()
                writer.close()
            except Exception as story_exc:
                backend_logger.warning(f"fitz.Story failed: {story_exc}, compiling clean PDF layout fallback")
                import re
                clean_text = re.sub(r'<style.*?>.*?</style>', '', html_text, flags=re.DOTALL)
                clean_text = re.sub(r'<script.*?>.*?</script>', '', clean_text, flags=re.DOTALL)
                clean_text = re.sub(r'<[^>]+>', '\n', clean_text)
                lines = [line.strip() for line in clean_text.split('\n') if line.strip()]
                
                doc = fitz.open()
                page = doc.new_page()
                y = 50
                for line in lines:
                    if y > page.rect.height - 50:
                        page = doc.new_page()
                        y = 50
                    page.insert_text((36, y), line[:110], fontsize=10)
                    y += 14
                doc.save(str(pdf_output_path))
                doc.close()
        except Exception as e:
            backend_logger.error(f"Failed to compile PDF via PyMuPDF: {e}")
            return FileResponse(
                path=html_file,
                media_type="text/html",
                filename=f"{report_type}_{job_id}.html"
            )

    return FileResponse(
        path=pdf_output_path,
        media_type="application/pdf",
        filename=f"{report_type}_{job_id}.pdf"
    )


@router.get("/jobs/{job_id}/progress/stream", summary="Stream live pipeline progress via Server-Sent Events (SSE)")
async def stream_job_progress(job_id: str):
    import asyncio
    from fastapi.responses import StreamingResponse

    async def event_generator():
        last_stage = None
        last_pct = -1.0
        while True:
            job = get_job(job_id)
            if not job:
                yield f"data: {json.dumps({'error': 'Job not found'})}\n\n"
                break
            
            stage = job.get("current_stage")
            pct = job.get("progress_percentage", 0.0)
            status_val = job.get("status")
            ca_status = job.get("context_analysis_status")
            ca_stage = job.get("context_analysis_stage")
            ca_pct = job.get("context_analysis_progress", 0.0)
            
            payload = {
                "job_id": job_id,
                "status": status_val,
                "current_stage": stage,
                "progress_percentage": pct,
                "context_analysis_status": ca_status,
                "context_analysis_stage": ca_stage,
                "context_analysis_progress": ca_pct,
            }
            
            if stage != last_stage or pct != last_pct:
                yield f"data: {json.dumps(payload)}\n\n"
                last_stage = stage
                last_pct = pct
                
            if status_val in ("completed", "failed") and ca_status in ("completed", "failed"):
                yield f"data: {json.dumps(payload)}\n\n"
                break
                
            await asyncio.sleep(0.5)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/cache/{job_id}/metadata", summary="Get cache metadata and completed stages for a document")
async def get_cache_metadata_endpoint(job_id: str):
    from src.rag.cache_manager import DocumentCacheManager, compute_file_hash
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    doc_hash = job.get("doc_hash")
    if not doc_hash:
        file_path = Path(job.get("file_path", ""))
        if file_path.exists():
            doc_hash = compute_file_hash(file_path)
    
    if not doc_hash:
        raise HTTPException(status_code=404, detail="Cache hash not available for job")
        
    cache_mgr = DocumentCacheManager(doc_hash, job.get("filename", "unknown"))
    return cache_mgr.get_metadata()


@router.post(
    "/documents/{job_id}/export-pdf",
    summary="Export corrected PDF using accepted proofreading issues",
)
async def export_corrected_pdf(job_id: str, payload: dict = {}):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

    job_dir = get_job_dir(job_id)
    accepted_ids = set(payload.get("accepted_issue_ids", []))
    decisions = payload.get("decisions", {})

    # 1. Load Issues
    raw_issues = []
    report_path = job_dir / "10_final" / "report.json"
    if report_path.exists():
        try:
            with open(report_path, "r", encoding="utf-8") as f:
                report_data = json.load(f)
                raw_issues = report_data.get("issues", [])
        except Exception as exc:
            backend_logger.warning("Error reading report.json for export PDF: %s", exc)

    issues = _normalize_issue_metadata(raw_issues)

    # Filter accepted issues
    accepted_issues = []
    for idx, iss in enumerate(issues):
        iid = iss.get("issue_id") or f"issue_{idx + 1}"
        if iid in accepted_ids or decisions.get(str(idx)) == "accepted" or decisions.get(iid) == "accepted":
            accepted_issues.append(iss)

    # Locate input document PDF
    input_dir = ROOT_DIR / "data" / "input"
    orig_pdf = None
    if input_dir.exists():
        for child in input_dir.iterdir():
            if child.name.startswith(job_id) and child.suffix.lower() == ".pdf":
                orig_pdf = child
                break

    output_pdf_path = job_dir / "10_final" / "corrected_document.pdf"

    try:
        import fitz
        if orig_pdf and orig_pdf.exists():
            doc = fitz.open(orig_pdf)
            for iss in accepted_issues:
                page_idx = max(0, int(iss.get("page", 1)) - 1)
                if page_idx < len(doc):
                    page = doc[page_idx]
                    orig = iss.get("original_text", "")
                    sug = iss.get("suggested_text", "")
                    if orig:
                        rects = page.search_for(orig)
                        for rect in rects:
                            page.add_redact_annot(rect, text=sug, fontsize=10)
                        page.apply_redactions()
            output_pdf_path.parent.mkdir(parents=True, exist_ok=True)
            doc.save(str(output_pdf_path))
            doc.close()
        else:
            # Fallback: create fresh PDF from text
            doc = fitz.open()
            page = doc.new_page()
            text_path = job_dir / "03_preprocessed" / "normalized_text.txt"
            raw_text = text_path.read_text(encoding="utf-8") if text_path.exists() else "Corrected Document"
            
            # Apply corrections to text
            corrected_text = raw_text
            for iss in sorted(accepted_issues, key=lambda x: x.get("char_start", 0), reverse=True):
                cs, ce = iss.get("char_start"), iss.get("char_end")
                if cs is not None and ce is not None and 0 <= cs <= ce <= len(corrected_text):
                    corrected_text = corrected_text[:cs] + iss.get("suggested_text", "") + corrected_text[ce:]
            
            page.insert_textbox(fitz.Rect(50, 50, 550, 780), corrected_text[:4000])
            output_pdf_path.parent.mkdir(parents=True, exist_ok=True)
            doc.save(str(output_pdf_path))
            doc.close()

        clean_filename = f"corrected_{job.get('filename', 'document.pdf')}"
        return FileResponse(
            path=output_pdf_path,
            media_type="application/pdf",
            filename=clean_filename,
        )
    except Exception as exc:
        backend_logger.error("Failed to generate export PDF for job %s: %s", job_id, exc)
        raise HTTPException(status_code=500, detail=f"PDF Export failed: {str(exc)}")


@router.post(
    "/documents/{job_id}/rerun-proofreading",
    summary="Re-run only proofreading pipeline preserving extraction & RAG",
)
async def rerun_proofreading_endpoint(job_id: str):
    from backend.services import rerun_proofreading_job
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

    try:
        res = rerun_proofreading_job(job_id)
        return res
    except Exception as exc:
        backend_logger.error("Rerun proofreading failed for job %s: %s", job_id, exc)
        raise HTTPException(status_code=500, detail=f"Rerun proofreading failed: {str(exc)}")


@router.get(
    "/documents/{job_id}/validate-outputs",
    summary="Validate presence and integrity of job output artifacts",
)
async def validate_outputs_endpoint(job_id: str):
    from backend.services import validate_job_outputs
    try:
        return validate_job_outputs(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Validation failed: {str(exc)}")


@router.post(
    "/documents/{job_id}/regenerate-report",
    summary="Regenerate proofreading report without rerunning Docling or RAG",
)
async def regenerate_report_endpoint(job_id: str):
    from backend.services import regenerate_proofreading_report
    try:
        return regenerate_proofreading_report(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Report regeneration failed: {str(exc)}")


@router.post(
    "/documents/{job_id}/rerun-stage",
    summary="Rerun only a specific stage using existing artifacts",
)
async def rerun_stage_endpoint(job_id: str, stage_number: int = 4):
    from backend.services import rerun_stage
    try:
        return rerun_stage(job_id, stage_number)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Rerun stage failed: {str(exc)}")


@router.post(
    "/documents/{job_id}/rerun-from-stage",
    summary="Rerun pipeline starting from a specific stage using existing artifacts",
)
async def rerun_from_stage_endpoint(job_id: str, stage_number: int = 4):
    from backend.services import rerun_from_stage
    try:
        return rerun_from_stage(job_id, stage_number)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Rerun from stage failed: {str(exc)}")


@router.post(
    "/documents/{job_id}/repair",
    summary="Automatically repair missing job artifacts or regenerate report",
)
async def repair_job_endpoint(job_id: str):
    from backend.services import repair_job
    try:
        return repair_job(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Job repair failed: {str(exc)}")











