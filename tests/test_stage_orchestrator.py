"""
test_stage_orchestrator.py
============================
Unit tests for the production-grade asynchronous StageOrchestrator engine.
Verifies stage initialization, execution tracking, state persistence, resumability, and error handling.
"""

import pytest
import json
from pathlib import Path
from src.stage_orchestrator import initialize_job_stages, StageOrchestrator
from backend.services import create_job, get_job, JOBS


def test_initialize_job_stages():
    stages = initialize_job_stages("2026-07-29T18:00:00")
    assert len(stages) == 8
    assert stages[0]["stage_id"] == "stage_1_upload"
    assert stages[0]["status"] == "Completed"
    assert stages[1]["stage_id"] == "stage_2_extraction"
    assert stages[1]["status"] == "Pending"


def test_stage_orchestrator_initialization(tmp_path):
    job_id = "test_job_123"
    dummy_file = tmp_path / "sample.pdf"
    dummy_file.write_text("Sample document text for test", encoding="utf-8")
    job_dir = tmp_path / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    # Initialize job in memory
    job = create_job("sample.pdf", dummy_file, job_id=job_id)
    assert job["job_id"] == job_id
    assert len(job["stages"]) == 8
    assert job["upload_ready"] is True

    orchestrator = StageOrchestrator(job_id, job_dir, dummy_file)
    orchestrator.update_stage_state("stage_2_extraction", "Running", start_time="2026-07-29T18:01:00")

    updated_job = get_job(job_id)
    assert updated_job["current_stage"] == "Document Content Extraction"
    assert updated_job["stages"][1]["status"] == "Running"

    orchestrator.update_stage_state(
        "stage_2_extraction",
        "Completed",
        end_time="2026-07-29T18:01:05",
        duration=5.0,
        output_location="structured_document.json"
    )

    updated_job = get_job(job_id)
    assert updated_job["stages"][1]["status"] == "Completed"
    assert updated_job["stages"][1]["duration"] == 5.0
    assert updated_job["overall_progress"] == 25  # 2 of 8 completed


def test_stage_3_and_4_execution_creates_spell_and_grammar_folders(tmp_path):
    job_id = "test_job_spell_grammar_folders"
    dummy_file = tmp_path / "sample.pdf"
    dummy_file.write_text("This is a sample document for testing stage folders.", encoding="utf-8")
    job_dir = tmp_path / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    # Setup 04_sentences/sentences.json
    sent_dir = job_dir / "04_sentences"
    sent_dir.mkdir(parents=True, exist_ok=True)
    sentences_data = [
        {
            "sentence_id": 1,
            "text": "The quick brown fox jumpss over the lazy dog.",
            "page": 1,
            "char_start": 0,
            "char_end": 45,
            "doc_char_start": 0,
            "doc_char_end": 45,
            "paragraph_id": 1
        },
        {
            "sentence_id": 2,
            "text": "Yesterday I goes to the office.",
            "page": 1,
            "char_start": 46,
            "char_end": 77,
            "doc_char_start": 46,
            "doc_char_end": 77,
            "paragraph_id": 1
        }
    ]
    (sent_dir / "sentences.json").write_text(json.dumps(sentences_data), encoding="utf-8")

    # Setup 05_protected_terms/protected_terms.json
    pt_dir = job_dir / "05_protected_terms"
    pt_dir.mkdir(parents=True, exist_ok=True)
    (pt_dir / "protected_terms.json").write_text(json.dumps([]), encoding="utf-8")

    # Setup 03_preprocessed/normalized_text.txt
    prep_dir = job_dir / "03_preprocessed"
    prep_dir.mkdir(parents=True, exist_ok=True)
    (prep_dir / "normalized_text.txt").write_text("The quick brown fox jumpss over the lazy dog. Yesterday I goes to the office.", encoding="utf-8")

    # Create job in memory
    job = create_job("sample.pdf", dummy_file, job_id=job_id)
    orchestrator = StageOrchestrator(job_id, job_dir, dummy_file)

    # Run Stage 3
    orchestrator.run_stage_3_spell()

    # Verify Stage 3 created 06_spell folder and artifacts
    spell_dir = job_dir / "06_spell"
    assert spell_dir.exists(), "06_spell directory was not created!"
    assert (spell_dir / "spell_candidates.json").exists(), "06_spell/spell_candidates.json missing!"
    assert (spell_dir / "filtered_spell_candidates.json").exists(), "06_spell/filtered_spell_candidates.json missing!"
    assert (spell_dir / "rejected_spell_candidates.json").exists(), "06_spell/rejected_spell_candidates.json missing!"

    # Verify Stage 3 also extracted grammar candidates for Stage 4
    grammar_dir = job_dir / "07_grammar"
    assert grammar_dir.exists(), "07_grammar directory was not created!"
    assert (grammar_dir / "grammar_candidates.json").exists(), "07_grammar/grammar_candidates.json missing!"

    # Run Stage 4
    orchestrator.run_stage_4_grammar()

    # Verify Stage 4 created grammar artifacts and final report
    assert (job_dir / "10_final" / "report.json").exists(), "10_final/report.json missing!"
    updated_job = get_job(job_id)
    assert updated_job["stages"][2]["status"] == "Completed", "Stage 3 did not complete!"
    assert updated_job["stages"][3]["status"] == "Completed", "Stage 4 did not complete!"

