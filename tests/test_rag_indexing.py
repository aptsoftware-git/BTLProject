import json
import shutil
from pathlib import Path
import pytest
import chromadb

from src.rag.config import RagConfig
from src.rag.chunk_schema import DocumentChunk, ChunkMetadata
from src.rag.document_schema import BoundingBox, StructuredDocument
from src.rag.index_manager import IndexManager
from src.rag.vector_store import VectorStore
from src.rag.embedder import Embedder
from src.rag.embedding_provider import SentenceTransformersEmbeddingProvider
from src.rag.multimodal_extractor import MultimodalExtractor

from src.config import ROOT_DIR

# Temp database path for tests
TEMP_DB_DIR = ROOT_DIR / "data" / "output" / "temp_chromadb_test"

@pytest.fixture(autouse=True)
def cleanup_temp_db():
    # Cleanup before and after test runs
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

def test_rag_indexing_pipeline():
    # 1. Create a mock list of chunks representing text, lists, tables, and images
    doc_id = "test_indexing_doc_uuid"
    chunks = [
        DocumentChunk(
            content="This is paragraph one under Heading 1.",
            metadata=ChunkMetadata(
                chunk_id=f"{doc_id}_chunk_0000",
                document_id=doc_id,
                page_number=1,
                chunk_type="text",
                heading="Heading 1",
                section="Heading 1",
                hierarchy_path=["#/texts/0"],
                source_element_ids=["#/texts/1"],
                word_count=7,
                token_estimate=9,
                bounding_boxes=[BoundingBox(l=10, t=20, r=30, b=40)]
            )
        ),
        DocumentChunk(
            content="| A1 | B1 |\n|---|---|\n| Cell 1 | Cell 2 |",
            metadata=ChunkMetadata(
                chunk_id=f"{doc_id}_chunk_0001",
                document_id=doc_id,
                page_number=2,
                chunk_type="table",
                heading="Tables Section",
                section="Heading 1 > Tables Section",
                hierarchy_path=["#/texts/0", "#/texts/2"],
                source_element_ids=["#/tables/0"],
                word_count=6,
                token_estimate=12,
                table_id="#/tables/0",
                bounding_boxes=[BoundingBox(l=10, t=10, r=50, b=50)]
            )
        ),
        DocumentChunk(
            content="Image Caption: Figure 1\nImage OCR Text: HELLO WORLD",
            metadata=ChunkMetadata(
                chunk_id=f"{doc_id}_chunk_0002",
                document_id=doc_id,
                page_number=2,
                chunk_type="image",
                heading="Images Section",
                section="Heading 1 > Images Section",
                hierarchy_path=["#/texts/0", "#/texts/3"],
                source_element_ids=["#/pictures/0"],
                word_count=8,
                token_estimate=11,
                image_id="#/pictures/0"
            )
        )
    ]

    # 2. Configure RAG with temp DB path
    config = RagConfig(
        embedding_model="BAAI/bge-small-en-v1.5",
        embedding_device="cpu",
        chroma_db_dir=TEMP_DB_DIR,
        collection_prefix="test_col_"
    )

    # 3. Initialize IndexManager
    index_manager = IndexManager.from_config(config)
    
    # 4. Run first indexing (initial insert)
    index_manager.index_document(doc_id, chunks)

    # Verify database files were created
    assert TEMP_DB_DIR.exists()

    # 5. Access ChromaDB directly to verify collections, items, and metadata
    client = chromadb.PersistentClient(path=str(TEMP_DB_DIR))
    collection_name = f"test_col_{doc_id}"
    
    # Verify collection exists
    collection = client.get_collection(name=collection_name)
    assert collection is not None
    
    # Retrieve data from ChromaDB
    results = collection.get(include=["metadatas", "documents", "embeddings"])
    
    # Verify correct number of items
    assert len(results["ids"]) == 3
    assert set(results["ids"]) == {f"{doc_id}_chunk_0000", f"{doc_id}_chunk_0001", f"{doc_id}_chunk_0002"}
    
    # Verify documents content
    assert "This is paragraph one under Heading 1." in results["documents"]
    
    # Verify metadata fields are stored correctly (specifically lists serialized as JSON strings)
    meta_dict = {m["chunk_id"]: m for m in results["metadatas"]}
    
    # Text chunk metadata verification
    text_meta = meta_dict[f"{doc_id}_chunk_0000"]
    assert text_meta["page_number"] == 1
    assert text_meta["chunk_type"] == "text"
    assert text_meta["heading"] == "Heading 1"
    assert json.loads(text_meta["hierarchy_path"]) == ["#/texts/0"]
    assert json.loads(text_meta["source_element_ids"]) == ["#/texts/1"]
    
    # Table chunk metadata verification
    table_meta = meta_dict[f"{doc_id}_chunk_0001"]
    assert table_meta["page_number"] == 2
    assert table_meta["chunk_type"] == "table"
    assert table_meta["table_id"] == "#/tables/0"
    
    # Image chunk metadata verification
    image_meta = meta_dict[f"{doc_id}_chunk_0002"]
    assert image_meta["chunk_type"] == "image"
    assert image_meta["image_id"] == "#/pictures/0"

    # Verify embeddings are exactly the correct dimensionality (BGE small has 384 dimensions)
    assert len(results["embeddings"]) == 3
    assert len(results["embeddings"][0]) == 384

    # 6. Run second indexing (duplicate insertion)
    # The duplicate check should detect that all chunks already exist and skip generating embeddings.
    # We can patch embedder.generate_embeddings to ensure it is not called!
    import unittest.mock as mock
    with mock.patch.object(index_manager.embedder, "generate_embeddings", return_value=[]) as mock_embed:
        index_manager.index_document(doc_id, chunks)
        # Should not be called because all 3 chunks already exist in ChromaDB collection
        mock_embed.assert_not_called()

    # 7. Test incremental indexing (inserting 1 new chunk + 3 old ones)
    new_chunk = DocumentChunk(
        content="This is a new chunk to test incremental indexing.",
        metadata=ChunkMetadata(
            chunk_id=f"{doc_id}_chunk_0003",
            document_id=doc_id,
            page_number=3,
            chunk_type="text",
            heading="New Heading",
            section="New Heading",
            hierarchy_path=[],
            source_element_ids=["#/texts/10"],
            word_count=9,
            token_estimate=12
        )
    )
    all_chunks = chunks + [new_chunk]
    
    # Patch get_embeddings to verify only the new chunk is embedded
    original_generate_embeddings = index_manager.embedder.generate_embeddings
    with mock.patch.object(index_manager.embedder, "generate_embeddings", side_effect=original_generate_embeddings) as mock_embed:
        index_manager.index_document(doc_id, all_chunks)
        # Should only be called with the 1 new chunk
        mock_embed.assert_called_once()
        args, kwargs = mock_embed.call_args
        passed_chunks = args[0]
        assert len(passed_chunks) == 1
        assert passed_chunks[0].metadata.chunk_id == f"{doc_id}_chunk_0003"

    # Verify the new chunk is stored
    new_results = collection.get()
    assert len(new_results["ids"]) == 4
    assert f"{doc_id}_chunk_0003" in new_results["ids"]

