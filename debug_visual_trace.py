import os
import sys
import json
from pathlib import Path

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(root_dir))

from src.rag.config import RagConfig
from src.rag.retriever import Retriever
from src.rag.chat_service import ChatService
from src.rag.image_processor import ImageRetrievalValidator, PortraitSpatialValidator

doc_id = "cff0427c29e541d496d067247fba5c52"
print(f"Testing document: {doc_id}")

retriever = Retriever.from_config()
queries = [
    "Can you show the photo of Sunil Kumar Mittra",
    "Show the image of Rhea Todi and Ravi Todi",
    "Show the logo of the company"
]

for q in queries:
    print("\n" + "="*80)
    print(f"QUERY: {q}")
    print("="*80)
    
    intent = retriever.detect_intent(q)
    print(f"Detected intent: {intent}")
    
    target_info = ImageRetrievalValidator.detect_query_target(q)
    print(f"Target info: {target_info}")
    
    retrieval_output = retriever.retrieve(doc_id, q)
    chunks = retrieval_output.retrieved_chunks
    print(f"Retrieved {len(chunks)} chunks:")
    for idx, c in enumerate(chunks):
        meta = c.metadata
        print(f"  [{idx+1}] Type: {meta.chunk_type}, Page: {meta.page_number}, ID: {meta.chunk_id}, ImgPath: {getattr(meta, 'image_path', None)}, Title: {getattr(meta, 'title', None)}, Entity: {getattr(meta, 'entity_name', None)}, Sim: {c.similarity_score:.3f}, Rerank: {c.reranker_score:.3f}")
