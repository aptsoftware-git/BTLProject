"""
test_proofreading_pdf_grounding_rejects_hallucinations.py
===========================================================
End-to-end regression test for the "no finding reaches the UI unless its
ORIGINAL text is independently confirmed in the actual source PDF" rule.

Exercises the real pipeline stages together:
  finding_mapper.build_findings()  -- sentence-text substring check
  -> pdf_bbox_resolver.resolve_bboxes()  -- independent PyMuPDF page-text search
  -> final_validation_layer.FinalValidationLayer.run()  -- last gate

against a real, tiny PDF built with PyMuPDF (not a mock), so the PDF search
is exercising real fitz text extraction rather than a stub.

Covers the exact false-positive shapes called out for this pipeline:
a candidate token that does not actually appear in the source PDF at all
(a stale/hallucinated candidate, e.g. "bord" -> "born" or "trn" -> "ten"
when the real text never contained "bord"/"trn") must be completely absent
from the accepted/final findings -- and a genuine, PDF-present error must
still survive, proving the gate rejects on real absence rather than
rejecting everything indiscriminately.
"""
import fitz
import pytest

from src.finding_mapper import build_findings
from src.pdf_bbox_resolver import resolve_bboxes
from src.final_validation_layer import FinalValidationLayer


REAL_SENTENCE = "The company was established in 1998 and operates a large steel plant."


@pytest.fixture()
def sample_pdf(tmp_path):
    """A one-page real PDF whose only text is REAL_SENTENCE, so a page-text
    search for anything not literally in that sentence must fail to find it."""
    pdf_path = tmp_path / "sample.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), REAL_SENTENCE, fontsize=12)
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


def _lookup_index(sentence_text, source_element_id="#/texts/0", source_bbox=None):
    from src.sentence_mapper import sentence_id_str
    return {
        sentence_id_str(1): {
            "text": sentence_text,
            "page_number": 1,
            "source_element_id": source_element_id,
            # Matches where sample_pdf's insert_text((72, 72), ...) actually
            # places the line (TOPLEFT page coordinates, y increasing downward).
            "source_bbox": source_bbox or {"l": 50.0, "t": 55.0, "r": 560.0, "b": 95.0, "coord_origin": "TOPLEFT"},
        }
    }


def _run_pipeline(report_issues, lookup_index, pdf_path):
    findings, auto_rejected = build_findings(report_issues, lookup_index)
    findings = resolve_bboxes(findings, pdf_path)
    layer = FinalValidationLayer()
    accepted, decision_log = layer.run(findings, auto_rejected)
    return accepted, decision_log


def test_hallucinated_original_not_in_pdf_is_fully_rejected(sample_pdf):
    """'bord' never appears anywhere in the real PDF text or the sentence --
    a candidate claiming otherwise must never reach final_findings."""
    report_issues = [{
        "sentence_id": 1,
        "original_text": "bord",
        "suggested_text": "born",
        "issue_type": "spelling",
        "confidence": 0.9,
    }]
    lookup_index = _lookup_index(REAL_SENTENCE)  # "bord" is not a substring of REAL_SENTENCE

    accepted, decision_log = _run_pipeline(report_issues, lookup_index, sample_pdf)

    assert accepted == [], "a token absent from both the sentence and the PDF must never be accepted"
    assert any(d["original"] == "bord" and d["decision"] == "rejected" for d in decision_log)


def test_hallucinated_original_trn_not_in_pdf_is_fully_rejected(sample_pdf):
    """Same shape with a second garbled token ('trn' -> 'ten')."""
    report_issues = [{
        "sentence_id": 1,
        "original_text": "trn",
        "suggested_text": "ten",
        "issue_type": "spelling",
        "confidence": 0.9,
    }]
    lookup_index = _lookup_index(REAL_SENTENCE)

    accepted, decision_log = _run_pipeline(report_issues, lookup_index, sample_pdf)

    assert accepted == []
    assert any(d["original"] == "trn" and d["decision"] == "rejected" for d in decision_log)


def test_genuine_pdf_present_error_still_survives(sample_pdf):
    """Control case: a real error whose original text genuinely is in both
    the sentence and the PDF must still be accepted -- the gate rejects on
    real absence, not indiscriminately."""
    # "established" is a real word in REAL_SENTENCE / the PDF; treat it as a
    # (contrived) tense/grammar correction target purely to exercise the
    # pipeline's acceptance path with a token that truly is present.
    report_issues = [{
        "sentence_id": 1,
        "original_text": "operates",
        "suggested_text": "operated",
        "issue_type": "grammar",
        "confidence": 0.9,
    }]
    lookup_index = _lookup_index(REAL_SENTENCE)  # "operates" IS a substring of REAL_SENTENCE

    accepted, decision_log = _run_pipeline(report_issues, lookup_index, sample_pdf)

    assert len(accepted) == 1
    assert accepted[0]["original"] == "operates"
    assert accepted[0]["pdf_grounded"] is True


def test_candidate_matching_sentence_but_absent_from_actual_pdf_is_rejected(tmp_path):
    """A candidate whose 'original' matches the (possibly stale/cached)
    sentence_text string but is not actually present at that location in the
    real PDF (e.g. the PDF was re-extracted/changed, or the sentence_text is
    stale) must still be caught by the independent PDF-text search -- the
    sentence-text match alone is not sufficient once a real PDF is
    available; pdf_bbox_resolver's own region-scoped page search is the
    authoritative, independent check requirement 5 asks for."""
    pdf_path = tmp_path / "changed.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "A completely different sentence with no matching words.", fontsize=12)
    doc.save(str(pdf_path))
    doc.close()

    report_issues = [{
        "sentence_id": 1,
        "original_text": "trn",
        "suggested_text": "ten",
        "issue_type": "spelling",
        "confidence": 0.9,
    }]
    # Stale cached sentence_text claims "trn" is present, but the real PDF no longer has it.
    lookup_index = _lookup_index("This trn was late for the meeting.")

    findings, auto_rejected = build_findings(report_issues, lookup_index)
    # finding_mapper's own sentence-text check passes (stale text still contains "trn"),
    # so it reaches pdf_bbox_resolver -- which must fail to ground it against the real PDF.
    assert findings and findings[0]["grounding_verified"] is True

    grounded = resolve_bboxes(findings, pdf_path)
    assert grounded[0]["pdf_grounded"] is False, "must not be grounded when the real PDF text no longer contains it"
