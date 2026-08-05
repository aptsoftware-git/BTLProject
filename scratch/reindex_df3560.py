import sys, os, json
from pathlib import Path
sys.path.insert(0, os.getcwd())

from src.rag.chunk_builder import ChunkBuilder
from src.rag.document_schema import StructuredDocument
from src.rag.chunk_schema import DocumentChunksOutput
from src.rag.index_manager import IndexManager
from src.rag.config import RagConfig

doc_id = "df35600eaeeb4bc292bb4537eb9789f8"
output_dir = Path("data/output") / doc_id
doc_file = output_dir / "structured_document.json"
chunks_file = output_dir / "document_chunks.json"

print(f"Loading structured document from {doc_file}...")
with open(doc_file, "r", encoding="utf-8") as f:
    data = json.load(f)

doc = StructuredDocument(**data)
print(f"Loaded structured document with {len(doc.elements)} elements.")

# Build updated section-aware chunks
builder = ChunkBuilder(target_tokens_min=250, target_tokens_max=1000, overlap_tokens=50)
chunks = builder.build_chunks(doc, doc_id)

print(f"Successfully generated {len(chunks)} updated section-aware chunks.")

# Inspect Page 5 chunks in new index
page5_chunks = [c for c in chunks if c.metadata.page_number == 5]
print(f"Page 5 now has {len(page5_chunks)} chunks (reduced from 8 micro-chunks):")
for idx, c in enumerate(page5_chunks, 1):
    meta = c.metadata
    print(f"  [{idx}] ID: {meta.chunk_id} | Heading: {meta.heading} | Section Heading: {meta.section_heading} | Sub Heading: {meta.sub_heading}")
    print(f"      Length: {len(c.content)} chars\n")

# Save updated chunks output
output_obj = DocumentChunksOutput(
    document_id=doc_id,
    file_name="BTL AR SS 09-10-2025 (c2c).pdf",
    chunks=chunks
)

with open(chunks_file, "w", encoding="utf-8") as f:
    json.dump(output_obj.dict(), f, indent=2, ensure_ascii=False)
print(f"Updated chunks saved to {chunks_file}")

# Also update cache copy if present
cache_dir = Path("data/cache/df35600eaeeb4bc292bb4537eb9789f8")
if cache_dir.exists():
    cache_chunks_file = cache_dir / "document_chunks.json"
    with open(cache_chunks_file, "w", encoding="utf-8") as f:
        json.dump(output_obj.dict(), f, indent=2, ensure_ascii=False)
    print(f"Updated cache chunks saved to {cache_chunks_file}")

# Rebuild vector store & index manager
config = RagConfig()
index_manager = IndexManager(config)
index_manager.index_document(doc_id, chunks)
print(f"Re-indexing complete for {doc_id}!")
