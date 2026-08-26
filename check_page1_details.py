import os
import sys
import json
from pathlib import Path

root_dir = Path(__file__).resolve().parent
img_dir = root_dir / "data" / "output" / "cff0427c29e541d496d067247fba5c52" / "05_images"

for jname in ["image_001.json", "image_059.json", "image_060.json", "image_137.json"]:
    p = img_dir / jname
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            d = json.load(f)
        print(f"\n--- {jname} ---")
        print("image_type:", d.get("image_type"))
        print("bbox:", d.get("bounding_box"))
        print("text_before:", d.get("text_before"))
        print("text_after:", d.get("text_after"))
        print("title:", d.get("title"))
        print("semantic_description:", d.get("semantic_description"))
        print("keywords:", d.get("keywords"))
