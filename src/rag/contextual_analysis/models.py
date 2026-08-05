from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

@dataclass
class EvidenceItem:
    page: int = 1
    section: str = "Document Section"
    paragraph: str = "Paragraph 1"
    quote: str = ""
    chunk_id: Optional[str] = None

@dataclass
class InconsistencyIssue:
    category: str  # Standardized Enterprise Category
    severity: str  # "CRITICAL", "HIGH", "MEDIUM", "LOW"
    confidence: float = 0.85  # Backward compatibility field (0.0 to 1.0)
    confidence_pct: int = 85  # 0 to 100
    materiality: str = "Moderate"  # "Material", "Moderate", "Informational"
    risk_score: int = 5  # 1 to 10
    risk_reason: str = "Identified during consistency audit."
    confidence_reason: str = "Verified by AI Validation Engine."
    finding_status: str = "Verified"  # "Detected", "Verified", "Rejected", "Consolidated", "Escalated"
    description: str = ""
    evidence: str = ""  # Backward compatibility field
    business_impact: str = "Operational execution deviation & stakeholder ambiguity."
    recommended_resolution: str = "Review source document to reconcile conflicting statements."
    evidence_items: List[EvidenceItem] = field(default_factory=list)
    object_ids: List[str] = field(default_factory=list)
    page_numbers: List[int] = field(default_factory=lambda: [1])
    section_path: str = "Document Section"
    quoted_text: str = ""
    finding_id: str = "finding_000"
    title: str = "Document Inconsistency"
    affected_pages: List[int] = field(default_factory=lambda: [1])
    audit_traceability: str = "Verified by Independent AI Validation Layer"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.confidence != 0.85 and self.confidence_pct == 85:
            if self.confidence <= 1.0:
                self.confidence_pct = int(self.confidence * 100)
            else:
                self.confidence_pct = int(self.confidence)

    @property
    def confidence_level(self) -> str:
        if self.confidence_pct >= 90:
            return "Very High"
        elif self.confidence_pct >= 80:
            return "High"
        elif self.confidence_pct >= 70:
            return "Medium"
        return "Low"

    @property
    def risk_tier(self) -> str:
        if self.risk_score >= 9:
            return "Critical Risk"
        elif self.risk_score >= 7:
            return "High Risk"
        elif self.risk_score >= 4:
            return "Medium Risk"
        return "Low Risk"

@dataclass
class RejectionSummaryItem:
    reason: str
    count: int

@dataclass
class ExecutiveSummary:
    document_name: str = "Document"
    total_pages: int = 1
    potential_findings: int = 0
    ai_verified_findings: int = 0
    rejected_findings: int = 0
    executive_findings: int = 0
    severity_breakdown: Dict[str, int] = field(default_factory=lambda: {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0})
    overall_risk_rating: str = "LOW"  # "CRITICAL", "HIGH", "MEDIUM", "LOW"
    rejection_summary: List[RejectionSummaryItem] = field(default_factory=list)
    total_issues: int = 0
    high_severity: int = 0
    medium_severity: int = 0
    low_severity: int = 0
    categories_distribution: Dict[str, int] = field(default_factory=dict)
    average_confidence: float = 0.0

@dataclass
class AnalysisReport:
    document_id: str
    source_file: str
    created_time: str
    summary: ExecutiveSummary
    issues: List[InconsistencyIssue] = field(default_factory=list)
