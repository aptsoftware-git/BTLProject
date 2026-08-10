"""
page_text_builder.py
=====================
Builds the page-wise running-text layer (03_page_text/) from a Docling
StructuredDocument (see src/rag/document_schema.py).

Only running-text element types (paragraph, heading, list_item) are
included; tables, images, captions, formulas, code and footnotes are
excluded entirely, per the proofreading-scope requirement that the
pipeline only ever sees running text.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

from src.utils import save_json

RUNNING_TEXT_TYPES = {"paragraph", "heading", "list_item", "text"}

# PDF en-dash-as-punctuation ("Gujarat – the world's tallest statue") regularly
# extracts from Docling/PyMuPDF as "Gujarat -the ..." -- a space before the
# hyphen but none after, gluing the hyphen onto the next word. This produces
# fragments like "-the" / "-commonly" once that text gets tokenized/split.
# Genuine hyphenated compounds ("high-speed", "co-founder") have NO space
# before the hyphen, so this pattern only ever matches the punctuation case.
_DASH_GLUE_RE = re.compile(r"(?<=\s)-(?=[a-zA-Z])")


def _normalize_dash_artifacts(text: str) -> str:
    return _DASH_GLUE_RE.sub("- ", text)


def build_page_text(structured_document: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Groups Docling elements by page, keeping only running-text types, in
    original document order.

    Returns [{"page_number": int, "text": str}, ...] for every page in
    1..page_count (pages with no running text get an empty string so page
    numbering in the UI stays contiguous). This is the exact artifact shape
    documented for 03_page_text/page_text.json -- for the parallel
    per-element structure (needed to split sentences per element instead of
    per merged page blob, and to tag each sentence with its real source
    type), see build_page_blocks().
    """
    page_texts_and_blocks = build_page_text_and_blocks(structured_document)
    return [{"page_number": p["page_number"], "text": p["text"]} for p in page_texts_and_blocks]


def build_page_text_and_blocks(structured_document: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Same grouping as build_page_text(), but also retains each source
    element's text/type/id/bbox as a "blocks" list per page, so sentence
    splitting can happen per-element (preserving heading/list-item
    boundaries) instead of over a single merged page-text blob, and so the
    real Docling provenance (element_id + bbox) survives for downstream PDF
    coordinate resolution (see src/pdf_bbox_resolver.py).

    Returns [{"page_number": int, "text": str, "blocks": [{"text": str, "type": str, "element_id": str|None, "bbox": dict|None}, ...]}, ...]
    """
    page_count = int(structured_document.get("page_count") or 0)
    elements = structured_document.get("elements") or []

    pages: Dict[int, List[Dict[str, str]]] = {}
    for el in elements:
        el_type = str(el.get("type") or "").lower()
        if el_type not in RUNNING_TEXT_TYPES:
            continue
        text = _normalize_dash_artifacts((el.get("text") or "").strip())
        if not text:
            continue
        metadata = el.get("metadata") or {}
        page_number = int(metadata.get("page_number") or 1)
        pages.setdefault(page_number, []).append({
            "text": text,
            "type": el_type if el_type != "text" else "paragraph",
            "element_id": el.get("id"),
            "bbox": metadata.get("bbox"),
        })

    max_page = max([page_count] + list(pages.keys())) if (page_count or pages) else 0

    result: List[Dict[str, Any]] = []
    for page_number in range(1, max_page + 1):
        blocks = pages.get(page_number, [])
        result.append({
            "page_number": page_number,
            "text": "\n\n".join(b["text"] for b in blocks),
            "blocks": blocks,
        })
    return result


def save_page_text(page_texts: List[Dict[str, Any]], output_dir: Path) -> Path:
    """Writes the combined page-text index file (03_page_text/page_text.json)."""
    out_path = output_dir / "page_text.json"
    save_json(page_texts, out_path)
    return out_path
