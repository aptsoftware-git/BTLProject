import json
from pathlib import Path

job_dir = Path("data/output/cff0427c29e541d496d067247fba5c52")

# Inspect 11_chunk_reasoning ambiguities
cr_path = job_dir / "11_chunk_reasoning" / "chunk_reasoning.json"
amb_sample = []
if cr_path.exists():
    with open(cr_path, "r", encoding="utf-8") as f:
        d = json.load(f)
    for c in d.get("chunks", []):
        if isinstance(c, dict):
            for amb in c.get("ambiguities", []):
                amb_sample.append(amb)

print(f"Total chunk ambiguities in 11_chunk_reasoning: {len(amb_sample)}")
if amb_sample:
    print("Sample 5 chunk ambiguities from 11_chunk_reasoning:")
    print(json.dumps(amb_sample[:5], indent=2))

# Inspect 14_claude_verification
cv_path = job_dir / "14_claude_verification" / "claude_verification.json"
if cv_path.exists():
    with open(cv_path, "r", encoding="utf-8") as f:
        d = json.load(f)
    vf = d.get("verified_findings", [])
    print(f"\nTotal findings in 14_claude_verification: {len(vf)}")
    rejection_reasons = {}
    for f in vf:
        status = f.get("status")
        reason = f.get("rejection_reason") or f.get("reject_reason") or status
        rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1
    print("Rejection reasons summary:", json.dumps(rejection_reasons, indent=2))
    
    rejected_sample = [f for f in vf if f.get("status") == "rejected"]
    if rejected_sample:
        print("\nSample 5 rejected findings in 14_claude_verification:")
        print(json.dumps(rejected_sample[:5], indent=2))

# Inspect rejection audit
ra_path = job_dir / "14_claude_verification" / "rejection_audit.json"
if ra_path.exists():
    with open(ra_path, "r", encoding="utf-8") as f:
        d = json.load(f)
    print("\nrejection_audit.json:", json.dumps(d, indent=2))

# Inspect final report generator rejection log / reasoning
fr_path = job_dir / "15_final_report" / "final_report.json"
if fr_path.exists():
    with open(fr_path, "r", encoding="utf-8") as f:
        d = json.load(f)
    print("\nfinal_report.json keys:", list(d.keys()))
    print("rejection_audit in final_report:", json.dumps(d.get("rejection_audit", {}), indent=2))
