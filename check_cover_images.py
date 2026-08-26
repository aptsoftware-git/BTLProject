import os
import sys
import json
from pathlib import Path

root_dir = Path(__file__).resolve().parent
img_dir = root_dir / "data" / "output" / "cff0427c29e541d496d067247fba5c52" / "05_images"

for jf in sorted(img_dir.glob("*.json")):
    with open(jf, "r", encoding="utf-8") as f:
        meta = json.load(f)
    page = meta.get("page") or meta.get("page_number")
    if page in (1, 2, 3):
        print(f"{jf.name} | Page {page} | Type: {meta.get('image_type')} | Title: {meta.get('title')} | Cap: {meta.get('caption_text')} | Retrievable: {meta.get('retrievable')} | Path: {meta.get('image_path')}")
