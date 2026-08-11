import json
from pathlib import Path

job_dir = Path("data/output/cff0427c29e541d496d067247fba5c52")

# 1. Inspect 14_claude_verification/claude_verification.json
p_verif = job_dir / "14_claude_verification" / "claude_verification.json"
if p_verif.exists():
    with open(p_verif, "r", encoding="utf-8") as f:
        d_verif = json.load(f)
    print("14_claude_verification keys:", list(d_verif.keys()))
    vf = d_verif.get("verified_findings", [])
    print(f"Total findings in verified_findings: {len(vf)}")
    if vf:
        print("Sample 3 verified_findings:")
        print(json.dumps(vf[:3], indent=2))

# 2. Inspect 15_final_report/final_report.json
p_final = job_dir / "15_final_report" / "final_report.json"
if p_final.exists():
    with open(p_final, "r", encoding="utf-8") as f:
        d_final = json.load(f)
    print("\n15_final_report keys:", list(d_final.keys()))
    print("rejected_findings count:", len(d_final.get("rejected_findings", [])))
    if d_final.get("rejected_findings"):
        print("Sample 3 rejected_findings in final_report.json:")
        print(json.dumps(d_final.get("rejected_findings")[:3], indent=2))
