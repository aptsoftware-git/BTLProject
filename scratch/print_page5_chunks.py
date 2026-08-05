import json
from pathlib import Path

doc_dir = Path("data/output/df35600eaeeb4bc292bb4537eb9789f8")
chunks_file = doc_dir / "document_chunks.json"

with open(chunks_file, "r", encoding="utf-8") as f:
    data = json.load(f)

chunks = data.get("chunks", [])

log_file = Path("scratch/page5_chunks_log.txt")
with open(log_file, "w", encoding="utf-8") as log:
    log.write(f"Total chunks in df35600eaeeb4bc292bb4537eb9789f8: {len(chunks)}\n")

    page5_chunks = [c for c in chunks if c.get("metadata", {}).get("page_number") == 5]
    log.write(f"Total chunks on Page 5: {len(page5_chunks)}\n\n")

    for idx, c in enumerate(page5_chunks):
        meta = c.get("metadata", {})
        content = c.get("content", "")
        log.write(f"=== Page 5 Chunk #{idx+1} (ID: {meta.get('chunk_id')}) ===\n")
        log.write(f"Heading: {meta.get('heading')} | Section: {meta.get('section')}\n")
        log.write(f"Content Length: {len(content)} chars\n")
        log.write(content + "\n")
        log.write("="*60 + "\n\n")

print(f"Log written to {log_file}")
