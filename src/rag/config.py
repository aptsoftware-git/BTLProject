import os
from dataclasses import dataclass
from pathlib import Path

# Resolve ROOT_DIR relative to src/rag/config.py (three levels up to reach DocumentProofreadingSystem root)
ROOT_DIR = Path(__file__).resolve().parent.parent.parent

@dataclass
class RagConfig:
    """
    Configuration settings for the RAG Assistant indexing and retrieval layer.
    """
    # Embedding Settings
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_batch_size: int = 32
    embedding_device: str = "cpu"  # Options: 'cpu', 'cuda', 'mps'
    
    # Vector Database Settings
    chroma_db_dir: Path = ROOT_DIR / "data" / "chromadb"
    collection_prefix: str = "doc_"
    
    # Ollama LLM Settings
    ollama_model: str = os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:7b")
    ollama_host: str = os.environ.get("OLLAMA_HOST", "http://192.168.19.21:11434")
    
    # Semantic Consistency Settings (Clustering & Retrieval)
    similarity_floor: float = 0.75
    retrieval_top_k: int = 10
    token_budget: int = 12000
    provider: str = os.environ.get("RAG_PROVIDER", "ollama")
    claude_model: str = os.environ.get("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")

    
    # Retrieval & Reranking settings
    reranker_model: str = "BAAI/bge-reranker-base"
    reranker_device: str = "cpu"  # Options: 'cpu', 'cuda', 'mps'
    
    # Top-K settings
    top_k_retrieve: int = 15       # Number of chunks retrieved initially (per search type, or total)
    top_k_rerank: int = 10         # Number of chunks passed to the reranking stage
    top_k_final: int = 5           # Number of final chunks returned to the user
    
    # Defaults
    top_k_default: int = 5
