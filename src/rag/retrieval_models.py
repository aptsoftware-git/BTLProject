from typing import List, Optional
from pydantic import BaseModel, Field
from src.rag.chunk_schema import ChunkMetadata

class ScoredChunk(BaseModel):
    """
    A semantic document chunk with its retrieval and reranking scores.
    """
    content: str = Field(..., description="Textual or structured content of the chunk")
    metadata: ChunkMetadata = Field(..., description="Associated metadata")
    similarity_score: float = Field(0.0, description="Semantic search cosine similarity score (or BM25 score)")
    reranker_score: float = Field(0.0, description="Relevance score assigned by the cross-encoder reranker")

class RetrievalOutput(BaseModel):
    """
    Final output returned by the retrieval engine.
    """
    question: str = Field(..., description="The query processed by the retrieval engine")
    retrieved_chunks: List[ScoredChunk] = Field(default_factory=list, description="Top sorted chunks matching the query")
    debug_info: Optional[dict] = Field(None, description="Developer debugging information")

