import os
import sys
import json
from pathlib import Path

root_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(root_dir))

from src.rag.image_processor import ImageRetrievalValidator
from src.rag.retriever import Retriever

r = Retriever.from_config()
chunks = r._load_document_chunks("cff0427c29e541d496d067247fba5c52")
img_chunks = [c for c in chunks if c.metadata.chunk_type == "image"]

for c in img_chunks:
    meta = c.metadata
    if "rhea" in (meta.entity_name or meta.title or "").lower():
        meta_dict = meta.model_dump() if hasattr(meta, "model_dump") else meta.__dict__
        val_rhea = ImageRetrievalValidator.validate_single_director_image(meta_dict, "rhea todi", doc_id="cff0427c29e541d496d067247fba5c52")
        print(f"Rhea chunk: {meta.chunk_id} | Title: {meta.title} | Entity: {meta.entity_name} | Validate 'rhea todi': {val_rhea}")

target_info = ImageRetrievalValidator.detect_query_target("Show the image of Rhea Todi and Ravi Todi")
print("Target Info:", target_info)
matched = r._search_images(img_chunks, "Show the image of Rhea Todi and Ravi Todi")
print(f"Matched count: {len(matched)}")
for m in matched:
    print(f"Matched: {m.metadata.chunk_id} | {m.metadata.title} | {m.metadata.image_path}")
