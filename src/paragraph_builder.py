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


import json
from pathlib import Path
from typing import Optional, Dict, Any

from src.models import Document, Paragraph


class ParagraphBuilder:
    """Builds Paragraph objects from normalized text while preserving layout metadata."""

    def __init__(self, logger: logging.Logger) -> None:
        self.logger = logger

    def build(self, document: Document, job_dir: Optional[Path] = None) -> Document:
        self.logger.stage("Building paragraphs with positional metadata")
        raw_paragraphs = [
            p.strip() for p in document.normalized_text.split("\n\n") if p.strip()
        ]

        meta_lookup = self._build_layout_meta_lookup(document, job_dir)

        paragraphs = []
        for idx, text in enumerate(raw_paragraphs):
            meta = meta_lookup.get(idx, {})
            page = meta.get("page", 1)
            bbox = meta.get("bbox")
            element_id = meta.get("element_id")
            
            paragraphs.append(
                Paragraph(
                    paragraph_id=idx,
                    page=page,
                    text=text,
                    bbox=bbox,
                    element_id=element_id
                )
            )

        document.paragraphs = paragraphs
        self.logger.info("Built %d paragraph(s) with positional metadata", len(paragraphs))
        return document

    def _build_layout_meta_lookup(self, document: Document, job_dir: Optional[Path] = None) -> Dict[int, Dict[str, Any]]:
        """Maps paragraph index -> {page, bbox, element_id} using structured_document.json or layout_blocks."""
        lookup = {}
        
        # 1. Primary path: Load from structured_document.json if available
        doc_json_path = None
        if job_dir:
            doc_json_path = Path(job_dir) / "structured_document.json"
        
        if doc_json_path and doc_json_path.exists():
            try:
                with open(doc_json_path, "r", encoding="utf-8") as f:
                    struct_doc = json.load(f)
                elements = struct_doc.get("elements", [])
                
                # Match elements to raw paragraphs
                raw_paragraphs = [p.strip() for p in document.normalized_text.split("\n\n") if p.strip()]
                elem_idx = 0
                for p_idx, p_text in enumerate(raw_paragraphs):
                    # Search for element matching paragraph text
                    matched = False
                    while elem_idx < len(elements):
                        el = elements[elem_idx]
                        elem_idx += 1
                        el_text = (el.get("text") or "").strip()
                        el_meta = el.get("metadata", {})
                        
                        if el_text and (p_text[:30] in el_text or el_text[:30] in p_text):
                            lookup[p_idx] = {
                                "page": el_meta.get("page_number", 1),
                                "bbox": el_meta.get("bbox"),
                                "element_id": el.get("id")
                            }
                            matched = True
                            break
                    if not matched and elem_idx >= len(elements) and elements:
                        # Fallback for remaining paragraphs
                        last_meta = elements[-1].get("metadata", {})
                        lookup[p_idx] = {
                            "page": last_meta.get("page_number", 1),
                            "bbox": last_meta.get("bbox"),
                            "element_id": elements[-1].get("id")
                        }
                return lookup
            except Exception as exc:
                self.logger.warning("Error reading structured_document.json for paragraph metadata: %s", exc)

        # 2. Fallback path: layout_blocks
        from src.models import BlockType
        idx = 0
        for block in document.layout_blocks:
            if block.block_type in (BlockType.PARAGRAPH, BlockType.HEADING):
                lookup[idx] = {
                    "page": block.page,
                    "bbox": getattr(block, "bbox", None),
                    "element_id": getattr(block, "element_id", None)
                }
                idx += 1
        return lookup
