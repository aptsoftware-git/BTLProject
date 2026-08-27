"""
test_unified_image_retrieval.py
=================================
Regression tests for the unified image retrieval architecture:

    PNG -> JSON metadata -> image registry -> ChromaDB/BM25 -> retriever
    -> LLM context -> API -> chat/gallery UI

connected end to end by one canonical image_id.

Every entity used below (Kavita Nair, Arjun Bose, ...) is a synthetic name
NOT present in PortraitSpatialValidator.KNOWN_DIRECTORS or any other
hardcoded roster -- these tests exist specifically to prove the retrieval
path works generically, from an image's own JSON metadata, rather than
depending on a fixed name list.
"""

import json
import shutil
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.config import ROOT_DIR
from src.rag.config import RagConfig
from src.rag.chunk_schema import DocumentChunk, ChunkMetadata
from src.rag.index_manager import IndexManager
from src.rag.retriever import Retriever
from src.rag.chat_service import ChatService
from backend.app import app
import backend.routes as routes
from fastapi.testclient import TestClient

TEMP_DB_DIR = ROOT_DIR / "data" / "output" / "temp_chromadb_unified_image_test"
DOC_ID = "test_unified_image_doc"


@pytest.fixture(autouse=True)
def cleanup_temp_db():
    if TEMP_DB_DIR.exists():
        shutil.rmtree(TEMP_DB_DIR, ignore_errors=True)
    yield
    if TEMP_DB_DIR.exists():
        shutil.rmtree(TEMP_DB_DIR, ignore_errors=True)


def _image_chunk(image_id, entity_name=None, designation=None, image_type="Photo",
                  semantic_description="", keywords=None, retrievable=True,
                  importance_score="MEDIUM", page=60, caption=None):
    return DocumentChunk(
        content=(
            f"Image ID: {image_id}\nImage Type: {image_type}\nPage: {page}\n"
            + (f"Entity: {entity_name} ({designation})\n" if entity_name else "")
            + f"Semantic Description: {semantic_description}\n"
            + f"Keywords: {', '.join(keywords or [])}"
        ),
        metadata=ChunkMetadata(
            chunk_id=f"{DOC_ID}_chunk_{image_id}",
            document_id=DOC_ID,
            page_number=page,
            chunk_type="image",
            heading="Visual Assets",
            section="Visual Assets",
            word_count=20,
            token_estimate=25,
            image_id=image_id,
            image_path=f"05_images/{image_id}.png",
            image_url=f"/outputs/{DOC_ID}/05_images/{image_id}.png",
            image_type=image_type,
            entity_name=entity_name,
            designation=designation,
            caption=caption or (f"Portrait of {entity_name}" if entity_name else semantic_description[:60]),
            semantic_description=semantic_description,
            keywords=keywords or [],
            retrievable=retrievable,
            importance_score=importance_score,
            association_method="explicit_caption" if entity_name else "vlm_semantic_description",
            association_confidence=0.9,
            confidence=0.9,
        ),
    )


