"""
sentence_mapper.py
====================
Builds the sentence-mapping layer (04_sentences/page_sentence_map.json +
04_sentences/sentence_lookup_index.json) from the page-text layer produced
by page_text_builder.py.

page_sentence_map.json is the SINGLE SOURCE OF TRUTH for mapping any
proofreading finding back to a page and a character span: every sentence
gets a stable "SENT_%06d" id, its page number, and both a page-local
character span (start_char/end_char, used by the frontend viewer) and a
document-level character span (doc_char_start/doc_char_end, used
internally so the untouched spell/grammar/validation agents keep working
against a single joined document string), plus source_element_id/
source_bbox provenance carried from the parent Docling element (see
page_text_builder.build_page_text_and_blocks()) for real PDF coordinate
resolution downstream (src/pdf_bbox_resolver.py).

Proofreading agents downstream only ever see {sentence_id, text} shaped
input (see to_legacy_sentences()) — never raw pages, tables, images or
layout objects.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.utils import save_json

_FALLBACK_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])")


def sentence_id_str(numeric_id: int) -> str:
    return f"SENT_{numeric_id:06d}"


def sentence_numeric_id(sentence_id: str) -> int:
    return int(str(sentence_id).split("_")[-1])


def _split_sentences(text: str, nlp=None) -> List[Tuple[str, int, int]]:
    """Returns [(sentence_text, start_char, end_char), ...] relative to `text`."""
    text = text or ""
    if not text.strip():
        return []

    if nlp is not None:
        try:
            doc = nlp(text)
            spans: List[Tuple[str, int, int]] = []
            for sent in doc.sents:
                start, end = sent.start_char, sent.end_char
                while start < end and text[start].isspace():
                    start += 1
                while end > start and text[end - 1].isspace():
                    end -= 1
                if end > start:
                    spans.append((text[start:end], start, end))
            if spans:
                return spans
        except Exception:
            pass

    # Lightweight regex fallback if spaCy is unavailable.
    spans = []
    cursor = 0
    for chunk in _FALLBACK_SENTENCE_RE.split(text):
        chunk_stripped = chunk.strip()
        if not chunk_stripped:
            continue
        idx = text.find(chunk_stripped, cursor)
        if idx == -1:
            idx = cursor
        spans.append((chunk_stripped, idx, idx + len(chunk_stripped)))
        cursor = idx + len(chunk_stripped)
    return spans


def build_sentence_map(
    page_texts: List[Dict[str, Any]], nlp=None
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Returns (page_sentence_map, lookup_index).

    If `page_texts` entries carry a "blocks" list (see
    page_text_builder.build_page_text_and_blocks()), sentences are split
    per source element (heading/list_item/paragraph) rather than over the
    whole merged page text -- this preserves each list item / heading as
    its own unit instead of letting the sentence splitter merge or cut
    across element boundaries, and tags each sentence with its real type
    instead of a hardcoded "paragraph". Falls back to whole-page splitting
    (type="paragraph") when no block info is available.
    """
    sentence_map: List[Dict[str, Any]] = []
    lookup_index: Dict[str, Any] = {}

    doc_cursor = 0
    seq = 0
    for page in sorted(page_texts, key=lambda p: p["page_number"]):
        page_number = page["page_number"]
        page_text = page.get("text") or ""
        blocks = page.get("blocks")

        if blocks:
            block_cursor = 0
            for block in blocks:
                block_text = block.get("text") or ""
                block_type = block.get("type") or "paragraph"
                block_element_id = block.get("element_id")
                block_bbox = block.get("bbox")
                # Re-locate this block's offset within the joined page_text
                # (blocks are joined with "\n\n" to form page_text).
                found_at = page_text.find(block_text, block_cursor)
                block_offset = found_at if found_at != -1 else block_cursor
                for sent_text, start_char, end_char in _split_sentences(block_text, nlp):
                    seq += 1
                    sid = sentence_id_str(seq)
                    page_start_char = block_offset + start_char
                    page_end_char = block_offset + end_char
                    doc_char_start = doc_cursor + page_start_char
                    doc_char_end = doc_cursor + page_end_char
                    entry = {
                        "sentence_id": sid,
                        "page_number": page_number,
                        "text": sent_text,
                        "start_char": page_start_char,
                        "end_char": page_end_char,
                        "type": block_type,
                        "doc_char_start": doc_char_start,
                        "doc_char_end": doc_char_end,
                        # Provenance anchor: the source Docling element this
                        # sentence was split from. Multiple sentences from the
                        # same element share the same region -- Docling only
                        # gives element-level granularity, not per-sentence --
                        # so src/pdf_bbox_resolver.py recovers word-level
                        # precision by searching within this element's bbox.
                        "source_element_id": block_element_id,
                        "source_bbox": block_bbox,
                    }
                    sentence_map.append(entry)
                    lookup_index[sid] = {
                        "page_number": page_number,
                        "text": sent_text,
                        "source_element_id": block_element_id,
                        "source_bbox": block_bbox,
                    }
                block_cursor = block_offset + len(block_text)
        else:
            for sent_text, start_char, end_char in _split_sentences(page_text, nlp):
                seq += 1
                sid = sentence_id_str(seq)
                doc_char_start = doc_cursor + start_char
                doc_char_end = doc_cursor + end_char
                entry = {
                    "sentence_id": sid,
                    "page_number": page_number,
                    "text": sent_text,
                    "start_char": start_char,
                    "end_char": end_char,
                    "type": "paragraph",
                    "doc_char_start": doc_char_start,
                    "doc_char_end": doc_char_end,
                    "source_element_id": None,
                    "source_bbox": None,
                }
                sentence_map.append(entry)
                lookup_index[sid] = {
                    "page_number": page_number,
                    "text": sent_text,
                    "source_element_id": None,
                    "source_bbox": None,
                }

        # +2 accounts for the "\n\n" joiner used by build_joined_text() below.
        doc_cursor += len(page_text) + 2

    return sentence_map, lookup_index


def build_joined_text(page_texts: List[Dict[str, Any]]) -> str:
    """The single document-level string that doc_char_start/end are relative to."""
    return "\n\n".join(p.get("text") or "" for p in sorted(page_texts, key=lambda p: p["page_number"]))


def save_sentence_map(
    sentence_map: List[Dict[str, Any]], lookup_index: Dict[str, Any], output_dir: Path
) -> Tuple[Path, Path]:
    map_path = output_dir / "page_sentence_map.json"
    lookup_path = output_dir / "sentence_lookup_index.json"
    save_json(sentence_map, map_path)
    save_json(lookup_index, lookup_path)
    return map_path, lookup_path


def to_legacy_sentences(sentence_map: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Converts the spec-shaped sentence map into the legacy `Sentence` dataclass
    shape (src/models.py) so the untouched spell / grammar / validation /
    report-generation stages keep working unmodified: they only ever read
    sentence_id, text, page and the doc-level char offsets off this object.
    """
    legacy = []
    for entry in sentence_map:
        numeric_id = sentence_numeric_id(entry["sentence_id"])
        legacy.append({
            "sentence_id": numeric_id,
            "paragraph_id": numeric_id,
            "page": entry["page_number"],
            "text": entry["text"],
            "start_offset": entry["start_char"],
            "end_offset": entry["end_char"],
            "doc_char_start": entry["doc_char_start"],
            "doc_char_end": entry["doc_char_end"],
            "bbox": None,
        })
    return legacy
