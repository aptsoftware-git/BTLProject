from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class UploadResponse(BaseModel):
    job_id: str
    filename: str


class ProofreadRequest(BaseModel):
    job_id: str


class StageStatusModel(BaseModel):
    stage_id: str
    name: str
    unlocked_feature: Optional[str] = None
    status: str  # Pending, Running, Completed, Failed, Skipped
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration: Optional[float] = None
    errors: Optional[str] = None
    output_location: Optional[str] = None


class JobStatusResponse(BaseModel):
    job_id: str
    filename: str
    status: str  # uploaded, pending, processing, completed, failed
    current_stage: str
    progress_percentage: float
    overall_progress: Optional[int] = 0
    created_at: str
    completed_at: Optional[str] = None
    error: Optional[str] = None
    upload_ready: Optional[bool] = True
    document_viewer_ready: Optional[bool] = False
    extraction_ready: Optional[bool] = False
    spell_ready: Optional[bool] = False
    grammar_ready: Optional[bool] = False
    proofreading_ready: Optional[bool] = False
    rag_ready: Optional[bool] = False
    context_analysis_ready: Optional[bool] = False
    comparative_analysis_ready: Optional[bool] = False
    reports_ready: Optional[bool] = False
    stages: Optional[List[StageStatusModel]] = []


class ResultsResponse(BaseModel):
    job_id: str
    status: str
    statistics: Dict[str, Any]
    issues: List[Any]
    protected_terms: List[Any]
    annotated_html: str
    corrected_html: str
    reports: Dict[str, str]
    raw_text: str = ""


class ProtectedTermsRequest(BaseModel):
    terms: List[str]


class PreferencesRequest(BaseModel):
    preferences: Dict[str, Any]


class RagChatRequest(BaseModel):
    document_id: str
    question: str
    selected_model: Optional[str] = None
    conversation_history_depth: Optional[int] = None


class RagIndexRequest(BaseModel):
    document_id: str


class RagModelResponse(BaseModel):
    id: str
    display_name: str
    description: str
    recommended: bool


