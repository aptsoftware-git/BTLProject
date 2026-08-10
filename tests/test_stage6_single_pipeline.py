"""
test_stage6_single_pipeline.py
=================================
Regression test locking in that Stage 6 (Ambiguity / Context Analysis) runs
only the single primary pipeline (semantic clustering -> claim extraction ->
chunk/cluster reasoning -> Claude verification -> final report), and no
longer also runs the redundant, independently-scored ContextAnalysisPipeline
("System A") the audit found duplicated the same LLM work with an
unaligned category taxonomy.
"""

import inspect

from src.stage_orchestrator import StageOrchestrator


def test_stage6_does_not_invoke_context_analysis_pipeline():
    source = inspect.getsource(StageOrchestrator.run_stage_6_context)
    # A code comment may still reference the retired pipeline by name for
    # context; what must be absent is any actual import or instantiation.
    assert "import ContextAnalysisPipeline" not in source
    assert "ContextAnalysisPipeline(" not in source


def test_stage6_still_invokes_the_primary_ambiguity_pipeline_chain():
    source = inspect.getsource(StageOrchestrator.run_stage_6_context)
    for expected in [
        "AmbiguityPipeline",
        "AmbiguityExtractor",
        "AmbiguityChunkAnalyzer",
        "AmbiguityClusterAnalyzer",
        "ClaudeInputBuilder",
        "ClaudeVerificationService",
        "FinalReportGenerator",
    ]:
        assert expected in source, f"Stage 6 must still invoke {expected}"


def test_stage6_cache_check_uses_final_report_json_not_system_a_report():
    source = inspect.getsource(StageOrchestrator.run_stage_6_context)
    assert '"15_final_report" / "final_report.json"' in source
