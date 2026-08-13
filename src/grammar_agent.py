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
import os
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
        import logging
        self.logger = logging.getLogger("pipeline")

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
        total_paragraphs = len(paragraphs_data)
        successful_paragraphs = 0
        failed_paragraphs = 0

        chunks = [paragraphs_data[i : i + batch_size] for i in range(0, len(paragraphs_data), batch_size)]
        self.logger.info(
            "GrammarAgent: Calling Ollama (model: '%s', host: '%s') across %d paragraph(s) in %d batch(es)...",
            self.config.model, self.config.host, total_paragraphs, len(chunks)
        )

        def safe_process_item(item: dict) -> List[Candidate]:
            nonlocal successful_paragraphs, failed_paragraphs
            protected_str = ", ".join(sorted({t.text for t in item.get("protected_terms", []) if hasattr(t, "text")})) or "(none)"
            prompt = _PROMPT_TEMPLATE.format(protected_terms=protected_str, paragraph_text=item["text"])
            try:
                raw = self._call_ollama(prompt)
                errors = self._parse_json(raw)
                cands = self._candidates_from_errors(item["text"], item["doc_char_start"], errors, sentence_id_for_offset_lookup)
                successful_paragraphs += 1
                return cands
            except Exception as exc:
                failed_paragraphs += 1
                self.logger.warning("GrammarAgent paragraph processing failed for offset %d: %s", item.get("doc_char_start", 0), exc)
                return []

        def process_chunk(chunk: List[dict]) -> List[Candidate]:
            nonlocal successful_paragraphs, failed_paragraphs
            chunk_candidates: List[Candidate] = []
            if len(chunk) == 1:
                return safe_process_item(chunk[0])

            all_protected = set()
            formatted_paragraphs = []
            for idx, p_item in enumerate(chunk, 1):
                for t in p_item.get("protected_terms", []):
                    if hasattr(t, "text"):
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
                if batch_data and isinstance(batch_data, list):
                    batch_success = True
                    for p_res in batch_data:
                        if not isinstance(p_res, dict):
                            continue
                        p_idx = p_res.get("paragraph_index", 0) - 1
                        if 0 <= p_idx < len(chunk):
                            item = chunk[p_idx]
                            errors = p_res.get("errors", [])
                            cands = self._candidates_from_errors(item["text"], item["doc_char_start"], errors, sentence_id_for_offset_lookup)
                            chunk_candidates.extend(cands)
                            successful_paragraphs += 1
            except Exception as batch_exc:
                self.logger.warning("GrammarAgent batch call failed (%s); falling back to single paragraph items.", batch_exc)
                batch_success = False

            if not batch_success:
                for item in chunk:
                    chunk_candidates.extend(safe_process_item(item))

            return chunk_candidates

        if len(chunks) > 1:
            from concurrent.futures import ThreadPoolExecutor
            workers = min(4, len(chunks))
            with ThreadPoolExecutor(max_workers=workers) as executor:
                results = executor.map(process_chunk, chunks)
                for res in results:
                    all_candidates.extend(res)
        else:
            for c in chunks:
                all_candidates.extend(process_chunk(c))

        self.logger.info(
            "GrammarAgent Review Summary — Paragraphs Total: %d, Successful: %d, Failed: %d, Candidates Generated: %d",
            total_paragraphs, successful_paragraphs, failed_paragraphs, len(all_candidates)
        )
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
            if not isinstance(err, dict):
                continue
            original = str(err.get("original", "") or "").strip()
            corrected = str(err.get("corrected", "") or "").strip()
            if not original or original == corrected:
                continue
            span = self._locate_span(paragraph_text, original, used_positions)
            if span is None:
                continue
            start, end = span
            char_start = paragraph_doc_offset + start
            char_end = paragraph_doc_offset + end

            sent_id = sentence_id_for_offset_lookup(char_start)
            sent_obj = None
            try:
                if hasattr(sentence_id_for_offset_lookup, "__code__") and "return_object" in sentence_id_for_offset_lookup.__code__.co_varnames:
                    sent_obj = sentence_id_for_offset_lookup(char_start, return_object=True)
            except Exception:
                sent_obj = None

            page_num = getattr(sent_obj, "page", 1) if sent_obj else 1
            bbox_val = getattr(sent_obj, "bbox", None) if sent_obj else None

            candidates.append(Candidate(
                sentence_id=sent_id,
                char_start=char_start,
                char_end=char_end,
                original_text=original,
                suggested_text=corrected,
                issue_type=self._map_type(str(err.get("type", "grammar"))),
                source=SourceAgent.LLM,
                reason=str(err.get("reason", "") or "Grammar/style suggestion from LLM"),
                confidence=0.75,
                page_number=page_num,
                bbox=bbox_val,
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
                        "options": {
                            "temperature": self.config.temperature,
                            "num_thread": getattr(self.config, "num_thread", None) or (os.cpu_count() or 4),
                        },
                    },
                    timeout=self.config.timeout_seconds,
                )
                resp.raise_for_status()
                return resp.json().get("response", "")
            except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as e:
                last_error = e
                if attempt <= self.config.max_retries:
                    time.sleep(1.5 * attempt)
        raise RuntimeError(
            f"Could not reach Ollama at {self.config.host} after {self.config.max_retries + 1} "
            f"attempts. Last error: {last_error}"
        )

    @staticmethod
    def _extract_json_string(raw: str) -> str:
        if not raw:
            return ""
        cleaned = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
        # Find first '{' or '[' and last '}' or ']'
        first_brace = min([i for i in [cleaned.find("{"), cleaned.find("[")] if i != -1], default=-1)
        last_brace = max([cleaned.rfind("}"), cleaned.rfind("]")], default=-1)
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            return cleaned[first_brace : last_brace + 1]
        return cleaned

    @classmethod
    def _parse_json(cls, raw: str) -> List[dict]:
        json_str = cls._extract_json_string(raw)
        if not json_str:
            return []
        try:
            data = json.loads(json_str)
            if isinstance(data, dict):
                return data.get("errors", [])
            elif isinstance(data, list):
                return data
            return []
        except (json.JSONDecodeError, AttributeError):
            return []

    @classmethod
    def _parse_batch_json(cls, raw: str) -> List[dict]:
        json_str = cls._extract_json_string(raw)
        if not json_str:
            return []
        try:
            data = json.loads(json_str)
            if isinstance(data, dict):
                return data.get("paragraph_results", []) or data.get("errors", [])
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
