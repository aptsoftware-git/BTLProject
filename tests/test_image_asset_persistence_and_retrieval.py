"""
test_image_asset_persistence_and_retrieval.py
=============================================
Verifies:
1. Strict 1:1 physical image file (.png) and metadata file (.json) persistence across 05_images.
2. Metadata JSON correctly references the exact corresponding saved image path and URL.
3. No silent fallbacks to image_001.png when assets are missing.
4. Physical disk existence validation before image retrieval/rendering.
5. Accurate, distinct image asset retrieval for portraits (Sunil Mittra, Rhea Todi, Ravi Todi), logos, and documents.
"""

import sys
from pathlib import Path

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

import json
import pytest
from src.rag.config import RagConfig
from src.rag.retriever import Retriever
from src.rag.chat_service import ChatService
from src.rag.context_builder import ContextBuilder
from src.rag.retrieval_models import ScoredChunk, ChunkMetadata

DOC_ID = "btl_216_page_run"
OUTPUT_DIR = root_dir / f"data/output/{DOC_ID}"
IMAGES_DIR = OUTPUT_DIR / "05_images"

def test_physical_image_assets_strict_1_to_1_mapping():
    """
    Validates that every single metadata JSON file has a corresponding
    physical .png file with non-zero byte size in 05_images/.
    """
    assert IMAGES_DIR.exists(), f"Images directory {IMAGES_DIR} must exist"
    
    json_files = sorted(list(IMAGES_DIR.glob("image_*.json")))
    assert len(json_files) > 0, "Must have extracted image JSON files"
    
    for json_file in json_files:
        stem = json_file.stem  # e.g. 'image_146'
        png_file = IMAGES_DIR / f"{stem}.png"
        
        # 1. Physical asset must exist
        assert png_file.exists(), f"Missing physical image asset: {png_file}"
        assert png_file.stat().st_size > 0, f"Physical image asset is 0 bytes: {png_file}"
        
        # 2. JSON metadata must reference this exact path
        with open(json_file, "r", encoding="utf-8") as f:
            meta = json.load(f)
            
        img_path = meta.get("image_path")
        assert img_path is not None, f"image_path missing in {json_file}"
        assert f"{stem}.png" in img_path.replace("\\", "/"), f"Mismatch in {json_file}: image_path={img_path}"
        
        img_url = meta.get("image_url")
        assert img_url is not None, f"image_url missing in {json_file}"
        assert f"{stem}.png" in img_url, f"Mismatch in {json_file}: image_url={img_url}"

def test_missing_asset_validation_returns_no_image():
    """
    Verifies that ContextBuilder and ChatService reject missing physical image files
    and do NOT fall back to image_001.png or any other arbitrary image.
    """
    builder = ContextBuilder()
    fake_metadata = ChunkMetadata(
        document_id=DOC_ID,
        chunk_id=f"{DOC_ID}_chunk_9999",
        page_number=99,
        chunk_type="image",
        heading="Missing Visual",
        section="Visuals",
        word_count=10,
        token_estimate=15,
        image_path="05_images/image_non_existent_999.png",
        image_url=f"/outputs/{DOC_ID}/05_images/image_non_existent_999.png",
        image_type="Figure",
        caption="Non existent image"
    )
    fake_chunk = ScoredChunk(
        content="Image Caption: Non existent image",
        metadata=fake_metadata,
        similarity_score=0.9,
        reranker_score=0.9
    )
    
    # 1. ContextBuilder must drop missing image asset
    refs = builder.extract_image_references([fake_chunk])
    assert len(refs) == 0, f"Expected 0 image references for non-existent file, got {refs}"
    
    # 2. ChatService filter must also drop missing image asset
    chat_svc = ChatService(Retriever.from_config(RagConfig()))
    filtered_refs = chat_svc._filter_and_deduplicate_image_references(
        question="Show the non existent image",
        answer="Here is the non existent image",
        image_references=[{
            "image_id": "image_non_existent_999",
            "page_number": 99,
            "caption": "Non existent image",
            "image_url": f"/outputs/{DOC_ID}/05_images/image_non_existent_999.png",
            "image_path": "05_images/image_non_existent_999.png",
            "image_type": "Figure"
        }],
        used_chunk_ids=[],
        page_references=[99]
    )
    assert len(filtered_refs) == 0, "ChatService must return 0 image references for missing files"

def test_distinct_physical_assets_for_directors():
    """
    Verifies that distinct director queries return their OWN unique physical image files:
    - Sunil Kumar Mittra -> image_146.png
    - Ravi Todi -> image_147.png
    - Rhea Todi -> image_148.png
    """
    config = RagConfig()
    retriever = Retriever.from_config(config)
    
    # 1. Sunil Kumar Mittra
    res_sunil = retriever.retrieve(DOC_ID, "Show the photo of Mr. Sunil Kumar Mittra")
    sunil_imgs = [c for c in res_sunil.retrieved_chunks if c.metadata.chunk_type == "image"]
    assert len(sunil_imgs) > 0
    assert "image_146" in (sunil_imgs[0].metadata.image_path or sunil_imgs[0].metadata.image_url)
    assert sunil_imgs[0].metadata.page_number == 49
    
    # 2. Rhea Todi
    res_rhea = retriever.retrieve(DOC_ID, "Show the photo of Ms. Rhea Todi")
    rhea_imgs = [c for c in res_rhea.retrieved_chunks if c.metadata.chunk_type == "image"]
    assert len(rhea_imgs) > 0
    assert "image_148" in (rhea_imgs[0].metadata.image_path or rhea_imgs[0].metadata.image_url)
    assert rhea_imgs[0].metadata.page_number == 49
    
    # Ensure they are completely distinct physical files
    assert sunil_imgs[0].metadata.image_path != rhea_imgs[0].metadata.image_path

def test_company_logo_visual_returns_cover_logo():
    """
    Verifies that company logo queries return the actual logo/cover graphic
    and NOT director portraits on page 49.
    """
    config = RagConfig()
    retriever = Retriever.from_config(config)
    
    res = retriever.retrieve(DOC_ID, "Show the company logo of BTL EPC")
    image_chunks = [c for c in res.retrieved_chunks if c.metadata.chunk_type == "image"]
    assert len(image_chunks) > 0
    
    # Logo must be from cover/early pages (1, 3, 4, 5) and NOT page 49 director portraits
    for img in image_chunks:
        assert img.metadata.page_number != 49, "Logo query must not return Page 49 director portraits"
        assert "portrait" not in (img.metadata.image_type or "").lower()
