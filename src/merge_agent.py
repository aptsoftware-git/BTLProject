"""
merge_agent.py
================
Step 14: Merge Agent.

Reconciles candidates whose spans overlap (e.g. LanguageTool and the LLM both
flagged the same word). Policy:
  - Single source flagged it -> keep as-is.
  - Multiple sources agree on the same suggested_text -> higher confidence,
    agreement_count incremented, boosted final_confidence.
  - Multiple sources disagree on the suggestion -> prefer the LLM's version
    (it has full-sentence/paragraph context; LanguageTool only has local
    rules), but keep the alternative sources in contributing_sources for
    the report.
"""

from __future__ import annotations

from typing import List, Optional, Set

from src.config import MergeConfig
from src.models import MergedIssue, SourceAgent, ValidatedIssue
from src.utils import dataclass_kwargs


ISSUE_TYPE_WEIGHTS = {
    "grammar": 1.0,
    "tense": 1.0,
    "spelling": 0.7,
    "punctuation": 0.6,
    "style": 0.5,
}


def get_issue_type_weight(issue_type: str | None) -> float:
    if not issue_type:
        return 1.0
    val = issue_type.value if hasattr(issue_type, "value") else str(issue_type)
    return ISSUE_TYPE_WEIGHTS.get(val.lower(), 1.0)


class MergeAgent:
    """Reconciles overlapping candidates from multiple detection agents."""

    def __init__(self, config: MergeConfig) -> None:
        self.config = config

    def merge(self, issues: List[ValidatedIssue]) -> List[MergedIssue]:
        if not issues:
            return []
        groups = self._group_overlapping(issues)
        merged: List[MergedIssue] = []
        for group in groups:
            res = self._merge_group(group)
            if res is not None:
                merged.append(res)
        return sorted(merged, key=lambda m: m.char_start)

    @staticmethod
    def _group_overlapping(issues: List[ValidatedIssue]) -> List[List[ValidatedIssue]]:
        issues_sorted = sorted(issues, key=lambda i: i.char_start)
        groups: List[List[ValidatedIssue]] = []
        for issue in issues_sorted:
            placed = False
            for group in groups:
                if any(issue.char_start < g.char_end and issue.char_end > g.char_start for g in group):
                    group.append(issue)
                    placed = True
                    break
            if not placed:
                groups.append([issue])
        return groups

    def calculate_confidence(self, sources: Set[SourceAgent | str], issue_type: Optional[str] = None) -> float:
        gf = getattr(SourceAgent, "GRAMFORMER", "gramformer")
        
        # Multi-source high agreement
        if len(sources) >= 3:
            return 1.00
        elif (SourceAgent.LLM in sources or gf in sources) and SourceAgent.LANGUAGETOOL in sources:
            return 0.95
        elif SourceAgent.LLM in sources and gf in sources:
            return 0.95
        elif (SourceAgent.LLM in sources or gf in sources) and SourceAgent.SYMSPELL in sources:
            return 0.90
        elif SourceAgent.LANGUAGETOOL in sources and SourceAgent.SYMSPELL in sources:
            return 0.88
        
        # Single source confidence
        if gf in sources:
            return 0.85
        elif SourceAgent.LLM in sources:
            return 0.80
        elif SourceAgent.LANGUAGETOOL in sources:
            if issue_type == "spelling":
                return 0.78
            elif issue_type == "grammar":
                return 0.73
            return 0.75
        elif SourceAgent.SYMSPELL in sources:
            return 0.35
        else:
            return 0.50

    def _merge_group(self, group: List[ValidatedIssue]) -> Optional[MergedIssue]:
        if not group:
            return None

        # Prioritize suggestions by source reliability and context:
        # LLM -> GRAMFORMER -> LANGUAGETOOL -> T5 -> SYMSPELL -> first available
        source_priority = [
            SourceAgent.LLM,
            getattr(SourceAgent, "GRAMFORMER", "gramformer"),
            SourceAgent.LANGUAGETOOL,
            getattr(SourceAgent, "T5", "t5"),
            SourceAgent.SYMSPELL,
        ]

        best: Optional[ValidatedIssue] = None
        for src in source_priority:
            matching = [i for i in group if i.source == src]
            if matching:
                best = matching[0]
                break
        
        if best is None:
            # Fallback: choose highest confidence candidate, or group[0]
            best = max(group, key=lambda i: getattr(i, "confidence", 0.5)) if group else None

        if best is None:
            return None

        # Candidates that agree with the chosen suggested_text
        agreeing_candidates = [i for i in group if i.suggested_text == best.suggested_text]
        agreement_count = len(agreeing_candidates)
        agreeing_sources = {i.source for i in agreeing_candidates}
        all_sources = {i.source for i in group}
        
        # Calculate dynamic confidence
        issue_type_val = best.issue_type.value if hasattr(best.issue_type, "value") else str(best.issue_type) if best.issue_type else None
        final_conf = self.calculate_confidence(agreeing_sources, issue_type_val)
        
        # If the candidate was marked as protected, force confidence to 0
        if getattr(best, "is_protected", False):
            final_conf = 0.0

        # Calculate severity
        weight = get_issue_type_weight(issue_type_val)
        severity_score = final_conf * weight

        if severity_score >= 0.85:
            severity = "critical"
        elif severity_score >= 0.65:
            severity = "high"
        elif severity_score >= 0.4:
            severity = "medium"
        else:
            severity = "low"

        return MergedIssue(
            **dataclass_kwargs(best),
            agreement_count=agreement_count,
            final_confidence=final_conf,
            contributing_sources=list(all_sources),
            severity=severity,
        )
