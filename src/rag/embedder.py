import logging
from typing import List, Optional
from src.rag.chunk_schema import DocumentChunk
from src.rag.embedding_provider import EmbeddingProvider, SentenceTransformersEmbeddingProvider
from src.rag.config import RagConfig

logger = logging.getLogger("pipeline")

class Embedder:
    """
    Manages the generation of embeddings using a configured EmbeddingProvider.
    """

    def __init__(self, provider: Optional[EmbeddingProvider] = None) -> None:
        if provider is None:
            self.provider = SentenceTransformersEmbeddingProvider(
                model_name=getattr(RagConfig, "EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
            )
        else:
            self.provider = provider

    def generate_embeddings(
        self, 
        chunks: List[DocumentChunk], 
        batch_size: int = 32
    ) -> List[List[float]]:
        """
        Generates exactly one embedding vector per semantic chunk in batches.
        """
        if not chunks:
            return []

        logger.info(f"Generating embeddings for {len(chunks)} chunks...")
        texts = [chunk.content for chunk in chunks]
        
        embeddings = []
        total_chunks = len(texts)
        
        # Batch processing
        for i in range(0, total_chunks, batch_size):
            batch_texts = texts[i : i + batch_size]
            batch_embeddings = self.provider.get_embeddings(batch_texts)
            embeddings.extend(batch_embeddings)
            
            # Log intermediate progress
            indexed_count = len(embeddings)
            logger.info(f"Generated embeddings for chunk {indexed_count}/{total_chunks}")

        logger.info("Finished embedding generation.")
        return embeddings
