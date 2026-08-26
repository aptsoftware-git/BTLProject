import os
import sys
import json
from pathlib import Path

root_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(root_dir))

chunks_path = root_dir / "data" / "output" / "cff0427c29e541d496d067247fba5c52" / "document_chunks.json"
with open(chunks_path, "r", encoding="utf-8") as f:
    data = json.load(f)

chunks = data.get("chunks", [])
print(f"Total chunks in document_chunks.json: {len(chunks)}")

image_chunks = [c for c in chunks if c.get("metadata", {}).get("chunk_type") == "image" or c.get("metadata", {}).get("image_id")]
print(f"Total image chunks: {len(image_chunks)}")

for c in image_chunks:
    meta = c.get("metadata", {})
    page = meta.get("page_number")
    img_type = meta.get("image_type")
    title = meta.get("title")
    entity = meta.get("entity_name")
    cap = meta.get("caption_text") or meta.get("caption")
    p = meta.get("image_path")
    if page in (1, 2, 3, 49) or any(k in str(title).lower() or k in str(entity).lower() for k in ["sunil", "ravi", "rhea", "logo"]):
        print(f"Page {page} | Type: {img_type} | Title: {title} | Entity: {entity} | Cap: {cap} | Path: {p} | Retrievable: {meta.get('retrievable')} | Importance: {meta.get('importance_score')}")
