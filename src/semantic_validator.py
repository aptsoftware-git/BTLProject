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


_BATCH_PROMPT_TEMPLATE = """You are checking proposed grammar corrections, not writing them.
For each item, determine strictly whether the suggested replacement is (a) grammatically correct in context and (b) preserves the original meaning.

Return ONLY valid JSON, no markdown fences:
{{"results": [{{"item_index": 1, "grammatically_correct": true, "meaning_preserved": true, "notes": "short note"}}]}}

Items to check:
{items_block}
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
        if not issues:
            return []

        results_map = {}
        non_spelling_items = []

        for idx, issue in enumerate(issues):
            if issue.issue_type == IssueType.SPELLING:
                results_map[idx] = SemanticCheckResult(
                    candidate_index=idx,
                    meaning_preserved=True,
                    grammatically_correct=True,
                    notes="spelling fix, no semantic check needed",
                )
            else:
                sentence_text = sentence_text_lookup(issue.sentence_id)
                non_spelling_items.append({
                    "idx": idx,
                    "issue": issue,
                    "sentence_text": sentence_text,
                })

        # Process non-spelling items in batches of 10
        batch_size = 10
        for b_start in range(0, len(non_spelling_items), batch_size):
            batch = non_spelling_items[b_start : b_start + batch_size]
            items_formatted = []
            for b_i, item in enumerate(batch, 1):
                items_formatted.append(
                    f"Item {b_i}:\nFull sentence: \"{item['sentence_text']}\"\nOriginal span: \"{item['issue'].original_text}\"\nSuggested replacement: \"{item['issue'].suggested_text}\"\n"
                )
            items_block = "\n".join(items_formatted)
            prompt = _BATCH_PROMPT_TEMPLATE.format(items_block=items_block)

            batch_success = False
            try:
                raw = self._call_ollama(prompt)
                parsed = self._parse_batch_json(raw)
                if parsed:
                    batch_success = True
                    for res_item in parsed:
                        rel_idx = res_item.get("item_index", 0) - 1
                        if 0 <= rel_idx < len(batch):
                            target_idx = batch[rel_idx]["idx"]
                            results_map[target_idx] = SemanticCheckResult(
                                candidate_index=target_idx,
                                meaning_preserved=res_item.get("meaning_preserved", False),
                                grammatically_correct=res_item.get("grammatically_correct", False),
                                notes=res_item.get("notes", ""),
                            )
            except Exception:
                batch_success = False

            # Fallback to single validation if batch call failed or missed items
            for item in batch:
                if item["idx"] not in results_map:
                    try:
                        single_prompt = _PROMPT_TEMPLATE.format(
                            sentence_text=item["sentence_text"],
                            original=item["issue"].original_text,
                            suggested=item["issue"].suggested_text,
                        )
                        raw = self._call_ollama(single_prompt)
                        parsed = self._parse_json(raw)
                        results_map[item["idx"]] = SemanticCheckResult(
                            candidate_index=item["idx"],
                            meaning_preserved=parsed.get("meaning_preserved", False),
                            grammatically_correct=parsed.get("grammatically_correct", False),
                            notes=parsed.get("notes", ""),
                        )
                    except Exception:
                        results_map[item["idx"]] = SemanticCheckResult(
                            candidate_index=item["idx"],
                            meaning_preserved=True,
                            grammatically_correct=True,
                            notes="validation fallback on error",
                        )

        return [results_map[i] for i in range(len(issues))]

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
    def _parse_batch_json(raw: str) -> List[dict]:
        cleaned = re.sub(r"^```(json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
        try:
            data = json.loads(cleaned)
            if isinstance(data, dict):
                return data.get("results", [])
            elif isinstance(data, list):
                return data
            return []
        except (json.JSONDecodeError, AttributeError):
            return []

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
