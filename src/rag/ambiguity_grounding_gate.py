"""
ambiguity_grounding_gate.py
==============================
Programmatic evidence-grounding gate for Ambiguity Analysis findings.

Enforces strict, robust evidence grounding:
1. Normalizes harmless differences (whitespace, line breaks, quotation marks,
   Unicode punctuation, PDF extraction spacing, hyphenation).
2. Checks cited source chunk.
3. If not found in cited chunk, searches neighboring/source chunks in document chunk map.
4. If found elsewhere, updates evidence location, preserves provenance, and sets grounding_verified=True.
5. If evidence genuinely cannot be located, rejects the candidate with explicit reason.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

_WS_RE = re.compile(r"[\s\u00a0\u200b\u200e\u200f]+")
_HYPHEN_BREAK_RE = re.compile(r"(\w+)-\s*[\r\n]+\s*(\w+)")
_DASHES_RE = re.compile(r"[\u2010\u2011\u2012\u2013\u2014\u2015\u2212]")


def normalize_text_robust(text: str) -> str:
    """Normalizes text for robust evidence matching across PDF/extraction formatting artifacts."""
    if not text:
        return ""
    # Unicode NFKC normalization
    t = unicodedata.normalize("NFKC", str(text))
    # Standardize quotation marks and apostrophes
    t = t.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'").replace("`", "'")
    # Standardize dashes
    t = _DASHES_RE.sub("-", t)
    # Remove PDF line-break hyphenation (e.g. "Engi-\nneering" -> "Engineering")
    t = _HYPHEN_BREAK_RE.sub(r"\1\2", t)
    # Collapse all whitespace and non-breaking spaces
    t = _WS_RE.sub(" ", t)
    return t.strip().lower()


def _quote_found_in_chunk(quote: str, chunk_text: str) -> bool:
    if not quote or not chunk_text:
        return False
    quote_n = normalize_text_robust(quote)
    chunk_n = normalize_text_robust(chunk_text)
    if not quote_n or not chunk_n:
        return False
    if quote_n in chunk_n:
        return True

    # Strip quote marks (' and ") added by LLM formatting
    quote_no_q = quote_n.replace('"', '').replace("'", '')
    chunk_no_q = chunk_n.replace('"', '').replace("'", '')
    if quote_no_q and quote_no_q in chunk_no_q:
        return True

    # Strip leading/trailing punctuation & symbols
    stripped_q = quote_no_q.strip(" .,;:'\"-–—()[]{}…")
    if stripped_q and len(stripped_q) >= 4 and stripped_q in chunk_no_q:
        return True
    return False


def verify_evidence(
    finding: Dict[str, Any], chunk_map: Dict[str, Dict[str, Any]]
) -> Tuple[bool, Optional[str]]:
    """Returns (grounded, reject_reason).

    Verifies evidence strictly but robustly:
    1. Check cited chunk_id.
    2. If missing/not matched, search neighboring chunks and full document chunk_map.
    3. If match found in another chunk: update evidence location & chunk_id on finding,
       preserve provenance, and mark grounding_verified=True.
    4. If quote cannot be found anywhere in document: reject candidate with explicit reason.
    """
    if not isinstance(finding, dict) or not chunk_map:
        return False, "invalid finding structure or empty chunk map"

    evidence_items: List[Dict[str, Any]] = list(finding.get("evidence") or [])
    top_chunk_id = finding.get("chunk_id")
    top_quote = finding.get("highlighted_ambiguity") or finding.get("quote") or finding.get("suspected_text")

    if not evidence_items and top_chunk_id and top_quote:
        evidence_items = [{"chunk_id": top_chunk_id, "quote": top_quote}]

    if not evidence_items:
        return False, "no source location or evidence quote text provided"

    all_chunks_list = list(chunk_map.items())
    grounded_any = False

    for item in evidence_items:
        if not isinstance(item, dict):
            continue
        cited_cid = item.get("chunk_id") or top_chunk_id
        quote = item.get("quote") or top_quote
        if not quote:
            continue

        # 1. Primary check: cited chunk_id
        primary_entry = chunk_map.get(cited_cid) if cited_cid else None
        if primary_entry and _quote_found_in_chunk(quote, primary_entry.get("text") or ""):
            item["chunk_id"] = cited_cid
            finding["grounding_verified"] = True
            grounded_any = True
            continue

        # 2. Neighbor / Provenance Search: search neighboring chunks & entire chunk_map
        matched_cid = None
        # Try adjacent chunk IDs first (e.g. if cited_cid is "chunk_014", check chunk_013, chunk_015)
        if cited_cid and "_" in str(cited_cid):
            prefix, _, num_str = str(cited_cid).rpartition("_")
            if num_str.isdigit():
                num = int(num_str)
                for delta in [-1, 1, -2, 2, -3, 3]:
                    candidate_cid = f"{prefix}_{num+delta:03d}"
                    cand_entry = chunk_map.get(candidate_cid)
                    if cand_entry and _quote_found_in_chunk(quote, cand_entry.get("text") or ""):
                        matched_cid = candidate_cid
                        break

        # If not found in adjacent chunks, search all chunks in chunk_map
        if not matched_cid:
            for cid, cdata in all_chunks_list:
                if _quote_found_in_chunk(quote, cdata.get("text") or ""):
                    matched_cid = cid
                    break

        if matched_cid:
            # Update evidence location to the real chunk where evidence lives
            item["chunk_id"] = matched_cid
            if not finding.get("chunk_id") or finding.get("chunk_id") == cited_cid:
                finding["chunk_id"] = matched_cid
            finding["grounding_verified"] = True
            grounded_any = True
        else:
            sample_q = str(quote)[:50]
            return False, f"evidence quote '{sample_q}...' could not be located in cited chunk '{cited_cid}' or any document source chunk"

    if grounded_any:
        return True, None

    return False, "evidence quote does not appear in document chunks"
