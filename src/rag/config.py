import os
from dataclasses import dataclass
from pathlib import Path

# Resolve ROOT_DIR relative to src/rag/config.py (three levels up to reach DocumentProofreadingSystem root)
ROOT_DIR = Path(__file__).resolve().parent.parent.parent

from src.model_router import MODEL_ROUTER

@dataclass
class RagConfig:
    """
    Configuration settings for the RAG Assistant indexing and retrieval layer.
    """
    # Embedding Settings
    embedding_model: str = os.environ.get("MODEL_EMBEDDING", MODEL_ROUTER.get_model("embedding_model"))
    embedding_batch_size: int = 32
    embedding_device: str = "cpu"  # Options: 'cpu', 'cuda', 'mps'
    
    # Vector Database Settings
    chroma_db_dir: Path = ROOT_DIR / "data" / "chromadb"
    collection_prefix: str = "doc_"
    
    # Ollama LLM Settings (RAG AI Assistant uses Qwen2.5-Coder:32B)
    ollama_model: str = os.environ.get("MODEL_RAG_CHAT", os.environ.get("OLLAMA_MODEL", MODEL_ROUTER.get_model("rag_chat")))
    ollama_host: str = os.environ.get("OLLAMA_HOST", "http://192.168.19.21:11434")
    
    # Semantic Consistency Settings (Clustering & Retrieval)
    similarity_floor: float = 0.75
    retrieval_top_k: int = 10
    token_budget: int = 12000
    provider: str = os.environ.get("RAG_PROVIDER", "ollama")
    claude_model: str = os.environ.get("MODEL_EXECUTIVE_REPORT", os.environ.get("ANTHROPIC_MODEL", MODEL_ROUTER.get_model("executive_report")))

    
    # Retrieval & Reranking settings
    reranker_model: str = "BAAI/bge-reranker-base"
    reranker_device: str = "cpu"  # Options: 'cpu', 'cuda', 'mps'
    
    # Top-K settings
    top_k_retrieve: int = 15       # Number of chunks retrieved initially (per search type, or total)
    top_k_rerank: int = 10         # Number of chunks passed to the reranking stage
    top_k_final: int = 5           # Number of final chunks returned to the user
    
    # Quality, Finding Filtering & Executive Report Thresholds
    finding_min_confidence: float = float(os.environ.get("FINDING_MIN_CONFIDENCE", 0.70))
    max_findings_per_report: int = int(os.environ.get("MAX_FINDINGS_PER_REPORT", 40))
    min_findings_per_report: int = int(os.environ.get("MIN_FINDINGS_PER_REPORT", 5))
    max_competitors: int = int(os.environ.get("MAX_COMPETITORS", 5))

    # Defaults
    top_k_default: int = 5

    # CPU-tuning knobs for the Context Analysis (Stage 6) sub-pipelines
    # (ambiguity_extractor.py, ambiguity_chunk_analyzer.py,
    # ambiguity_cluster_analyzer.py, contextual_analysis/pipeline.py).
    # On a CPU-only, single-instance Ollama server these ThreadPoolExecutor
    # worker counts don't parallelize actual inference -- Ollama serializes
    # on one CPU worker -- so a high value just adds request-queueing
    # overhead. Default stays high (assumes GPU/multi-instance Ollama);
    # override CONTEXT_MAX_WORKERS=1 or 2 for CPU-only hosts.
    context_max_workers: int = int(os.environ.get("CONTEXT_MAX_WORKERS", 8))
    # Chunks bundled per LLM call in ambiguity_chunk_analyzer.py -- smaller
    # batches mean smaller prompts and faster per-call CPU prefill/decode.
    context_chunk_batch_size: int = int(os.environ.get("CONTEXT_CHUNK_BATCH_SIZE", 10))
