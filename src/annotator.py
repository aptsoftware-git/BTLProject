"""
annotator.py
=============
Step 15: Annotation Engine.

Produces two HTML documents:
  - annotated_original.html: original text with color-coded highlights
    (spelling / grammar) and hover tooltips showing type, original,
    suggestion, confidence, and reason. Multi-source agreement renders
    with a solid outline; single-source flags render with a dashed one.
  - corrected_document.html: the text with corrections applied, only the
    changed words highlighted in green.

Shared page shell / base CSS lives in html_writer.py so this module and any
future HTML-producing stage don't duplicate markup.
"""

from __future__ import annotations

from typing import List, Tuple

from src.html_writer import escape, page_shell
from src.models import IssueType, MergedIssue

_LEGEND = (
    '<div class="legend">'
    '<span class="sev-low">Low</span>'
    '<span class="sev-medium">Medium</span>'
    '<span class="sev-high">High</span>'
    '<span class="sev-critical">Critical</span>'
    "</div>"
)
_CORRECTED_LEGEND = '<div class="legend"><span class="corrected">Corrected</span></div>'


def _css_class(severity: str) -> str:
    """Map the MergedIssue severity down to CSS classes."""
    return f"sev-{severity}"


class Annotator:
    def __init__(self, full_text: str) -> None:
        self.full_text = full_text

    def build(self, issues: List[MergedIssue]) -> Tuple[str, str]:
        return self._build_annotated(issues), self._build_corrected(issues)

    def _build_annotated(self, issues: List[MergedIssue]) -> str:
        issues_sorted = sorted(issues, key=lambda i: i.char_start)
        parts = []
        cursor = 0
        for issue in issues_sorted:
            parts.append(escape(self.full_text[cursor:issue.char_start]))
            def _val(x):
                return x.value if hasattr(x, "value") else str(x) if x else ""
            sources = ", ".join(sorted(_val(s) for s in issue.contributing_sources)) or _val(issue.source)
            tooltip = (
                f"Issue Type: {_val(issue.issue_type).title()}\n"
                f"Original: {issue.original_text}\n"
                f"Suggestion: {issue.suggested_text}\n"
                f"Reason: {issue.reason}\n"
                f"Confidence: {issue.final_confidence:.2f}\n"
                f"Severity: {issue.severity.title()}\n"
                f"Source: {sources}\n"
                f"Agreement Count: {issue.agreement_count}"
            )
            t_str = _val(issue.issue_type).lower()
            if "spell" in t_str:
                css_class = "spelling"
            elif "gramm" in t_str or "tense" in t_str:
                css_class = "grammar"
            elif "style" in t_str:
                css_class = "style"
            else:
                css_class = "punctuation"
            border = "border-high" if (getattr(issue, "final_confidence", 0.5) or 0.5) >= 0.7 else "border-low"

            parts.append(
                f'<mark class="{css_class} {border}" data-tooltip="{escape(tooltip)}">'
                f"{escape(issue.original_text)}</mark>"
            )
            cursor = issue.char_end
        parts.append(escape(self.full_text[cursor:]))
        body = f'<div class="paragraph">{"".join(parts)}</div>'
        return page_shell("Annotated Original", _LEGEND + body)

    def _build_corrected(self, issues: List[MergedIssue]) -> str:
        issues_sorted = sorted(issues, key=lambda i: i.char_start)
        parts = []
        cursor = 0
        for issue in issues_sorted:
            parts.append(escape(self.full_text[cursor:issue.char_start]))
            parts.append(f'<mark class="corrected">{escape(issue.suggested_text)}</mark>')
            cursor = issue.char_end
        parts.append(escape(self.full_text[cursor:]))
        body = f'<div class="paragraph">{"".join(parts)}</div>'
        return page_shell("Corrected Document", _CORRECTED_LEGEND + body)
