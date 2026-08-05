import sys, os, json
from pathlib import Path
sys.path.insert(0, os.getcwd())

from src.rag.config import RagConfig
from src.rag.chunk_schema import DocumentChunk, ChunkMetadata
from src.rag.query_processor import QueryProcessor
from src.rag.bm25_search import BM25Search
from src.rag.hybrid_search import HybridSearch
from src.rag.context_builder import ContextBuilder
from src.rag.prompt_builder import PromptBuilder

doc_id = "df35600eaeeb4bc292bb4537eb9789f8"
query = "Name all the marquee clients of the company"

config = RagConfig()
chunks_file = Path("data/output") / doc_id / "document_chunks.json"

with open(chunks_file, "r", encoding="utf-8") as f:
    data = json.load(f)

chunks = []
for c in data.get("chunks", []):
    meta_data = c.get("metadata", {})
    meta = ChunkMetadata(
        chunk_id=meta_data.get("chunk_id"),
        document_id=meta_data.get("document_id"),
        page_number=meta_data.get("page_number"),
        chunk_type=meta_data.get("chunk_type"),
        heading=meta_data.get("heading"),
        section=meta_data.get("section"),
        word_count=meta_data.get("word_count"),
        token_estimate=meta_data.get("token_estimate"),
    )
    chunks.append(DocumentChunk(content=c.get("content", ""), metadata=meta))

print(f"Loaded {len(chunks)} chunks for {doc_id}")

# Run BM25 search
bm25 = BM25Search(chunks)
bm25_results = bm25.search(query, top_k=40)

print(f"\nTop 10 BM25 Matches:")
for rank, (chunk, score) in enumerate(bm25_results[:10], 1):
    meta = chunk.metadata
    print(f"Rank #{rank} | Score: {score:.4f} | Chunk: {meta.chunk_id} | Page: {meta.page_number} | Heading: {meta.heading}")
    print(f"Snippet: {chunk.content[:200].strip()}\n")

# Run ContextBuilder on top 10 BM25 chunks
from src.rag.retrieval_models import ScoredChunk
scored_chunks = [ScoredChunk(content=c.content, metadata=c.metadata, similarity_score=s, reranker_score=s) for c, s in bm25_results[:10]]

cb = ContextBuilder(max_tokens=4000)
context_str, used_ids, pages = cb.build_context(scored_chunks)

pb = PromptBuilder()
prompt_data = pb.build_prompt(context_str, query)

output_md = Path("scratch/marquee_client_debug_raw.md")
with open(output_md, "w", encoding="utf-8") as out:
    out.write(f"# MARQUEE CLIENTS RETRIEVAL TRACE\n\n")
    out.write(f"**Query:** `{query}`  \n")
    out.write(f"**Document ID:** `{doc_id}`  \n\n")
    out.write(f"## Top 10 Retrieved Chunks (BM25 + Hybrid Candidate Set)\n\n")
    for rank, (c, s) in enumerate(bm25_results[:10], 1):
        meta = c.metadata
        out.write(f"### CHUNK {rank}\n")
        out.write(f"- **Score:** `{s:.4f}`\n")
        out.write(f"- **Chunk ID:** `{meta.chunk_id}`\n")
        out.write(f"- **Page:** `{meta.page_number}`\n")
        out.write(f"- **Heading:** `{meta.heading}`\n")
        out.write(f"- **Section:** `{meta.section}`\n")
        out.write(f"- **Character Length:** `{len(c.content)}` chars\n\n")
        out.write(f"```text\n{c.content}\n```\n\n")
    
    out.write(f"## Assembled LLM Context\n\n")
    out.write(f"- **Used Chunks:** `{used_ids}`\n")
    out.write(f"- **Pages Represented:** `{pages}`\n\n")
    out.write(f"```text\n{context_str}\n```\n\n")
    out.write(f"## Assembled Final User Prompt\n\n")
    out.write(f"```text\n{prompt_data['prompt']}\n```\n")

print(f"Log saved to {output_md}")
