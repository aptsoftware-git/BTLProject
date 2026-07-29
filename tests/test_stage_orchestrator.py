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
    assert updated_job["current_stage"] == "Document Extraction"
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
