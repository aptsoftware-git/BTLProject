import sys, os, json
from pathlib import Path
sys.path.insert(0, os.getcwd())

from src.rag.config import RagConfig
from src.rag.retriever import Retriever
from src.rag.context_builder import ContextBuilder
from src.rag.prompt_builder import PromptBuilder

doc_id = "df35600eaeeb4bc292bb4537eb9789f8"
query = "Name all the marquee clients of the company"

print("="*60)
print("TESTING RETRIEVER.RETRIEVE() LIVE BACKEND FLOW")
print("="*60)

retriever = Retriever.from_config()
output = retriever.retrieve(doc_id, query)

print(f"Retrieved Chunks Count: {len(output.retrieved_chunks)}")
for idx, sc in enumerate(output.retrieved_chunks, 1):
    meta = sc.metadata
    print(f"  #{idx} ID: {meta.chunk_id} | Page: {meta.page_number} | Section Heading: {getattr(meta, 'section_heading', None)} | Heading: {meta.heading}")
    print(f"      Content ({len(sc.content)} chars):\n{sc.content[:200]}...\n")

cb = ContextBuilder(max_tokens=4000)
context_str, used_ids, pages = cb.build_context(output.retrieved_chunks)

print(f"Pages Represented: {pages}")
print(f"Used Chunk IDs: {used_ids}")
print(f"Total Context Length: {len(context_str)} characters")
print("="*60)
print("ASSEMBLED CONTEXT:")
print("="*60)
print(context_str)
