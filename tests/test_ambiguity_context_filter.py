"""
test_ambiguity_context_filter.py
===================================
Regression tests for the deterministic context-awareness guard
(src/rag/ambiguity_context_filter.py): legitimate reporting-period changes
and unit/scale conversions must not be reported as conflicts, per the
audit's identified false-positive risks (FY2023 vs FY2024, crore vs
million).
"""

from src.rag.ambiguity_context_filter import is_context_conflict_plausible


def test_different_reporting_periods_rejected_as_false_positive():
    finding = {
        "category": "Numerical inconsistency",
        "evidence": [
            {"quote": "FY2023 revenue was $10 million"},
            {"quote": "FY2024 revenue was $15 million"},
        ],
    }
    plausible, reason = is_context_conflict_plausible(finding)
    assert plausible is False
    assert "reporting periods" in reason


def test_unit_scale_equivalent_values_rejected_as_false_positive():
    finding = {
        "category": "Numerical inconsistency",
        "evidence": [
            {"quote": "Investment of 1.2 crore was made"},
            {"quote": "Investment of 12 million was made"},
        ],
    }
    plausible, reason = is_context_conflict_plausible(finding)
    assert plausible is False
    assert "numerically equivalent" in reason


def test_genuine_same_period_conflict_passes():
    finding = {
        "category": "Numerical inconsistency",
        "evidence": [
            {"quote": "FY2024 revenue was $10 million"},
            {"quote": "FY2024 revenue was $50 million"},
        ],
    }
    plausible, reason = is_context_conflict_plausible(finding)
    assert plausible is True
    assert reason is None


def test_non_context_sensitive_category_passes_through():
    finding = {
        "category": "Terminology inconsistency",
        "evidence": [
            {"quote": "FY2023 uses term A"},
            {"quote": "FY2024 uses term B"},
        ],
    }
    plausible, reason = is_context_conflict_plausible(finding)
    assert plausible is True


def test_single_evidence_item_passes_through():
    finding = {"category": "Numerical inconsistency", "evidence": [{"quote": "FY2024 revenue was $10 million"}]}
    plausible, reason = is_context_conflict_plausible(finding)
    assert plausible is True
