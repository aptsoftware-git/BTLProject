import sys
import os
from pathlib import Path
sys.path.insert(0, os.getcwd())

import json
import logging
from src.rag.config import RagConfig
from src.rag.retriever import Retriever
from src.rag.context_builder import ContextBuilder
from src.rag.prompt_builder import PromptBuilder

# Configure logging
logging.basicConfig(level=logging.INFO)

document_id = "df35600eaeeb4bc292bb4537eb9789f8"
question = "Name all the marquee clients of the company"

print("="*60)
print(f"QUESTION: {question}")
print(f"DOCUMENT ID: {document_id}")
print("="*60)

# Initialize Retriever
retriever = Retriever.from_config()
retrieval_output = retriever.retrieve(document_id, question)

chunks = retrieval_output.retrieved_chunks

print(f"\nTotal Retrieved Chunks: {len(chunks)}")
print("="*60)

debug_log = []
debug_log.append(f"# RAG Debug Log — Marquee Clients Investigation\n\n")
debug_log.append(f"**Document ID:** `{document_id}`  \n")
debug_log.append(f"**Question:** `{question}`  \n")
debug_log.append(f"**Total Retrieved Chunks:** {len(chunks)}  \n\n")

debug_log.append("## Phase 2: Retrieved Chunks Breakdown\n\n")

for rank, scored_chunk in enumerate(chunks, 1):
    meta = scored_chunk.metadata
    content = scored_chunk.content
    score = getattr(scored_chunk, "reranker_score", getattr(scored_chunk, "similarity_score", 0.0))
    
    print(f"\nCHUNK {rank}")
    print(f"Score: {score:.4f}")
    print(f"Chunk ID: {meta.chunk_id}")
    print(f"Page: {meta.page_number}")
    print(f"Heading: {meta.heading}")
    print(f"Section: {meta.section}")
    print(f"Character Length: {len(content)}")
    print("Text Preview:")
    print(content[:300])
    print("-" * 50)

    debug_log.append(f"### CHUNK {rank}\n")
    debug_log.append(f"- **Score:** `{score:.4f}`\n")
    debug_log.append(f"- **Chunk ID:** `{meta.chunk_id}`\n")
    debug_log.append(f"- **Page:** `{meta.page_number}`\n")
    debug_log.append(f"- **Heading:** `{meta.heading}`\n")
    debug_log.append(f"- **Section:** `{meta.section}`\n")
    debug_log.append(f"- **Character Length:** `{len(content)}` chars\n\n")
    debug_log.append(f"```text\n{content}\n```\n\n")

# Phase 3: Final LLM Context Assembly
context_builder = ContextBuilder(max_tokens=4000)
context_str, used_chunk_ids, page_references = context_builder.build_context(chunks)

prompt_builder = PromptBuilder()
prompt_data = prompt_builder.build_prompt(context_str, question)

debug_log.append("## Phase 3: Final LLM Context & Assembled Prompt\n\n")
debug_log.append(f"- **Total Chunks Included in Context:** {len(used_chunk_ids)}\n")
debug_log.append(f"- **Pages Represented:** {page_references}\n")
debug_log.append(f"- **Total Context Character Length:** {len(context_str)} chars\n\n")
debug_log.append(f"### Assembled Context Sent to LLM\n\n```text\n{context_str}\n```\n\n")
debug_log.append(f"### Assembled System Prompt\n\n```text\n{prompt_data['system']}\n```\n\n")
debug_log.append(f"### Assembled User Prompt\n\n```text\n{prompt_data['prompt']}\n```\n")

log_path = Path("scratch/marquee_debug_raw.md")
with open(log_path, "w", encoding="utf-8") as f:
    f.writelines(debug_log)

print(f"\nTrace log saved to: {log_path}")
