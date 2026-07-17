from dataclasses import dataclass, field
from typing import List, Dict, Any

@dataclass
class InconsistencyIssue:
    category: str  # e.g., "Numeric Mismatch", "Contradiction", "Terminology Inconsistency", "Reference Conflict"
    severity: str  # "High", "Medium", "Low"
    confidence: float  # 0.0 to 1.0
    description: str
    evidence: str
    object_ids: List[str]
    page_numbers: List[int]
    section_path: str
    quoted_text: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class ExecutiveSummary:
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
