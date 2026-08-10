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
        """Maps paragraph index -> {page, bbox, element_id} using structured_document.json or layout_blocks with interpolation for unmatched paragraphs."""
        lookup = {}
        raw_paragraphs = [p.strip() for p in document.normalized_text.split("\n\n") if p.strip()]

        # 1. Primary path: Read directly from structured_document.json
        struct_doc_paths = []
        if job_dir:
            struct_doc_paths.extend([
                Path(job_dir) / "structured_document.json",
                Path(job_dir) / "02_docling" / "structured_document.json",
            ])
        
        elements = []
        for s_path in struct_doc_paths:
            if s_path.exists():
                try:
                    with open(s_path, "r", encoding="utf-8") as f:
                        s_data = json.load(f)
                    elements = s_data.get("elements", [])
                    if elements:
                        break
                except Exception:
                    pass

        def _clean_text(s: str) -> str:
            import re
            return re.sub(r"\W+", "", s or "").lower()

        matched_pages: Dict[int, int] = {}

        if elements:
            for p_idx, p_text in enumerate(raw_paragraphs):
                p_clean = _clean_text(p_text[:80])
                matched_el = None
                
                # Direct or substring match
                for el in elements:
                    el_text = (el.get("text") or "").strip()
                    el_clean = _clean_text(el_text[:80])
                    if el_clean and (p_clean in el_clean or el_clean in p_clean or p_clean[:30] == el_clean[:30]):
                        matched_el = el
                        break
                
                if matched_el:
                    meta = matched_el.get("metadata", {})
                    pg = int(meta.get("page_number", meta.get("page", 1)) or 1)
                    matched_pages[p_idx] = pg
                    lookup[p_idx] = {
                        "page": pg,
                        "bbox": self._normalize_bbox(meta.get("bbox")),
                        "element_id": matched_el.get("id")
                    }
                elif p_idx < len(elements):
                    meta = elements[p_idx].get("metadata", {})
                    pg = int(meta.get("page_number", meta.get("page", 1)) or 1)
                    matched_pages[p_idx] = pg
                    lookup[p_idx] = {
                        "page": pg,
                        "bbox": self._normalize_bbox(meta.get("bbox")),
                        "element_id": elements[p_idx].get("id")
                    }
        else:
            # 2. Secondary path: Match directly with document.layout_blocks
            from src.models import BlockType
            narrative_blocks = [
                b for b in getattr(document, "layout_blocks", [])
                if getattr(b, "block_type", None) in (BlockType.PARAGRAPH, BlockType.HEADING)
            ]

            for p_idx, p_text in enumerate(raw_paragraphs):
                p_clean = _clean_text(p_text[:80])
                matched_meta = None
                for b in narrative_blocks:
                    b_text = (getattr(b, "text", "") or "").strip()
                    b_clean = _clean_text(b_text[:80])
                    if b_clean and (p_clean in b_clean or b_clean in p_clean or p_clean[:30] == b_clean[:30]):
                        pg = int(getattr(b, "page", 1) or 1)
                        matched_pages[p_idx] = pg
                        matched_meta = {
                            "page": pg,
                            "bbox": self._normalize_bbox(getattr(b, "bbox", None)),
                            "element_id": getattr(b, "element_id", None)
                        }
                        break
                
                if matched_meta:
                    lookup[p_idx] = matched_meta
                elif p_idx < len(narrative_blocks):
                    nb = narrative_blocks[p_idx]
                    pg = int(getattr(nb, "page", 1) or 1)
                    matched_pages[p_idx] = pg
                    lookup[p_idx] = {
                        "page": pg,
                        "bbox": self._normalize_bbox(getattr(nb, "bbox", None)),
                        "element_id": getattr(nb, "element_id", None)
                    }

        # Interpolate page numbers for any unmatched paragraphs instead of defaulting to Page 1
        for p_idx in range(len(raw_paragraphs)):
            if p_idx not in lookup or lookup[p_idx].get("page") is None:
                # Find preceding known page
                prev_pg = None
                for k in range(p_idx - 1, -1, -1):
                    if k in matched_pages:
                        prev_pg = matched_pages[k]
                        break
                # Find succeeding known page
                next_pg = None
                for k in range(p_idx + 1, len(raw_paragraphs)):
                    if k in matched_pages:
                        next_pg = matched_pages[k]
                        break
                
                inferred_pg = prev_pg or next_pg or 1
                lookup[p_idx] = {
                    "page": inferred_pg,
                    "bbox": None,
                    "element_id": None
                }

        return lookup

    @staticmethod
    def _normalize_bbox(raw_bbox: Any) -> Optional[Dict[str, float]]:
        if not raw_bbox:
            return None
        if isinstance(raw_bbox, dict):
            l = float(raw_bbox.get("l", raw_bbox.get("x0", 0)) or 0)
            t = float(raw_bbox.get("t", raw_bbox.get("y0", 0)) or 0)
            r = float(raw_bbox.get("r", raw_bbox.get("x1", 0)) or 0)
            b = float(raw_bbox.get("b", raw_bbox.get("y1", 0)) or 0)
            if (l == 0 and t == 0 and r == 0 and b == 0) or l >= r or t >= b:
                return None
            return {"x0": l, "y0": t, "x1": r, "y1": b}
        elif isinstance(raw_bbox, (list, tuple)) and len(raw_bbox) >= 4:
            l, t, r, b = float(raw_bbox[0]), float(raw_bbox[1]), float(raw_bbox[2]), float(raw_bbox[3])
            if (l == 0 and t == 0 and r == 0 and b == 0) or l >= r or t >= b:
                return None
            return {"x0": l, "y0": t, "x1": r, "y1": b}
        return None
