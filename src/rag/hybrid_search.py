import logging
from typing import List, Tuple, Dict, Set
from src.rag.chunk_schema import DocumentChunk

logger = logging.getLogger("pipeline")

class HybridSearch:
    """
    Fuses dense semantic search results (from vector DB) and sparse lexical search results (from BM25)
    using Reciprocal Rank Fusion (RRF).
    """

    @staticmethod
    def fuse_results(
        semantic_results: List[Tuple[DocumentChunk, float]],
        bm25_results: List[Tuple[DocumentChunk, float]],
        k: int = 60
    ) -> List[Tuple[DocumentChunk, float, float]]:
        """
        Combines semantic and lexical results using Reciprocal Rank Fusion (RRF).
        Returns a sorted list of Tuples: (DocumentChunk, rrf_score, original_semantic_score).
        """
        logger.info("Merging search results using Reciprocal Rank Fusion (RRF)...")
        
        # Maps chunk_id -> DocumentChunk
        chunk_map: Dict[str, DocumentChunk] = {}
        
        # Maps chunk_id -> original semantic similarity score (defaults to 0.0)
        semantic_scores: Dict[str, float] = {}
        
        # Record ranks
        semantic_ranks: Dict[str, int] = {}
        for rank, (chunk, score) in enumerate(semantic_results):
            cid = chunk.metadata.chunk_id
            chunk_map[cid] = chunk
            semantic_ranks[cid] = rank + 1
            semantic_scores[cid] = score

        bm25_ranks: Dict[str, int] = {}
        for rank, (chunk, _) in enumerate(bm25_results):
            cid = chunk.metadata.chunk_id
            chunk_map[cid] = chunk
            bm25_ranks[cid] = rank + 1

        # Calculate RRF score for all unique candidate chunks
        rrf_scores: Dict[str, float] = {}
        for cid in chunk_map.keys():
            score = 0.0
            if cid in semantic_ranks:
                score += 1.0 / (k + semantic_ranks[cid])
            if cid in bm25_ranks:
                score += 1.0 / (k + bm25_ranks[cid])
            rrf_scores[cid] = score

        # Build list of tuples: (chunk, rrf_score, semantic_score)
        fused = []
        for cid, rrf_score in rrf_scores.items():
            chunk = chunk_map[cid]
            sem_score = semantic_scores.get(cid, 0.0)
            fused.append((chunk, rrf_score, sem_score))

        # Sort descending by RRF score
        fused.sort(key=lambda x: x[1], reverse=True)
        
        logger.info(f"Fused hybrid search results: {len(fused)} unique chunks.")
        return fused
