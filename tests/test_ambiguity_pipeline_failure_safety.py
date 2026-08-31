"""
test_ambiguity_pipeline_failure_safety.py
==========================================
Regression tests for the "0 findings must be distinguishable from analysis
could not be completed" requirement.

Every stage of the ambiguity/Claude-verification chain
(ambiguity_extractor -> ambiguity_chunk_analyzer -> ambiguity_cluster_analyzer
-> claude/verification_service -> final_report_generator) used to respond to
a missing required upstream input file with `logger.error(...); return`
instead of raising. Since stage_orchestrator.run_stage_6_context() calls
these in sequence inside a single try/except with no per-call return-value
checks, a failure anywhere in the chain (an incomplete extraction, a failed
LLM call, a missing intermediate artifact) used to propagate as silence all
the way to the UI: the stage got marked "Completed" and the final report
showed zero findings -- indistinguishable from a document that genuinely
has no ambiguities.

These tests verify each stage now raises instead, so the orchestrator's
try/except correctly marks the stage "Failed" rather than "Completed".
"""
import pytest

from src.rag.ambiguity_extractor import AmbiguityExtractor
from src.rag.ambiguity_chunk_analyzer import AmbiguityChunkAnalyzer
from src.rag.ambiguity_cluster_analyzer import AmbiguityClusterAnalyzer
from src.rag.claude.verification_service import ClaudeVerificationService
from src.rag.final_report_generator import FinalReportGenerator


def test_claim_extraction_raises_when_no_chunks_available(tmp_path):
    with pytest.raises(RuntimeError, match="AMBIGUITY PIPELINE INCOMPLETE"):
        AmbiguityExtractor().run_extraction(tmp_path, "job1")


def test_chunk_analysis_raises_when_claims_missing(tmp_path):
    with pytest.raises(RuntimeError, match="AMBIGUITY PIPELINE INCOMPLETE"):
        AmbiguityChunkAnalyzer().run_analysis(tmp_path, "job1")


def test_cluster_analysis_raises_when_clusters_missing(tmp_path):
    with pytest.raises(RuntimeError, match="AMBIGUITY PIPELINE INCOMPLETE"):
        AmbiguityClusterAnalyzer().run_analysis(tmp_path, "job1")


def test_cluster_analysis_raises_when_claims_missing_but_clusters_present(tmp_path):
    clusters_dir = tmp_path / "09_semantic_clusters"
    clusters_dir.mkdir(parents=True)
    (clusters_dir / "semantic_clusters.json").write_text('{"clusters": []}', encoding="utf-8")
    with pytest.raises(RuntimeError, match="AMBIGUITY PIPELINE INCOMPLETE"):
        AmbiguityClusterAnalyzer().run_analysis(tmp_path, "job1")


def test_claude_verification_raises_when_input_missing(tmp_path):
    with pytest.raises(RuntimeError, match="AMBIGUITY PIPELINE INCOMPLETE"):
        ClaudeVerificationService().run_verification(tmp_path, "job1")


def test_final_report_raises_when_claude_response_missing(tmp_path):
    with pytest.raises(RuntimeError, match="AMBIGUITY PIPELINE INCOMPLETE"):
        FinalReportGenerator().generate_report(tmp_path, "job1")
