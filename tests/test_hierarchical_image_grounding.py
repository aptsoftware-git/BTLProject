"""
test_hierarchical_image_grounding.py
====================================
Comprehensive tests for Hierarchical Caption and Layout Grounding:
1. Complete storage of 16 structured metadata fields across all extracted image JSONs.
2. Explicit caption first priority.
3. Structured layout & card grounding for portraits (entity_name, designation, same_card_layout).
4. Section-aware spatial context for uncaptioned large visuals without fabricating captions.
5. Importance classification (HIGH, MEDIUM, LOW).
6. Retrieval gating (retrievable=False for LOW/decorative elements).
7. Negative guard against keyword fabrication.
8. End-to-end visual retrieval across portraits, logos, diagrams, and decorative suppression.
"""

import sys
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

import json
import pytest
from src.rag.config import RagConfig
from src.rag.retriever import Retriever
from src.rag.image_processor import HierarchicalLayoutGrounder, PortraitSpatialValidator
from src.rag.context_builder import ContextBuilder
from src.rag.retrieval_models import ScoredChunk, ChunkMetadata

DOC_ID = "btl_216_page_run"
OUTPUT_DIR = root_dir / f"data/output/{DOC_ID}"
IMAGES_DIR = OUTPUT_DIR / "05_images"

def test_all_16_metadata_fields_stored_in_json():
    """
    Verifies that every extracted image metadata JSON file in 05_images
    contains the complete suite of required hierarchical grounding fields.
    """
    assert IMAGES_DIR.exists(), f"Images directory {IMAGES_DIR} must exist"
    json_files = sorted(list(IMAGES_DIR.glob("image_*.json")))
    assert len(json_files) == 208, f"Expected 208 image JSONs, found {len(json_files)}"

    required_fields = [
        "image_id", "page", "bounding_box", "image_type", "explicit_caption",
        "entity_name", "designation", "section_heading", "text_before",
        "text_after", "layout_context", "semantic_description",
        "importance_score", "retrievable", "association_method", "confidence"
    ]

    for jf in json_files:
        with open(jf, "r", encoding="utf-8") as f:
            data = json.load(f)
        for field in required_fields:
            assert field in data, f"Field '{field}' missing in {jf.name}"
            
        assert data["importance_score"] in ("HIGH", "MEDIUM", "LOW")
        assert isinstance(data["retrievable"], bool)
        assert data["association_method"] in (
            "explicit_caption", "same_card_layout", "section_spatial_context",
            "surrounding_text", "vlm_semantic_description", "none"
        )
        assert 0.0 <= data["confidence"] <= 1.0

def test_explicit_caption_priority():
    """
    Verifies that when an explicit caption is present, it is prioritized
    as the highest-confidence association method.
    """
    grounded = HierarchicalLayoutGrounder.ground_image(
        image_id="img_test_caption",
        page_number=10,
        bbox={"l": 50, "r": 250, "t": 400, "b": 200},
        doc_elements_on_page=[],
        doc_title="Annual Report",
        active_section="Financial Highlights",
        explicit_caption="Figure 4.2: Revenue Trend 2020-2024"
    )

    assert grounded["association_method"] == "explicit_caption"
    assert grounded["explicit_caption"] == "Figure 4.2: Revenue Trend 2020-2024"
    assert grounded["confidence"] >= 0.95
    assert grounded["importance_score"] == "HIGH"
    assert grounded["retrievable"] is True

def test_structured_card_layout_grounding_for_board_directors():
    """
    Verifies that Page 49 Board of Directors portraits are grounded via same_card_layout
    with exact entity_name, designation, and high confidence.
    """
    # 1. Sunil Kumar Mittra (image_146.json)
    with open(IMAGES_DIR / "image_146.json", "r", encoding="utf-8") as f:
        meta_146 = json.load(f)
    assert meta_146["association_method"] == "same_card_layout"
    assert meta_146["entity_name"] == "Mr. Sunil Kumar Mittra"
    assert meta_146["designation"] == "Chairman"
    assert meta_146["importance_score"] == "HIGH"
    assert meta_146["retrievable"] is True
    assert meta_146["confidence"] >= 0.90

    # 2. Rhea Todi (image_148.json)
    with open(IMAGES_DIR / "image_148.json", "r", encoding="utf-8") as f:
        meta_148 = json.load(f)
    assert meta_148["association_method"] == "same_card_layout"
    assert meta_148["entity_name"] == "Ms. Rhea Todi"
    assert meta_148["designation"] == "Whole time Director"
    assert meta_148["importance_score"] == "HIGH"
    assert meta_148["retrievable"] is True

