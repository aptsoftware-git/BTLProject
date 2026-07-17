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

from typing import List

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
        groups = self._group_overlapping(issues)
        merged = [self._merge_group(group) for group in groups]
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

    def calculate_confidence(self, sources: set[SourceAgent], issue_type: Optional[str] = None) -> float:
        # Base confidence depending on sources
        if SourceAgent.LANGUAGETOOL in sources and SourceAgent.LLM in sources and SourceAgent.SYMSPELL in sources:
            return 1.00
        elif SourceAgent.LANGUAGETOOL in sources and SourceAgent.LLM in sources:
            return 0.95
        elif SourceAgent.LANGUAGETOOL in sources and SourceAgent.SYMSPELL in sources:
            return 0.88
        elif SourceAgent.SYMSPELL in sources and SourceAgent.LLM in sources:
            return 0.82
        elif SourceAgent.LANGUAGETOOL in sources:
            conf = 0.75
            if issue_type == "spelling":
                conf = 0.78
            elif issue_type == "grammar":
                conf = 0.73
            return conf
        elif SourceAgent.LLM in sources:
            return 0.80
        elif SourceAgent.SYMSPELL in sources:
            return 0.35
        else:
            return 0.50

    def _merge_group(self, group: List[ValidatedIssue]) -> MergedIssue:
        # Prioritize suggestions by source: LLM -> LanguageTool -> SymSpell
        llm_candidates = [i for i in group if i.source == SourceAgent.LLM]
        lt_candidates = [i for i in group if i.source == SourceAgent.LANGUAGETOOL]
        ss_candidates = [i for i in group if i.source == SourceAgent.SYMSPELL]
        
        if llm_candidates:
            best = llm_candidates[0]
        elif lt_candidates:
            best = lt_candidates[0]
        else:
            best = ss_candidates[0]

        # Candidates that agree with the chosen suggested_text
        agreeing_candidates = [i for i in group if i.suggested_text == best.suggested_text]
        agreement_count = len(agreeing_candidates)
        agreeing_sources = {i.source for i in agreeing_candidates}
        all_sources = {i.source for i in group}
        
        # Calculate dynamic confidence
        final_conf = self.calculate_confidence(agreeing_sources, best.issue_type.value if best.issue_type else None)
        
        # If the candidate was marked as protected, force confidence to 0
        if best.is_protected:
            final_conf = 0.0

        # Calculate severity
        issue_type_str = best.issue_type.value if hasattr(best.issue_type, "value") else str(best.issue_type) if best.issue_type else None
        weight = get_issue_type_weight(issue_type_str)
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
