"""
grammar_agent.py
=================
Step 11: LLM Paragraph Reviewer (also serves as Level-2 grammar detection
per the architecture spec -- LanguageTool is Level 1, this local LLM is
Level 2, run over the whole paragraph rather than sentence-by-sentence).

Runs the local LLM (via Ollama) over a whole PARAGRAPH at a time so it has
enough context to catch tense drift across sentences, e.g. "Yesterday he
goes to the school." The model returns structured JSON with explicit
original/corrected spans, which sidesteps the classic problem of diffing
two full rewritten sentences token-by-token.

Protected terms for the paragraph are injected directly into the prompt as
a belt-and-suspenders measure; the REAL guarantee is the Validation Agent
that runs on every candidate afterwards regardless of what the LLM does.
"""

from __future__ import annotations

import json
import re
import time
from typing import Callable, Dict, List, Tuple

import requests

from src.config import OllamaConfig
from src.models import Candidate, IssueType, ProtectedTerm, SourceAgent

_PROMPT_TEMPLATE = """You are a spelling and grammar correction engine. You detect and correct ONLY genuine \
errors in spelling, grammar, tense, and punctuation.
CRITICAL INSTRUCTIONS:
- You must NEVER rewrite the paragraph.
- You must NEVER paraphrase.
- You must NEVER improve style or change wording for clarity or flow.
- You must NEVER simplify sentences.
- You must ONLY target objective spelling, grammar, tense, and punctuation mistakes.
- You must NOT modify any name of a person, author, organization, company, place, product, or brand.
- Do not modify variables, equations, programming identifiers, file names, or repeated technical terms.

PROTECTED TOKENS (do not alter these under any circumstances, in any form, even partially):
{protected_terms}

Before producing your final answer, silently check if the original span overlaps with any token in the PROTECTED TOKENS list. If it does, drop that correction entirely.

Return ONLY valid JSON, no prose, no markdown fences, no code blocks:
{{"errors": [{{"original": "...", "corrected": "...", "reason": "...", "type": "spelling|grammar|tense|punctuation"}}]}}

If there are no errors, return {{"errors": []}}.

Paragraph:
\"\"\"{paragraph_text}\"\"\"
"""


_BATCH_PROMPT_TEMPLATE = """You are a spelling and grammar correction engine. You detect and correct ONLY genuine \
errors in spelling, grammar, tense, and punctuation across multiple paragraphs.
CRITICAL INSTRUCTIONS:
- You must NEVER rewrite paragraphs or paraphrase.
- You must NEVER improve style or change wording for flow.
- You must ONLY target objective spelling, grammar, tense, and punctuation mistakes.
- You must NOT modify any name of a person, organization, company, place, product, or protected token.

PROTECTED TOKENS:
{protected_terms}

Return ONLY valid JSON with no markdown fences:
{{"paragraph_results": [{{"paragraph_index": 1, "errors": [{{"original": "...", "corrected": "...", "reason": "...", "type": "spelling|grammar|tense|punctuation"}}]}}]}}

Paragraphs to review:
{paragraphs_block}
"""


