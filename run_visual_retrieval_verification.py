import os
import sys
import json
import time
from pathlib import Path
from unittest.mock import MagicMock

# Add root dir to sys.path
root_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(root_dir))

from src.rag.config import RagConfig
from src.rag.retriever import Retriever
from src.rag.context_builder import ContextBuilder
from src.rag.chat_service import ChatService
from src.rag.image_processor import ImageRetrievalValidator


def run_full_verification():
    print("=" * 80)
    print("MULTIMODAL VISUAL RETRIEVAL VERIFICATION RUN")
    print("=" * 80)

    doc_id = "cff0427c29e541d496d067247fba5c52"
    retriever = Retriever.from_config()
    context_builder = ContextBuilder()

    queries = [
        "Can you show the photo of Sunil Kumar Mittra",
        "Show the image of Rhea Todi and Ravi Todi",
        "Show the logo of the company",
        "Can you show the photo of Elon Musk"
    ]

    results = []

    for query in queries:
        print(f"\n" + "-" * 80)
        print(f"QUERY: \"{query}\"")
        print("-" * 80)

        # 1. Intent Detection
        intent = retriever.detect_intent(query)
        target_info = ImageRetrievalValidator.detect_query_target(query)
        print(f"1. Intent Detected: {intent} | Target Info: {target_info}")

        # 2. Retriever Search
        retrieval_output = retriever.retrieve(doc_id, query)
        retrieved_chunks = retrieval_output.retrieved_chunks
        image_chunks = [c for c in retrieved_chunks if c.metadata.chunk_type == "image"]
        
        print(f"2. Retrieved Total Chunks: {len(retrieved_chunks)} | Image Chunks: {len(image_chunks)}")
        for idx, img_c in enumerate(image_chunks):
            m = img_c.metadata
            print(f"   [Candidate #{idx+1}] ChunkID: {m.chunk_id} | Page: {m.page_number} | Title: {m.title} | Entity: {m.entity_name} | Path: {m.image_path}")

        # 3. Chat Service / Context Builder Execution
        mock_ollama = MagicMock()
        mock_ollama.generate.return_value = "I could not find this information in the uploaded document."
        chat_service = ChatService(retriever=retriever, ollama_client=mock_ollama, context_builder=context_builder)
        
        response = chat_service.answer_question(doc_id, query)

        # 4. Physical PNG & Frontend Asset Verification
        print(f"\n3. API Response Summary:")
        print(f"   - Answer: {response.answer}")
        print(f"   - Image References Count: {len(response.image_references)}")
        print(f"   - Page References: {response.page_references}")
        print(f"   - Used Chunk IDs: {response.used_chunk_ids}")

        print(f"\n4. Trace Breakdown:")
        if response.image_references:
            for idx, img_ref in enumerate(response.image_references):
                img_url = img_ref.get("image_url")
                page_num = img_ref.get("page_number")
                title_val = img_ref.get("title") or img_ref.get("caption")
                img_path = img_ref.get("image_path")
                
                # Physical validation
                is_valid = ImageRetrievalValidator.validate_physical_file(
                    image_path=img_path,
                    image_url=img_url,
                    doc_id=doc_id
                )
                
                trace_entry = {
                    "Query": query,
                    "Retrieved image_id": img_ref.get("image_id"),
                    "Title / Entity": title_val,
                    "Physical PNG": img_path,
                    "Exists on Disk": is_valid,
                    "Page": page_num,
                    "API image_url": img_url,
                    "Frontend display result": f"<ImageEvidenceCard url='{img_url}' page={page_num} caption='{title_val}' />"
                }
                print(f"   Image #{idx+1}: {trace_entry}")
                results.append(trace_entry)
        else:
            trace_entry = {
                "Query": query,
                "Retrieved image_id": None,
                "Title / Entity": None,
                "Physical PNG": None,
                "Exists on Disk": False,
                "Page": None,
                "API image_url": None,
                "Frontend display result": "Zero-result Fallback: 'I could not find this information in the uploaded document.'"
            }
            print(f"   Fallback Result: {trace_entry}")
            results.append(trace_entry)

    print("\n" + "=" * 80)
    print("FINAL SUMMARY REPORT:")
    print("=" * 80)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    run_full_verification()
