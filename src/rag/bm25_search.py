import re
import logging
from typing import List, Tuple
from rank_bm25 import BM25Okapi
from src.rag.chunk_schema import DocumentChunk

logger = logging.getLogger("pipeline")

class BM25Search:
    """
    Performs tokenized lexical search using the BM25 (Best Matching 25) algorithm over a set of document chunks.
    """

    def __init__(self, chunks: List[DocumentChunk]) -> None:
        self.chunks = chunks
        self.tokenized_corpus = [self._tokenize(chunk.content) for chunk in chunks]
        self.bm25 = BM25Okapi(self.tokenized_corpus)

    def _tokenize(self, text: str) -> List[str]:
        """
        Tokenizes text by lowercasing, stripping punctuation, and splitting on whitespace.
        """
        if not text:
            return []
        # Lowercase folding and punctuation stripping
        cleaned = text.lower()
        cleaned = re.sub(r'[^\w\s]', ' ', cleaned)
        return cleaned.split()

    def search(self, query: str, top_k: int = 10) -> List[Tuple[DocumentChunk, float]]:
        """
        Performs BM25 search for a query and returns the top_k chunks paired with their BM25 relevance score.
        """
        if not self.chunks or not query:
            return []

        logger.info(f"Running BM25 search for query: {repr(query)}")
        tokenized_query = self._tokenize(query)
        
        # Calculate BM25 scores for all corpus documents
        scores = self.bm25.get_scores(tokenized_query)
        
        # Pair chunks with scores
        scored_chunks = [(chunk, float(score)) for chunk, score in zip(self.chunks, scores)]
        
        # Sort descending by score
        scored_chunks.sort(key=lambda x: x[1], reverse=True)
        
        # Return top K results
        return scored_chunks[:top_k]
