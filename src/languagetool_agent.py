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
        """Process a list of sentences concurrently with real-time progress logging, returning all detected candidates."""
        if not self.available or not sentences:
            return []

        import logging
        import time
        logger = logging.getLogger("backend")
        total_sents = len(sentences)
        logger.info("LanguageTool: Starting rule & spell check on %d sentence(s)...", total_sents)

        def check_sentence(sentence: Sentence) -> List[Candidate]:
            if sentence.doc_char_start is None or not sentence.text.strip():
                return []
            sentence_candidates = []
            try:
                matches = self.tool.check(sentence.text)
                for m in matches:
                    if not m.replacements:
                        continue
                    issue_type = self._classify(m.rule_id, m.rule_issue_type)
                    sentence_candidates.append(Candidate(
                        sentence_id=sentence.sentence_id,
                        char_start=sentence.doc_char_start + m.offset,
                        char_end=sentence.doc_char_start + m.offset + m.error_length,
                        original_text=sentence.text[m.offset:m.offset + m.error_length],
                        suggested_text=m.replacements[0],
                        issue_type=issue_type,
                        source=SourceAgent.LANGUAGETOOL,
                        reason=m.message,
                        confidence=0.75,
                        page_number=sentence.page,
                        bbox=sentence.bbox,
                    ))
            except Exception:
                pass
            return sentence_candidates

        candidates: List[Candidate] = []
        start_time = time.time()

        if len(sentences) > 5:
            from concurrent.futures import ThreadPoolExecutor, as_completed
            workers = min(16, max(4, len(sentences) // 25))
            completed_count = 0
            last_log_time = start_time

            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {executor.submit(check_sentence, s): s for s in sentences}
                for fut in as_completed(futures):
                    completed_count += 1
                    try:
                        res = fut.result()
                        if res:
                            candidates.extend(res)
                    except Exception:
                        pass

                    now = time.time()
                    if (now - last_log_time >= 2.5) or (completed_count == total_sents) or (completed_count % 500 == 0):
                        elapsed = max(0.1, now - start_time)
                        speed = completed_count / elapsed
                        rem = total_sents - completed_count
                        eta_sec = rem / speed if speed > 0 else 0
                        eta_str = f"{int(eta_sec // 60)}m {int(eta_sec % 60):02d}s" if eta_sec >= 60 else f"{int(eta_sec)}s"
                        logger.info(
                            "LanguageTool Progress: %d/%d sentences (%.1f%%) | Speed: %.1f sent/s | ETA: %s | Candidates flagged: %d",
                            completed_count, total_sents, (completed_count / total_sents) * 100, speed, eta_str, len(candidates)
                        )
                        last_log_time = now
        else:
            for s in sentences:
                candidates.extend(check_sentence(s))

        total_duration = round(time.time() - start_time, 2)
        logger.info(
            "LanguageTool: Completed check on %d sentences in %.2fs (%.1f sent/s) -> %d candidate(s) flagged.",
            total_sents, total_duration, (total_sents / max(0.01, total_duration)), len(candidates)
        )
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
