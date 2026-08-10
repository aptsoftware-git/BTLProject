"""
test_pdf_bbox_resolver.py
============================
Regression tests for src/pdf_bbox_resolver.py's provenance-first PDF
coordinate resolution: element-bbox-clipped word matching as the primary
mechanism, a narrow region-scoped search_for() fallback, and "never guess"
(bbox=None, pdf_grounded=False) when neither resolves cleanly.

Also locks in the running-text-only filter (src/page_text_builder.py) that
guarantees table/image/figure text can never produce a proofreading finding
in the first place, regardless of what pdf_bbox_resolver does downstream.
"""

import fitz
import pytest

from src.page_text_builder import build_page_text_and_blocks
from src.pdf_bbox_resolver import resolve_bboxes


def _bbox_from_rect(rect):
    return {"l": rect.x0, "t": rect.y0, "r": rect.x1, "b": rect.y1, "coord_origin": "TOPLEFT"}


def _finding(page_number, element_id, bbox, original, finding_id="ERR_0001"):
    return {
        "finding_id": finding_id,
        "page_number": page_number,
        "source_element_id": element_id,
        "source_bbox": bbox,
        "original": original,
    }


@pytest.fixture
def single_sentence_pdf(tmp_path):
    doc = fitz.open()
    page = doc.new_page()
    rect = fitz.Rect(50, 50, 500, 100)
    page.insert_textbox(rect, "The company have achieved significant growth.", fontsize=12, fontname="helv")
    path = tmp_path / "single.pdf"
    doc.save(str(path))
    doc.close()
    return path, rect


def test_single_occurrence_resolves_to_word_not_sentence(single_sentence_pdf):
    path, rect = single_sentence_pdf
    finding = _finding(1, "e1", _bbox_from_rect(rect), "have")

    out = resolve_bboxes([finding], path)

    assert out[0]["pdf_grounded"] is True
    bbox = out[0]["bbox"]
    assert bbox is not None
    # A single word must be much narrower than the whole sentence textbox --
    # this is the "highlight the word, not the sentence" requirement.
    assert (bbox["x1"] - bbox["x0"]) < (rect.x1 - rect.x0) * 0.5
    assert rect.x0 <= bbox["x0"] and bbox["x1"] <= rect.x1 + 5


def test_same_word_in_two_different_elements_resolves_independently(tmp_path):
    doc = fitz.open()
    page = doc.new_page()
    rect_a = fitz.Rect(50, 50, 500, 90)
    rect_b = fitz.Rect(50, 400, 500, 440)
    page.insert_textbox(rect_a, "Our growth was strong this year.", fontsize=12, fontname="helv")
    page.insert_textbox(rect_b, "Future growth is expected too.", fontsize=12, fontname="helv")
    path = tmp_path / "two_elements.pdf"
    doc.save(str(path))
    doc.close()

    finding_a = _finding(1, "e_a", _bbox_from_rect(rect_a), "growth", "ERR_0001")
    finding_b = _finding(1, "e_b", _bbox_from_rect(rect_b), "growth", "ERR_0002")

    out = resolve_bboxes([finding_a, finding_b], path)

    a, b = out[0], out[1]
    assert a["pdf_grounded"] is True and b["pdf_grounded"] is True
    # Each match must land inside its OWN element's region, not the other's --
    # this is exactly the case a blind whole-page search_for() gets wrong.
    assert rect_a.y0 - 5 <= a["bbox"]["y0"] <= rect_a.y1 + 5
    assert rect_b.y0 - 5 <= b["bbox"]["y0"] <= rect_b.y1 + 5


def test_two_findings_in_same_sentence_resolve_to_distinct_occurrences(tmp_path):
    doc = fitz.open()
    page = doc.new_page()
    rect = fitz.Rect(50, 50, 500, 90)
    page.insert_textbox(rect, "The team have have missed the deadline.", fontsize=12, fontname="helv")
    path = tmp_path / "repeated_word.pdf"
    doc.save(str(path))
    doc.close()

    finding1 = _finding(1, "e1", _bbox_from_rect(rect), "have", "ERR_0001")
    finding2 = _finding(1, "e1", _bbox_from_rect(rect), "have", "ERR_0002")

    out = resolve_bboxes([finding1, finding2], path)

    assert out[0]["pdf_grounded"] is True and out[1]["pdf_grounded"] is True
    # Reading order left-to-right on the same line: first occurrence's box
    # must sit strictly before the second occurrence's box.
    assert out[0]["bbox"]["x0"] < out[1]["bbox"]["x0"]


