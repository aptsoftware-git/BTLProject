import sys, os
sys.path.insert(0, os.path.abspath("."))

from pathlib import Path
import json
import backend.services as services
from src.stage_orchestrator import StageOrchestrator, initialize_job_stages

job_id = "cff0427c29e541d496d067247fba5c52"
services.CURRENT_JOB_ID = job_id

job_dir = Path("data/output") / job_id
input_file = Path("data/input/cff0427c29e541d496d067247fba5c52_BTL AR SS 09-10-2025 (c2c).pdf")
if not input_file.exists():
    input_file = Path("data/input/BTL AR SS 09-10-2025 (c2c).pdf")

# Register job in memory
services.JOBS[job_id] = {
    "job_id": job_id,
    "filename": "BTL AR SS 09-10-2025 (c2c).pdf",
    "file_path": str(input_file.resolve()),
    "status": "processing",
    "current_stage": "Stage 6 Context Analysis",
    "stages": initialize_job_stages(),
    "created_at": "2026-08-13T12:00:00"
}
services.save_job_metadata(job_id)

orchestrator = StageOrchestrator(job_id, job_dir, input_file)

print(f"=== RUNNING STAGE 6 FOR REAL 216-PAGE DOCUMENT: {job_id} ===")
orchestrator.run_stage_6_context(force_regenerate=True)

print("\n=== STAGE 6 ARTIFACT & STAGE VERIFICATION ===")
dirs_to_verify = [
    "09_semantic_clusters",
    "10_claim_extraction",
    "11_chunk_reasoning",
    "12_cluster_reasoning",
    "13_claude_input",
    "14_claude_verification",
    "15_final_report"
]

for d in dirs_to_verify:
    dp = job_dir / d
    exists = dp.exists()
    file_count = len(list(dp.glob("*"))) if exists else 0
    print(f"Directory '{d}': exists={exists}, files={file_count}")

final_report_json = job_dir / "15_final_report" / "final_report.json"
rejected_json = job_dir / "15_final_report" / "rejected_candidates.json"

print(f"\nfinal_report.json exists: {final_report_json.exists()}")
print(f"rejected_candidates.json exists: {rejected_json.exists()}")

if final_report_json.exists():
    with open(final_report_json, "r", encoding="utf-8") as f:
        rep_data = json.load(f)
    
    verified_findings = rep_data.get("findings", [])
    rejected_findings = rep_data.get("rejected_findings", [])
    
    print(f"\n--- FINDINGS SUMMARY ---")
    print(f"Verified Findings Count: {len(verified_findings)}")
    print(f"Rejected Candidates Count: {len(rejected_findings)}")
    
    from collections import Counter
    taxonomy_counts = Counter(f.get("category") for f in verified_findings)
    print("\nTaxonomy Breakdown (Verified Findings):")
    for cat, count in taxonomy_counts.items():
        print(f"  - {cat}: {count}")

    print("\nSample Verified Findings:")
    for idx, vf in enumerate(verified_findings[:3], start=1):
        print(f"  {idx}. [{vf.get('severity')}] {vf.get('category')} | Page {vf.get('page_number')} - '{vf.get('title')}'")
        print(f"     Quote: \"{vf.get('highlighted_ambiguity', '')[:90]}...\"")
        print(f"     Location: {vf.get('location_display')}")

    print("\nSample Rejected Candidates & Reasons:")
    for idx, rf in enumerate(rejected_findings[:3], start=1):
        print(f"  {idx}. Category: {rf.get('category') or rf.get('business_category')}")
        print(f"     Reject Reason: {rf.get('reject_reason')}")
