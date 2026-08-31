"""
test_supplement_missing_images.py
==================================
Regression test for MultimodalExtractor._supplement_missing_images_from_pdf:
Docling's own picture-layout classifier can under-detect real embedded
images even on a batch that otherwise converts successfully (small images,
decorative-looking regions, low-confidence calls). This cross-checks a
successfully-converted batch against a raw PyMuPDF embedded-image
enumeration and adds any picture Docling's classifier missed, so a document
never silently ends up with fewer extracted images than it actually
contains.
"""
from pathlib import Path

import fitz
from PIL import Image

from src.rag.document_schema import StructuredDocument, BoundingBox, ImageMetadata
from src.rag.multimodal_extractor import MultimodalExtractor


def _make_pdf_with_two_images(path: Path):
    img1_path = path.parent / "img1.png"
    img2_path = path.parent / "img2.png"
    Image.new("RGB", (80, 80), color=(200, 0, 0)).save(img1_path)
    Image.new("RGB", (80, 80), color=(0, 0, 200)).save(img2_path)

    doc = fitz.open()
    page = doc.new_page()
    page.insert_image(fitz.Rect(50, 50, 150, 150), filename=str(img1_path))
    page.insert_image(fitz.Rect(300, 300, 400, 400), filename=str(img2_path))
    doc.save(str(path))
    doc.close()


def test_supplement_adds_image_docling_missed_entirely(tmp_path):
    """Docling detected zero pictures on the page (simulated); both real
    embedded images must be added by the raw PyMuPDF cross-check."""
    pdf_path = tmp_path / "doc.pdf"
    _make_pdf_with_two_images(pdf_path)

    batch_doc = StructuredDocument(
        title="t", file_name="t", file_type="pdf", page_count=1, elements=[], tables={}, images={}
    )

    extractor = MultimodalExtractor()
    added = extractor._supplement_missing_images_from_pdf(batch_doc, pdf_path)

    assert added == 2
    assert len(batch_doc.images) == 2
    for img in batch_doc.images.values():
        assert img.page_number == 1
        assert img.image_path is None  # left unset for the existing crop-from-PDF fallback


def test_supplement_does_not_duplicate_image_docling_already_found():
    """If Docling already reported a picture at (roughly) the same region,
    the raw scan must recognize it as the same image and not add a duplicate
    entry for it -- only genuinely undetected images get added."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        pdf_path = tmp_path / "doc.pdf"
        _make_pdf_with_two_images(pdf_path)

        # Docling already found the FIRST image (at 50,50 - 150,150, TOPLEFT
        # page space) but missed the second one entirely.
        existing_bbox = BoundingBox(l=50, t=50, r=150, b=150, coord_origin="TOPLEFT")
        batch_doc = StructuredDocument(
            title="t", file_name="t", file_type="pdf", page_count=1, elements=[],
            tables={}, images={
                "#/pictures/0": ImageMetadata(image_id="#/pictures/0", page_number=1, bbox=existing_bbox)
            }
        )

        extractor = MultimodalExtractor()
        added = extractor._supplement_missing_images_from_pdf(batch_doc, pdf_path)

        assert added == 1, "only the undetected second image should be added"
        assert len(batch_doc.images) == 2