class GrammarAgent:
    """Local-LLM based Level-2 grammar check + paragraph-level reviewer."""

    def __init__(self, config: OllamaConfig) -> None:
        self.config = config

    def run(
        self,
        paragraph_text: str,
        paragraph_doc_offset: int,
        sentence_id_for_offset_lookup: Callable[[int], int],
        protected_terms_in_paragraph: List[ProtectedTerm],
    ) -> List[Candidate]:
        results = self.run_batch(
            [{
                "text": paragraph_text,
                "doc_char_start": paragraph_doc_offset,
                "protected_terms": protected_terms_in_paragraph,
            }],
            sentence_id_for_offset_lookup=sentence_id_for_offset_lookup,
            batch_size=1,
        )
        return results

    def run_batch(
        self,
        paragraphs_data: List[dict],
        sentence_id_for_offset_lookup: Callable[[int], int],
        batch_size: int = 15,
    ) -> List[Candidate]:
        if not paragraphs_data:
            return []

        all_candidates: List[Candidate] = []

        # Process in chunks of batch_size
        for i in range(0, len(paragraphs_data), batch_size):
            chunk = paragraphs_data[i : i + batch_size]
            
            # Fast single fallback if batch_size == 1
            if len(chunk) == 1:
                item = chunk[0]
                protected_str = ", ".join(sorted({t.text for t in item["protected_terms"]})) or "(none)"
                prompt = _PROMPT_TEMPLATE.format(protected_terms=protected_str, paragraph_text=item["text"])
                try:
                    raw = self._call_ollama(prompt)
                    errors = self._parse_json(raw)
                    all_candidates.extend(
                        self._candidates_from_errors(item["text"], item["doc_char_start"], errors, sentence_id_for_offset_lookup)
                    )
                except Exception:
                    pass
                continue

            # Multi-paragraph batch execution
            all_protected = set()
            formatted_paragraphs = []
            for idx, p_item in enumerate(chunk, 1):
                for t in p_item.get("protected_terms", []):
                    all_protected.add(t.text)
                formatted_paragraphs.append(f"[Paragraph {idx}]\n{p_item['text']}\n")

            protected_str = ", ".join(sorted(all_protected)) or "(none)"
            paragraphs_block = "\n".join(formatted_paragraphs)
            prompt = _BATCH_PROMPT_TEMPLATE.format(
                protected_terms=protected_str, paragraphs_block=paragraphs_block
            )

            batch_success = False
            try:
                raw = self._call_ollama(prompt)
                batch_data = self._parse_batch_json(raw)
                if batch_data:
                    batch_success = True
                    for p_res in batch_data:
                        p_idx = p_res.get("paragraph_index", 0) - 1
                        if 0 <= p_idx < len(chunk):
                            item = chunk[p_idx]
                            errors = p_res.get("errors", [])
                            all_candidates.extend(
                                self._candidates_from_errors(item["text"], item["doc_char_start"], errors, sentence_id_for_offset_lookup)
                            )
            except Exception:
                batch_success = False

            # Fallback to individual processing if batch failed
            if not batch_success:
                for item in chunk:
                    protected_str = ", ".join(sorted({t.text for t in item["protected_terms"]})) or "(none)"
                    prompt = _PROMPT_TEMPLATE.format(protected_terms=protected_str, paragraph_text=item["text"])
                    try:
                        raw = self._call_ollama(prompt)
                        errors = self._parse_json(raw)
                        all_candidates.extend(
                            self._candidates_from_errors(item["text"], item["doc_char_start"], errors, sentence_id_for_offset_lookup)
                        )
                    except Exception:
                        pass

        return all_candidates

    def _candidates_from_errors(
        self,
        paragraph_text: str,
        paragraph_doc_offset: int,
        errors: List[dict],
        sentence_id_for_offset_lookup: Callable[[int], int],
    ) -> List[Candidate]:
        candidates = []
        used_positions: Dict[str, int] = {}
        for err in errors:
            original = err.get("original", "").strip()
            corrected = err.get("corrected", "").strip()
            if not original or original == corrected:
                continue
            span = self._locate_span(paragraph_text, original, used_positions)
            if span is None:
                continue
            start, end = span
            candidates.append(Candidate(
                sentence_id=sentence_id_for_offset_lookup(paragraph_doc_offset + start),
                char_start=paragraph_doc_offset + start,
                char_end=paragraph_doc_offset + end,
                original_text=original,
                suggested_text=corrected,
                issue_type=self._map_type(err.get("type", "grammar")),
                source=SourceAgent.LLM,
                reason=err.get("reason", ""),
                confidence=0.7,
            ))
        return candidates

    def _call_ollama(self, prompt: str) -> str:
        last_error = None
        for attempt in range(1, self.config.max_retries + 2):
            try:
                resp = requests.post(
                    f"{self.config.host}/api/generate",
                    json={
                        "model": self.config.model, "prompt": prompt, "stream": False,
                        "options": {"temperature": self.config.temperature},
                    },
                    timeout=self.config.timeout_seconds,
                )
                resp.raise_for_status()
                return resp.json().get("response", "")
            except (requests.ConnectionError, requests.Timeout) as e:
                last_error = e
                if attempt <= self.config.max_retries:
                    time.sleep(1.5 * attempt)  # brief backoff before retrying over the network
        raise RuntimeError(
            f"Could not reach Ollama at {self.config.host} after {self.config.max_retries + 1} "
            f"attempts. Check the IP, that 'ollama serve' is bound to 0.0.0.0 (not just "
            f"127.0.0.1) on that machine, and that nothing blocks port 11434 between the two "
            f"machines. Last error: {last_error}"
        )

    @staticmethod
    def _parse_json(raw: str) -> List[dict]:
        # strip stray markdown fences the model sometimes adds despite instructions
        cleaned = re.sub(r"^```(json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
        try:
            data = json.loads(cleaned)
            return data.get("errors", [])
        except (json.JSONDecodeError, AttributeError):
            return []  # fail closed: no candidates rather than a crash

    @staticmethod
    def _parse_batch_json(raw: str) -> List[dict]:
        cleaned = re.sub(r"^```(json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
        try:
            data = json.loads(cleaned)
            if isinstance(data, dict):
                return data.get("paragraph_results", [])
            elif isinstance(data, list):
                return data
            return []
        except (json.JSONDecodeError, AttributeError):
            return []

    @staticmethod
    def _locate_span(paragraph_text: str, original: str, used_positions: Dict[str, int]) -> Tuple[int, int] | None:
        start_from = used_positions.get(original, 0)
        idx = paragraph_text.find(original, start_from)
        if idx == -1:
            idx = paragraph_text.find(original)  # retry from the top as a fallback
            if idx == -1:
                return None
        used_positions[original] = idx + len(original)
        return idx, idx + len(original)

    @staticmethod
    def _map_type(type_str: str) -> IssueType:
        mapping = {"spelling": IssueType.SPELLING, "grammar": IssueType.GRAMMAR, "tense": IssueType.TENSE}
        return mapping.get(type_str.lower(), IssueType.GRAMMAR)
