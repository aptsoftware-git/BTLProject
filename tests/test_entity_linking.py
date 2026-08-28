"""
End-to-end verification of person/entity grounding:
  person name -> portrait -> linked biography text -> qualification question -> correct routing.

Fully generic: uses a made-up person/document, never a hardcoded roster.
"""
import pytest

from src.rag.entity_linker import (
    chunk_mentions_entity,
    generate_entity_key,
    link_entities_across_chunks,
    normalize_entity_text,
)
from src.rag.chunk_schema import ChunkMetadata, DocumentChunk
from src.rag.retriever import Retriever

DOC_ID = "doc_test_entity_linking"
PERSON_NAME = "Ravi Todi"
DESIGNATION = "Managing Director"


def _make_chunk_dict(chunk_id, chunk_type, content, **meta_overrides):
    meta = {
        "chunk_id": chunk_id,
        "document_id": DOC_ID,
        "page_number": 3,
        "chunk_type": chunk_type,
        "heading": None,
        "section": "Board of Directors",
        "hierarchy_path": [],
        "source_element_ids": [],
        "word_count": len(content.split()),
        "token_estimate": len(content.split()) * 2,
        "bounding_boxes": [],
    }
    meta.update(meta_overrides)
    return {"content": content, "metadata": meta}


def _portrait_chunk_dict():
    return _make_chunk_dict(
        f"{DOC_ID}_chunk_0005",
        "image",
        "Image ID: img_005\nImage Type: Portrait Photo\nAssociated Person/Entity: Ravi Todi (Managing Director)",
        entity_name=PERSON_NAME,
        designation=DESIGNATION,
        association_method="spatial_document_context",
        image_id="img_005",
    )


def _bio_chunk_dict():
    return _make_chunk_dict(
        f"{DOC_ID}_chunk_0002",
        "text",
        (
            "Ravi Todi, Managing Director, holds an MBA in Finance from IIM Ahmedabad and a "
            "B.Tech in Mechanical Engineering. He has over 20 years of experience in the "
            "infrastructure and EPC sector and has led the company's expansion into renewable "
            "energy projects across five states."
        ),
    )


def _unrelated_chunk_dict():
    return _make_chunk_dict(
        f"{DOC_ID}_chunk_0009",
        "text",
        "The company was incorporated in 1998 and is headquartered in Kolkata, West Bengal.",
    )


def _other_person_portrait_chunk_dict():
    return _make_chunk_dict(
        f"{DOC_ID}_chunk_0006",
        "image",
        "Image ID: img_006\nImage Type: Portrait Photo\nAssociated Person/Entity: Deepak Mehta (Chief Financial Officer)",
        entity_name="Deepak Mehta",
        designation="Chief Financial Officer",
        association_method="ocr_grounded_identity",
        image_id="img_006",
    )


class TestEntityLinkerCore:
    def test_generate_entity_key_is_stable_and_generic(self):
        key1 = generate_entity_key(DOC_ID, "Mr. Ravi Todi")
        key2 = generate_entity_key(DOC_ID, "ravi todi")
        assert key1 == key2
        assert key1 == f"{DOC_ID}_entity_ravi_todi"

    def test_generate_entity_key_none_for_empty_name(self):
        assert generate_entity_key(DOC_ID, "") is None
        assert generate_entity_key(DOC_ID, None) is None

    def test_chunk_mentions_entity_generic_matching(self):
        bio = _bio_chunk_dict()["content"]
        assert chunk_mentions_entity(bio, PERSON_NAME) is True
        assert chunk_mentions_entity(_unrelated_chunk_dict()["content"], PERSON_NAME) is False
        assert chunk_mentions_entity(bio, "Someone Else") is False

    def test_link_entities_across_chunks_links_portrait_to_bio_only(self):
        chunks = [_portrait_chunk_dict(), _bio_chunk_dict(), _unrelated_chunk_dict()]
        stats = link_entities_across_chunks(chunks, DOC_ID)

        assert stats["portraits_linked"] == 1
        assert stats["text_chunks_linked"] == 1

        portrait_meta = chunks[0]["metadata"]
        bio_meta = chunks[1]["metadata"]
        unrelated_meta = chunks[2]["metadata"]

        expected_key = generate_entity_key(DOC_ID, PERSON_NAME)
        assert portrait_meta["entity_id"] == expected_key
        assert portrait_meta["linked_text_chunk_ids"] == [f"{DOC_ID}_chunk_0002"]

        assert bio_meta["entity_id"] == expected_key
        assert expected_key in bio_meta["entity_ids"]

        assert "entity_id" not in unrelated_meta

    def test_link_entities_no_hardcoded_name(self):
        """Same logic must work for an arbitrary person never seen before -- no roster."""
        chunks = [
            _make_chunk_dict(
                "doc2_chunk_0001", "image", "Portrait",
                entity_name="Priya Sharma", designation="Chief Executive Officer",
                association_method="explicit_caption", image_id="img_001",
            ),
            _make_chunk_dict(
                "doc2_chunk_0002", "text",
                "Priya Sharma completed her doctorate in Chemical Engineering and has 15 years "
                "of leadership experience across three continents.",
            ),
        ]
        stats = link_entities_across_chunks(chunks, "doc2")
        assert stats["portraits_linked"] == 1
        assert chunks[0]["metadata"]["linked_text_chunk_ids"] == ["doc2_chunk_0002"]


