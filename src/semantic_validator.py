"""
semantic_validator.py
======================
Step 12: Semantic Validator.

Runs AFTER the Validation Agent (protected-terms filter), and only on
GRAMMAR / TENSE candidates (spelling fixes don't need a meaning check).
Confirms that applying the suggested correction still makes sense in the
full sentence -- catches cases where the LLM's own correction over-corrects
or drifts from the original meaning. This is a second, independent LLM call
with a narrow yes/no style prompt, which is cheaper and more reliable than
asking for open-ended review.
"""

from __future__ import annotations

import json
import re
import time
from typing import Callable, List, Tuple

import requests

from src.config import OllamaConfig
from src.models import IssueType, SemanticCheckResult, ValidatedIssue

_PROMPT_TEMPLATE = """You are checking a proposed grammar correction, not writing one. \
Given the ORIGINAL sentence, the ORIGINAL span, and the SUGGESTED replacement, answer strictly \
whether the suggestion is (a) grammatically correct in context and (b) preserves the original \
meaning without adding, removing, or changing any information. Do not consider style preferences.

Return ONLY valid JSON, no prose, no markdown fences:
{{"grammatically_correct": true|false, "meaning_preserved": true|false, "notes": "one short sentence"}}

Full sentence: "{sentence_text}"
Original span: "{original}"
Suggested replacement: "{suggested}"
"""


class SemanticValidator:
    """Independent second-pass LLM check that a correction preserves meaning."""

    def __init__(self, config: OllamaConfig) -> None:
        self.config = config

    def run(
        self, issues: List[ValidatedIssue], sentence_text_lookup: Callable[[int], str]
    ) -> List[SemanticCheckResult]:
        """
        sentence_text_lookup: callable(sentence_id) -> full sentence text,
        used to give the model surrounding context beyond just the span.
        """
        results = []
        for idx, issue in enumerate(issues):
            if issue.issue_type == IssueType.SPELLING:
                results.append(SemanticCheckResult(
                    candidate_index=idx, meaning_preserved=True, grammatically_correct=True,
                    notes="spelling fix, no semantic check needed",
                ))
                continue
            sentence_text = sentence_text_lookup(issue.sentence_id)
            prompt = _PROMPT_TEMPLATE.format(
                sentence_text=sentence_text, original=issue.original_text, suggested=issue.suggested_text,
            )
            raw = self._call_ollama(prompt)
            parsed = self._parse_json(raw)
            results.append(SemanticCheckResult(
                candidate_index=idx,
                meaning_preserved=parsed.get("meaning_preserved", False),
                grammatically_correct=parsed.get("grammatically_correct", False),
                notes=parsed.get("notes", ""),
            ))
        return results

    def _call_ollama(self, prompt: str) -> str:
        last_error = None
        for attempt in range(1, self.config.max_retries + 2):
            try:
                resp = requests.post(
                    f"{self.config.host}/api/generate",
                    json={
                        "model": self.config.model, "prompt": prompt, "stream": False,
                        "options": {"temperature": 0.0},
                    },
                    timeout=self.config.timeout_seconds,
                )
                resp.raise_for_status()
                return resp.json().get("response", "")
            except (requests.ConnectionError, requests.Timeout) as e:
                last_error = e
                if attempt <= self.config.max_retries:
                    time.sleep(1.5 * attempt)
        raise RuntimeError(f"Could not reach Ollama at {self.config.host}. Last error: {last_error}")

    @staticmethod
    def _parse_json(raw: str) -> dict:
        cleaned = re.sub(r"^```(json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return {"grammatically_correct": False, "meaning_preserved": False, "notes": "parse failure"}

    @staticmethod
    def filter_passed(
        issues: List[ValidatedIssue], results: List[SemanticCheckResult]
    ) -> Tuple[List[ValidatedIssue], List[ValidatedIssue]]:
        passed, failed = [], []
        for issue, result in zip(issues, results):
            if result.grammatically_correct and result.meaning_preserved:
                passed.append(issue)
            else:
                failed.append(issue)
        return passed, failed
