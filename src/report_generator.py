"""
report_generator.py
=====================
Step 16: Report Generator.

Produces three artifacts from the final merged issue list:
  - report.json   machine-readable, full detail per issue
  - changes.md     human-readable, grouped by sentence
  - summary.csv    one row per issue: page, paragraph, sentence, issue type,
                    original, replacement, confidence, reason, source agent(s)
"""

from __future__ import annotations

import csv
import io
from typing import Dict, List, Tuple

from src.models import MergedIssue, Sentence


class ReportGenerator:
    def __init__(self, full_text: str, sentences: List[Sentence]) -> None:
        self.full_text = full_text
        self.sentences = sentences
        self._sentence_by_id: Dict[int, Sentence] = {s.sentence_id: s for s in sentences}

    def build(self, issues: List[MergedIssue]) -> Tuple[dict, str, str]:
        """Returns (report_dict, changes_markdown, summary_csv)."""
        report = {
            "total_issues": len(issues),
            "by_type": self._count_by_type(issues),
            # Raw MergedIssue dataclass instances -- utils.save_json /
            # utils.to_serializable know how to serialize these directly,
            # so no manual per-item conversion is needed here.
            "issues": issues,
        }
        return report, self._build_changes_md(issues), self._build_summary_csv(issues)

    @staticmethod
    def _count_by_type(issues: List[MergedIssue]) -> dict:
        counts: Dict[str, int] = {}
        for issue in issues:
            counts[issue.issue_type.value] = counts.get(issue.issue_type.value, 0) + 1
        return counts

    def _build_changes_md(self, issues: List[MergedIssue]) -> str:
        by_sentence: Dict[int, List[MergedIssue]] = {}
        for issue in issues:
            by_sentence.setdefault(issue.sentence_id, []).append(issue)

        lines = ["# Changes Report\n"]
        for sentence in self.sentences:
            sentence_issues = by_sentence.get(sentence.sentence_id)
            if not sentence_issues:
                continue
            corrected_text = self._apply_corrections(sentence.text, sentence.doc_char_start or 0, sentence_issues)
            lines.append(f"## Page {sentence.page}, Sentence {sentence.sentence_id}\n")
            lines.append(f"**Original**\n\n{sentence.text}\n")
            lines.append(f"**Corrected**\n\n{corrected_text}\n")
            lines.append("---\n")
            for issue in sentence_issues:
                sources = ", ".join(sorted(s.value for s in issue.contributing_sources)) or issue.source.value
                lines.append(f"`{issue.original_text}` \u2192 `{issue.suggested_text}`  ")
                lines.append(
                    f"*{issue.reason}* (Confidence: {issue.final_confidence:.2f}, "
                    f"Agreement Count: {issue.agreement_count}, "
                    f"Source Agents: {sources}, "
                    f"Protected Reason: {issue.protected_reason or 'None'})\n"
                )
            lines.append("\n")
        return "\n".join(lines)

    def _build_summary_csv(self, issues: List[MergedIssue]) -> str:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow([
            "page", "paragraph", "sentence", "issue_type", "original",
            "replacement", "confidence", "agreement_count", "source_agents",
            "reason", "protected_reason",
        ])
        for issue in sorted(issues, key=lambda i: i.char_start):
            sentence = self._sentence_by_id.get(issue.sentence_id)
            page = sentence.page if sentence else ""
            paragraph = sentence.paragraph_id if sentence else ""
            sources = "|".join(sorted(s.value for s in issue.contributing_sources)) or issue.source.value
            writer.writerow([
                page, paragraph, issue.sentence_id, issue.issue_type.value,
                issue.original_text, issue.suggested_text,
                f"{issue.final_confidence:.2f}", issue.agreement_count, sources,
                issue.reason, issue.protected_reason or "None",
            ])
        return buffer.getvalue()

    @staticmethod
    def _apply_corrections(sentence_text: str, doc_offset: int, issues: List[MergedIssue]) -> str:
        issues_sorted = sorted(issues, key=lambda i: i.char_start, reverse=True)
        text = sentence_text
        for issue in issues_sorted:
            local_start = issue.char_start - doc_offset
            local_end = issue.char_end - doc_offset
            if 0 <= local_start <= len(text) and 0 <= local_end <= len(text):
                text = text[:local_start] + issue.suggested_text + text[local_end:]
        return text
