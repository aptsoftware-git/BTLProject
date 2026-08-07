"""
filter.py
=========
Stage 3 of the pipeline: Production Proofreadable Content Filter.

1. Content Classification & Exclusions:
   Classifies extracted blocks into: paragraph, heading, table, image, caption, header, footer, logo, watermark, page_number.
   ALLOWED_TYPES = { BlockType.PARAGRAPH, BlockType.HEADING }
   Excludes all tables, captions, images, figures, headers, footers, page numbers, references.

2. Image-Heavy Page Filtering:
   Calculates text_area_ratio = proofreadable_text_area / page_area for each page.
   If text_area_ratio < 0.15, page is marked:
     { "proofreadable": false, "reason": "Image Dominated Page" }
   Image-dominated pages remain visible in the PDF viewer but generate ZERO proofreading findings.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Any

from src.models import BlockType, Document
from src.utils import remove_urls_and_emails, strip_markdown


ALLOWED_TYPES = {BlockType.PARAGRAPH, BlockType.HEADING}
KEEP_TYPES = ALLOWED_TYPES  # Backward compatibility alias


class RunningTextFilter:
    """Classifies content blocks and filters non-narrative / image-heavy page content."""

    def __init__(self, logger: logging.Logger) -> None:
        self.logger = logger

    def filter(self, document: Document, output_dir: Path | None = None) -> Document:
        if hasattr(self.logger, "stage"):
            self.logger.stage("Filtering Proofreadable Content")
        else:
            self.logger.info("Filtering Proofreadable Content")

        # Group layout blocks by page
        page_blocks: Dict[int, List[Any]] = {}
        for block in document.layout_blocks:
            page_blocks.setdefault(block.page, []).append(block)

        page_classifications: Dict[int, Dict[str, Any]] = {}
        excluded_pages = set()

        # Calculate text_area_ratio per page
        for page_num, blocks in page_blocks.items():
            proof_blocks = [b for b in blocks if b.block_type in ALLOWED_TYPES]
            
            # Calculate total page area and proofreadable area
            proofreadable_area = 0.0
            total_block_area = 0.0
            
            for b in blocks:
                bbox = getattr(b, "bbox", None)
                if bbox and isinstance(bbox, dict):
                    w = abs(float(bbox.get("x1", 0) or bbox.get("r", 0)) - float(bbox.get("x0", 0) or bbox.get("l", 0)))
                    h = abs(float(bbox.get("y1", 0) or bbox.get("b", 0)) - float(bbox.get("y0", 0) or bbox.get("t", 0)))
                    area = w * h
                else:
                    area = float(len(b.text.strip()))
                
                total_block_area += area
                if b.block_type in ALLOWED_TYPES:
                    proofreadable_area += area

            # Calculate text_area_ratio
            if total_block_area > 0:
                text_area_ratio = proofreadable_area / total_block_area
            else:
                text_area_ratio = 0.0

            # If page is image-dominated (text_area_ratio < 0.15), flag page and exclude from proofreading
            if text_area_ratio < 0.15 and len(proof_blocks) < 2:
                page_classifications[page_num] = {
                    "page": page_num,
                    "proofreadable": False,
                    "reason": "Image Dominated Page",
                    "text_area_ratio": round(text_area_ratio, 4)
                }
                excluded_pages.add(page_num)
                self.logger.info("Page %d flagged as Image Dominated (text_area_ratio=%.3f). Zero findings will be generated.", page_num, text_area_ratio)
            else:
                page_classifications[page_num] = {
                    "page": page_num,
                    "proofreadable": True,
                    "reason": "Sufficient Narrative Content",
                    "text_area_ratio": round(text_area_ratio, 4)
                }

        kept_texts = []
        removed_count = 0

        for block in document.layout_blocks:
            # Exclude non-allowed block types AND image-dominated pages
            if block.block_type in ALLOWED_TYPES and block.page not in excluded_pages:
                cleaned = strip_markdown(block.text)
                cleaned = remove_urls_and_emails(cleaned)
                if cleaned.strip():
                    kept_texts.append(cleaned.strip())
            else:
                removed_count += 1

        document.filtered_text = "\n\n".join(kept_texts)

        # Save page classifications if output_dir provided
        if output_dir:
            try:
                class_path = Path(output_dir) / "02_filtered" / "page_classifications.json"
                class_path.parent.mkdir(parents=True, exist_ok=True)
                class_path.write_text(json.dumps(page_classifications, indent=2), encoding="utf-8")
            except Exception as e:
                self.logger.warning("Could not save page classifications: %s", e)

        self.logger.info(
            "Filter complete: Kept %d narrative block(s), removed %d non-narrative / image-heavy block(s). Excluded pages: %s",
            len(kept_texts), removed_count, list(excluded_pages) or "None"
        )
        return document
