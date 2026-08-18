"""
test_merge_agent_regression.py
==============================
Regression tests for MergeAgent ensuring safe merging across:
  1. spelling-only groups
  2. grammar-only groups (Gramformer / LLM without SymSpell)
  3. mixed spelling + grammar groups
  4. empty / invalid groups
"""

import pytest
from src.config import MergeConfig
from src.merge_agent import MergeAgent
from src.models import IssueType, MergedIssue, SourceAgent, ValidatedIssue


@pytest.fixture
def merge_agent():
    return MergeAgent(MergeConfig())


def make_issue(
    char_start: int,
    char_end: int,
    original_text: str,
    suggested_text: str,
    issue_type: IssueType = IssueType.GRAMMAR,
    source: SourceAgent = SourceAgent.GRAMFORMER,
    confidence: float = 0.85,
    sentence_id: int = 1,
    page_number: int = 1,
    is_protected: bool = False,
) -> ValidatedIssue:
    return ValidatedIssue(
        sentence_id=sentence_id,
        char_start=char_start,
        char_end=char_end,
        original_text=original_text,
        suggested_text=suggested_text,
        issue_type=issue_type,
        source=source,
        reason="Test reason",
        confidence=confidence,
        page_number=page_number,
        is_protected=is_protected,
    )


def test_merge_spelling_only_group(merge_agent):
    """Case 1: Spelling-only groups (e.g. SymSpell) merge safely."""
    issues = [
        make_issue(10, 18, "occuring", "occurring", IssueType.SPELLING, SourceAgent.SYMSPELL, 0.7),
    ]
    merged = merge_agent.merge(issues)
    assert len(merged) == 1
    assert merged[0].original_text == "occuring"
    assert merged[0].suggested_text == "occurring"
    assert merged[0].source == SourceAgent.SYMSPELL
    assert merged[0].agreement_count == 1
    assert merged[0].final_confidence > 0.0


def test_merge_grammar_only_group_gramformer(merge_agent):
    """Case 2: Grammar-only groups (Gramformer only, no SymSpell) must not raise IndexError."""
    issues = [
        make_issue(50, 53, "are", "is", IssueType.GRAMMAR, SourceAgent.GRAMFORMER, 0.85),
    ]
    merged = merge_agent.merge(issues)
    assert len(merged) == 1
    assert merged[0].original_text == "are"
    assert merged[0].suggested_text == "is"
    assert merged[0].source == SourceAgent.GRAMFORMER
    assert merged[0].agreement_count == 1
    assert merged[0].final_confidence == 0.85


def test_merge_grammar_only_multiple_agents(merge_agent):
    """Case 2b: Multiple grammar agents (Gramformer + LLM) agreeing on grammar fix."""
    issues = [
        make_issue(50, 53, "are", "is", IssueType.GRAMMAR, SourceAgent.GRAMFORMER, 0.85),
        make_issue(50, 53, "are", "is", IssueType.GRAMMAR, SourceAgent.LLM, 0.80),
    ]
    merged = merge_agent.merge(issues)
    assert len(merged) == 1
    assert merged[0].original_text == "are"
    assert merged[0].suggested_text == "is"
    assert merged[0].agreement_count == 2
    assert merged[0].final_confidence == 0.95
    assert set(merged[0].contributing_sources) == {SourceAgent.GRAMFORMER, SourceAgent.LLM}


def test_merge_mixed_spelling_and_grammar(merge_agent):
    """Case 3: Mixed spelling and grammar groups overlapping the same token span."""
    issues = [
        make_issue(100, 106, "submit", "submits", IssueType.SPELLING, SourceAgent.SYMSPELL, 0.5),
        make_issue(100, 106, "submit", "submitted", IssueType.GRAMMAR, SourceAgent.GRAMFORMER, 0.85),
    ]
    merged = merge_agent.merge(issues)
    assert len(merged) == 1
    # Gramformer suggestion preferred over SymSpell
    assert merged[0].original_text == "submit"
    assert merged[0].suggested_text == "submitted"
    assert merged[0].source == SourceAgent.GRAMFORMER
    assert set(merged[0].contributing_sources) == {SourceAgent.SYMSPELL, SourceAgent.GRAMFORMER}


def test_merge_empty_and_invalid_groups(merge_agent):
    """Case 4: Empty lists and empty groups return empty list without exceptions."""
    assert merge_agent.merge([]) == []
    assert merge_agent._merge_group([]) is None


def test_merge_preserves_non_overlapping_separate_issues(merge_agent):
    """Test that multiple independent spelling and grammar issues across a document are all preserved."""
    issues = [
        make_issue(10, 18, "occuring", "occurring", IssueType.SPELLING, SourceAgent.SYMSPELL, 0.7),
        make_issue(50, 53, "are", "is", IssueType.GRAMMAR, SourceAgent.GRAMFORMER, 0.85),
        make_issue(100, 106, "submit", "submitted", IssueType.GRAMMAR, SourceAgent.GRAMFORMER, 0.85),
    ]
    merged = merge_agent.merge(issues)
    assert len(merged) == 3
    assert [m.char_start for m in merged] == [10, 50, 100]
    assert [m.suggested_text for m in merged] == ["occurring", "is", "submitted"]
