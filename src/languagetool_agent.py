"""
languagetool_agent.py
======================
Step 8: LanguageTool Agent -- primary spelling + rule-based grammar candidate
generator. Runs locally (Java server under the hood via language_tool_python).
"""

from __future__ import annotations

from typing import List

import language_tool_python

from src.config import LanguageToolConfig
from src.models import Candidate, IssueType, SourceAgent, Sentence

_SPELLING_RULE_PREFIXES = ("MORFOLOGIK", "HUNSPELL", "SPELLER")
_TENSE_RULE_HINTS = ("VERB", "TENSE", "AGREEMENT")


class LanguageToolAgent:
    """Primary spelling + grammar detector. One instance per pipeline run."""

    def __init__(self, config: LanguageToolConfig) -> None:
        self.config = config
        try:
            self.tool = language_tool_python.LanguageTool(config.language)
            self.available = True
        except Exception:
            self.tool = None
            self.available = False

    def close(self) -> None:
        if self.tool:
            self.tool.close()

    def run(self, sentence: Sentence) -> List[Candidate]:
        return self.run_batch([sentence])

    def run_batch(self, sentences: List[Sentence]) -> List[Candidate]:
        """Process a list of sentences, returning all detected candidates."""
        if not self.available or not sentences:
            return []
        
        candidates: List[Candidate] = []
        for sentence in sentences:
            if sentence.doc_char_start is None:
                continue
            matches = self.tool.check(sentence.text)
            for m in matches:
                if not m.replacements:
                    continue
                issue_type = self._classify(m.rule_id, m.rule_issue_type)
                candidates.append(Candidate(
                    sentence_id=sentence.sentence_id,
                    char_start=sentence.doc_char_start + m.offset,
                    char_end=sentence.doc_char_start + m.offset + m.error_length,
                    original_text=sentence.text[m.offset:m.offset + m.error_length],
                    suggested_text=m.replacements[0],
                    issue_type=issue_type,
                    source=SourceAgent.LANGUAGETOOL,
                    reason=m.message,
                    confidence=0.75,
                ))
        return candidates

    @staticmethod
    def _classify(rule_id: str, rule_issue_type: str) -> IssueType:
        rid = rule_id.upper()
        if any(p in rid for p in _SPELLING_RULE_PREFIXES) or rule_issue_type == "misspelling":
            return IssueType.SPELLING
        if any(h in rid for h in _TENSE_RULE_HINTS):
            return IssueType.TENSE if "TENSE" in rid else IssueType.GRAMMAR
        if rule_issue_type == "typographical":
            return IssueType.PUNCTUATION
        return IssueType.GRAMMAR
