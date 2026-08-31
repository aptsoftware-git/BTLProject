"""
test_image_global_uniqueness.py
================================
Regression tests for the multi-batch image extraction/persistence bug:

Docling numbers pictures locally within whatever document it just parsed
(pictures_0, pictures_1, ...). Every batch of a large document is converted
from a fresh temp PDF, so every batch's Docling numbering restarts at 0 --
but every batch used to persist its images' "image_id" as that raw,
non-unique self_ref straight into the JSON metadata sidecar. Two downstream
consumers both trusted that field as a stable unique identifier:

  - image_deduplicator.validate_and_cleanup_image_artifacts' "exactly one
    JSON per image_id" enforcement pass, and
  - chunk_builder's cross-batch 05_images JSON rescan.

Both treated every batch's Nth picture as a duplicate of every other
batch's Nth picture and deleted/skipped it, even when the two were
completely different images (e.g. two different Board of Directors
portraits) -- this is how a 216-page document with 90+ extracted images
ended with only ~51 left afterward.

The fix (see multimodal_extractor.py's per-image loop) assigns image_id
from a run-wide global counter that is identical to the final filename
stem, so it can never collide across batches. These tests verify the
surviving safety net in validate_and_cleanup_image_artifacts: even if two
JSON files ever do end up sharing an image_id again in the future, only a
byte-for-byte identical PNG pair may be collapsed -- a shared id string
alone must never delete the only copy of a distinct image.
"""

import json

from PIL import Image

from src.rag.image_deduplicator import validate_and_cleanup_image_artifacts
from src.rag.image_processor import ImageProcessor


class _FakePictureElement:
    """Minimal stand-in for a Docling PictureItem: only the attributes
    ImageProcessor.process_image actually reads."""

    def __init__(self, self_ref):
        self.self_ref = self_ref
        self.captions = []

    def get_image(self, doc):
        return Image.new("RGB", (4, 4), color=(10, 20, 30))


def test_process_image_filename_prefix_prevents_cross_batch_collision(tmp_path):
    """Two different batches whose Docling parse both restart picture
    numbering at 0 must never write to the same filename in the shared
    05_images directory -- each batch's raw extraction filename is tagged
    with its own batch_tag before any later renaming happens."""
    images_dir = tmp_path / "05_images"

    meta_batch1 = ImageProcessor.process_image(
        _FakePictureElement("#/pictures/0"), doc=None,
        output_images_dir=images_dir, filename_prefix="b1"
    )
    meta_batch2 = ImageProcessor.process_image(
        _FakePictureElement("#/pictures/0"), doc=None,
        output_images_dir=images_dir, filename_prefix="b2"
    )

    assert meta_batch1.image_path != meta_batch2.image_path
    assert images_dir.joinpath("b1_pictures_0.png").exists()
    assert images_dir.joinpath("b2_pictures_0.png").exists(), (
        "batch 2's picture must not have overwritten batch 1's picture "
        "just because Docling numbered them both pictures_0 locally"
    )


def _write_image_pair(images_dir, stem, image_id, png_bytes, page=1):
    images_dir.mkdir(parents=True, exist_ok=True)
    (images_dir / f"{stem}.png").write_bytes(png_bytes)
    (images_dir / f"{stem}.json").write_text(
        json.dumps({"image_id": image_id, "page": page}), encoding="utf-8"
    )


def test_cleanup_keeps_both_images_when_content_differs_despite_shared_image_id(tmp_path):
    """Two genuinely different images (e.g. two different board-member
    portraits) that happen to share an image_id string must both survive --
    a shared id is not proof of duplication."""
    images_dir = tmp_path / "05_images"
    _write_image_pair(images_dir, "image_001", "pictures_0", b"PORTRAIT-A-BYTES")
    _write_image_pair(images_dir, "image_016", "pictures_0", b"PORTRAIT-B-DIFFERENT-BYTES")

    validate_and_cleanup_image_artifacts(output_dir=tmp_path, document_id="doc1")

    assert (images_dir / "image_001.png").exists()
    assert (images_dir / "image_001.json").exists()
    assert (images_dir / "image_016.png").exists(), "distinct image must not be deleted just because image_id collided"
    assert (images_dir / "image_016.json").exists()


def test_cleanup_removes_true_byte_identical_duplicate_sharing_image_id(tmp_path):
    """A genuine byte-for-byte duplicate sharing an image_id is still
    collapsed down to a single canonical copy."""
    images_dir = tmp_path / "05_images"
    _write_image_pair(images_dir, "image_001", "pictures_0", b"SAME-BYTES-EXACTLY")
    _write_image_pair(images_dir, "image_016", "pictures_0", b"SAME-BYTES-EXACTLY")

    validate_and_cleanup_image_artifacts(output_dir=tmp_path, document_id="doc1")

    assert (images_dir / "image_001.png").exists()
    assert not (images_dir / "image_016.png").exists(), "byte-identical duplicate should be collapsed"
    assert not (images_dir / "image_016.json").exists()


def test_cleanup_is_a_no_op_when_every_image_id_is_already_globally_unique(tmp_path):
    """The fixed pipeline assigns image_id == filename stem for every image,
    so normal operation must never trigger the collision path at all."""
    images_dir = tmp_path / "05_images"
    _write_image_pair(images_dir, "image_001", "image_001", b"AAA", page=1)
    _write_image_pair(images_dir, "image_002", "image_002", b"BBB", page=5)
    _write_image_pair(images_dir, "image_003", "image_003", b"CCC", page=49)

    stats = validate_and_cleanup_image_artifacts(output_dir=tmp_path, document_id="doc1")

    for stem in ("image_001", "image_002", "image_003"):
        assert (images_dir / f"{stem}.png").exists()
        assert (images_dir / f"{stem}.json").exists()
    assert stats["retained_images"] == 3
