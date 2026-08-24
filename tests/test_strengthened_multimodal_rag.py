import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock

from src.config import ROOT_DIR
from src.rag.config import RagConfig
from src.rag.query_processor import QueryProcessor, QueryCategory, QueryClassification
from src.rag.retriever import Retriever
from src.rag.prompt_builder import PromptBuilder
from src.rag.context_builder import ContextBuilder
from src.rag.chat_service import ChatService
from src.rag.retrieval_models import ScoredChunk
from src.rag.response_models import GroundedAnswerResponse
from src.rag.chunk_schema import DocumentChunk, ChunkMetadata

DOC_ID = "btl_216_page_run"

# ==============================================================================
# 1. QUERY UNDERSTANDING & ROUTING TESTS
# ==============================================================================

def test_query_classification_routing():
    qp = QueryProcessor()
    
    # 1. Factual / Entity Query
    clf_factual = qp.classify_query("What is the registered office address and CIN of BTL EPC LIMITED?")
    assert clf_factual.primary_category == QueryCategory.FACTUAL_ENTITY
    assert clf_factual.has_exact_entity_target is True
    assert "btl epc limited" in [e.lower() for e in clf_factual.target_entities] or "cin" in [e.lower() for e in clf_factual.target_entities]
    
    # 2. Table Query
    clf_table = qp.classify_query("Show the table of financial performance metrics for FY24")
    assert clf_table.primary_category == QueryCategory.TABLE
    assert clf_table.has_explicit_table_request is True
    
    # 3. Visual - Logo Query
    clf_logo = qp.classify_query("Show the company logo")
    assert clf_logo.primary_category == QueryCategory.IMAGE_VISUAL
    assert clf_logo.has_explicit_visual_request is True
    assert clf_logo.target_visual_type == "logo"
    
    # 4. Visual - Person Portrait Query
    clf_portrait = qp.classify_query("Show the photo of Mr. Sunil Kumar Mittra")
    assert clf_portrait.primary_category == QueryCategory.IMAGE_VISUAL
    assert clf_portrait.has_explicit_visual_request is True
    assert clf_portrait.target_visual_type == "portrait"
    
    # 5. Visual - Diagram / Flowchart Query
    clf_diagram = qp.classify_query("Show the architecture diagram and plant layout figure")
    assert clf_diagram.primary_category == QueryCategory.IMAGE_VISUAL
    assert clf_diagram.has_explicit_visual_request is True
    assert clf_diagram.target_visual_type == "diagram"
    
    # 6. Summary Query
    clf_summary = qp.classify_query("Provide a comprehensive executive summary of all business divisions")
    assert clf_summary.primary_category == QueryCategory.SUMMARY
    assert clf_summary.top_k_final >= 10
    
    # 7. Mixed Query (Directors + Photos)
    clf_mixed = qp.classify_query("List all members of the Board of Directors along with their photos")
    assert clf_mixed.primary_category == QueryCategory.MIXED
    assert clf_mixed.has_explicit_visual_request is True

# ==============================================================================
# 2. DOCUMENT LOADING & PATH RESOLUTION TESTS
# ==============================================================================

def test_document_path_resolution_and_chunks_loading():
    config = RagConfig(
        embedding_model="BAAI/bge-small-en-v1.5",
        reranker_model="cross-encoder/ms-marco-MiniLM-L-6-v2",
    )
    retriever = Retriever.from_config(config)
    
    output_dir = retriever._resolve_output_dir(DOC_ID)
    assert output_dir.exists(), f"Output directory for {DOC_ID} must exist at {output_dir}"
    
    chunks = retriever._load_document_chunks(DOC_ID)
    assert len(chunks) > 0, "Should load document chunks for btl_216_page_run"
    
    # Verify presence of text, table, and image chunks
    chunk_types = {c.metadata.chunk_type for c in chunks}
    assert "text" in chunk_types
    assert "table" in chunk_types or any(c.metadata.table_id for c in chunks)
    assert "image" in chunk_types or any(c.metadata.image_id for c in chunks)

# ==============================================================================
# 3. FACTUAL, COMPANY DETAILS & DIRECTORS RETRIEVAL
# ==============================================================================

def test_company_registered_office_and_cin_retrieval():
    config = RagConfig()
    retriever = Retriever.from_config(config)
    
    query = "What is the registered office address and CIN of BTL EPC LIMITED?"
    res = retriever.retrieve(DOC_ID, query)
    
    assert len(res.retrieved_chunks) > 0
    top_chunks_text = "\n".join(c.content for c in res.retrieved_chunks[:5]).lower()
    
    # Must retrieve Jessore Road and CIN number
    assert "jessore road" in top_chunks_text or "kolkata" in top_chunks_text
    assert "u29100wb1992plc054541" in top_chunks_text or "cin" in top_chunks_text
    
    # Page 50 or Page 89 should be in the retrieved chunk pages
    retrieved_pages = [c.metadata.page_number for c in res.retrieved_chunks]
    assert 50 in retrieved_pages or 89 in retrieved_pages or 66 in retrieved_pages

