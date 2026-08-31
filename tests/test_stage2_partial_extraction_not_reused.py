"""
test_stage2_partial_extraction_not_reused.py
=============================================
Regression test for the "image/page count gets permanently stuck after a
mid-extraction crash" bug.

multimodal_extractor.extract() persists 02_docling/structured_document.json
incrementally after every page batch (for crash-resume), but only writes
03_knowledge_objects/knowledge_objects.json once, at the very end, after
every batch succeeds. StageOrchestrator._get_or_build_structured_document
used to reuse structured_document.json purely because it existed -- so any
transient failure partway through a large document (a NameError, an Ollama
timeout, an OOM) left a partial file that got silently served as "the whole
document" on the next attempt, forever, since nothing ever re-triggered a
real extraction after that.

These tests verify: a partial structured_document.json (no
knowledge_objects.json alongside it) is never reused as-is -- extract() must
be invoked again to resume and complete it -- while a genuinely complete
pair (both files present) is still reused as a real cache hit, without
paying to re-run extraction on every stage retry.
"""
import json
from unittest.mock import patch, MagicMock

from src.stage_orchestrator import StageOrchestrator


def _make_orchestrator(job_dir):
    return StageOrchestrator(job_id="job1", job_dir=job_dir, file_path=job_dir / "input.pdf")


def test_partial_structured_document_without_knowledge_objects_triggers_reextraction(tmp_path):
    docling_dir = tmp_path / "02_docling"
    docling_dir.mkdir(parents=True)
    # Only 15 of 216 pages made it in before the crash.
    (docling_dir / "structured_document.json").write_text(
        json.dumps({"title": "t", "file_name": "t", "file_type": "pdf", "page_count": 15,
                    "elements": [], "tables": {}, "images": {}}),
        encoding="utf-8",
    )
    # knowledge_objects.json deliberately absent -- extraction never finished.

    orch = _make_orchestrator(tmp_path)

    fake_master_doc = MagicMock()
    fake_master_doc.model_dump.return_value = {"page_count": 216, "elements": [], "tables": {}, "images": {}}

    with patch("src.rag.multimodal_extractor.MultimodalExtractor") as MockExtractor:
        MockExtractor.return_value.extract.return_value = ("raw text", fake_master_doc, 216)
        result = orch._get_or_build_structured_document()

    MockExtractor.return_value.extract.assert_called_once()
    assert result["page_count"] == 216, "must return the freshly completed extraction, not the stale partial one"


def test_complete_pair_is_reused_without_reextraction(tmp_path):
    docling_dir = tmp_path / "02_docling"
    docling_dir.mkdir(parents=True)
    ko_dir = tmp_path / "03_knowledge_objects"
    ko_dir.mkdir(parents=True)

    (docling_dir / "structured_document.json").write_text(
        json.dumps({"title": "t", "file_name": "t", "file_type": "pdf", "page_count": 216,
                    "elements": [], "tables": {}, "images": {}}),
        encoding="utf-8",
    )
    (ko_dir / "knowledge_objects.json").write_text(json.dumps([{"id": 1}]), encoding="utf-8")

    orch = _make_orchestrator(tmp_path)

    with patch("src.rag.multimodal_extractor.MultimodalExtractor") as MockExtractor:
        result = orch._get_or_build_structured_document()

    MockExtractor.return_value.extract.assert_not_called()
    assert result["page_count"] == 216
