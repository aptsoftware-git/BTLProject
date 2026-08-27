"""
End-to-end verification of the generic (non-hardcoded) image grounding and
retrieval pipeline. Every scenario here is built from synthetic sample data
constructed inside the test itself -- no dependency on any real document,
company name, image ID, filename, or page number baked into the production
code. The point is to prove the pipeline works for ANY document's own
content, not just the one BTL EPC fixture other tests exercise.

Covers the five scenarios called out for verification:
  1. portrait -> person name (spatial + OCR grounding)
  2. signature -> person name (signature-block text grounding)
  3. logo -> organization (generic legal-entity-suffix extraction)
  4. descriptive visual queries (no person/logo target, e.g. "the diagram")
  5. indirect semantic image queries (no explicit visual trigger word)
"""
import sys
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))

from src.rag.image_processor import (
    HierarchicalLayoutGrounder,
    PortraitSpatialValidator,
    ImageRetrievalValidator,
    extract_generic_person_identity,
    extract_generic_organization_name,
)


def _text_el(text, l, t, r, b, page=1):
    return {
        "id": f"#/texts/{text[:6]}",
        "type": "paragraph",
        "text": text,
        "metadata": {"bbox": {"l": l, "t": t, "r": r, "b": b}, "page_number": page},
    }


# ---------------------------------------------------------------------------
# 1. Portrait -> person name
# ---------------------------------------------------------------------------

def test_portrait_grounds_to_nearby_named_person_generic():
    """A portrait-shaped image next to a titled name+designation is grounded
    to THAT person, using entirely synthetic names never seen anywhere in
    the production code."""
    bbox = {"l": 100, "t": 700, "r": 200, "b": 600}  # ~100x100pt portrait
    nearby_text = [_text_el("Mr. Alaric Voss Whole-time Director", l=210, t=705, r=350, b=690)]

    match = PortraitSpatialValidator.match_person_to_portrait_spatial(bbox, nearby_text)
    assert match is not None
    assert "Alaric Voss" in match["person_name"]
    assert match["designation"] == "Whole-time Director"

    grounded = HierarchicalLayoutGrounder.ground_image(
        image_id="#/pictures/synthetic_1",
        page_number=12,
        bbox=bbox,
        doc_elements_on_page=nearby_text,
        doc_title="Synthetic Test Holdings Limited",
    )
    assert grounded["entity_name"] and "Alaric Voss" in grounded["entity_name"]
    assert grounded["designation"] == "Whole-time Director"
    assert grounded["image_type"] == "Portrait Photo"
    assert grounded["association_method"] == "same_card_layout"
    assert grounded["retrievable"] is True


def test_portrait_not_confused_with_different_similar_person():
    """Two distinct people with a shared surname must never be conflated --
    each portrait must ground to ITS OWN adjacent name."""
    bbox_a = {"l": 100, "t": 700, "r": 200, "b": 600}
    nearby_a = [_text_el("Ms. Priya Wentworth Independent Director", l=210, t=705, r=350, b=690)]
    grounded_a = HierarchicalLayoutGrounder.ground_image(
        image_id="#/pictures/synthetic_a", page_number=12, bbox=bbox_a, doc_elements_on_page=nearby_a
    )

    bbox_b = {"l": 100, "t": 500, "r": 200, "b": 400}
    nearby_b = [_text_el("Mr. Desmond Wentworth Chairman", l=210, t=505, r=350, b=490)]
    grounded_b = HierarchicalLayoutGrounder.ground_image(
        image_id="#/pictures/synthetic_b", page_number=12, bbox=bbox_b, doc_elements_on_page=nearby_b
    )

    assert "Priya Wentworth" in grounded_a["entity_name"]
    assert "Desmond Wentworth" in grounded_b["entity_name"]
    assert grounded_a["entity_name"] != grounded_b["entity_name"]

    # A query for the bare shared surname "Wentworth" must be flagged
    # ambiguous, derived purely from these two synthetic entities.
    known_entities = [grounded_a["entity_name"], grounded_b["entity_name"]]
    target = ImageRetrievalValidator.detect_query_target("Show the photo of Wentworth", known_entities=known_entities)
    assert target["target_type"] == "ambiguous_surname"

    # But a full name resolves unambiguously to the right person.
    target2 = ImageRetrievalValidator.detect_query_target("Show the photo of Priya Wentworth", known_entities=known_entities)
    assert target2["target_type"] == "portrait"
    assert "priya" in target2["target_person"]


