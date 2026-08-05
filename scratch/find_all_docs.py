import os, json
from pathlib import Path

print("Current directory:", os.getcwd())
for path in Path(".").rglob("*.json"):
    if "chunk" in path.name.lower() or "doc" in path.name.lower() or "store" in path.name.lower():
        try:
            size = path.stat().st_size
            print(f"Found JSON: {path} ({size} bytes)")
        except Exception:
            pass
