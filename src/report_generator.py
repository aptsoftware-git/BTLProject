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
        formatted_issues = []
        raw_issue_dicts = []

        APPROVED_CATEGORIES = {
            "spelling", "grammar", "missing_hyphen", "incorrect_hyphenation",
            "missing_space", "extra_space", "hyphenation", "spacing", "tense", "verb_form"
        }

        REJECTED_KEYWORDS = {
            "style", "rewrite", "tone", "readability", "phrasing", "reword",
            "enhancement", "content", "engaging", "concise", "formal"
        }

        for idx, issue in enumerate(issues):
            type_str = (getattr(issue, "issue_type", "grammar") or "grammar").lower()
            if hasattr(type_str, "value"):
                type_str = type_str.value.lower()
            else:
                type_str = str(type_str).lower()

            reason_str = str(getattr(issue, "reason", "") or "").lower()

            # Skip protected issues or out-of-scope categories
            if getattr(issue, "is_protected", False):
                continue
            if any(kw in type_str or kw in reason_str for kw in REJECTED_KEYWORDS):
                continue

            s = self._sentence_by_id.get(issue.sentence_id)
            page = s.page if (s and getattr(s, "page", None)) else (getattr(issue, "page_number", None) or getattr(issue, "page", 1))

            bbox = getattr(issue, "bbox", None)
            if (not bbox or (isinstance(bbox, dict) and bbox.get("x0", 0) == 0 and bbox.get("x1", 0) == 0)) and s:
                bbox = getattr(s, "bbox", None)

            # Preserve real PDF bbox; NEVER generate synthetic fallback coordinates
            bbox_dict = None
            location_verified = False
            if isinstance(bbox, dict):
                x0 = float(bbox.get("x0", bbox.get("l", 0)) or 0)
                y0 = float(bbox.get("y0", bbox.get("t", 0)) or 0)
                x1 = float(bbox.get("x1", bbox.get("r", 0)) or 0)
                y1 = float(bbox.get("y1", bbox.get("b", 0)) or 0)
                if (x0 != 0 or y0 != 0 or x1 != 0 or y1 != 0) and x1 > x0 and y1 > y0:
                    bbox_dict = {"x0": round(x0, 2), "y0": round(y0, 2), "x1": round(x1, 2), "y1": round(y1, 2)}
                    location_verified = True

            iid = getattr(issue, "issue_id", None) or f"issue_{idx + 1}"
            issue.issue_id = iid
            issue.page_number = int(page)
            issue.bbox = bbox_dict
            formatted_issues.append(issue)

            d = issue.to_dict() if hasattr(issue, "to_dict") else dict(issue.__dict__) if hasattr(issue, "__dict__") else dict(issue)
            d["issue_id"] = iid
            d["sentence_id"] = issue.sentence_id
            d["page"] = int(page)
            d["page_number"] = int(page)
            d["bbox"] = bbox_dict
            d["location_verified"] = location_verified
            d["sentence_text"] = s.text if s else ""
            d["corrected_sentence_text"] = self._apply_corrections(s.text, s.doc_char_start or 0, [issue]) if s else ""
            raw_issue_dicts.append(d)

        report = {
            "total_issues": len(formatted_issues),
            "by_type": self._count_by_type(formatted_issues),
            "issues": raw_issue_dicts,
        }
        return report, self._build_changes_md(formatted_issues), self._build_summary_csv(formatted_issues)

    @staticmethod
    def _val(x):
        return x.value if hasattr(x, "value") else str(x) if x else ""

    @classmethod
    def _count_by_type(cls, issues: List[MergedIssue]) -> dict:
        counts: Dict[str, int] = {}
        for issue in issues:
            t = cls._val(issue.issue_type)
            counts[t] = counts.get(t, 0) + 1
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
                sources = ", ".join(sorted(self._val(s) for s in issue.contributing_sources)) or self._val(issue.source)
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
            sources = "|".join(sorted(self._val(s) for s in issue.contributing_sources)) or self._val(issue.source)
            writer.writerow([
                page, paragraph, issue.sentence_id, self._val(issue.issue_type),
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