@pytest.fixture
def indexed_gallery(tmp_path):
    """Indexes a synthetic set of image chunks (generic, non-hardcoded
    entities) and mirrors them as real 05_images/image_XXX.png+json pairs
    on disk, so the same canonical image_id can be traced from the vector
    index all the way to the physical gallery asset."""
    chunks = [
        DocumentChunk(
            content="General overview of company operations and project delivery timelines.",
            metadata=ChunkMetadata(
                chunk_id=f"{DOC_ID}_chunk_text0", document_id=DOC_ID, page_number=5,
                chunk_type="text", heading="Overview", section="Overview",
                word_count=10, token_estimate=12,
            ),
        ),
        _image_chunk(
            "image_201", entity_name="Ms. Kavita Nair", designation="Regional Manager",
            image_type="Portrait Photo", importance_score="HIGH",
            semantic_description="Portrait photograph of Ms. Kavita Nair, Regional Manager, at the Ranchi site office.",
            keywords=["portrait", "kavita nair", "regional manager"], page=60,
        ),
        _image_chunk(
            "image_202", entity_name="Mr. Arjun Bose", designation="Site Engineer",
            image_type="Portrait Photo", importance_score="HIGH",
            semantic_description="Portrait photograph of Mr. Arjun Bose, Site Engineer.",
            keywords=["portrait", "arjun bose", "site engineer"], page=61,
        ),
        _image_chunk(
            "image_203", image_type="Decorative", importance_score="LOW", retrievable=False,
            semantic_description="Thin decorative divider line.", keywords=["divider"], page=62,
        ),
        _image_chunk(
            "image_204", image_type="Logo", importance_score="HIGH",
            semantic_description="Official company logo mark.",
            keywords=["logo", "company logo", "brand"], page=1,
        ),
        _image_chunk(
            "image_205", image_type="Photo", importance_score="MEDIUM",
            semantic_description="Aerial view of the 132kV substation construction site at Deoghar.",
            keywords=["substation", "construction", "site", "deoghar", "132kv"], page=90,
        ),
    ]

    config = RagConfig(
        embedding_model="BAAI/bge-small-en-v1.5",
        embedding_device="cpu",
        reranker_model="cross-encoder/ms-marco-MiniLM-L-6-v2",
        reranker_device="cpu",
        chroma_db_dir=TEMP_DB_DIR,
        collection_prefix="test_unified_img_",
    )
    IndexManager.from_config(config).index_document(DOC_ID, chunks)

    output_dir = TEMP_DB_DIR.parent / "output" / DOC_ID
    images_dir = output_dir / "05_images"
    images_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "document_chunks.json").write_text(
        json.dumps({
            "document_id": DOC_ID, "file_name": "test.pdf",
            "chunks": [c.model_dump() if hasattr(c, "model_dump") else c.dict() for c in chunks],
        }),
        encoding="utf-8",
    )

    # Mirror every image chunk as a real PNG+JSON pair in 05_images, keyed
    # by the SAME image_id used in the vector index.
    for c in chunks:
        if c.metadata.chunk_type != "image":
            continue
        seq = c.metadata.image_id
        (images_dir / f"{seq}.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")
        (images_dir / f"{seq}.json").write_text(json.dumps({
            "image_id": seq,
            "image_url": c.metadata.image_url,
            "page": c.metadata.page_number,
            "image_type": c.metadata.image_type,
            "semantic_description": c.metadata.semantic_description,
            "entity_name": c.metadata.entity_name,
            "designation": c.metadata.designation,
            "caption": c.metadata.caption,
            "keywords": c.metadata.keywords,
            "retrievable": c.metadata.retrievable,
        }), encoding="utf-8")

    yield {"config": config, "output_dir": output_dir}

    shutil.rmtree(output_dir, ignore_errors=True)


def _image_ids(retrieval_output):
    return [
        c.metadata.image_id
        for c in retrieval_output.retrieved_chunks
        if c.metadata.chunk_type == "image"
    ]


def test_generic_single_person_query_resolves_correct_image_id(indexed_gallery):
    retriever = Retriever.from_config(indexed_gallery["config"])
    result = retriever.retrieve(DOC_ID, "Show me the photo of Kavita Nair")
    ids = _image_ids(result)
    assert "image_201" in ids
    assert "image_202" not in ids


def test_generic_multi_person_query_returns_both_images(indexed_gallery):
    retriever = Retriever.from_config(indexed_gallery["config"])
    result = retriever.retrieve(DOC_ID, "Show photos of Kavita Nair and Arjun Bose")
    ids = set(_image_ids(result))
    assert "image_201" in ids
    assert "image_202" in ids


def test_logo_query_returns_logo_not_portraits(indexed_gallery):
    retriever = Retriever.from_config(indexed_gallery["config"])
    result = retriever.retrieve(DOC_ID, "Show the company logo")
    ids = _image_ids(result)
    assert "image_204" in ids
    assert "image_201" not in ids
    assert "image_202" not in ids


def test_decorative_image_never_surfaces_for_visual_query(indexed_gallery):
    retriever = Retriever.from_config(indexed_gallery["config"])
    result = retriever.retrieve(DOC_ID, "Show me the images in this document")
    ids = _image_ids(result)
    assert "image_203" not in ids


def test_semantic_description_based_query_returns_correct_image(indexed_gallery):
    """
    No entity/name is involved here at all -- this image is found purely
    through its semantic_description / keywords, proving the unified
    architecture does not depend solely on entity/name matching.
    """
    retriever = Retriever.from_config(indexed_gallery["config"])
    result = retriever.retrieve(DOC_ID, "Show the substation construction site image at Deoghar")
    ids = _image_ids(result)
    assert "image_205" in ids


