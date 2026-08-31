"""
test_image_metadata_rag_linking_e2e.py
=======================================
End-to-end, on-disk verification that a portrait image's persisted JSON
metadata (05_images/image_NNN.json) is actually wired into the RAG chunk/
index layer -- not just correct in isolation.

Specifically verifies the full chain link_person_entities_for_document is
responsible for, using real files on disk (not just in-memory dicts):

  1. Every image has exactly one JSON sidecar with the grounded person
     fields already on it (entity_name, designation, nearby_text) -- this
     is what multimodal_extractor's per-image loop + HierarchicalLayoutGrounder
     are expected to have produced before this stage runs.
  2. link_person_entities_for_document resolves that name into a stable
     entity_id and stamps it onto BOTH the image's chunk record and its
     05_images/*.json file on disk (not just the in-memory chunk list).
  3. Every text chunk that genuinely discusses that same person (by real
     text content, not by proximity to a heading) gets entity_id/entity_ids
     AND gets recorded on the image's own linked_text_chunk_ids -- so a
     qualifications-style query can be answered from real document prose.
  4. The reverse link also lands on disk: the text chunk gets
     linked_image_ids pointing back at the portrait, so a text-only query
     can also surface the associated image.
  5. An unrelated image (no resolvable identity) and an unrelated text
     chunk (doesn't mention the person) are left alone -- linking is
     content-driven, never a blanket "attach everything" pass.
"""
import json
from pathlib import Path

from src.rag.entity_linker import link_person_entities_for_document


def _write_image_json(images_dir: Path, stem: str, data: dict):
    images_dir.mkdir(parents=True, exist_ok=True)
    (images_dir / f"{stem}.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")
    (images_dir / f"{stem}.json").write_text(json.dumps(data), encoding="utf-8")


def _chunk(chunk_id, chunk_type, content="", **meta):
    return {"content": content, "metadata": {"chunk_id": chunk_id, "chunk_type": chunk_type, **meta}}


def test_portrait_metadata_is_linked_to_real_biography_chunk_end_to_end(tmp_path):
    output_dir = tmp_path
    document_id = "doc1"
    images_dir = output_dir / "05_images"

    # 1. A portrait already grounded by HierarchicalLayoutGrounder with real
    #    person fields -- this is what multimodal_extractor persists today.
    _write_image_json(images_dir, "image_001", {
        "image_id": "image_001",
        "page": 12,
        "image_type": "Portrait Photo",
        "entity_name": "Jane Doe",
        "designation": "Chief Financial Officer",
        "nearby_text": "Jane Doe, Chief Financial Officer, brings over 20 years of experience in corporate finance.",
        "association_method": "same_card_layout",
        "retrievable": True,
    })
    # An unrelated image with no resolvable identity -- must be left alone.
    _write_image_json(images_dir, "image_002", {
        "image_id": "image_002",
        "page": 3,
        "image_type": "Chart",
        "entity_name": None,
    })

    chunks = [
        _chunk("doc1_chunk_0001", "image", image_id="image_001", entity_name="Jane Doe", designation="Chief Financial Officer", page_number=12),
        _chunk("doc1_chunk_0002", "image", image_id="image_002", page_number=3),
        _chunk(
            "doc1_chunk_0003", "text",
            content="Jane Doe joined the board in 2015. She holds an MBA from a leading business school and has "
                    "over 20 years of experience in corporate finance, having previously served as CFO of a "
                    "listed manufacturing company.",
            page_number=13,
        ),
        _chunk("doc1_chunk_0004", "text", content="The plant produces 500,000 tonnes of steel annually.", page_number=45),
    ]
    chunks_data = {"chunks": chunks}
    (output_dir / "document_chunks.json").write_text(json.dumps(chunks_data), encoding="utf-8")
    (output_dir / "06_chunks").mkdir(parents=True, exist_ok=True)
    (output_dir / "06_chunks" / "document_chunks.json").write_text(json.dumps(chunks_data), encoding="utf-8")

    stats = link_person_entities_for_document(output_dir=output_dir, document_id=document_id, vector_store=None)

    assert stats["portraits_linked"] == 1
    assert stats["text_chunks_linked"] == 1

    updated = json.loads((output_dir / "document_chunks.json").read_text(encoding="utf-8"))
    by_id = {c["metadata"]["chunk_id"]: c["metadata"] for c in updated["chunks"]}

    # 2. The portrait's chunk record got a stable entity_id and knows which
    #    text chunk actually discusses this person.
    portrait_meta = by_id["doc1_chunk_0001"]
    assert portrait_meta["entity_id"]
    assert portrait_meta["linked_text_chunk_ids"] == ["doc1_chunk_0003"]

    # 3. The real biography chunk got the same entity_id, and the reverse
    #    link back to the portrait's image_id.
    bio_meta = by_id["doc1_chunk_0003"]
    assert bio_meta["entity_id"] == portrait_meta["entity_id"]
    assert bio_meta.get("linked_image_ids") == ["image_001"]

    # 4. The unrelated image and unrelated text chunk were left alone.
    assert not by_id["doc1_chunk_0002"].get("entity_id")
    assert not by_id["doc1_chunk_0004"].get("entity_id")
    assert not by_id["doc1_chunk_0004"].get("linked_image_ids")

    # 5. The link landed on the actual 05_images/*.json file on disk too --
    #    not just the in-memory chunk list -- so anything reading the image's
    #    own metadata sidecar directly (the UI, a re-chunk pass, a fresh
    #    index build) sees the same connection.
    image_json_on_disk = json.loads((images_dir / "image_001.json").read_text(encoding="utf-8"))
    assert image_json_on_disk["entity_id"] == portrait_meta["entity_id"]
    assert image_json_on_disk["linked_text_chunk_ids"] == ["doc1_chunk_0003"]
    # And the fields HierarchicalLayoutGrounder had already produced are untouched.
    assert image_json_on_disk["entity_name"] == "Jane Doe"
    assert image_json_on_disk["designation"] == "Chief Financial Officer"
    assert "20 years of experience" in image_json_on_disk["nearby_text"]

    unrelated_image_json = json.loads((images_dir / "image_002.json").read_text(encoding="utf-8"))
    assert "entity_id" not in unrelated_image_json or not unrelated_image_json.get("entity_id")


def test_no_person_in_document_leaves_metadata_untouched(tmp_path):
    """A document with images but no grounded person identity anywhere must
    not fabricate entity links -- absence of identity evidence must not
    produce a wrong or empty-but-present entity_id."""
    output_dir = tmp_path
    images_dir = output_dir / "05_images"
    _write_image_json(images_dir, "image_001", {
        "image_id": "image_001", "page": 3, "image_type": "Chart", "entity_name": None,
    })
    chunks_data = {"chunks": [
        _chunk("doc1_chunk_0001", "image", image_id="image_001", page_number=3),
        _chunk("doc1_chunk_0002", "text", content="Revenue grew 12% year over year.", page_number=4),
    ]}
    (output_dir / "document_chunks.json").write_text(json.dumps(chunks_data), encoding="utf-8")

    stats = link_person_entities_for_document(output_dir=output_dir, document_id="doc1", vector_store=None)

    assert stats["portraits_linked"] == 0
    assert stats["text_chunks_linked"] == 0
    image_json_on_disk = json.loads((images_dir / "image_001.json").read_text(encoding="utf-8"))
    assert not image_json_on_disk.get("entity_id")
