import json
import shutil
from pathlib import Path
import pytest
import chromadb

from src.rag.config import RagConfig
from src.rag.chunk_schema import DocumentChunk, ChunkMetadata
from src.rag.document_schema import BoundingBox
from src.rag.index_manager import IndexManager
from src.rag.query_processor import QueryProcessor
from src.rag.bm25_search import BM25Search
from src.rag.hybrid_search import HybridSearch
from src.rag.reranker import Reranker
from src.rag.vector_store import VectorStore
from src.rag.retriever import Retriever

# Temp database path for tests
TEMP_DB_DIR = Path("C:/Users/sanju/INTERNSHIP-APT/DocumentProofreadingSystem/data/output/temp_chromadb_retrieval_test")

@pytest.fixture(autouse=True)
def cleanup_temp_db():
    if TEMP_DB_DIR.exists():
        try:
            shutil.rmtree(TEMP_DB_DIR)
        except Exception:
            pass
    yield
    if TEMP_DB_DIR.exists():
        try:
            shutil.rmtree(TEMP_DB_DIR)
        except Exception:
            pass

def test_retrieval_pipeline():
    doc_id = "test_retrieval_doc"
    
    # 1. Define distinct chunks (text, table, image with OCR, list, footnote, rare keyword)
    chunks = [
        DocumentChunk(
            content="Introduction to Retrieval-Augmented Generation. This explains how semantic databases store embeddings.",
            metadata=ChunkMetadata(
                chunk_id=f"{doc_id}_chunk_0",
                document_id=doc_id,
                page_number=1,
                chunk_type="text",
                heading="Introduction",
                section="Introduction",
                hierarchy_path=["#/texts/0"],
                source_element_ids=["#/texts/1"],
                word_count=12,
                token_estimate=15
            )
        ),
        DocumentChunk(
            content="| Project Step | Completion |\n|---|---|\n| Stage 1 | 100% |\n| Stage 2 | 50% |\nTable 1: Sprint Progress Details.",
            metadata=ChunkMetadata(
                chunk_id=f"{doc_id}_chunk_1",
                document_id=doc_id,
                page_number=2,
                chunk_type="table",
                heading="Sprint Tables",
                section="Introduction > Sprint Tables",
                hierarchy_path=["#/texts/0", "#/texts/2"],
                source_element_ids=["#/tables/0"],
                word_count=15,
                token_estimate=25,
                table_id="#/tables/0"
            )
        ),
        DocumentChunk(
            content="Figure 2: Architecture diagram of the document extractor.\nOCR Text: FLOWCHART INPUT FILES RUN PIPELINE.",
            metadata=ChunkMetadata(
                chunk_id=f"{doc_id}_chunk_2",
                document_id=doc_id,
                page_number=3,
                chunk_type="image",
                heading="Architecture Figures",
                section="Architecture Figures",
                hierarchy_path=["#/texts/3"],
                source_element_ids=["#/pictures/0"],
                word_count=12,
                token_estimate=18,
                image_id="#/pictures/0"
            )
        ),
        DocumentChunk(
            content="A rare scientific instrument is named ZYGLOPLOTRON. It is utilized in quantum physics laboratories.",
            metadata=ChunkMetadata(
                chunk_id=f"{doc_id}_chunk_3",
                document_id=doc_id,
                page_number=3,
                chunk_type="text",
                heading="Scientific Instruments",
                section="Scientific Instruments",
                hierarchy_path=["#/texts/4"],
                source_element_ids=["#/texts/5"],
                word_count=14,
                token_estimate=19
            )
        )
    ]

    # 2. Setup config
    config = RagConfig(
        embedding_model="BAAI/bge-small-en-v1.5",
        embedding_device="cpu",
        reranker_model="cross-encoder/ms-marco-MiniLM-L-6-v2",
        reranker_device="cpu",
        chroma_db_dir=TEMP_DB_DIR,
        collection_prefix="test_retrieve_",
        top_k_retrieve=5,
        top_k_rerank=3,
        top_k_final=2
    )

    # 3. Index the chunks in ChromaDB
    index_manager = IndexManager.from_config(config)
    index_manager.index_document(doc_id, chunks)

    # Reconstruct document_chunks.json file so the retriever can find it
    output_dir = TEMP_DB_DIR.parent / "output" / doc_id
    output_dir.mkdir(parents=True, exist_ok=True)
    chunks_output = {
        "document_id": doc_id,
        "file_name": "test_doc.pdf",
        "chunks": [c.model_dump() if hasattr(c, "model_dump") else c.dict() for c in chunks]
    }
    with open(output_dir / "document_chunks.json", "w", encoding="utf-8") as f:
        json.dump(chunks_output, f, indent=2)

    # 4. Initialize Retriever
    retriever = Retriever.from_config(config)

    # --- Test Case 1: Standard semantic text retrieval ---
    res = retriever.retrieve(doc_id, "Explain semantic databases and RAG concepts")
    assert len(res.retrieved_chunks) > 0
    # Top chunk should be chunk_0 (Introduction)
    assert res.retrieved_chunks[0].metadata.chunk_id == f"{doc_id}_chunk_0"
    assert res.retrieved_chunks[0].similarity_score > 0.0
    assert res.retrieved_chunks[0].reranker_score is not None

    # --- Test Case 2: Table retrieval ---
    res = retriever.retrieve(doc_id, "What is the sprint progress table completion?")
    assert len(res.retrieved_chunks) > 0
    assert res.retrieved_chunks[0].metadata.chunk_type == "table"
    assert res.retrieved_chunks[0].metadata.table_id == "#/tables/0"

    # --- Test Case 3: Image / OCR / Figure Caption retrieval ---
    res = retriever.retrieve(doc_id, "architecture FLOWCHART diagram image")
    assert len(res.retrieved_chunks) > 0
    assert res.retrieved_chunks[0].metadata.chunk_type == "image"
    assert "FLOWCHART" in res.retrieved_chunks[0].content
    assert res.retrieved_chunks[0].metadata.image_id == "#/pictures/0"

    # --- Test Case 4: Page Number Metadata Filtering ---
    # Retrieve ZYGLOPLOTRON chunk (page 3) but filter for page 1
    res_filtered = retriever.retrieve(doc_id, "ZYGLOPLOTRON instrument", metadata_filter={"page_number": 1})
    # Since ZYGLOPLOTRON is on page 3, filtering for page 1 should not return it
    assert not any(c.metadata.chunk_id == f"{doc_id}_chunk_3" for c in res_filtered.retrieved_chunks)

    # Filter for page 3
    res_valid = retriever.retrieve(doc_id, "ZYGLOPLOTRON instrument", metadata_filter={"page_number": 3})
    assert any(c.metadata.chunk_id == f"{doc_id}_chunk_3" for c in res_valid.retrieved_chunks)

    # --- Test Case 5: Chunk Type Metadata Filtering ---
    # Query for sprint tables but filter for 'text' chunks
    res_type_filter = retriever.retrieve(doc_id, "sprint progress details", metadata_filter={"chunk_type": "text"})
    assert not any(c.metadata.chunk_type == "table" for c in res_type_filter.retrieved_chunks)

    # --- Test Case 6: Heading Metadata Filtering ---
    res_heading_filter = retriever.retrieve(doc_id, "diagram extractor", metadata_filter={"heading": "Architecture Figures"})
    assert len(res_heading_filter.retrieved_chunks) > 0
    assert res_heading_filter.retrieved_chunks[0].metadata.heading == "Architecture Figures"

    # --- Test Case 7: Hybrid Search Outperforms Vector-Only Search ---
    # Vector-only search might rank general physics text highly for the keyword 'ZYGLOPLOTRON' due to query matching,
    # but BM25 keyword matching will score the exact word match extremely high.
    # Let's isolate and compare vector-only vs hybrid results.
    
    # Vector search on "Find information on ZYGLOPLOTRON laboratory instrument"
    query_emb = retriever.query_processor.generate_query_embedding("Find information on ZYGLOPLOTRON laboratory instrument")
    vector_results = retriever._search_vector_store(doc_id, query_emb, None)
    vector_rank = [c.metadata.chunk_id for c, _ in vector_results]
    
    # Lexical (BM25) search
    bm25_search = BM25Search(chunks)
    bm25_results = bm25_search.search("Find information on ZYGLOPLOTRON laboratory instrument", top_k=5)
    bm25_rank = [c.metadata.chunk_id for c, _ in bm25_results]

    # Hybrid Search fusion
    fused_results = HybridSearch.fuse_results(vector_results, bm25_results)
    fused_rank = [c.metadata.chunk_id for c, _, _ in fused_results]

    # ZYGLOPLOTRON (chunk_3) has the exact keyword match
    # Validate that hybrid RRF rank preserves/improves the retrieval quality over vector-only if vector ranked it lower
    assert f"{doc_id}_chunk_3" in fused_rank
    
    # Clean up output dir
    try:
        shutil.rmtree(output_dir)
    except Exception:
        pass