def test_generic_entity_match_survives_top_k_and_low_text_similarity(indexed_gallery):
    """
    The query text barely overlaps the chunk's raw content (phrased very
    differently from the indexed text), yet the entity/metadata-match path
    must still surface the image -- valid image results are not rejected
    by generic text-only confidence/fallback guards.
    """
    retriever = Retriever.from_config(indexed_gallery["config"])
    result = retriever.retrieve(DOC_ID, "who is arjun bose")
    ids = _image_ids(result)
    assert "image_202" in ids


def test_canonical_image_id_connects_retriever_to_gallery_api(indexed_gallery):
    """
    Full chain verification: PNG/JSON -> indexing -> query -> image_id ->
    API. The image_id returned by the retriever for a person query must be
    the exact same image_id the gallery API resolves back to a physical
    PNG for that same document.
    """
    retriever = Retriever.from_config(indexed_gallery["config"])
    result = retriever.retrieve(DOC_ID, "Show me the photo of Kavita Nair")
    retrieved_ids = set(_image_ids(result))
    assert "image_201" in retrieved_ids

    output_dir = indexed_gallery["output_dir"]
    orig_get_job, orig_get_job_dir = routes.get_job, routes.get_job_dir
    routes.get_job = lambda jid: {"job_id": jid, "status": "completed"} if jid == DOC_ID else None
    routes.get_job_dir = lambda jid: output_dir
    try:
        client = TestClient(app)
        gallery = client.get(f"/api/documents/{DOC_ID}/images").json()
    finally:
        routes.get_job, routes.get_job_dir = orig_get_job, orig_get_job_dir

    gallery_ids = {img["image_id"] for img in gallery["images"]}
    assert "image_201" in gallery_ids
    assert retrieved_ids & gallery_ids, "retriever and gallery API must resolve to the same canonical image_id"


# ---------------------------------------------------------------------------
# Indirect / semantic-only queries (no visual trigger word at all) must
# still surface an image, as long as ContextBuilder's own relevance ranking
# already selected that image's chunk into the LLM's context.
# ---------------------------------------------------------------------------

_MINIMAL_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0"
    b"\x00\x00\x03\x01\x01\x00\x18\xdd\x8d\xb0\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.fixture(autouse=True)
def _indirect_query_fake_image_file():
    # validate_physical_file requires a real backing file on disk (no
    # test/mock substring bypass) -- create the one _fake_image_ref() below
    # claims, so these tests exercise real, non-bypassed validation.
    real_path = ROOT_DIR / "data" / "output" / "test_indirect_doc" / "05_images" / "image_301.png"
    real_path.parent.mkdir(parents=True, exist_ok=True)
    real_path.write_bytes(_MINIMAL_PNG_BYTES)
    yield
    if real_path.exists():
        real_path.unlink()


def _make_chat_service():
    # retriever/ollama are never touched by _filter_and_deduplicate_image_references
    return ChatService(retriever=MagicMock(), ollama_client=MagicMock())


def _fake_image_ref(chunk_id, image_type="Photo", importance_score="MEDIUM", entity_name=None):
    return {
        "image_id": f"id_{chunk_id}",
        "chunk_id": chunk_id,
        "page_number": 60,
        "image_type": image_type,
        "importance_score": importance_score,
        "retrievable": True,
        "entity_name": entity_name,
        "designation": None,
        "caption": "Aerial view of the substation construction site.",
        "semantic_description": "Aerial view of the substation construction site at Deoghar.",
        "keywords": ["substation", "construction", "site"],
        "image_url": "/outputs/test_indirect_doc/05_images/image_301.png",
        "image_path": "05_images/image_301.png",
        "document_id": "test_indirect_doc",
    }


def test_indirect_keyword_free_query_returns_image_when_chunk_was_used_in_context():
    service = _make_chat_service()
    img = _fake_image_ref("c_site_1")
    result = service._filter_and_deduplicate_image_references(
        question="Tell me about the substation construction progress at Deoghar",  # no "photo"/"image"/"picture"/etc.
        answer="The substation construction at Deoghar is progressing well.",
        image_references=[img],
        used_chunk_ids=["c_site_1"],  # ContextBuilder actually selected this chunk into the LLM's context
        page_references=[60],
        document_id="test_indirect_doc",
    )
    assert len(result) == 1
    assert result[0]["chunk_id"] == "c_site_1"