def test_indexing_end_to_end_on_pdf():
    # End-to-end extraction and automatic indexing on nsmail.pdf
    pdf_path = ROOT_DIR / "data" / "input" / "nsmail.pdf"
    if not pdf_path.exists():
        return
        
    temp_output_dir = ROOT_DIR / "data" / "output" / "temp_indexing_test_run"
    temp_output_dir.mkdir(parents=True, exist_ok=True)
    
    # Configure custom database path for testing
    import src.rag.config
    import unittest.mock as mock
    
    test_rag_config = RagConfig(
        embedding_model="BAAI/bge-small-en-v1.5",
        embedding_device="cpu",
        chroma_db_dir=TEMP_DB_DIR,
        collection_prefix="test_col_run_"
    )
    
    # Mock RagConfig instantiation inside from_config to point to our test database
    with mock.patch("src.rag.config.RagConfig", return_value=test_rag_config):
        extractor = MultimodalExtractor(
            enable_ocr=False,
            enable_table_extraction=True,
            enable_image_extraction=True
        )
        
        # When extract runs, it triggers ChunkBuilder and IndexManager.from_config()
        doc_id = temp_output_dir.name
        raw_text, structured_doc, page_count = extractor.extract(pdf_path, temp_output_dir)
        
        # Verify collection exists in ChromaDB
        client = chromadb.PersistentClient(path=str(TEMP_DB_DIR))
        collection_name = f"test_col_run_{doc_id}"
        
        collection = client.get_collection(name=collection_name)
        assert collection is not None
        
        results = collection.get()
        assert len(results["ids"]) > 0
        
    # Clean up output dir
    try:
        shutil.rmtree(temp_output_dir)
    except Exception:
        pass
