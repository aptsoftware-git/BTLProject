"""
test_extraction_fallback_images.py
====================================
Regression tests for the PyMuPDF fallback extraction path
(MultimodalExtractor._build_fallback_structured_document_for_batch), used
whenever Docling batch conversion fails for a page range.

Before this fix, that fallback discarded every image on the pages it
covered (it only ever emitted text elements), which meant a single failed
Docling batch could silently drop dozens of real pictures from 05_images
with no error, no log signal a human would notice, and no way for any
downstream retrievability fix to recover them -- they never reached
persistence at all.

These tests verify the fallback now:
  * enumerates every real embedded image on a page (via
    page.get_image_info, not the unreliable get_text("blocks")
    block_type == 1 classifier -- verified empirically to miss real
    embedded pictures on production documents),
  * produces ImageMetadata entries with a correct page_number + bbox,
  * those entries crop into real, non-empty PNGs via the existing
    ImageProcessor.crop_image_from_pdf codepath,
  * pages with genuinely no images produce no image entries (no false
    positives), and
  * degenerate/zero-area image blocks are skipped.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.config import ROOT_DIR
from src.rag.multimodal_extractor import MultimodalExtractor
from src.rag.image_processor import ImageProcessor

REAL_PDF = ROOT_DIR / "data" / "output" / "btl_216_page_run" / "01_document" / "uploaded.pdf"


@pytest.mark.skipif(not REAL_PDF.exists(), reason="real btl_216_page_run source PDF fixture not present")
def test_fallback_extraction_finds_real_images_on_known_portrait_page():
    """Page 49 (0-indexed 48) is independently known (test_hierarchical_image_grounding.py)
    to contain the 9 director portraits image_146.json..image_154.json.

    page_number here is batch-local (1-based within [start_page, end_page)),
    matching Docling's own numbering when it parses a per-batch temp PDF --
    see test_fallback_extraction_multiple_images_across_pages below, which
    documents the same contract. multimodal_extractor.extract()'s
    "Update batch element IDs and page offsets" pass is what adds
    batch_start on top of this to get the absolute page (49 here); this
    isolated unit test calls the builder directly, without that pass.
    """
    extractor = MultimodalExtractor()
    doc = extractor._build_fallback_structured_document_for_batch(
        file_path=REAL_PDF, start_page=48, end_page=49,
        file_name="btl", file_type="pdf",
    )
    assert len(doc.images) == 9, f"expected 9 portrait images on page 49, found {len(doc.images)}"
    for img_meta in doc.images.values():
        assert img_meta.page_number == 1  # batch-local: this batch covers only absolute page 49
        assert img_meta.bbox is not None
        assert img_meta.image_path is None  # left unset for the main loop's crop-from-PDF fallback to fill in


@pytest.mark.skipif(not REAL_PDF.exists(), reason="real btl_216_page_run source PDF fixture not present")
def test_fallback_detected_image_crops_into_real_nonempty_png(tmp_path):
    extractor = MultimodalExtractor()
    doc = extractor._build_fallback_structured_document_for_batch(
        file_path=REAL_PDF, start_page=48, end_page=49,
        file_name="btl", file_type="pdf",
    )
    assert doc.images, "fixture page must have detected at least one image"
    img_meta = next(iter(doc.images.values()))

    target_path = tmp_path / "fallback_crop.png"
    result = ImageProcessor.crop_image_from_pdf(
        pdf_path=REAL_PDF,
        page_number=img_meta.page_number,
        bbox=img_meta.bbox,
        target_path=target_path,
    )
    assert result is not None
    assert target_path.exists()
    assert target_path.stat().st_size > 0


def test_fallback_extraction_produces_no_images_on_text_only_page():
    """A page with zero embedded images (mocked) must never produce phantom
    image entries -- the fix must not introduce false positives."""
    extractor = MultimodalExtractor()

    mock_page = MagicMock()
    mock_page.get_image_info.return_value = []
    mock_page.get_text.return_value = [
        (10.0, 10.0, 400.0, 30.0, "A heading with more than fifteen characters.", 0, 0),
    ]

    mock_doc = MagicMock()
    mock_doc.page_count = 1
    mock_doc.__getitem__.return_value = mock_page
    mock_doc.__enter__.return_value = mock_doc
    mock_doc.__exit__.return_value = False

    with patch("fitz.open", return_value=mock_doc):
        doc = extractor._build_fallback_structured_document_for_batch(
            file_path=Path("dummy.pdf"), start_page=0, end_page=1,
            file_name="dummy", file_type="pdf",
        )

    assert doc.images == {}
    assert len(doc.elements) == 1


def test_fallback_extraction_skips_degenerate_zero_area_image_blocks():
    """A zero-width or zero-height image bbox (a MuPDF artefact, not a real
    picture) must be skipped, not saved as a broken/empty asset."""
    extractor = MultimodalExtractor()

    mock_page = MagicMock()
    mock_page.get_image_info.return_value = [
        {"bbox": (10.0, 10.0, 10.0, 50.0)},   # zero width -- degenerate
        {"bbox": (10.0, 10.0, 50.0, 10.0)},   # zero height -- degenerate
        {"bbox": (10.0, 10.0, 50.0, 50.0)},   # valid
    ]
    mock_page.get_text.return_value = []

    mock_doc = MagicMock()
    mock_doc.page_count = 1
    mock_doc.__getitem__.return_value = mock_page
    mock_doc.__enter__.return_value = mock_doc
    mock_doc.__exit__.return_value = False

    with patch("fitz.open", return_value=mock_doc):
        doc = extractor._build_fallback_structured_document_for_batch(
            file_path=Path("dummy.pdf"), start_page=0, end_page=1,
            file_name="dummy", file_type="pdf",
        )

    assert len(doc.images) == 1
    only_image = next(iter(doc.images.values()))
    assert only_image.bbox.l == 10.0 and only_image.bbox.r == 50.0


def test_fallback_extraction_multiple_images_across_pages():
    """Images on different pages within the same fallback batch must each
    get their own entry with the correct page_number."""
    extractor = MultimodalExtractor()

    def make_page(image_bboxes):
        p = MagicMock()
        p.get_image_info.return_value = [{"bbox": b} for b in image_bboxes]
        p.get_text.return_value = []
        return p

    page1 = make_page([(10.0, 10.0, 50.0, 50.0)])
    page2 = make_page([(20.0, 20.0, 60.0, 60.0), (70.0, 70.0, 110.0, 110.0)])

    mock_doc = MagicMock()
    mock_doc.page_count = 2
    mock_doc.__getitem__.side_effect = lambda i: [page1, page2][i]
    mock_doc.__enter__.return_value = mock_doc
    mock_doc.__exit__.return_value = False

    with patch("fitz.open", return_value=mock_doc):
        doc = extractor._build_fallback_structured_document_for_batch(
            file_path=Path("dummy.pdf"), start_page=0, end_page=2,
            file_name="dummy", file_type="pdf",
        )

    assert len(doc.images) == 3
    pages_seen = sorted(m.page_number for m in doc.images.values())
    assert pages_seen == [1, 2, 2]
