import json
from pathlib import Path

job_dir = Path("data/output/cff0427c29e541d496d067247fba5c52")

print("=== DEEP PIPELINE TRACE ===")

# Step 1: 06_chunks
p_chunks = job_dir / "06_chunks" / "document_chunks.json"
if p_chunks.exists():
    with open(p_chunks, "r", encoding="utf-8") as f:
        d_chunks = json.load(f)
    print(f"1. 06_chunks count: {len(d_chunks.get('chunks', []))}")

# Step 2: 10_claim_extraction
p_claims = job_dir / "10_claim_extraction" / "chunk_claims.json"
if p_claims.exists():
    with open(p_claims, "r", encoding="utf-8") as f:
        d_claims = json.load(f)
    chunks_list = d_claims.get("chunks", [])
    print(f"2. 10_claim_extraction chunks count: {len(chunks_list)}")
    # Check if extractions had entities, claims, etc.
    total_claims = 0
    total_entities = 0
    for c in chunks_list:
        ext = c.get("extraction", {})
        total_claims += len(ext.get("claims", []))
        total_entities += len(ext.get("entities", []))
    print(f"   Total extracted claims: {total_claims}, Total extracted entities: {total_entities}")

# Step 3: 11_chunk_reasoning
p_reason = job_dir / "11_chunk_reasoning" / "chunk_reasoning.json"
if p_reason.exists():
    with open(p_reason, "r", encoding="utf-8") as f:
        d_reason = json.load(f)
    chunks_reason = d_reason.get("chunks", [])
    print(f"3. 11_chunk_reasoning chunks count: {len(chunks_reason)}")
    total_ambs = 0
    amb_types = {}
    for c in chunks_reason:
        if isinstance(c, dict):
            ambs = c.get("ambiguities", [])
            total_ambs += len(ambs)
            for a in ambs:
                if isinstance(a, dict):
                    t = a.get("type", a.get("detector_type", "dict_without_type"))
                    amb_types[t] = amb_types.get(t, 0) + 1
                elif isinstance(a, str):
                    amb_types["string"] = amb_types.get("string", 0) + 1
                else:
                    amb_types["other"] = amb_types.get("other", 0) + 1
    print(f"   Total chunk ambiguities: {total_ambs}")
    print(f"   Ambiguity types: {json.dumps(amb_types, indent=2)}")

# Step 4: 12_cluster_reasoning
p_cluster = job_dir / "12_cluster_reasoning" / "cluster_reasoning.json"
if p_cluster.exists():
    with open(p_cluster, "r", encoding="utf-8") as f:
        d_cluster = json.load(f)
    print(f"4. 12_cluster_reasoning clusters count: {len(d_cluster)}")
    total_cluster_findings = 0
    for clid, cl in d_cluster.items():
        if isinstance(cl, dict):
            finds = cl.get("cluster_findings", [])
            total_cluster_findings += len(finds)
    print(f"   Total cluster findings: {total_cluster_findings}")

# Step 5: 13_claude_input
p_input = job_dir / "13_claude_input" / "claude_input.json"
if p_input.exists():
    with open(p_input, "r", encoding="utf-8") as f:
        d_input = json.load(f)
    cr = d_input.get("chunk_reasoning", {})
    clr = d_input.get("cluster_reasoning", {})
    print(f"5. 13_claude_input: packaged {len(cr)} chunks with ambiguities/risk, {len(clr)} clusters")

# Step 6: 14_claude_verification
p_verif = job_dir / "14_claude_verification" / "claude_verification.json"
if p_verif.exists():
    with open(p_verif, "r", encoding="utf-8") as f:
        d_verif = json.load(f)
    vf = d_verif.get("verified_findings", [])
    print(f"6. 14_claude_verification total verified findings: {len(vf)}")
    statuses = {}
    rej_reasons = {}
    for item in vf:
        st = item.get("status")
        statuses[st] = statuses.get(st, 0) + 1
        rr = item.get("rejection_reason") or item.get("reject_reason") or "N/A"
        rej_reasons[rr] = rej_reasons.get(rr, 0) + 1
    print(f"   Statuses: {json.dumps(statuses, indent=2)}")
    print(f"   Rejection reasons: {json.dumps(rej_reasons, indent=2)}")

# Step 7: 15_final_report
p_final = job_dir / "15_final_report" / "final_report.json"
if p_final.exists():
    with open(p_final, "r", encoding="utf-8") as f:
        d_final = json.load(f)
    ef = d_final.get("executive_findings", [])
    rf = d_final.get("rejected_findings", [])
    print(f"7. 15_final_report: executive_findings: {len(ef)}, rejected_findings: {len(rf)}")
