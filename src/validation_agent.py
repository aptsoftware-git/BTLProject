"""
validation_agent.py
====================
Step 10: Validation Agent.

Single gatekeeper for EVERY candidate regardless of source (LanguageTool,
SymSpell, or the LLM). If a candidate's span overlaps a protected term, it
is dropped -- tagged, not silently discarded, so rejected.json stays useful
for debugging/demo purposes.
"""

from __future__ import annotations

from typing import List, Tuple

from src.models import Candidate, ProtectedTerm, ValidatedIssue
from src.protected_terms import ProtectedTermsBuilder
from src.utils import dataclass_kwargs


class ValidationAgent:
    """Filters every candidate correction against the protected-terms list."""

    def __init__(self, protected_terms: List[ProtectedTerm]) -> None:
        self.protected_terms = protected_terms

    def validate(self, candidates: List[Candidate]) -> Tuple[List[ValidatedIssue], List[ValidatedIssue]]:
        """Returns (accepted, rejected)."""
        accepted: List[ValidatedIssue] = []
        rejected: List[ValidatedIssue] = []
        for candidate in candidates:
            hit = ProtectedTermsBuilder.overlaps(candidate.char_start, candidate.char_end, self.protected_terms)
            issue = ValidatedIssue(
                **dataclass_kwargs(candidate),
                is_protected=hit is not None,
                protected_reason=hit.reason if hit else None,
            )
            (rejected if hit else accepted).append(issue)
        return accepted, rejected
