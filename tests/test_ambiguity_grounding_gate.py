"""
test_ambiguity_grounding_gate.py
===================================
Regression tests for the programmatic evidence-grounding gate
(src/rag/ambiguity_grounding_gate.py). The audit found that grounding for
Ambiguity Analysis findings rested entirely on LLM self-report -- these
tests lock in that a finding is only accepted when its evidence quote is a
real, verifiable substring of the cited chunk's actual text.
"""

from src.rag.ambiguity_grounding_gate import verify_evidence

CHUNK_MAP = {
    "c1": {"text": "Revenue grew by 12% in FY2024 compared to the prior year."},
    "c2": {"text": "The board approved the budget in March 2024."},
}


def test_verbatim_quote_is_grounded():
    finding = {"evidence": [{"chunk_id": "c1", "quote": "Revenue grew by 12% in FY2024"}]}
    grounded, reason = verify_evidence(finding, CHUNK_MAP)
    assert grounded is True
    assert reason is None


def test_hallucinated_quote_is_rejected():
    finding = {"evidence": [{"chunk_id": "c1", "quote": "Revenue collapsed by 90% due to fraud"}]}
    grounded, reason = verify_evidence(finding, CHUNK_MAP)
    assert grounded is False
    assert "does not appear verbatim" in reason


def test_missing_evidence_list_is_rejected():
    finding = {"evidence": []}
    grounded, reason = verify_evidence(finding, CHUNK_MAP)
    assert grounded is False
    assert "no source location" in reason


def test_citing_nonexistent_chunk_id_is_rejected():
    finding = {"evidence": [{"chunk_id": "c99", "quote": "Revenue grew by 12% in FY2024"}]}
    grounded, reason = verify_evidence(finding, CHUNK_MAP)
    assert grounded is False
    assert "not found" in reason


def test_at_least_one_grounded_evidence_item_is_sufficient():
    finding = {
        "evidence": [
            {"chunk_id": "c1", "quote": "fabricated text"},
            {"chunk_id": "c2", "quote": "The board approved the budget in March 2024"},
        ]
    }
    grounded, reason = verify_evidence(finding, CHUNK_MAP)
    assert grounded is True


def test_fallback_to_top_level_chunk_id_and_highlighted_ambiguity():
    finding = {"chunk_id": "c1", "highlighted_ambiguity": "grew by 12% in FY2024"}
    grounded, reason = verify_evidence(finding, CHUNK_MAP)
    assert grounded is True


def test_whitespace_normalization_tolerance():
    finding = {"evidence": [{"chunk_id": "c1", "quote": "Revenue   grew by 12%   in FY2024"}]}
    grounded, _ = verify_evidence(finding, CHUNK_MAP)
    assert grounded is True
