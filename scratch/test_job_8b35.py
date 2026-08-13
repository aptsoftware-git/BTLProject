import sys, os
sys.path.insert(0, os.path.abspath("."))

from pathlib import Path
import json
import backend.services as services
from src.stage_orchestrator import StageOrchestrator, initialize_job_stages

job_id = "8b35ab6d7934469b929f6155c6f0fa04"
services.CURRENT_JOB_ID = job_id

job_dir = Path("data/output") / job_id
job_dir.mkdir(parents=True, exist_ok=True)
input_file = Path("data/input/8b35ab6d7934469b929f6155c6f0fa04_LT_Company_Brochure.pdf")

# Register job in memory
services.JOBS[job_id] = {
    "job_id": job_id,
    "filename": "LT_Company_Brochure.pdf",
    "file_path": str(input_file.resolve()),
    "status": "processing",
    "current_stage": "Document Content Extraction",
    "stages": initialize_job_stages(),
    "created_at": "2026-08-13T12:00:00"
}
services.save_job_metadata(job_id)

orchestrator = StageOrchestrator(job_id, job_dir, input_file)

print("--- Running Stage 1 Upload ---")
orchestrator.run_stage_1_upload()

print("--- Running Stage 2 Extraction ---")
orchestrator.run_stage_2_extraction()

print("--- Running Stage 3 Spell ---")
orchestrator.run_stage_3_spell()

print("--- Running Stage 4 Grammar (Forced Regenerate) ---")
orchestrator.run_stage_4_grammar(force_regenerate=True)

print("\n=== STAGE EXECUTION VERIFICATION ===")
metadata_path = job_dir / "metadata.json"
with open(metadata_path, "r", encoding="utf-8") as f:
    meta = json.load(f)

print("Proofreading Status:", meta.get("proofreading_status"))
print("Proofreading Ready:", meta.get("proofreading_ready"))
print("Job Status:", meta.get("status"))

grammar_cand_path = job_dir / "07_grammar" / "grammar_candidates.json"
accepted_path = job_dir / "08_validation" / "accepted.json"
semantic_path = job_dir / "09_semantic" / "semantic_failed.json"
report_path = job_dir / "10_final" / "report.json"
mapped_findings_path = job_dir / "10_final" / "mapped_findings.json"

print("07_grammar/grammar_candidates.json exists:", grammar_cand_path.exists())
print("08_validation/accepted.json exists:", accepted_path.exists())
print("09_semantic/semantic_failed.json exists:", semantic_path.exists())
print("10_final/report.json exists:", report_path.exists())
print("10_final/mapped_findings.json exists:", mapped_findings_path.exists())

if mapped_findings_path.exists():
    with open(mapped_findings_path, "r", encoding="utf-8") as f:
        findings = json.load(f)
    print(f"Total Mapped Findings: {len(findings)}")
    grounded = [f for f in findings if f.get("pdf_grounded") and f.get("bbox")]
    print(f"PDF Grounded Findings: {len(grounded)}")
    if findings:
        for idx, sample in enumerate(findings[:5]):
            print(f"  Finding {idx+1}: '{sample.get('original')}' -> '{sample.get('suggestion')}' | Page {sample.get('page_number')} | Bbox: {sample.get('bbox')}")
