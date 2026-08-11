import json
from pathlib import Path

job_dir = Path("data/output/cff0427c29e541d496d067247fba5c52")

print("=================================================================")
print("STAGE 6 AMBIGUITY ANALYSIS FULL ARTIFACT AUDIT REPORT")
print("Job ID: cff0427c29e541d496d067247fba5c52")
print("=================================================================\n")

# 1. 06_chunks/
p_06 = job_dir / "06_chunks" / "document_chunks.json"
chunks_06_count = 0
if p_06.exists():
    with open(p_06, "r", encoding="utf-8") as f:
        d_06 = json.load(f)
    chunks_06_count = len(d_06.get("chunks", []))
print(f"1. 06_chunks/document_chunks.json: {chunks_06_count} chunks")

# 2. 10_claim_extraction/
p_10_claims = job_dir / "10_claim_extraction" / "chunk_claims.json"
p_10_idx = job_dir / "10_claim_extraction" / "claim_index.json"
claims_chunks_count = 0
claims_total = 0
claim_idx_count = 0
if p_10_claims.exists():
    with open(p_10_claims, "r", encoding="utf-8") as f:
        d_10 = json.load(f)
    claims_chunks_count = len(d_10.get("chunks", []))
    claims_total = sum(len(c.get("extraction", {}).get("claims", [])) for c in d_10.get("chunks", []))
if p_10_idx.exists():
    with open(p_10_idx, "r", encoding="utf-8") as f:
        d_idx = json.load(f)
    claim_idx_count = len(d_idx)

print(f"2. 10_claim_extraction/: {claims_chunks_count} chunks processed, {claims_total} claims extracted ({claim_idx_count} in claim_index.json)")

# 3. 11_chunk_reasoning/
p_11_reason = job_dir / "11_chunk_reasoning" / "chunk_reasoning.json"
p_11_amb_idx = job_dir / "11_chunk_reasoning" / "ambiguity_index.json"
chunk_reasoned_count = 0
chunk_ambiguities_flagged = 0
if p_11_reason.exists():
    with open(p_11_reason, "r", encoding="utf-8") as f:
        d_11 = json.load(f)
    chunk_reasoned_count = len(d_11.get("chunks", []))
    chunk_ambiguities_flagged = sum(len(c.get("ambiguities", [])) for c in d_11.get("chunks", []) if isinstance(c, dict))
print(f"3. 11_chunk_reasoning/: {chunk_reasoned_count} chunks evaluated, {chunk_ambiguities_flagged} chunk-level ambiguity items in chunk_reasoning.json")

# 4. 12_cluster_reasoning/
p_12 = job_dir / "12_cluster_reasoning" / "cluster_reasoning.json"
clusters_count = 0
cluster_findings_count = 0
cluster_findings_list = []
if p_12.exists():
    with open(p_12, "r", encoding="utf-8") as f:
        d_12 = json.load(f)
    clusters_count = len(d_12)
    for clid, cl in d_12.items():
        if isinstance(cl, dict):
            finds = cl.get("cluster_findings", [])
            cluster_findings_count += len(finds)
            cluster_findings_list.extend(finds)
print(f"4. 12_cluster_reasoning/: {clusters_count} clusters evaluated, {cluster_findings_count} cluster findings flagged")

# 5. 13_claude_input/
p_13 = job_dir / "13_claude_input" / "claude_input.json"
input_chunks_count = 0
input_clusters_count = 0
if p_13.exists():
    with open(p_13, "r", encoding="utf-8") as f:
        d_13 = json.load(f)
    input_chunks_count = len(d_13.get("chunk_reasoning", {}))
    input_clusters_count = len(d_13.get("cluster_reasoning", {}))
print(f"5. 13_claude_input/: packaged payload with {input_chunks_count} chunks and {input_clusters_count} clusters")

# 6. 14_claude_verification/
p_14 = job_dir / "14_claude_verification" / "claude_response.json"
verified_count = 0
confirmed_count = 0
rejected_count = 0
verified_findings_list = []
if p_14.exists():
    with open(p_14, "r", encoding="utf-8") as f:
        d_14 = json.load(f)
    verified_findings_list = d_14.get("verified_findings", [])
    verified_count = len(verified_findings_list)
    confirmed_count = sum(1 for item in verified_findings_list if item.get("status") == "confirmed")
    rejected_count = sum(1 for item in verified_findings_list if item.get("status") == "rejected")
print(f"6. 14_claude_verification/claude_response.json: {verified_count} findings ({confirmed_count} confirmed, {rejected_count} rejected)")

# 7. 15_final_report/final_report.json
p_15 = job_dir / "15_final_report" / "final_report.json"
final_exec_count = 0
final_rejected_count = 0
final_exec_findings = []
final_rejected_findings = []
if p_15.exists():
    with open(p_15, "r", encoding="utf-8") as f:
        d_15 = json.load(f)
    final_exec_findings = d_15.get("executive_findings", [])
    final_rejected_findings = d_15.get("rejected_findings", [])
    final_exec_count = len(final_exec_findings)
    final_rejected_count = len(final_rejected_findings)

print(f"7. 15_final_report/final_report.json: {final_exec_count} executive findings, {final_rejected_count} rejected findings\n")

print("=================================================================")
print("DETAILED ANALYSIS OF CANDIDATE FINDINGS AND REJECTIONS")
print("=================================================================")

if cluster_findings_list:
    print(f"\n[12_cluster_reasoning] Candidate Cluster Findings ({len(cluster_findings_list)}):")
    for idx, cf in enumerate(cluster_findings_list, 1):
        print(f"  Candidate {idx}: ID={cf.get('issue_id')}, Type={cf.get('type')}")
        print(f"    Description: {cf.get('description')}")
        print(f"    Reason: {cf.get('reason')}")
        print(f"    Evidence ({len(cf.get('evidence', []))} quotes):")
        for ev in cf.get('evidence', []):
            print(f"      - [{ev.get('chunk_id')}]: \"{ev.get('quote')}\"")

if verified_findings_list:
    print(f"\n[14_claude_verification] Verified Findings List ({len(verified_findings_list)}):")
    for idx, vf in enumerate(verified_findings_list, 1):
        print(f"  Finding {idx}: ID={vf.get('issue_id')}, Status={vf.get('status')}, Raw Cat={vf.get('raw_category')}")
        print(f"    Explanation: {vf.get('explanation')}")

if final_rejected_findings:
    print(f"\n[15_final_report] Rejections in final_report.json ({len(final_rejected_findings)}):")
    for idx, rf in enumerate(final_rejected_findings, 1):
        print(f"  Rejected {idx}: ID={rf.get('issue_id')}")
        print(f"    Reject Reason: {rf.get('reject_reason')}")
        print(f"    Explanation: {rf.get('explanation')}")
