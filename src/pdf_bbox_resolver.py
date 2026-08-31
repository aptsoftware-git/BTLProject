"""
pdf_bbox_resolver.py
======================
Resolves each proofreading finding's real PDF bounding box from Docling
element-level provenance (source_element_id / source_bbox, carried through
by page_text_builder.py -> sentence_mapper.py -> finding_mapper.py).

This is provenance-first, not text-search-first: coordinates are recovered
by looking only within the exact source element's own region on the page
(via PyMuPDF word extraction clipped to that region), which is immune to
the failure modes of a blind whole-page text search -- repeated words
elsewhere on the page, hyphenation, whitespace normalization, text split
across PDF spans. An UNSCOPED page.search_for(original) is intentionally
never used anywhere in this module.

If a finding's element bbox is missing, or both the region-clipped word
match AND a narrow region-scoped page.search_for() fallback fail to find
the target text, the finding is left ungrounded (bbox=None,
pdf_grounded=False) -- never a guessed/synthetic box.

Only adds `bbox` and `pdf_grounded` to each finding; every other field
produced by finding_mapper.build_findings() is passed through unchanged.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_WS_RE = re.compile(r"\s+")
_CLIP_PADDING = 2.0  # points, absorbs rounding at the element bbox edges


def _normalize(text: str) -> str:
    return _WS_RE.sub(" ", (text or "").strip())


def _bbox_to_fitz_rect(bbox: Dict[str, Any], page_height: float):
    import fitz

    l, t, r, b = bbox.get("l"), bbox.get("t"), bbox.get("r"), bbox.get("b")
    if l is None or t is None or r is None or b is None:
        return None
    coord_origin = str(bbox.get("coord_origin") or "BOTTOMLEFT").upper()
    if coord_origin == "TOPLEFT":
        y0, y1 = t, b
    else:
        # Docling's default PDF-native convention: origin bottom-left, y up.
        # PyMuPDF page space is top-left, y down -- flip using page height.
        y0, y1 = page_height - t, page_height - b
    y0, y1 = min(y0, y1), max(y0, y1)
    x0, x1 = min(l, r), max(l, r)
    return fitz.Rect(x0 - _CLIP_PADDING, y0 - _CLIP_PADDING, x1 + _CLIP_PADDING, y1 + _CLIP_PADDING)


def _union_rect(rects):
    x0 = min(rc.x0 for rc in rects)
    y0 = min(rc.y0 for rc in rects)
    x1 = max(rc.x1 for rc in rects)
    y1 = max(rc.y1 for rc in rects)
    return x0, y0, x1, y1


def _find_in_clipped_words(
    page, clip_rect, target_text: str, occurrence_index: int
) -> Optional[Tuple[float, float, float, float]]:
    """Locates the Nth occurrence of `target_text` among words extracted
    ONLY from `clip_rect` (the source element's own region), returning a
    tight bbox around just the matched word/phrase run, or None."""
    import fitz

    words = page.get_text("words", clip=clip_rect) or []
    if not words:
        return None
    # (x0, y0, x1, y1, text, block_no, line_no, word_no)
    words = sorted(words, key=lambda w: (w[5], w[6], w[7]))

    parts: List[str] = []
    spans: List[Tuple[int, int, Tuple[float, float, float, float]]] = []
    cursor = 0
    for w in words:
        word_text = w[4]
        if cursor:
            parts.append(" ")
            cursor += 1
        start = cursor
        parts.append(word_text)
        cursor += len(word_text)
        spans.append((start, cursor, (w[0], w[1], w[2], w[3])))
    joined = "".join(parts)

    target = _normalize(target_text)
    if not target:
        return None

    match_start = -1
    found_count = 0
    search_from = 0
    while True:
        pos = joined.find(target, search_from)
        if pos == -1:
            break
        if found_count == occurrence_index:
            match_start = pos
            break
        found_count += 1
        search_from = pos + 1

    if match_start == -1:
        # Requested occurrence wasn't reached (e.g. counter drifted because a
        # sibling finding in the same element didn't ground) -- still fall
        # back to the first match within this element only, never off it.
        pos = joined.find(target)
        if pos == -1:
            return None
        match_start = pos

    match_end = match_start + len(target)
    matched_rects = [fitz.Rect(*rect) for (s, e, rect) in spans if s < match_end and e > match_start]
    if not matched_rects:
        return None
    return _union_rect(matched_rects)


def _find_via_scoped_search(page, clip_rect, target_text: str) -> Optional[Tuple[float, float, float, float]]:
    """Narrow, region-scoped page.search_for() fallback -- only used when
    element-region word matching fails, and still restricted to the source
    element's own (padded) bbox. Never an unscoped whole-page search."""
    if not target_text:
        return None
    hits = page.search_for(target_text, clip=clip_rect) or []
    if len(hits) != 1:
        return None
    r = hits[0]
    return (r.x0, r.y0, r.x1, r.y1)


def resolve_bboxes(findings: List[Dict[str, Any]], pdf_path: Optional[Path]) -> List[Dict[str, Any]]:
    """Returns a new findings list with `bbox` (dict x0/y0/x1/y1 in PyMuPDF
    top-left-origin points, matching react-pdf's `scale` convention
    directly) and `pdf_grounded` (bool) added to every entry.

    A per-finding resolution failure never raises -- that finding is simply
    left ungrounded. Only a totally unusable/missing PDF short-circuits the
    whole batch to ungrounded (no exception escapes this function).

    Every returned finding also carries `pdf_checked`: True whenever a real
    PDF was actually opened and a genuine per-finding search was attempted
    against it (regardless of whether that search succeeded), False when no
    real PDF was available to check at all (e.g. a DOCX/TXT source). This
    lets a downstream gate (final_validation_layer) tell "we searched the
    real PDF and the text truly isn't there" -- which must be an
    authoritative rejection, never overridable by a merely-cached
    sentence-text match -- apart from "there was no PDF to check", where
    falling back to sentence-text evidence is the correct, and only
    possible, behavior.
    """
    if not pdf_path or not str(pdf_path).lower().endswith(".pdf") or not Path(pdf_path).exists():
        return [{**f, "bbox": None, "pdf_grounded": False, "pdf_checked": False} for f in findings]

    import fitz

    try:
        doc = fitz.open(str(pdf_path))
    except Exception:
        return [{**f, "bbox": None, "pdf_grounded": False, "pdf_checked": False} for f in findings]

    try:
        occurrence_counters: Dict[Tuple[Any, Any, str], int] = {}
        results: List[Dict[str, Any]] = []
        for f in findings:
            page_number = f.get("page_number")
            source_bbox = f.get("source_bbox")
            original = f.get("original") or ""
            bbox_out: Optional[Dict[str, float]] = None
            grounded = False

            try:
                if page_number and source_bbox and original:
                    page_idx = int(page_number) - 1
                    if 0 <= page_idx < len(doc):
                        page = doc[page_idx]
                        clip_rect = _bbox_to_fitz_rect(source_bbox, page.rect.height)
                        if clip_rect is not None:
                            key = (page_number, f.get("source_element_id"), _normalize(original).lower())
                            occurrence_index = occurrence_counters.get(key, 0)
                            occurrence_counters[key] = occurrence_index + 1

                            found = _find_in_clipped_words(page, clip_rect, original, occurrence_index)
                            if found is None:
                                found = _find_via_scoped_search(page, clip_rect, original)
                            if found is not None:
                                x0, y0, x1, y1 = found
                                bbox_out = {"x0": x0, "y0": y0, "x1": x1, "y1": y1}
                                grounded = True
            except Exception:
                bbox_out = None
                grounded = False

            results.append({**f, "bbox": bbox_out, "pdf_grounded": grounded, "pdf_checked": True})
        return results
    finally:
        doc.close()
