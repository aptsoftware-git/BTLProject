"""
sentence_splitter.py
======================
Stage 6 of the pipeline: Sentence Splitter.

Uses spaCy's sentence boundary detection. If the configured spaCy
model is not installed / downloadable, falls back to a conservative
regex-based splitter so the pipeline still functions end-to-end.
"""

from __future__ import annotations

import logging
import re
from typing import List, Optional
import spacy

from src.config import SpacyConfig
from src.models import Document, Sentence


_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'\u201c])")


class SentenceSplitter:
    """Splits paragraph text into Sentence objects."""

    def __init__(self, logger: logging.Logger, config: SpacyConfig, nlp: Optional[spacy.Language] = None) -> None:
        self.logger = logger
        self.config = config
        self._nlp = nlp

    def _get_nlp(self):
        if self._nlp is not None:
            return self._nlp
        if self._nlp is False:
            return None
        try:
            import spacy
            try:
                # Disable heavy components for ultra-fast sentence boundary detection
                nlp = spacy.load(self.config.model_name, disable=["tagger", "parser", "ner", "lemmatizer"])
                if "sentencizer" not in nlp.pipe_names:
                    nlp.add_pipe("sentencizer")
                self._nlp = nlp
            except Exception:
                nlp = spacy.blank("en")
                nlp.add_pipe("sentencizer")
                self._nlp = nlp
        except Exception as exc:  # noqa: BLE001
            self.logger.warning(
                "spaCy model '%s' unavailable (%s); using regex sentence splitter",
                self.config.model_name, exc,
            )
            self._nlp = False
        return self._nlp

    def split(self, document: Document) -> Document:
        self.logger.stage("Sentence splitting")
        nlp = self._get_nlp()
        sentence_counter = 0

        if nlp and document.paragraphs:
            texts = [p.text for p in document.paragraphs]
            docs = list(nlp.pipe(texts, batch_size=500))
            for paragraph, doc in zip(document.paragraphs, docs):
                sentences: List[Sentence] = []
                spans = [(s.text.strip(), s.start_char, s.end_char) for s in doc.sents if s.text.strip()]
                for text, start, end in spans:
                    sentences.append(
                        Sentence(
                            sentence_id=sentence_counter,
                            paragraph_id=paragraph.paragraph_id,
                            page=paragraph.page,
                            text=text,
                            start_offset=start,
                            end_offset=end,
                        )
                    )
                    sentence_counter += 1
                paragraph.sentences = sentences
        else:
            for paragraph in document.paragraphs:
                sentences: List[Sentence] = []
                spans = self._regex_split(paragraph.text)
                for text, start, end in spans:
                    sentences.append(
                        Sentence(
                            sentence_id=sentence_counter,
                            paragraph_id=paragraph.paragraph_id,
                            page=paragraph.page,
                            text=text,
                            start_offset=start,
                            end_offset=end,
                        )
                    )
                    sentence_counter += 1
                paragraph.sentences = sentences

        total_sentences = sum(len(p.sentences) for p in document.paragraphs)
        self.logger.info("Split into %d sentence(s)", total_sentences)
        return document

    @staticmethod
    def _regex_split(text: str):
        parts = _SENTENCE_BOUNDARY.split(text)
        spans = []
        cursor = 0
        for part in parts:
            part = part.strip()
            if not part:
                continue
            start = text.find(part, cursor)
            if start == -1:
                start = cursor
            end = start + len(part)
            cursor = end
            spans.append((part, start, end))
        return spans