def _chunk_from_dict(d):
    return DocumentChunk(content=d["content"], metadata=ChunkMetadata(**d["metadata"]))


class TestEndToEndPersonResolutionAndRouting:
    """
    Full path: person name in query -> resolve document's own grounded
    entity -> route a qualification question to the linked biography text
    (not the portrait), and route a photo question to the portrait (not
    unrelated images or another person's portrait).
    """

    @pytest.fixture
    def linked_chunks(self):
        raw = [_portrait_chunk_dict(), _bio_chunk_dict(), _unrelated_chunk_dict(), _other_person_portrait_chunk_dict()]
        link_entities_across_chunks(raw, DOC_ID)
        return [_chunk_from_dict(d) for d in raw]

    @pytest.fixture
    def retriever(self):
        return Retriever(config=None, query_processor=None, vector_store=None, reranker=None)

    def test_qualification_query_detects_person_biography_intent(self, retriever):
        assert retriever.detect_intent("What are Ravi Todi's qualifications?") == "person_biography"
        assert retriever.detect_intent("Tell me about his educational background") == "person_biography"

    def test_qualification_query_prioritizes_biography_text_over_portrait(self, retriever, linked_chunks):
        portrait, bio, unrelated, other_portrait = linked_chunks
        fused = [(portrait, 1.0, 1.0), (bio, 1.0, 1.0), (unrelated, 1.0, 1.0), (other_portrait, 1.0, 1.0)]

        boosted = retriever._boost_candidates(
            "what are ravi todi's qualifications", fused, intent="person_biography"
        )
        scores = {c.metadata.chunk_id: score for c, score, _ in boosted}

        assert scores[bio.metadata.chunk_id] > scores[portrait.metadata.chunk_id]
        assert scores[bio.metadata.chunk_id] > scores[unrelated.metadata.chunk_id]

    def test_portrait_query_detects_visual_intent(self, retriever):
        assert retriever.detect_intent("Show me the portrait of Ravi Todi") == "person_portrait_visual"

    def test_portrait_query_prioritizes_own_portrait_over_bio_and_other_portraits(self, retriever, linked_chunks):
        portrait, bio, unrelated, other_portrait = linked_chunks
        fused = [(portrait, 1.0, 1.0), (bio, 1.0, 1.0), (unrelated, 1.0, 1.0), (other_portrait, 1.0, 1.0)]

        boosted = retriever._boost_candidates(
            "show me the portrait of ravi todi", fused, intent="person_portrait_visual"
        )
        scores = {c.metadata.chunk_id: score for c, score, _ in boosted}

        assert scores[portrait.metadata.chunk_id] > scores[bio.metadata.chunk_id]
        # A different, specifically-named person's portrait must not outrank
        # (or match) the resolved person's own portrait.
        assert scores[portrait.metadata.chunk_id] > scores[other_portrait.metadata.chunk_id]

    def test_generic_no_hardcoded_person_also_resolves(self, retriever):
        """The routing logic itself carries no reference to this fixture's
        specific name -- verified by re-running with a wholly different name."""
        raw = [
            _make_chunk_dict(
                "doc3_chunk_0001", "image", "Portrait",
                entity_name="Amara Okafor", designation="Chief Technology Officer",
                association_method="same_card_layout", image_id="img_100",
            ),
            _make_chunk_dict(
                "doc3_chunk_0002", "text",
                "Amara Okafor holds a PhD in Computer Science and has published extensively on "
                "distributed systems before joining as CTO.",
            ),
        ]
        link_entities_across_chunks(raw, "doc3")
        chunks = [_chunk_from_dict(d) for d in raw]
        fused = [(c, 1.0, 1.0) for c in chunks]

        assert retriever.detect_intent("What is Amara Okafor's experience?") == "person_biography"
        boosted = retriever._boost_candidates(
            "what is amara okafor's experience", fused, intent="person_biography"
        )
        scores = {c.metadata.chunk_id: score for c, score, _ in boosted}
        assert scores["doc3_chunk_0002"] > scores["doc3_chunk_0001"]
