"""
gramformer_agent.py
===================
Primary Grammar Checking Engine using Gramformer (fine-tuned Seq2Seq model) and ERRANT.

Workflow:
  1. Filter and batch running-text sentences from 04_sentences/sentences.json.
  2. Run batched sequence-to-sequence inference with Gramformer model (prithivida/grammar_error_correcter_v1).
  3. Extract precise word/phrase-level edits using ERRANT get_edits().
  4. Anchor exact character offsets (start, end) against sentence text and document-level offsets.
  5. Filter against protected terms, entities, acronyms, and numbers.
  6. Return Candidate objects with exact provenance for PDF grounding and reporting.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List, Optional, Set, Tuple

# Suppress Hugging Face background advisory/telemetry threads
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["TRANSFORMERS_NO_ADVISORY_WARNINGS"] = "1"
os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "0"

import errant
import torch
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

from src.config import GramformerConfig, ROOT_DIR
from src.domain_words import is_valid_domain_term
from src.models import Candidate, IssueType, ProtectedTerm, Sentence, SourceAgent
from src.spell_filter import (
    CANONICAL_CORPORATE_ENTITIES,
    CANONICAL_COUNTRIES,
    CANONICAL_INDIAN_LOCATIONS,
    KNOWN_ACRONYMS,
)

logger = logging.getLogger("backend")


# Map ERRANT rule tags to IssueType and human-readable messages
ERRANT_TYPE_MAP = {
    "R:VERB:SVA": (IssueType.GRAMMAR, "Subject-verb agreement error"),
    "R:VERB:TENSE": (IssueType.TENSE, "Verb tense inconsistency"),
    "U:VERB:TENSE": (IssueType.TENSE, "Unnecessary verb tense marker"),
    "M:VERB:TENSE": (IssueType.TENSE, "Missing verb tense inflection"),
    "R:VERB:FORM": (IssueType.GRAMMAR, "Incorrect verb form"),
    "R:VERB": (IssueType.GRAMMAR, "Incorrect verb usage"),
    "R:NOUN:NUM": (IssueType.GRAMMAR, "Noun number (singular/plural) agreement error"),
    "R:NOUN": (IssueType.GRAMMAR, "Noun usage error"),
    "R:PRON": (IssueType.GRAMMAR, "Pronoun agreement error"),
    "R:DET": (IssueType.GRAMMAR, "Incorrect determiner or article"),
    "M:DET": (IssueType.GRAMMAR, "Missing determiner or article"),
    "U:DET": (IssueType.GRAMMAR, "Unnecessary determiner or article"),
    "R:PREP": (IssueType.GRAMMAR, "Incorrect preposition"),
    "M:PREP": (IssueType.GRAMMAR, "Missing preposition"),
    "U:PREP": (IssueType.GRAMMAR, "Unnecessary preposition"),
    "R:PUNCT": (IssueType.PUNCTUATION, "Incorrect punctuation"),
    "M:PUNCT": (IssueType.PUNCTUATION, "Missing punctuation mark"),
    "U:PUNCT": (IssueType.PUNCTUATION, "Unnecessary punctuation mark"),
    "R:SPELL": (IssueType.SPELLING, "Spelling error detected during grammar analysis"),
    "R:WO": (IssueType.GRAMMAR, "Word order error"),
    "R:ORTH": (IssueType.PUNCTUATION, "Spacing or hyphenation error"),
    "R:MORPH": (IssueType.GRAMMAR, "Morphological error"),
    "R:CONJ": (IssueType.GRAMMAR, "Conjunction error"),
    "R:ADJ": (IssueType.GRAMMAR, "Adjective form error"),
    "R:ADV": (IssueType.GRAMMAR, "Adverb form error"),
}


class GramformerAgent:
    """
    Primary Grammar Engine backed by Gramformer Seq2Seq neural network and ERRANT.
    """

    def __init__(self, config: Optional[GramformerConfig] = None) -> None:
        self.config = config or GramformerConfig()
        self.device = "cuda" if (self.config.use_gpu and torch.cuda.is_available()) else "cpu"
        self.model_name = self.config.model_name
        self.batch_size = self.config.batch_size
        self.max_length = self.config.max_length

        logger.info("Initializing GramformerAgent with model '%s' on %s...", self.model_name, self.device)
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            self.model = AutoModelForSeq2SeqLM.from_pretrained(self.model_name)
            self.model.to(self.device)
            self.model.eval()
            self.annotator = errant.load("en")
            self.available = True
            logger.info("GramformerAgent initialized successfully.")
        except Exception as exc:
            logger.exception("Failed to initialize GramformerAgent: %s", exc)
            self.tokenizer = None
            self.model = None
            self.annotator = None
            self.available = False

    def _should_skip_sentence(self, text: str) -> bool:
        """Filter out non-sentences, numbers, table fragments, and short headings."""
        t = text.strip()
        if len(t) < 6:
            return True
        # Skip if no alphabetic characters
        if not re.search(r"[A-Za-z]", t):
            return True
        # Skip pure number lists / financial rows e.g. "12.3 45.6 78.9"
        words = t.split()
        if len(words) <= 2 and not any(len(w) >= 3 and w.isalpha() for w in words):
            return True
        alpha_count = sum(1 for c in t if c.isalpha())
        digit_count = sum(1 for c in t if c.isdigit())
        if digit_count > alpha_count and len(words) < 5:
            return True
        return False

    def _is_protected(
        self,
        orig_text: str,
        sug_text: str,
        char_start: int,
        char_end: int,
        protected_terms: Optional[List[ProtectedTerm]],
    ) -> bool:
        """Returns True if the edit touches a protected name, place, org, acronym, domain term, or number."""
        orig_clean = orig_text.strip()
        orig_lower = orig_clean.lower()
        sug_lower = sug_text.strip().lower()

        # 1. Number preservation: never change numbers/amounts/dates
        if re.search(r"\d", orig_clean) or re.search(r"\d", sug_text):
            return True

        # 2. Acronyms & all-caps terms
        if (orig_clean.isupper() and len(orig_clean) >= 2) or "/" in orig_clean or orig_lower in KNOWN_ACRONYMS:
            return True

        # 3. Canonical Entities
        if orig_lower in CANONICAL_CORPORATE_ENTITIES or orig_lower in CANONICAL_COUNTRIES or orig_lower in CANONICAL_INDIAN_LOCATIONS:
            return True

        # 4. Domain Terms
        if is_valid_domain_term(orig_lower):
            return True

        # 5. Span / Text Protected Terms Check
        if protected_terms:
            for pt in protected_terms:
                pt_text_lower = pt.text.strip().lower()
                if pt_text_lower == orig_lower or pt_text_lower == sug_lower:
                    return True
                # Span overlap check
                if pt.char_start < char_end and pt.char_end > char_start:
                    return True

        return False

    def correct_batch(
        self,
        sentences: List[Sentence],
        protected_terms: Optional[List[ProtectedTerm]] = None,
    ) -> List[Candidate]:
        """
        Process sentences in batches through Gramformer, extract edits using ERRANT,
        and construct Candidates with exact character offsets for PDF grounding.
        """
        if not self.available or not sentences:
            if not self.available:
                raise RuntimeError("GramformerAgent is not available or model failed to load.")
            return []

        # Filter sentences to review
        candidates: List[Candidate] = []
        reviewable_sentences: List[Sentence] = []
        for s in sentences:
            if not self._should_skip_sentence(s.text):
                reviewable_sentences.append(s)

        logger.info("Gramformer: Reviewing %d/%d sentences...", len(reviewable_sentences), len(sentences))
        if not reviewable_sentences:
            return []

        # Batch inference
        for i in range(0, len(reviewable_sentences), self.batch_size):
            batch_sents = reviewable_sentences[i:i + self.batch_size]
            prompt_texts = ["gec: " + s.text.strip() for s in batch_sents]

            try:
                inputs = self.tokenizer(
                    prompt_texts,
                    padding=True,
                    truncation=True,
                    max_length=self.max_length,
                    return_tensors="pt"
                ).to(self.device)

                with torch.no_grad():
                    outputs = self.model.generate(
                        **inputs,
                        max_length=self.max_length,
                        num_beams=4,
                        early_stopping=True
                    )

                corrected_texts = self.tokenizer.batch_decode(outputs, skip_special_tokens=True)

                for sent, corrected in zip(batch_sents, corrected_texts):
                    corrected = corrected.strip()
                    orig_text = sent.text.strip()
                    if orig_text == corrected:
                        continue

                    # Extract precise edits with ERRANT
                    try:
                        orig_doc = self.annotator.parse(orig_text)
                        cor_doc = self.annotator.parse(corrected)
                        edits = self.annotator.annotate(orig_doc, cor_doc)
                    except Exception as err:
                        logger.debug("ERRANT annotation failed for sentence %d: %s", sent.sentence_id, err)
                        continue

                    base_doc_offset = sent.doc_char_start if sent.doc_char_start is not None else (sent.start_offset or 0)

                    for e in edits:
                        # Character spans in the sentence
                        span = orig_doc[e.o_start:e.o_end]
                        start_in_sent = span.start_char
                        end_in_sent = span.end_char
                        edit_orig_text = span.text.strip()
                        edit_sug_text = e.c_str.strip()

                        # Skip empty or identical edits
                        if not edit_orig_text and not edit_sug_text:
                            continue
                        if edit_orig_text.lower() == edit_sug_text.lower() and len(edit_orig_text) > 0:
                            continue

                        # Compute document-level character offsets
                        cand_doc_start = base_doc_offset + start_in_sent
                        cand_doc_end = base_doc_offset + end_in_sent

                        # Check protected terms
                        if self._is_protected(edit_orig_text, edit_sug_text, cand_doc_start, cand_doc_end, protected_terms):
                            continue

                        # Map ERRANT classification
                        issue_type, default_reason = ERRANT_TYPE_MAP.get(
                            e.type, (IssueType.GRAMMAR, f"Grammar issue ({e.type})")
                        )

                        candidates.append(Candidate(
                            sentence_id=sent.sentence_id,
                            char_start=cand_doc_start,
                            char_end=cand_doc_end,
                            original_text=edit_orig_text,
                            suggested_text=edit_sug_text,
                            issue_type=issue_type,
                            source=SourceAgent.GRAMFORMER,
                            reason=default_reason,
                            confidence=0.85,
                            page_number=sent.page,
                            bbox=sent.bbox,
                        ))

            except Exception as batch_err:
                logger.warning("Gramformer batch execution error at index %d: %s", i, batch_err)

        logger.info("Gramformer: Extracted %d candidate grammar findings.", len(candidates))
        return candidates