def test_indirect_keyword_free_query_suppresses_image_not_used_in_context():
    """The image exists in image_references (e.g. retrieved as a weak/incidental
    candidate) but was NOT selected into the LLM's actual context -- must not
    be shown, since a purely indirect query gives no other relevance signal."""
    service = _make_chat_service()
    img = _fake_image_ref("c_site_2")
    result = service._filter_and_deduplicate_image_references(
        question="Tell me about the substation construction progress at Deoghar",
        answer="The substation construction at Deoghar is progressing well.",
        image_references=[img],
        used_chunk_ids=[],  # not actually used in context
        page_references=[60],
        document_id="test_indirect_doc",
    )
    assert result == []


def test_indirect_query_still_rejects_decorative_low_even_if_used_in_context():
    service = _make_chat_service()
    img = _fake_image_ref("c_deco", image_type="Decorative", importance_score="LOW")
    result = service._filter_and_deduplicate_image_references(
        question="Tell me about the substation construction progress",
        answer="The substation construction is progressing well.",
        image_references=[img],
        used_chunk_ids=["c_deco"],
        page_references=[60],
        document_id="test_indirect_doc",
    )
    assert result == []


def test_direct_visual_query_still_works_unchanged():
    """Direct name queries are unaffected by the used_chunk_ids relaxation --
    they still go through full entity/target validation."""
    service = _make_chat_service()
    img = _fake_image_ref("c_kavita", image_type="Portrait Photo", entity_name="Ms. Kavita Nair")
    img["caption"] = "Portrait of Ms. Kavita Nair"
    img["semantic_description"] = "Portrait photograph of Ms. Kavita Nair, Regional Manager."
    result = service._filter_and_deduplicate_image_references(
        question="Show me the photo of Kavita Nair",
        answer="Here is the requested photo.",
        image_references=[img],
        used_chunk_ids=[],  # not used in context -- irrelevant for a direct visual query
        page_references=[60],
        document_id="test_indirect_doc",
    )
    assert len(result) == 1
    assert result[0]["chunk_id"] == "c_kavita"


def test_ambiguous_surname_query_still_rejected_even_if_chunk_used_in_context():
    # Ambiguity is derived purely from THIS document's own registered
    # entities (never a fixed surname list) -- so the fixture must itself
    # contain two distinct people sharing the surname for "Todi" to be
    # genuinely ambiguous here.
    service = _make_chat_service()
    img_a = _fake_image_ref("c_todi_a", image_type="Portrait Photo", entity_name="Mr. Ravi Todi")
    img_b = _fake_image_ref("c_todi_b", image_type="Portrait Photo", entity_name="Ms. Rhea Todi")
    result = service._filter_and_deduplicate_image_references(
        question="Show me the photo of Todi",  # surname only -- ambiguous
        answer="Here is a photo.",
        image_references=[img_a, img_b],
        used_chunk_ids=["c_todi_a", "c_todi_b"],
        page_references=[60],
        document_id="test_indirect_doc",
    )
    assert result == []


def test_bare_surname_query_not_ambiguous_when_document_has_only_one_match():
    """A bare surname that resolves to exactly ONE person in this document's
    own registry is a normal, unambiguous portrait lookup -- ambiguity must
    never be assumed from the surname text alone."""
    service = _make_chat_service()
    img = _fake_image_ref("c_todi_solo", image_type="Portrait Photo", entity_name="Mr. Ravi Todi")
    result = service._filter_and_deduplicate_image_references(
        question="Show me the photo of Todi",
        answer="Here is a photo.",
        image_references=[img],
        used_chunk_ids=["c_todi_solo"],
        page_references=[60],
        document_id="test_indirect_doc",
    )
    assert len(result) == 1
    assert result[0]["chunk_id"] == "c_todi_solo"


def test_keyword_free_query_with_no_relevant_image_returns_nothing():
    """Sanity: this relaxation must not turn into 'always attach some image' --
    with no used_chunk_ids overlap at all, nothing is returned."""
    service = _make_chat_service()
    img = _fake_image_ref("c_unrelated")
    result = service._filter_and_deduplicate_image_references(
        question="What was the audited profit after tax for FY24?",
        answer="The audited profit after tax for FY24 was 60 crore.",
        image_references=[img],
        used_chunk_ids=["some_other_text_chunk_id"],
        page_references=[45],
        document_id="test_indirect_doc",
    )
    assert result == []
