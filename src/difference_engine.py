"""
Step 13: Difference Engine.

NOTE: this is intentionally much simpler than a classic token-diff engine.
Because every agent (LanguageTool, SymSpell, LLM) already emits explicit
char_start/char_end spans (see models.Candidate), there is no need to diff
two full rewritten sentences token-by-token -- that approach is what caused
the old "Grammar Candidates: 0" bug when T5 was the primary source.

This module's job now is just a sanity re-check: confirm the recorded span
still contains exactly `original_text` in the current document text (guards
against stale offsets after any upstream normalization step), and drop
no-op candidates where suggested == original.
"""

from __future__ import annotations

from src.models import ValidatedIssue


class DifferenceEngine:
    def __init__(self, full_document_text: str):
        self.full_text = full_document_text

    def run(self, issues: list[ValidatedIssue]) -> list[ValidatedIssue]:
        confirmed = []
        for issue in issues:
            if issue.original_text == issue.suggested_text:
                continue  # no actual change, nothing to annotate
            span_text = self.full_text[issue.char_start:issue.char_end]
            if span_text != issue.original_text:
                # offsets drifted -- try a local re-anchor within a small window
                # before giving up on the candidate entirely
                window_start = max(0, issue.char_start - 20)
                window_end = min(len(self.full_text), issue.char_end + 20)
                local_idx = self.full_text[window_start:window_end].find(issue.original_text)
                if local_idx == -1:
                    continue  # can't confirm this span still exists -- drop it
                issue.char_start = window_start + local_idx
                issue.char_end = issue.char_start + len(issue.original_text)
            confirmed.append(issue)
        return confirmed