def test_statutory_auditors_and_board_retrieval():
    config = RagConfig()
    retriever = Retriever.from_config(config)
    
    # Statutory Auditors
    res_auditor = retriever.retrieve(DOC_ID, "Who are the statutory auditors of BTL EPC LIMITED?")
    assert len(res_auditor.retrieved_chunks) > 0
    auditor_text = "\n".join(c.content for c in res_auditor.retrieved_chunks[:5]).lower()
    assert "jkvs" in auditor_text or "chartered accountants" in auditor_text or "statutory auditors" in auditor_text
    
    # Board of Directors
    res_board = retriever.retrieve(DOC_ID, "Who are the members of the Board of Directors?")
    assert len(res_board.retrieved_chunks) > 0
    board_pages = [c.metadata.page_number for c in res_board.retrieved_chunks]
    assert 49 in board_pages or 50 in board_pages

# ==============================================================================
# 4. EXACT TABLE RETRIEVAL & STRUCTURAL PRESERVATION
# ==============================================================================

def test_exact_table_retrieval():
    config = RagConfig()
    retriever = Retriever.from_config(config)
    
    query = "Show the table of financial summary and metrics"
    res = retriever.retrieve(DOC_ID, query)
    
    # Should retrieve table chunks
    table_chunks = [c for c in res.retrieved_chunks if c.metadata.chunk_type == "table" or "|" in c.content]
    assert len(table_chunks) > 0
    
    # Verify markdown table structure is intact
    top_table = table_chunks[0].content
    assert "|" in top_table
    assert "\n|---" in top_table or "\n| ---" in top_table or "---|" in top_table

# ==============================================================================
# 5. COMPANY LOGO VISUAL RETRIEVAL
# ==============================================================================

def test_company_logo_visual_retrieval():
    config = RagConfig()
    retriever = Retriever.from_config(config)
    
    query = "Show the company logo of BTL EPC"
    res = retriever.retrieve(DOC_ID, query)
    
    image_chunks = [c for c in res.retrieved_chunks if c.metadata.chunk_type == "image"]
    assert len(image_chunks) > 0
    
    # Logo should NOT be a page 49 portrait photo
    for img in image_chunks:
        assert img.metadata.page_number != 49, "Logo retrieval must not return page 49 person portraits"

# ==============================================================================
# 6. VERIFIED PERSON-TO-IMAGE PORTRAIT ASSOCIATION
# ==============================================================================

def test_sunil_mittra_portrait_verified_association():
    config = RagConfig()
    retriever = Retriever.from_config(config)
    
    query = "Show the photo of Mr. Sunil Kumar Mittra"
    res = retriever.retrieve(DOC_ID, query)
    
    image_chunks = [c for c in res.retrieved_chunks if c.metadata.chunk_type == "image"]
    assert len(image_chunks) > 0
    
    # Verify Sunil Kumar Mittra's portrait on page 49
    sunil_img = image_chunks[0]
    assert sunil_img.metadata.page_number == 49
    caption = (getattr(sunil_img.metadata, "caption", None) or sunil_img.metadata.heading or "").lower()
    vlm = (getattr(sunil_img.metadata, "semantic_description", None) or "").lower()
    ocr = (getattr(sunil_img.metadata, "ocr_text", None) or "").lower()
    
    assert "sunil" in caption or "mittra" in caption or "sunil" in vlm or "sunil" in ocr

def test_board_collection_photos_retrieval():
    config = RagConfig()
    retriever = Retriever.from_config(config)
    
    query = "List all directors along with their photos"
    res = retriever.retrieve(DOC_ID, query)
    
    image_chunks = [c for c in res.retrieved_chunks if c.metadata.chunk_type == "image"]
    # All 9 portraits reside on page 49
    p49_portraits = [c for c in image_chunks if c.metadata.page_number == 49]
    assert len(p49_portraits) >= 5

class FakeOllamaClient:
    def __init__(self, response_text="I could not find this information in the uploaded document."):
        self.response_text = response_text
        self.last_prompt = None
        self.last_system = None
    
    def generate(self, model, prompt, system=None, timeout=300):
        self.last_prompt = prompt
        self.last_system = system
        return self.response_text

# ==============================================================================
# 7. UNSUPPORTED QUESTIONS & FALLBACK CONTROL
# ==============================================================================

def test_unsupported_query_strict_grounding_fallback():
    fake_client = FakeOllamaClient("I could not find this information in the uploaded document.")
    chat_service = ChatService(ollama_client=fake_client)
    
    # Unrelated question not present in the document
    unsupported_query = "What was the mission launch timeline of the James Webb Space Telescope in 2021?"
    
    resp = chat_service.answer_question(DOC_ID, unsupported_query)
    
    assert "could not find this information in the uploaded document" in resp.answer.lower()
    assert len(resp.image_references) == 0, "Must not attach images to unsupported queries"
    assert resp.metadata.get("grounding_status") == "unsupported_query" or len(resp.used_chunk_ids) == 0

# ==============================================================================
# 8. PROMPT BUILDER STRICT CITATIONS AND RULES
# ==============================================================================

def test_prompt_builder_strict_grounding_rules():
    pb = PromptBuilder()
    context = "=== SECTION CONTEXT: CORPORATE DIRECTORY [Page 50] ===\nRegistered Office: 2, Jessore Road, Kolkata 700028\n=== END SECTION CONTEXT ==="
    question = "Where is the registered office located?"
    
    prompt_dict = pb.build_prompt(context, question)
    
    assert "STRICT" in prompt_dict["system"].upper() or "ONLY USING" in prompt_dict["system"].upper()
    assert "[Page 50]" in prompt_dict["prompt"]
    assert "2, Jessore Road" in prompt_dict["prompt"]
    assert "Question: Where is the registered office located?" in prompt_dict["prompt"]
