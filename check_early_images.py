import os
import sys
import json
from pathlib import Path

root_dir = Path(__file__).resolve().parent
chunks_path = root_dir / "data" / "output" / "cff0427c29e541d496d067247fba5c52" / "document_chunks.json"
with open(chunks_path, "r", encoding="utf-8") as f:
    data = json.load(f)

chunks = data.get("chunks", [])
image_chunks = [c for c in chunks if c.get("metadata", {}).get("chunk_type") == "image" or c.get("metadata", {}).get("image_id")]

for c in image_chunks:
    meta = c.get("metadata", {})
    page = meta.get("page_number")
    if page <= 10:
        print(f"Page {page} | Type: {meta.get('image_type')} | Title: {meta.get('title')} | Entity: {meta.get('entity_name')} | Cap: {meta.get('caption_text') or meta.get('caption')} | Path: {meta.get('image_path')} | Retrievable: {meta.get('retrievable')} | Importance: {meta.get('importance_score')} | ID: {meta.get('image_id')}")