def test_uncaptioned_large_visual_section_spatial_context():
    """
    Verifies that uncaptioned full-page / large visuals receive section_spatial_context
    without fabricating an explicit caption.
    """
    grounded = HierarchicalLayoutGrounder.ground_image(
        image_id="img_large_visual",
        page_number=45,
        bbox={"l": 40, "r": 550, "t": 750, "b": 350},  # Large visual covering ~45% of page
        doc_elements_on_page=[
            {"text": "Project Execution Highlights", "type": "heading", "bbox": {"l": 40, "r": 400, "t": 800, "b": 770}},
            {"text": "Our engineering capabilities span across critical sectors.", "type": "paragraph", "bbox": {"l": 40, "r": 500, "t": 320, "b": 280}}
        ],
        doc_title="BTL EPC Annual Report",
        active_section="Project Execution",
        explicit_caption=None
    )

    assert grounded["association_method"] == "section_spatial_context"
    assert grounded["explicit_caption"] is None, "Must NOT fabricate explicit caption"
    assert grounded["layout_context"] in ("full_page_visual", "section_figure")
    assert grounded["importance_score"] == "HIGH"
    assert grounded["retrievable"] is True
    assert grounded["text_before"] == "Project Execution Highlights"
    assert grounded["text_after"] == "Our engineering capabilities span across critical sectors."

def test_negative_guard_against_generic_keyword_fabrication():
    """
    Verifies that unassociated landscape / background images are not given
    fabricated person names or designations based on generic nearby text.
    """
    grounded = HierarchicalLayoutGrounder.ground_image(
        image_id="img_unassociated_landscape",
        page_number=37,
        bbox={"l": 40, "r": 550, "t": 250, "b": 100},  # Wide banner (aspect ratio 3.4 > 1.28)
        doc_elements_on_page=[
            {"text": "Ms. Rhea Todi was present at the site opening ceremony.", "type": "paragraph", "bbox": {"l": 40, "r": 500, "t": 80, "b": 50}}
        ],
        doc_title="BTL EPC Annual Report",
        active_section="Corporate Overview",
        explicit_caption=None
    )

    # Portrait validator must reject banner geometry
    assert grounded["entity_name"] is None, "Must NOT assign person to banner/landscape photo"
    assert grounded["designation"] is None
    assert grounded["association_method"] != "same_card_layout"

def test_retrieval_gating_suppresses_decorative_elements():
    """
    Verifies that decorative elements, tiny icons, and line separators are marked
    retrievable=False, importance_score=LOW, and excluded from visual retrieval.
    """
    grounded_icon = HierarchicalLayoutGrounder.ground_image(
        image_id="img_tiny_bullet_icon",
        page_number=12,
        bbox={"l": 50, "r": 70, "t": 300, "b": 280},  # 20x20 pt tiny icon
        doc_elements_on_page=[],
        doc_title="BTL EPC Annual Report",
        active_section="General"
    )
    assert grounded_icon["importance_score"] == "LOW"
    assert grounded_icon["retrievable"] is False
    assert grounded_icon["image_type"] == "Decorative"

    # Verify Retriever filters out non-retrievable chunks
    config = RagConfig()
    retriever = Retriever.from_config(config)
    res = retriever.retrieve(DOC_ID, "Show images and diagrams")
    for c in res.retrieved_chunks:
        if c.metadata.chunk_type == "image":
            assert c.metadata.retrievable is not False, "Retrieved chunk must be retrievable"
            assert c.metadata.importance_score != "LOW", "Retrieved chunk must not be LOW importance"
            assert (c.metadata.image_type or "").lower() != "decorative", "Must not retrieve decorative images"

def test_end_to_end_portrait_and_logo_visual_retrieval():
    """
    Verifies end-to-end retrieval for:
    1. Portrait query: returns verified Page 49 director portrait.
    2. Logo query: returns cover/emblem logo.
    """
    config = RagConfig()
    retriever = Retriever.from_config(config)

    # 1. Portrait: Sunil Kumar Mittra
    res_sunil = retriever.retrieve(DOC_ID, "Show the photo of Mr. Sunil Kumar Mittra")
    sunil_imgs = [c for c in res_sunil.retrieved_chunks if c.metadata.chunk_type == "image"]
    assert len(sunil_imgs) > 0
    assert sunil_imgs[0].metadata.page_number == 49
    assert "image_146" in (sunil_imgs[0].metadata.image_path or sunil_imgs[0].metadata.image_url)
    assert sunil_imgs[0].metadata.entity_name == "Mr. Sunil Kumar Mittra"
    assert sunil_imgs[0].metadata.association_method == "same_card_layout"

    # 2. Logo: Company logo
    res_logo = retriever.retrieve(DOC_ID, "Show the company logo of BTL EPC")
    logo_imgs = [c for c in res_logo.retrieved_chunks if c.metadata.chunk_type == "image"]
    assert len(logo_imgs) > 0
    for img in logo_imgs:
        assert img.metadata.page_number != 49, "Logo must not return Page 49 director portraits"
        assert "portrait" not in (img.metadata.image_type or "").lower()