def test_portrait_survives_minor_ocr_spelling_error():
    """A misspelled OCR/VLM read of the name must not block matching a
    photo-of-X query when the document's own text has the correct spelling
    nearby -- fuzzy tolerance, not exact-string-only."""
    from src.rag.retriever import Retriever

    correct_name = "Marguerite Delacroix-Fenwick"
    misspelled_ocr = "Marguarite Delacroiks-Fenwick"  # plausible OCR slip
    assert Retriever.fuzzy_match_entity(misspelled_ocr, correct_name)


# ---------------------------------------------------------------------------
# 2. Signature -> person name
# ---------------------------------------------------------------------------

def test_signature_grounds_to_nearby_named_person_generic():
    grounded = HierarchicalLayoutGrounder.ground_image(
        image_id="#/pictures/synthetic_sig",
        page_number=88,
        bbox={"l": 100, "t": 200, "r": 260, "b": 170},  # wide, short -- signature-shaped
        doc_elements_on_page=[],
        ocr_text="Authorised Signatory\nMr. Tobias Ferrand Kingsley\nChief Financial Officer",
    )
    assert grounded["image_type"] == "Signature"
    assert grounded["entity_name"] and "Tobias Ferrand Kingsley" in grounded["entity_name"]
    assert grounded["designation"] == "Chief Financial Officer"
    assert grounded["association_method"] == "signature_text_grounded"
    assert grounded["retrievable"] is True


def test_signature_without_indicator_is_not_misgrounded():
    """No signature-block phrase present -> must not fabricate a signature
    association just because a name-like string is nearby."""
    grounded = HierarchicalLayoutGrounder.ground_image(
        image_id="#/pictures/synthetic_no_sig",
        page_number=88,
        bbox={"l": 100, "t": 200, "r": 260, "b": 170},
        doc_elements_on_page=[],
        ocr_text="Total consolidated revenue for the year under review",
    )
    assert grounded["image_type"] != "Signature"


# ---------------------------------------------------------------------------
# 3. Logo -> organization
# ---------------------------------------------------------------------------

def test_logo_grounds_to_organization_name_generic():
    """The organization name attached to a logo must come from real nearby
    text (a legal-entity suffix), never a hardcoded company name."""
    org_name = extract_generic_organization_name(["Northwind Aerostructures Private Limited — Annual Report"])
    assert org_name == "Northwind Aerostructures Private Limited"

    grounded = HierarchicalLayoutGrounder.ground_image(
        image_id="#/pictures/synthetic_logo",
        page_number=1,
        bbox={"l": 40, "t": 780, "r": 120, "b": 740},
        doc_elements_on_page=[_text_el("logo mark of Northwind Aerostructures Private Limited", l=0, t=790, r=200, b=780)],
        explicit_caption="Northwind Aerostructures Private Limited logo",
        doc_title="Northwind Aerostructures Private Limited",
    )
    assert grounded["image_type"] == "Logo"
    assert "Northwind Aerostructures Private Limited" in grounded["title"]
    assert grounded["entity_name"] is None  # a logo is never attributed to a person


def test_logo_falls_back_to_doc_title_when_no_suffix_found():
    """When no legal-entity-suffix text is available, fall back to the
    document's own title -- still never a hardcoded name."""
    grounded = HierarchicalLayoutGrounder.ground_image(
        image_id="#/pictures/synthetic_logo2",
        page_number=1,
        bbox={"l": 40, "t": 780, "r": 120, "b": 740},
        doc_elements_on_page=[_text_el("logo", l=0, t=790, r=200, b=780)],
        explicit_caption="Company logo",
        doc_title="Zephyrine Holdings",
    )
    assert grounded["image_type"] == "Logo"
    assert "Zephyrine Holdings" in grounded["title"]


