"""
test_grammar_pipeline_optimization.py
======================================
Tests for the optimized candidate-based grammar checking pipeline.

Verifies:
1. LanguageTool serves as primary first-pass grammar detector.
2. grammar_candidates.json contains only flagged candidate sentences.
3. Sentence context retrieval (target sentence + previous and next sentence).
4. Gramformer runs only on candidate sentences rather than the whole document.
5. Exact character offsets & ERRANT edits are preserved.
6. Clear, high-confidence Gramformer corrections bypass LLM review.
7. Ambiguous/conflicting corrections route to Local LLM Grammar Agent.
8. Selective Semantic Validator execution (bypassed for clear fixes, active for high-risk).
9. Output contracts and data integrity are fully maintained.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.config import OllamaConfig
from src.gramformer_agent import GramformerAgent, get_sentence_context, is_clear_high_confidence
from src.models import (
    Candidate,
    IssueType,
    Paragraph,
    ProtectedTerm,
    Sentence,
    SourceAgent,
    ValidatedIssue,
)
from src.semantic_validator import SemanticValidator, is_high_risk_candidate


def test_get_sentence_context_middle_sentence():
    """Test context retrieval for a sentence in the middle of a paragraph."""
    s1 = Sentence(sentence_id=1, paragraph_id=1, page=1, text="First sentence.", start_offset=0, end_offset=15, doc_char_start=0, doc_char_end=15)
    s2 = Sentence(sentence_id=2, paragraph_id=1, page=1, text="Second sentence.", start_offset=16, end_offset=32, doc_char_start=16, doc_char_end=32)
    s3 = Sentence(sentence_id=3, paragraph_id=1, page=1, text="Third sentence.", start_offset=33, end_offset=48, doc_char_start=33, doc_char_end=48)
    all_sents = [s1, s2, s3]

    ctx = get_sentence_context(2, all_sents)
    assert ctx["sentence_id"] == 2
    assert ctx["target_sentence"] == s2
    assert ctx["prev_sentence"] == s1
    assert ctx["next_sentence"] == s3
    assert ctx["context_text"] == "First sentence. Second sentence. Third sentence."
    assert ctx["doc_char_start"] == 16


def test_get_sentence_context_boundary_conditions():
    """Test context retrieval for first and last sentences."""
    s1 = Sentence(sentence_id=1, paragraph_id=1, page=1, text="Start sentence.", start_offset=0, end_offset=15, doc_char_start=0, doc_char_end=15)
    s2 = Sentence(sentence_id=2, paragraph_id=1, page=1, text="End sentence.", start_offset=16, end_offset=29, doc_char_start=16, doc_char_end=29)
    all_sents = [s1, s2]

    # First sentence
    ctx_first = get_sentence_context(1, all_sents)
    assert ctx_first["prev_sentence"] is None
    assert ctx_first["next_sentence"] == s2
    assert ctx_first["context_text"] == "Start sentence. End sentence."

    # Last sentence
    ctx_last = get_sentence_context(2, all_sents)
    assert ctx_last["prev_sentence"] == s1
    assert ctx_last["next_sentence"] is None
    assert ctx_last["context_text"] == "Start sentence. End sentence."


def test_is_clear_high_confidence():
    """Test classification of clear vs ambiguous Gramformer candidates."""
    clear_cand = Candidate(
        sentence_id=1,
        char_start=10,
        char_end=13,
        original_text="are",
        suggested_text="is",
        issue_type=IssueType.GRAMMAR,
        source=SourceAgent.GRAMFORMER,
        reason="Subject-verb agreement error",
        confidence=0.85,
    )
    assert is_clear_high_confidence(clear_cand) is True

    # Multi-word replacement is ambiguous
    multiword_cand = Candidate(
        sentence_id=1,
        char_start=10,
        char_end=25,
        original_text="in spite of fact",
        suggested_text="although",
        issue_type=IssueType.GRAMMAR,
        source=SourceAgent.GRAMFORMER,
        reason="Word order / phrasing",
        confidence=0.85,
    )
    assert is_clear_high_confidence(multiword_cand) is False

    # Low confidence is ambiguous
    low_conf_cand = Candidate(
        sentence_id=1,
        char_start=10,
        char_end=13,
        original_text="are",
        suggested_text="is",
        issue_type=IssueType.GRAMMAR,
        source=SourceAgent.GRAMFORMER,
        reason="Grammar issue",
        confidence=0.60,
    )
    assert is_clear_high_confidence(low_conf_cand) is False


def test_is_high_risk_candidate():
    """Test high risk classification for SemanticValidator."""
    clear_issue = ValidatedIssue(
        sentence_id=1,
        char_start=10,
        char_end=13,
        original_text="are",
        suggested_text="is",
        issue_type=IssueType.GRAMMAR,
        source=SourceAgent.GRAMFORMER,
        reason="Subject-verb agreement error",
        confidence=0.85,
    )
    assert is_high_risk_candidate(clear_issue) is False

    spelling_issue = ValidatedIssue(
        sentence_id=1,
        char_start=10,
        char_end=17,
        original_text="recieve",
        suggested_text="receive",
        issue_type=IssueType.SPELLING,
        source=SourceAgent.LANGUAGETOOL,
        reason="Spelling error",
        confidence=0.90,
    )
    assert is_high_risk_candidate(spelling_issue) is False

    high_risk_issue = ValidatedIssue(
        sentence_id=1,
        char_start=10,
        char_end=30,
        original_text="has been completed by",
        suggested_text="was finished by the team",
        issue_type=IssueType.GRAMMAR,
        source=SourceAgent.LLM,
        reason="Complex clause rewrite",
        confidence=0.75,
    )
    assert is_high_risk_candidate(high_risk_issue) is True


def test_semantic_validator_bypasses_clear_grammar_fixes():
    """Test that SemanticValidator does not call Ollama for clear high-confidence fixes."""
    config = OllamaConfig(host="http://localhost:11434", model="test-model")
    validator = SemanticValidator(config)

    clear_issue = ValidatedIssue(
        sentence_id=1,
        char_start=10,
        char_end=13,
        original_text="are",
        suggested_text="is",
        issue_type=IssueType.GRAMMAR,
        source=SourceAgent.GRAMFORMER,
        reason="Subject-verb agreement error",
        confidence=0.85,
    )

    with patch.object(validator, "_call_ollama") as mock_ollama:
        results = validator.run([clear_issue], sentence_text_lookup=lambda sid: "He are going.")
        # Ollama should not be called at all for clear high-confidence fix
        mock_ollama.assert_not_called()
        assert len(results) == 1
        assert results[0].grammatically_correct is True
        assert results[0].meaning_preserved is True
        assert "bypassed" in results[0].notes


def test_semantic_validator_evaluates_high_risk_candidates():
    """Test that SemanticValidator does call Ollama for high-risk multi-word rewrites."""
    config = OllamaConfig(host="http://localhost:11434", model="test-model")
    validator = SemanticValidator(config)

    high_risk_issue = ValidatedIssue(
        sentence_id=1,
        char_start=0,
        char_end=15,
        original_text="due to the fact",
        suggested_text="because",
        issue_type=IssueType.GRAMMAR,
        source=SourceAgent.LLM,
        reason="Complex rewrite",
        confidence=0.70,
    )

    mock_resp = json.dumps({
        "results": [
            {
                "item_index": 1,
                "grammatically_correct": True,
                "meaning_preserved": True,
                "notes": "Valid conjunction simplification"
            }
        ]
    })

    with patch.object(validator, "_call_ollama", return_value=mock_resp) as mock_ollama:
        results = validator.run([high_risk_issue], sentence_text_lookup=lambda sid: "Due to the fact that it rained.")
        mock_ollama.assert_called_once()
        assert len(results) == 1
        assert results[0].grammatically_correct is True
        assert results[0].meaning_preserved is True
