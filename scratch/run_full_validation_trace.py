import sys, os, json
from pathlib import Path
sys.path.insert(0, os.getcwd())

from src.rag.config import RagConfig
from src.rag.chunk_schema import DocumentChunk, ChunkMetadata
from src.rag.bm25_search import BM25Search
from src.rag.retrieval_models import ScoredChunk
from src.rag.context_builder import ContextBuilder
from src.rag.prompt_builder import PromptBuilder
from src.rag.ollama_client import OllamaClient

doc_id = "df35600eaeeb4bc292bb4537eb9789f8"
query = "Name all the marquee clients of the company"

print("="*60)
print(f"RUNNING VALIDATION TRACE FOR FIX")
print(f"Query: {query}")
print("="*60)

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
        section_heading=meta_data.get("section_heading"),
        sub_heading=meta_data.get("sub_heading"),
        section=meta_data.get("section"),
        word_count=meta_data.get("word_count"),
        token_estimate=meta_data.get("token_estimate"),
    )
    chunks.append(DocumentChunk(content=c.get("content", ""), metadata=meta))

print(f"Loaded {len(chunks)} updated chunks.")

# Perform Heading-Aware BM25 Search
clean_q = query.lower()
bm25 = BM25Search(chunks)
bm25_results = bm25.search(clean_q, top_k=20)

# Apply Heading-Aware Boosting
boosted = []
for chunk, score in bm25_results:
    meta = chunk.metadata
    sec_head = (getattr(meta, "section_heading", "") or getattr(meta, "heading", "") or "").lower()
    sub_head = (getattr(meta, "sub_heading", "") or "").lower()
    boost = 0.0
    if any(w in sec_head or w in sub_head for w in ["marquee", "client"]):
        boost += 15.0
    boosted.append((chunk, score + boost))

boosted.sort(key=lambda x: x[1], reverse=True)

print(f"\nTop Boosted Candidates:")
for rank, (chunk, score) in enumerate(boosted[:5], 1):
    meta = chunk.metadata
    print(f"  #{rank} Score: {score:.2f} | Chunk: {meta.chunk_id} | Page: {meta.page_number} | Section Heading: {meta.section_heading} | Heading: {meta.heading}")

# Sibling Section Expansion
selected_candidates = [c for c, _ in boosted[:5]]
seen_ids = {c.metadata.chunk_id for c in selected_candidates}

expanded_set = list(selected_candidates)
for cand in selected_candidates:
    sec_h = getattr(cand.metadata, "section_heading", None)
    if sec_h and "marquee" in sec_h.lower():
        for other in chunks:
            if other.metadata.chunk_id not in seen_ids:
                other_sec = getattr(other.metadata, "section_heading", None)
                if other.metadata.page_number == cand.metadata.page_number and other_sec and "marquee" in other_sec.lower():
                    expanded_set.append(other)
                    seen_ids.add(other.metadata.chunk_id)

print(f"\nTotal Expanded Section Chunks for Context: {len(expanded_set)}")

scored_chunks = [ScoredChunk(content=c.content, metadata=c.metadata, similarity_score=1.0, reranker_score=1.0) for c in expanded_set]

cb = ContextBuilder(max_tokens=4000)
context_str, used_ids, pages = cb.build_context(scored_chunks)

print(f"Pages Represented: {pages}")
print(f"Context Length: {len(context_str)} characters")

pb = PromptBuilder()
prompt_data = pb.build_prompt(context_str, query)

print("\nCalling Ollama with assembled context...")
ollama = OllamaClient()
answer = ollama.generate(
    model="qwen2.5-coder:32b",
    prompt=prompt_data["prompt"],
    system=prompt_data["system"],
    timeout=120
)

print("="*60)
print("FINAL MODEL RESPONSE AFTER FIX:")
print("="*60)
print(answer)
print("="*60)

validation_report = {
    "before": {
        "retrieved_chunks": ["df35600eaeeb4bc292bb4537eb9789f8_chunk_0026", "df35600eaeeb4bc292bb4537eb9789f8_chunk_0027", "df35600eaeeb4bc292bb4537eb9789f8_chunk_0028"],
        "retrieved_pages": [5],
        "context_character_length": 1280,
        "clients_extracted": ["Bharat Heavy Electricals Limited (BHEL)"]
    },
    "after": {
        "used_chunk_ids": used_ids,
        "retrieved_pages": pages,
        "context_character_length": len(context_str),
        "llm_response": answer
    }
}

with open("scratch/full_validation_result.json", "w", encoding="utf-8") as f:
    json.dump(validation_report, f, indent=2, ensure_ascii=False)

print("\nValidation report saved to scratch/full_validation_result.json")
