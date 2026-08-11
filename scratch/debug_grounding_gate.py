import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json
from src.rag.ambiguity_grounding_gate import _normalize, _quote_found_in_chunk, verify_evidence

job_dir = Path("data/output/cff0427c29e541d496d067247fba5c52")

with open(job_dir / "06_chunks" / "document_chunks.json", "r", encoding="utf-8") as f:
    d_chunks = json.load(f)

chunk_map = {}
for c in d_chunks.get("chunks", []):
    meta = c.get("metadata", {})
    cid = meta.get("chunk_id") or c.get("chunk_id")
    if cid:
        chunk_map[cid] = {"text": c.get("text") or c.get("content") or ""}

with open(job_dir / "15_final_report" / "final_report.json", "r", encoding="utf-8") as f:
    d_final = json.load(f)

rejected = d_final.get("rejected_findings", [])
print(f"Total rejected findings in final_report.json: {len(rejected)}")

for idx, f_item in enumerate(rejected, 1):
    issue_id = f_item.get("issue_id")
    print(f"\n--- Rejected Item {idx}: {issue_id} ---")
    print(f"Explanation: {f_item.get('explanation')}")
    evidence = f_item.get("evidence", [])
    if not evidence:
        fallback_cid = f_item.get("chunk_id")
        fallback_q = f_item.get("highlighted_ambiguity") or f_item.get("quote")
        evidence = [{"chunk_id": fallback_cid, "quote": fallback_q}]
    
    print(f"Evidence items count: {len(evidence)}")
    for ev_idx, ev in enumerate(evidence, 1):
        cid = ev.get("chunk_id")
        q = ev.get("quote")
        chunk_entry = chunk_map.get(cid)
        if not chunk_entry:
            print(f"  Ev {ev_idx}: chunk_id '{cid}' NOT FOUND in chunk_map!")
            continue
        c_text = chunk_entry.get("text", "")
        found = _quote_found_in_chunk(q, c_text)
        print(f"  Ev {ev_idx} [chunk {cid}]: quote_found = {found}")
        print(f"    Quote: {repr(q)}")
        print(f"    Quote normalized: {repr(_normalize(q))}")
        print(f"    Chunk text snippet (first 100 chars): {repr(c_text[:100])}")
        if not found:
            q_norm = _normalize(q)
            c_norm = _normalize(c_text)
            words_in_q = q_norm.split()
            matched_words = [w for w in words_in_q if w in c_norm]
            print(f"    Word match ratio: {len(matched_words)} / {len(words_in_q)} words found in chunk_text")
