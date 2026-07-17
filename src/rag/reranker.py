import logging
from typing import List, Tuple
from src.rag.chunk_schema import DocumentChunk

logger = logging.getLogger("pipeline")

class Reranker:
    """
    Reranks candidate document chunks based on cross-encoder query-chunk relevance scores.
    """

    def __init__(self, model_name: str = "BAAI/bge-reranker-base", device: str = "cpu") -> None:
        self.model_name = model_name
        self.device = device
        self._model = None

    @property
    def model(self):
        """Lazy load the cross-encoder model to save memory."""
        if self._model is None:
            from sentence_transformers import CrossEncoder
            logger.info(f"Loading CrossEncoder reranker model: {self.model_name} on {self.device}")
            self._model = CrossEncoder(self.model_name, device=self.device)
        return self._model

    def rerank(self, query: str, chunks: List[DocumentChunk]) -> List[Tuple[DocumentChunk, float]]:
        """
        Calculates cross-encoder scores for all (Query, Chunk) pairs and returns chunks sorted by score.
        """
        if not chunks:
            return []

        logger.info(f"Reranking {len(chunks)} chunks using CrossEncoder model: {self.model_name}...")
        
        # Format input pairs
        pairs = [[query, chunk.content] for chunk in chunks]
        
        # Predict relevance scores
        # predict returns a list or numpy array of floats
        scores = self.model.predict(pairs, convert_to_numpy=True)
        
        # Pair chunks with scores
        scored_chunks = [(chunk, float(score)) for chunk, score in zip(chunks, scores.tolist())]
        
        # Sort descending by score
        scored_chunks.sort(key=lambda x: x[1], reverse=True)
        
        logger.info("Finished reranking.")
        return scored_chunks
