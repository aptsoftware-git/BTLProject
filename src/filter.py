"""
filter.py
=========
Stage 3 of the pipeline: Running Text Filter.

Keeps only PARAGRAPH (and HEADING, treated as running text for
proofreading purposes) blocks. Discards tables, captions, figures,
references, headers, footers and page numbers. Also strips residual
URLs and markdown syntax from what remains.
"""

from __future__ import annotations

import logging

from src.models import BlockType, Document
from src.utils import remove_urls_and_emails, strip_markdown


KEEP_TYPES = {BlockType.PARAGRAPH, BlockType.HEADING}


class RunningTextFilter:
    """Removes non-running-text content and residual markup/URLs."""

    def __init__(self, logger: logging.Logger) -> None:
        self.logger = logger

    def filter(self, document: Document) -> Document:
        self.logger.stage("Filtering")
        kept_texts = []
        removed_count = 0
        for block in document.layout_blocks:
            if block.block_type in KEEP_TYPES:
                cleaned = strip_markdown(block.text)
                cleaned = remove_urls_and_emails(cleaned)
                if cleaned.strip():
                    kept_texts.append(cleaned.strip())
            else:
                removed_count += 1

        document.filtered_text = "\n\n".join(kept_texts)
        self.logger.info(
            "Kept %d running-text block(s), removed %d non-running block(s)",
            len(kept_texts), removed_count,
        )
        return document
