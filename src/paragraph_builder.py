"""
paragraph_builder.py
=====================
Stage 5 of the pipeline: Paragraph Builder.

Converts normalized text into Paragraph objects, tracking a running
paragraph id and an approximate page number (paragraphs inherit page
from the layout blocks that produced them where possible; otherwise a
single-page document is assumed).
"""

from __future__ import annotations

import logging

from src.models import Document, Paragraph


class ParagraphBuilder:
    """Builds Paragraph objects from normalized text."""

    def __init__(self, logger: logging.Logger) -> None:
        self.logger = logger

    def build(self, document: Document) -> Document:
        self.logger.stage("Building paragraphs")
        raw_paragraphs = [
            p.strip() for p in document.normalized_text.split("\n\n") if p.strip()
        ]

        page_lookup = self._build_page_lookup(document)

        paragraphs = []
        for idx, text in enumerate(raw_paragraphs):
            page = page_lookup.get(idx, 1)
            paragraphs.append(Paragraph(paragraph_id=idx, page=page, text=text))

        document.paragraphs = paragraphs
        self.logger.info("Built %d paragraph(s)", len(paragraphs))
        return document

    @staticmethod
    def _build_page_lookup(document: Document) -> dict:
        """Best-effort mapping from paragraph index -> page number, based
        on the order of PARAGRAPH/HEADING blocks from the layout stage."""
        from src.models import BlockType

        lookup = {}
        idx = 0
        for block in document.layout_blocks:
            if block.block_type in (BlockType.PARAGRAPH, BlockType.HEADING):
                lookup[idx] = block.page
                idx += 1
        return lookup
