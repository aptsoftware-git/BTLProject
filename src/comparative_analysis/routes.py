from __future__ import annotations

import logging
from fastapi import APIRouter, HTTPException, BackgroundTasks
from src.comparative_analysis.models import (
    ComparativeAnalysisRequest,
    ComparativeAnalysisResponse,
)
from src.comparative_analysis.service import ComparativeAnalysisService

logger = logging.getLogger("comparative_analysis.routes")

router = APIRouter(prefix="/comparative-analysis", tags=["Comparative Analysis"])

# Service instance placeholder
service = ComparativeAnalysisService()


@router.post(
    "/analyze",
    response_model=ComparativeAnalysisResponse,
    summary="Initiate Comparative Analysis for an Indexed Document"
)
async def analyze_document(request: ComparativeAnalysisRequest):
    """
    Triggers the Comparative Analysis pipeline on a document that has already been indexed in ChromaDB.

    This endpoint DOES NOT reprocess the uploaded document from scratch.
    It retrieves pre-indexed semantic chunks from ChromaDB and performs market comparison.
    """
    logger.info("Received API request for comparative analysis on document_id: %s", request.document_id)
    try:
        response = service.run_analysis(request)
        return response
    except Exception as exc:
        logger.error("Error handling comparative analysis request: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get(
    "/status/{analysis_id}",
    summary="Get Status of Comparative Analysis Job"
)
async def get_analysis_status(analysis_id: str):
    """
    Returns current execution status for a comparative analysis job.
    """
    return {
        "analysis_id": analysis_id,
        "status": "completed",
        "progress_percentage": 100.0,
        "message": "Comparative analysis job placeholder status."
    }


@router.get(
    "/results/{analysis_id}",
    response_model=ComparativeAnalysisResponse,
    summary="Get Detailed Comparative Analysis Results"
)
async def get_analysis_results(analysis_id: str):
    """
    Returns full comparative analysis results including feature matrix, SWOT, recommendations, and innovation opportunities.
    """
    # Placeholder return for interface verification
    stub_req = ComparativeAnalysisRequest(document_id=f"doc_{analysis_id}")
    return service.run_analysis(stub_req)
