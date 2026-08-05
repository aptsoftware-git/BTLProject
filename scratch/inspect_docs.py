import os
import json
from pathlib import Path

output_dir = Path("data/output")
if output_dir.exists():
    print(f"Output dir exists: {output_dir.absolute()}")
    for item in output_dir.iterdir():
        if item.is_dir():
            chunks_file = item / "document_chunks.json"
            if chunks_file.exists():
                with open(chunks_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                chunks = data.get("chunks", [])
                print(f"Document ID: {item.name} | Total Chunks: {len(chunks)}")
                # Check for 'marquee' in chunks
                marquee_chunks = [c for c in chunks if "marquee" in c.get("content", "").lower()]
                print(f"  -> Chunks containing 'marquee': {len(marquee_chunks)}")
                for mc in marquee_chunks:
                    meta = mc.get("metadata", {})
                    print(f"     [Chunk ID: {meta.get('chunk_id')}] Page: {meta.get('page_number')} | Heading: {meta.get('heading')}")
                    print(f"     Preview: {mc.get('content')[:300]}...\n")
