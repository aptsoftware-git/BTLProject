import json
import logging
from pathlib import Path
from typing import List, Set, Optional

from src.rag.config import RagConfig
from src.rag.chunk_schema import DocumentChunk, ChunkMetadata
from src.rag.embedder import Embedder
from src.rag.vector_store import VectorStore
from src.rag.document_schema import BoundingBox

logger = logging.getLogger("pipeline")

class IndexManager:
    """
    Orchestrates the loading of chunks, duplicate detection, embedding generation, and vector store ingestion.
    """

    def __init__(self, config: RagConfig, embedder: Embedder, vector_store: VectorStore) -> None:
        self.config = config
        self.embedder = embedder
        self.vector_store = vector_store

    @classmethod
    def from_config(cls, config: Optional[RagConfig] = None) -> "IndexManager":
        """
        Factory method to initialize the index manager and its dependencies from a RAG configuration.
        """
        config = config or RagConfig()
        
        from src.rag.embedding_provider import SentenceTransformersEmbeddingProvider
        
        # Initialize dependencies
        provider = SentenceTransformersEmbeddingProvider(
            model_name=config.embedding_model,
            device=config.embedding_device
        )
        embedder = Embedder(provider)
        vector_store = VectorStore(
            db_dir=config.chroma_db_dir,
            collection_prefix=config.collection_prefix
        )
        return cls(config, embedder, vector_store)

    def index_document(self, document_id: str, chunks: List[DocumentChunk]) -> None:
        """
        Indices a list of DocumentChunks:
          1. Detects which chunks are already stored to skip embedding calculation.
          2. Generates embeddings for new chunks.
          3. Upserts new chunks and embeddings into ChromaDB.
        """
        logger.info(f"Starting indexing for document: {document_id}")
        logger.info("Loading chunks...")

        if not chunks:
            logger.warning("No chunks provided to index.")
            return

        # 1. Fetch already indexed chunk IDs to avoid duplicate work
        existing_ids = self.vector_store.get_existing_chunk_ids(document_id)
        logger.info(f"Found {len(existing_ids)} already indexed chunk(s) in database.")

        # Filter out chunks that are already present
        chunks_to_index = [c for c in chunks if c.metadata.chunk_id not in existing_ids]

        if not chunks_to_index:
            logger.info("All chunks are already indexed. Finished indexing (skipped duplicate work).")
            return

        logger.info(f"Need to generate embeddings and index {len(chunks_to_index)}/{len(chunks)} chunk(s).")

        # 2. Generate embeddings
        embeddings = self.embedder.generate_embeddings(
            chunks_to_index, 
            batch_size=self.config.embedding_batch_size
        )

        # 3. Store in Vector Database
        self.vector_store.index_chunks(document_id, chunks_to_index, embeddings)
        logger.info("Finished indexing.")

    def index_from_file(self, chunks_json_path: Path, document_id: str) -> None:
        """
        Loads document chunks from a document_chunks.json file and indexes them.
        """
        logger.info(f"Reading chunks from file: {chunks_json_path}")
        if not chunks_json_path.exists():
            raise FileNotFoundError(f"Chunks file not found: {chunks_json_path}")

        with open(chunks_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        chunks_list = data.get("chunks", [])
        chunks = []
        for c in chunks_list:
            meta_data = c.get("metadata", {})
            
            # Reconstruct BoundingBoxes in metadata
            bboxes = []
            for bbox_data in meta_data.get("bounding_boxes", []):
                if bbox_data:
                    bboxes.append(BoundingBox(**bbox_data))

            meta = ChunkMetadata(
                chunk_id=meta_data.get("chunk_id"),
                document_id=meta_data.get("document_id"),
                page_number=meta_data.get("page_number"),
                chunk_type=meta_data.get("chunk_type"),
                heading=meta_data.get("heading"),
                section=meta_data.get("section"),
                hierarchy_path=meta_data.get("hierarchy_path", []),
                source_element_ids=meta_data.get("source_element_ids", []),
                word_count=meta_data.get("word_count"),
                token_estimate=meta_data.get("token_estimate"),
                bounding_boxes=bboxes,
                image_id=meta_data.get("image_id"),
                table_id=meta_data.get("table_id")
            )
            chunks.append(DocumentChunk(content=c.get("content"), metadata=meta))

        self.index_document(document_id, chunks)
