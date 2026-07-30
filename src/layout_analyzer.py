"""
layout_analyzer.py
===================
Stage 2 of the pipeline: Layout Analyzer.

Splits raw extracted text into blocks (paragraph-separated) and
classifies each block as heading / paragraph / table / caption / figure
/ header / footer / reference / page_number, using structural and
lexical heuristics. This keeps the system fully self-contained (no
extra model download needed beyond what the extractor already used).
"""

from __future__ import annotations

import logging
import re
from typing import List

from src.models import BlockType, Document, LayoutBlock
from src.utils import is_page_number


HEADING_PATTERN = re.compile(r"^\s{0,3}(#{1,6}\s+.+|[A-Z][A-Za-z0-9 \-:]{2,80})$")
NUMBERED_HEADING_PATTERN = re.compile(r"^\s{0,3}\d+(\.\d+)*\s+[A-Z].{0,80}$")
CAPTION_PATTERN = re.compile(r"^\s*(table|figure|fig\.?)\s+\d+", re.IGNORECASE)
REFERENCE_SECTION_PATTERN = re.compile(
    r"^\s*(references|bibliography|works cited)\s*$", re.IGNORECASE
)
REFERENCE_ENTRY_PATTERN = re.compile(
    r"^\s*(\[\d+\]|\d+\.)\s+.+\(\d{4}\)|^\s*[A-Z][a-zA-Z]+,\s*[A-Z]\.[^.]*\(\d{4}\)"
)
HEADER_FOOTER_KEYWORDS = re.compile(
    r"^(confidential|draft|copyright|all rights reserved)\b", re.IGNORECASE
)
TABLE_ROW_PATTERN = re.compile(r"^\s*\|.*\|\s*$|^(\s*\S+\s*\|){2,}")


class LayoutAnalyzer:
    """Classifies raw text blocks into semantic layout categories."""

    def __init__(self, logger: logging.Logger) -> None:
        self.logger = logger

    def analyze(self, document: Document) -> Document:
        if hasattr(self.logger, "stage"):
            self.logger.stage("Analyzing layout")
        else:
            self.logger.info("Analyzing layout")
        blocks = self._split_into_blocks(document.raw_text)

        layout_blocks: List[LayoutBlock] = []
        in_reference_section = False
        for idx, (page, text) in enumerate(blocks):
            block_type = self._classify(text, in_reference_section)
            if block_type == BlockType.REFERENCE and REFERENCE_SECTION_PATTERN.match(text.strip()):
                in_reference_section = True
            layout_blocks.append(
                LayoutBlock(block_id=idx, page=page, text=text, block_type=block_type)
            )

        document.layout_blocks = layout_blocks
        counts = {}
        for block in layout_blocks:
            counts[block.block_type.value] = counts.get(block.block_type.value, 0) + 1
        self.logger.info("Layout classification counts: %s", counts)
        return document

    # ------------------------------------------------------------------
    def _split_into_blocks(self, raw_text: str):
        """Split on blank lines, tracking an approximate page number via
        common form-feed / 'Page N' markers left by extractors."""
        page = 1
        blocks = []
        current_lines: List[str] = []

        def flush():
            if current_lines:
                text = "\n".join(current_lines).strip()
                if text:
                    blocks.append((page, text))
            current_lines.clear()

        for line in raw_text.splitlines():
            if "\x0c" in line:  # form feed = page break from some extractors
                flush()
                page += 1
                continue
            if line.strip() == "":
                flush()
                continue
            current_lines.append(line)
        flush()
        return blocks

    def _classify(self, text: str, in_reference_section: bool) -> BlockType:
        stripped = text.strip()

        if is_page_number(stripped):
            return BlockType.PAGE_NUMBER
        if REFERENCE_SECTION_PATTERN.match(stripped):
            return BlockType.REFERENCE
        if in_reference_section and len(stripped) > 0:
            return BlockType.REFERENCE
        if TABLE_ROW_PATTERN.match(stripped):
            return BlockType.TABLE
        if CAPTION_PATTERN.match(stripped):
            return BlockType.CAPTION
        if REFERENCE_ENTRY_PATTERN.match(stripped):
            return BlockType.REFERENCE
        if HEADER_FOOTER_KEYWORDS.match(stripped):
            return BlockType.HEADER
        if len(stripped.split("\n")) == 1 and (
            HEADING_PATTERN.match(stripped) and len(stripped) < 90 and not stripped.endswith(".")
        ):
            return BlockType.HEADING
        if NUMBERED_HEADING_PATTERN.match(stripped) and len(stripped) < 90:
            return BlockType.HEADING
        if len(stripped) < 5:
            return BlockType.FOOTER
        return BlockType.PARAGRAPH