def test_hyphenated_word_resolves(tmp_path):
    doc = fitz.open()
    page = doc.new_page()
    rect = fitz.Rect(50, 50, 500, 90)
    page.insert_textbox(rect, "Please contact the co-founder for details.", fontsize=12, fontname="helv")
    path = tmp_path / "hyphen.pdf"
    doc.save(str(path))
    doc.close()

    finding = _finding(1, "e1", _bbox_from_rect(rect), "co-founder")
    out = resolve_bboxes([finding], path)

    assert out[0]["pdf_grounded"] is True
    assert out[0]["bbox"] is not None


def test_extra_whitespace_in_target_still_matches(single_sentence_pdf):
    path, rect = single_sentence_pdf
    # Target has a doubled space -- normalization must still find it against
    # the PDF's single-spaced extracted text.
    finding = _finding(1, "e1", _bbox_from_rect(rect), "have  achieved")

    out = resolve_bboxes([finding], path)

    assert out[0]["pdf_grounded"] is True
    assert out[0]["bbox"] is not None


def test_multiword_phrase_unions_matched_words_only(single_sentence_pdf):
    path, rect = single_sentence_pdf
    finding = _finding(1, "e1", _bbox_from_rect(rect), "achieved significant growth")

    out = resolve_bboxes([finding], path)

    assert out[0]["pdf_grounded"] is True
    bbox = out[0]["bbox"]
    # Three words unioned should still be narrower than the full sentence box.
    assert (bbox["x1"] - bbox["x0"]) < (rect.x1 - rect.x0) * 0.85


def test_missing_source_bbox_is_ungrounded_no_crash(single_sentence_pdf):
    path, _rect = single_sentence_pdf
    finding = _finding(1, "e1", None, "have")

    out = resolve_bboxes([finding], path)

    assert out[0]["pdf_grounded"] is False
    assert out[0]["bbox"] is None


def test_unresolvable_target_text_is_ungrounded_no_crash(single_sentence_pdf):
    path, rect = single_sentence_pdf
    finding = _finding(1, "e1", _bbox_from_rect(rect), "banana")

    out = resolve_bboxes([finding], path)

    assert out[0]["pdf_grounded"] is False
    assert out[0]["bbox"] is None


def test_non_pdf_original_marks_everything_ungrounded(tmp_path):
    fake_docx = tmp_path / "not_a_pdf.docx"
    fake_docx.write_bytes(b"not really a pdf")
    finding = _finding(1, "e1", {"l": 0, "t": 0, "r": 100, "b": 20, "coord_origin": "TOPLEFT"}, "have")

    out = resolve_bboxes([finding], fake_docx)

    assert out[0]["pdf_grounded"] is False
    assert out[0]["bbox"] is None


def test_missing_pdf_path_marks_everything_ungrounded():
    finding = _finding(1, "e1", {"l": 0, "t": 0, "r": 100, "b": 20, "coord_origin": "TOPLEFT"}, "have")

    out = resolve_bboxes([finding], None)

    assert out[0]["pdf_grounded"] is False
    assert out[0]["bbox"] is None


# ---------------------------------------------------------------------------
# Running-text scope regression: table/image/figure content must never reach
# page_text_builder's blocks, so it can never become a finding in the first
# place -- independent of anything pdf_bbox_resolver does.
# ---------------------------------------------------------------------------

def _structured_doc(elements, page_count=1):
    return {"page_count": page_count, "elements": elements}


def test_table_and_image_only_page_produces_zero_blocks():
    elements = [
        {"type": "table", "text": "Revenue | 2023 | 2024", "metadata": {"page_number": 1}},
        {"type": "image", "text": "", "metadata": {"page_number": 1}},
        {"type": "caption", "text": "Figure 1: Revenue chart", "metadata": {"page_number": 1}},
        {"type": "footnote", "text": "See appendix A.", "metadata": {"page_number": 1}},
    ]
    pages = build_page_text_and_blocks(_structured_doc(elements))

    assert len(pages) == 1
    assert pages[0]["blocks"] == []
    assert pages[0]["text"] == ""


def test_image_heavy_page_only_yields_the_running_text():
    elements = [
        {"type": "image", "text": "", "metadata": {"page_number": 1}},
        {"type": "paragraph", "text": "A brief caption-adjacent note.", "metadata": {"page_number": 1}},
        {"type": "table", "text": "Q1 | Q2 | Q3", "metadata": {"page_number": 1}},
    ]
    pages = build_page_text_and_blocks(_structured_doc(elements))

    assert len(pages) == 1
    assert len(pages[0]["blocks"]) == 1
    assert pages[0]["blocks"][0]["text"] == "A brief caption-adjacent note."
    assert pages[0]["blocks"][0]["type"] == "paragraph"
