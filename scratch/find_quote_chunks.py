import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json
from src.rag.ambiguity_grounding_gate import _normalize

job_dir = Path("data/output/cff0427c29e541d496d067247fba5c52")

with open(job_dir / "06_chunks" / "document_chunks.json", "r", encoding="utf-8") as f:
    d_chunks = json.load(f)

chunks_list = d_chunks.get("chunks", [])

with open(job_dir / "15_final_report" / "final_report.json", "r", encoding="utf-8") as f:
    d_final = json.load(f)

rejected = d_final.get("rejected_findings", [])

print("=== QUOTE LOCATION SEARCH IN ALL DOCUMENT CHUNKS ===")
for idx, f_item in enumerate(rejected, 1):
    issue_id = f_item.get("issue_id")
    print(f"\nFinding {idx}: {issue_id}")
    print(f"Explanation: {f_item.get('explanation')}")
    evidence = f_item.get("evidence", [])
    for ev in evidence:
        q = ev.get("quote")
        cited_cid = ev.get("chunk_id")
        q_norm = _normalize(q)
        
        found_cids = []
        for ch in chunks_list:
            cid = ch.get("metadata", {}).get("chunk_id") or ch.get("chunk_id")
            c_text = ch.get("text") or ch.get("content") or ""
            if q_norm in _normalize(c_text):
                found_cids.append(cid)
        
        print(f"  Quote: {repr(q[:70])}")
        print(f"    Cited chunk_id: {cited_cid}")
        print(f"    Actual matching chunk_id(s) in document: {found_cids}")
