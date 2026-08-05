import json
from pathlib import Path

doc_dir = Path("data/output/df35600eaeeb4bc292bb4537eb9789f8")
print("Files in doc_dir:", [f.name for f in doc_dir.iterdir()])

chunks_file = doc_dir / "document_chunks.json"
if not chunks_file.exists():
    chunks_file = doc_dir / "06_chunks" / "document_chunks.json"

if chunks_file.exists():
    with open(chunks_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    chunks = data.get("chunks", []) if isinstance(data, dict) else data
    print(f"Total chunks: {len(chunks)}")
    for idx, c in enumerate(chunks):
        content = c.get("content", "") if isinstance(c, dict) else str(c)
        meta = c.get("metadata", {}) if isinstance(c, dict) else {}
        if "marquee" in content.lower() or "bhel" in content.lower() or "client" in content.lower():
            print(f"--- Chunk #{idx} (Page {meta.get('page_number')}) ---")
            print(f"ID: {meta.get('chunk_id')} | Heading: {meta.get('heading')} | Section: {meta.get('section')}")
            print(f"Length: {len(content)} chars")
            print(f"Content:\n{content[:500]}\n")
else:
    print(f"Chunks file not found in {doc_dir}")
