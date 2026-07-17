"""
preprocessing.py
=================
Stage 4 of the pipeline: Text Preprocessor.

Normalizes Unicode form, smart quotes, dashes, whitespace and strips
control characters so downstream NLP (spaCy, SymSpell, T5) sees clean,
consistent text.
"""

from __future__ import annotations

import logging
import re
import unicodedata

from src.models import Document


QUOTE_MAP = {
    "\u2018": "'", "\u2019": "'", "\u201a": "'", "\u201b": "'",
    "\u201c": '"', "\u201d": '"', "\u201e": '"', "\u201f": '"',
}
DASH_MAP = {
    "\u2010": "-", "\u2011": "-", "\u2012": "-",
    "\u2013": "-", "\u2014": "-", "\u2015": "-",
}
CONTROL_CHAR_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
MULTI_SPACE_PATTERN = re.compile(r"[ \t]+")
MULTI_NEWLINE_PATTERN = re.compile(r"\n{3,}")
HYPHEN_LINEBREAK_PATTERN = re.compile(r"(\w)-\n(\w)")


class TextPreprocessor:
    """Normalizes text prior to paragraph/sentence construction."""

    def __init__(self, logger: logging.Logger) -> None:
        self.logger = logger

    def normalize(self, document: Document) -> Document:
        self.logger.stage("Preprocessing")
        text = document.filtered_text

        text = unicodedata.normalize("NFKC", text)
        text = self._translate(text, QUOTE_MAP)
        text = self._translate(text, DASH_MAP)
        text = CONTROL_CHAR_PATTERN.sub("", text)
        text = HYPHEN_LINEBREAK_PATTERN.sub(r"\1\2", text)
        text = MULTI_SPACE_PATTERN.sub(" ", text)
        text = MULTI_NEWLINE_PATTERN.sub("\n\n", text)
        text = "\n".join(line.strip() for line in text.split("\n"))

        document.normalized_text = text.strip()
        self.logger.info("Normalized text length: %d characters", len(document.normalized_text))
        return document

    @staticmethod
    def _translate(text: str, mapping: dict) -> str:
        for src, dst in mapping.items():
            text = text.replace(src, dst)
        return text
