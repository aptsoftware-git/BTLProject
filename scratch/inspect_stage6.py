import json
from pathlib import Path

job_dir = Path("data/output/cff0427c29e541d496d067247fba5c52")

print("=== STAGE 6 INSPECTION FOR JOB cff0427c29e541d496d067247fba5c52 ===")

# 1. 06_chunks
p = job_dir / "06_chunks" / "document_chunks.json"
if p.exists():
    with open(p, "r", encoding="utf-8") as f:
        d = json.load(f)
    print(f"06_chunks: {len(d.get('chunks', []))} chunks")

# 2. 10_claim_extraction
p = job_dir / "10_claim_extraction" / "chunk_claims.json"
if p.exists():
    with open(p, "r", encoding="utf-8") as f:
        d = json.load(f)
    chunks_with_claims = len(d.get("chunks", []))
    total_claims = sum(len(c.get("claims", [])) for c in d.get("chunks", []))
    print(f"10_claim_extraction (chunk_claims.json): {chunks_with_claims} chunks processed, {total_claims} total claims extracted")

p = job_dir / "10_claim_extraction" / "claim_index.json"
if p.exists():
    with open(p, "r", encoding="utf-8") as f:
        d = json.load(f)
    print(f"10_claim_extraction (claim_index.json): {len(d)} claims in index")

# 3. 11_chunk_reasoning
p = job_dir / "11_chunk_reasoning" / "chunk_reasoning.json"
if p.exists():
    with open(p, "r", encoding="utf-8") as f:
        d = json.load(f)
    chunks_reasoned = len(d.get("chunks", []))
    ambs_chunk = sum(len(c.get("ambiguities", [])) for c in d.get("chunks", []) if isinstance(c, dict))
    print(f"11_chunk_reasoning (chunk_reasoning.json): {chunks_reasoned} chunks evaluated, {ambs_chunk} chunk-level ambiguities flagged")

p = job_dir / "11_chunk_reasoning" / "ambiguity_index.json"
if p.exists():
    with open(p, "r", encoding="utf-8") as f:
        d = json.load(f)
    print(f"11_chunk_reasoning (ambiguity_index.json): {len(d)} ambiguities in index")

# 4. 12_cluster_reasoning
p = job_dir / "12_cluster_reasoning" / "cluster_reasoning.json"
if p.exists():
    with open(p, "r", encoding="utf-8") as f:
        d = json.load(f)
    clusters_count = len(d)
    cluster_findings = sum(len(c.get("cluster_findings", [])) for c in d.values() if isinstance(c, dict))
    print(f"12_cluster_reasoning (cluster_reasoning.json): {clusters_count} clusters evaluated, {cluster_findings} cluster findings flagged")

# 5. 13_claude_input
p = job_dir / "13_claude_input" / "claude_input.json"
if p.exists():
    with open(p, "r", encoding="utf-8") as f:
        d = json.load(f)
    print(f"13_claude_input (claude_input.json): packaged payload present (chunks: {len(d.get('chunk_reasoning', {}))}, clusters: {len(d.get('cluster_reasoning', {}))})")

# 6. 14_claude_verification
p = job_dir / "14_claude_verification" / "claude_verification.json"
if p.exists():
    with open(p, "r", encoding="utf-8") as f:
        d = json.load(f)
    vf = d.get("verified_findings", [])
    conf = [x for x in vf if x.get("status") == "confirmed"]
    rej = [x for x in vf if x.get("status") == "rejected"]
    print(f"14_claude_verification (claude_verification.json): {len(vf)} total findings ({len(conf)} confirmed, {len(rej)} rejected)")

# 7. 15_final_report
p = job_dir / "15_final_report" / "final_report.json"
if p.exists():
    with open(p, "r", encoding="utf-8") as f:
        d = json.load(f)
    exec_findings = d.get("executive_findings", [])
    print(f"15_final_report (final_report.json): {len(exec_findings)} executive findings in final_report.json")
    if exec_findings:
        print("FINDINGS IN FINAL REPORT:")
        print(json.dumps(exec_findings, indent=2))