# ---------------------------------------------------------------------------
# 4. Descriptive visual queries (no named target)
# ---------------------------------------------------------------------------

def test_descriptive_visual_query_is_general_visual_not_misread_as_person():
    """A purely descriptive visual query with no proper name anywhere in it
    must route to general_visual, not be misread as a person lookup."""
    query = "What does the architecture diagram show?"
    target = ImageRetrievalValidator.detect_query_target(query, known_entities=[])
    assert target["is_visual"] is True
    assert target["target_type"] == "general_visual"

    chart_meta = {
        "image_type": "Diagram",
        "title": "Process Flow",
        "caption": "System architecture diagram",
        "semantic_description": "A flowchart of the ingestion pipeline",
        "importance_score": "HIGH",
        "retrievable": True,
        "entity_name": None,
        "keywords": ["diagram", "architecture", "pipeline"],
        "image_path": "irrelevant.png",
    }
    from unittest.mock import patch
    with patch.object(ImageRetrievalValidator, "validate_physical_file", return_value=True):
        assert ImageRetrievalValidator.validate_image_candidate(chart_meta, query, doc_id="synthetic_doc") is True


def test_descriptive_query_with_capitalized_proper_noun_still_a_person_search():
    """A genuinely capitalized proper name mid-query IS trusted as a person
    search even with no document registry available yet (generic
    capitalization signal, not a roster)."""
    names = ImageRetrievalValidator.extract_person_names_from_query(
        "Can you show me a picture of Fabian Okonkwo please", known_entities=[]
    )
    assert any("fabian" in n and "okonkwo" in n for n in names)


# ---------------------------------------------------------------------------
# 5. Indirect semantic image queries
# ---------------------------------------------------------------------------

def test_indirect_semantic_query_matches_via_content_not_keyword():
    """A query with no explicit visual trigger word at all should still be
    treated as visual via 'look like' / content-driven language, and must
    match purely on the image's own grounded description -- never a
    hardcoded document rule."""
    query = "What does the manufacturing process look like at the plant?"
    assert ImageRetrievalValidator.is_visual_query(query) is True

    process_photo_meta = {
        "image_type": "Photo",
        "title": "Manufacturing floor",
        "caption": "Assembly line at the primary plant",
        "semantic_description": "Workers operating machinery on the manufacturing floor",
        "importance_score": "MEDIUM",
        "retrievable": True,
        "entity_name": None,
        "keywords": ["manufacturing", "plant", "assembly"],
        "image_path": "irrelevant.png",
    }
    from unittest.mock import patch
    with patch.object(ImageRetrievalValidator, "validate_physical_file", return_value=True):
        assert ImageRetrievalValidator.validate_image_candidate(process_photo_meta, query, doc_id="synthetic_doc") is True


def test_decorative_image_never_returned_for_person_query_via_incidental_text():
    """A decorative image whose keywords/description happen to textually
    mention a person's name (but which is not actually their portrait) must
    never be returned -- guards against false positives from incidental
    text overlap."""
    decorative_meta = {
        "image_type": "Decorative",
        "title": "Section divider",
        "caption": None,
        "semantic_description": "A message from our Chairman, Mr. Reginald Ashworth, opens this section",
        "importance_score": "LOW",
        "retrievable": False,
        "entity_name": None,
        "keywords": ["divider", "reginald ashworth"],
        "image_path": "irrelevant.png",
        "image_path_exists": True,
    }
    from unittest.mock import patch
    with patch.object(ImageRetrievalValidator, "validate_physical_file", return_value=True):
        result = ImageRetrievalValidator.validate_single_director_image(
            decorative_meta, {"name": "Reginald Ashworth", "variants": ["reginald ashworth"]}, doc_id="synthetic_doc"
        )
    assert result is False


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
