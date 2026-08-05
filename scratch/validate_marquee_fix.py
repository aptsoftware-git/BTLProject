import sys, os, json
from pathlib import Path
sys.path.insert(0, os.getcwd())

from src.rag.config import RagConfig
from src.rag.retriever import Retriever
from src.rag.context_builder import ContextBuilder
from src.rag.prompt_builder import PromptBuilder

document_id = "df35600eaeeb4bc292bb4537eb9789f8"
question = "Name all the marquee clients of the company"

print("="*60)
print(f"VALIDATING RETRIEVAL FIX FOR QUESTION: {question}")
print("="*60)

retriever = Retriever.from_config()
retrieval_output = retriever.retrieve(document_id, question)

chunks = retrieval_output.retrieved_chunks

print(f"\nTotal Retrieved Chunks After Fix: {len(chunks)}")
print("="*60)

for rank, scored_chunk in enumerate(chunks, 1):
    meta = scored_chunk.metadata
    content = scored_chunk.content
    print(f"\nCHUNK {rank}")
    print(f"Chunk ID: {meta.chunk_id} | Page: {meta.page_number}")
    print(f"Section Heading: {getattr(meta, 'section_heading', None)} | Sub Heading: {getattr(meta, 'sub_heading', None)}")
    print(f"Heading: {meta.heading} | Section: {meta.section}")
    print(f"Length: {len(content)} chars")
    print(f"Preview:\n{content[:250]}...\n" + "-"*40)

context_builder = ContextBuilder(max_tokens=4000)
context_str, used_chunk_ids, page_references = context_builder.build_context(chunks)

prompt_builder = PromptBuilder()
prompt_data = prompt_builder.build_prompt(context_str, question)

output_file = Path("scratch/validation_marquee_output.json")
with open(output_file, "w", encoding="utf-8") as f:
    json.dump({
        "question": question,
        "used_chunk_ids": used_chunk_ids,
        "pages_represented": page_references,
        "context_character_length": len(context_str),
        "context": context_str,
        "prompt": prompt_data["prompt"]
    }, f, indent=2, ensure_ascii=False)

print(f"\nValidation context saved to {output_file}")
