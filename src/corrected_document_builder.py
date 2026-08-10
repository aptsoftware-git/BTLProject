"""
corrected_document_builder.py
===============================
Rebuilds a clean corrected document (PDF / DOCX / HTML) from the Docling
page-text layer plus ACCEPTED findings only. Per spec this NEVER edits the
original PDF directly — it always regenerates fresh output from the
extracted page/sentence structure, preserving page boundaries and
paragraph breaks as closely as the running-text extraction allows.
"""

from __future__ import annotations

import html as html_lib
from pathlib import Path
from typing import Any, Dict, List


def apply_accepted_corrections(
    page_texts: List[Dict[str, Any]],
    sentence_map: List[Dict[str, Any]],
    findings: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Returns a new page_texts list with ACCEPTED findings applied, and only those."""
    sentences_by_id = {s["sentence_id"]: s for s in sentence_map}

    accepted_by_sentence: Dict[str, List[Dict[str, Any]]] = {}
    for f in findings:
        if f.get("status") != "accepted":
            continue
        sid = f.get("sentence_id")
        if not sid or f.get("token_start") is None or f.get("token_end") is None:
            continue
        accepted_by_sentence.setdefault(sid, []).append(f)

    corrected_sentence_by_id: Dict[str, str] = {}
    for sid, sent_findings in accepted_by_sentence.items():
        sentence = sentences_by_id.get(sid)
        if not sentence:
            continue
        text = sentence["text"]
        for f in sorted(sent_findings, key=lambda x: x["token_start"], reverse=True):
            ts, te = f["token_start"], f["token_end"]
            if 0 <= ts <= te <= len(text):
                text = text[:ts] + (f.get("suggestion") or "") + text[te:]
        corrected_sentence_by_id[sid] = text

    sentences_per_page: Dict[int, List[Dict[str, Any]]] = {}
    for s in sentence_map:
        sentences_per_page.setdefault(s["page_number"], []).append(s)

    corrected_pages: List[Dict[str, Any]] = []
    for page in sorted(page_texts, key=lambda p: p["page_number"]):
        page_number = page["page_number"]
        text = page.get("text") or ""
        touched = sorted(
            [s for s in sentences_per_page.get(page_number, []) if s["sentence_id"] in corrected_sentence_by_id],
            key=lambda s: s["start_char"],
            reverse=True,
        )
        for s in touched:
            start, end = s["start_char"], s["end_char"]
            if 0 <= start <= end <= len(text):
                text = text[:start] + corrected_sentence_by_id[s["sentence_id"]] + text[end:]
        corrected_pages.append({"page_number": page_number, "text": text})

    return corrected_pages


def build_html(corrected_pages: List[Dict[str, Any]], title: str = "Corrected Document") -> str:
    parts = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'>",
        f"<title>{html_lib.escape(title)}</title>",
        "<style>"
        "body{font-family:Georgia,serif;max-width:800px;margin:40px auto;line-height:1.6;color:#1a1a1a;}"
        ".page{padding-bottom:32px;margin-bottom:32px;border-bottom:1px solid #ddd;}"
        ".page-number{color:#888;font-size:12px;margin-bottom:12px;text-transform:uppercase;letter-spacing:.05em;}"
        "</style></head><body>",
    ]
    for page in corrected_pages:
        parts.append(f"<div class='page' data-page='{page['page_number']}'>")
        parts.append(f"<div class='page-number'>Page {page['page_number']}</div>")
        for para in (page.get("text") or "").split("\n\n"):
            para = para.strip()
            if para:
                parts.append(f"<p>{html_lib.escape(para)}</p>")
        parts.append("</div>")
    parts.append("</body></html>")
    return "\n".join(parts)


def build_docx(corrected_pages: List[Dict[str, Any]], output_path: Path) -> Path:
    from docx import Document as DocxDocument

    doc = DocxDocument()
    for i, page in enumerate(corrected_pages):
        for para in (page.get("text") or "").split("\n\n"):
            para = para.strip()
            if para:
                doc.add_paragraph(para)
        if i < len(corrected_pages) - 1:
            doc.add_page_break()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output_path))
    return output_path


def build_pdf(corrected_pages: List[Dict[str, Any]], output_path: Path) -> Path:
    import fitz

    doc = fitz.open()
    for page in corrected_pages:
        pdf_page = doc.new_page(width=595, height=842)  # A4
        rect = fitz.Rect(56, 56, 595 - 56, 842 - 56)
        text = page.get("text") or ""
        pdf_page.insert_textbox(rect, text, fontsize=11, fontname="helv")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output_path))
    doc.close()
    return output_path
