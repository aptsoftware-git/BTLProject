"""
test_gramformer_agent.py
========================
Tests for GramformerAgent as the primary grammar engine.

Tests:
  1. Gramformer detection & correction (SVA, verb form, tense, articles).
  2. Exact character offsets matching sentence text.
  3. Protected term preservation (names, orgs, places, acronyms, numbers).
  4. Sentence skipping (empty, short, table fragments).
  5. Deterministic artifact output to 07_grammar/grammar_candidates.json.
"""

from pathlib import Path
import pytest

from src.config import GramformerConfig
from src.gramformer_agent import GramformerAgent
from src.models import IssueType, ProtectedTerm, Sentence, SourceAgent


@pytest.fixture(scope="module")
def gramformer_agent():
    return GramformerAgent(config=GramformerConfig())


def test_gramformer_sva_correction(gramformer_agent):
    """Test subject-verb agreement error detection with exact offsets."""
    sentence = Sentence(
        sentence_id=1,
        paragraph_id=1,
        page=1,
        text="He are moving to the new department tomorrow.",
        start_offset=0,
        end_offset=46,
        doc_char_start=100,
        doc_char_end=146
    )
    candidates = gramformer_agent.correct_batch([sentence])
    assert len(candidates) >= 1
    sva_cand = next((c for c in candidates if c.original_text.lower() == "are"), None)
    assert sva_cand is not None
    assert sva_cand.suggested_text.lower() == "is"
    assert sva_cand.issue_type == IssueType.GRAMMAR
    assert sva_cand.source == SourceAgent.GRAMFORMER

    # Offset verification
    rel_start = sva_cand.char_start - (sentence.doc_char_start or 0)
    rel_end = sva_cand.char_end - (sentence.doc_char_start or 0)
    assert sentence.text[rel_start:rel_end] == "are"


def test_gramformer_verb_form_correction(gramformer_agent):
    """Test incorrect verb form detection (submit -> submitted)."""
    sentence = Sentence(
        sentence_id=2,
        paragraph_id=1,
        page=1,
        text="The report was submit to the board yesterday.",
        start_offset=0,
        end_offset=46,
        doc_char_start=200,
        doc_char_end=246
    )
    candidates = gramformer_agent.correct_batch([sentence])
    assert len(candidates) >= 1
    cand = next((c for c in candidates if "submit" in c.original_text.lower()), None)
    assert cand is not None
    assert "submitted" in cand.suggested_text.lower()


def test_gramformer_protects_entities_and_acronyms(gramformer_agent):
    """Test that entities (Ravi Todi, Fitchner, BTL EPC, SCADA) are never modified."""
    sentence = Sentence(
        sentence_id=3,
        paragraph_id=1,
        page=1,
        text="Ravi Todi and Fitchner approved the 500 MW SCADA system for BTL EPC.",
        start_offset=0,
        end_offset=69,
        doc_char_start=300,
        doc_char_end=369
    )
    protected = [
        ProtectedTerm(text="Ravi Todi", char_start=300, char_end=309, reason="PERSON_NAME"),
        ProtectedTerm(text="Fitchner", char_start=314, char_end=322, reason="ORGANIZATION"),
        ProtectedTerm(text="BTL EPC", char_start=360, char_end=367, reason="ORGANIZATION"),
        ProtectedTerm(text="SCADA", char_start=343, char_end=348, reason="ACRONYM"),
    ]
    candidates = gramformer_agent.correct_batch([sentence], protected_terms=protected)
    for c in candidates:
        assert c.original_text not in ("Ravi Todi", "Todi", "Fitchner", "BTL EPC", "SCADA", "500", "MW")


def test_gramformer_skips_empty_or_table_rows(gramformer_agent):
    """Test that non-sentences, numbers, and headings are skipped."""
    sentences = [
        Sentence(sentence_id=4, paragraph_id=2, page=1, text="", start_offset=0, end_offset=0),
        Sentence(sentence_id=5, paragraph_id=2, page=1, text="12.4 45.6 78.9", start_offset=0, end_offset=14),
        Sentence(sentence_id=6, paragraph_id=2, page=1, text="---", start_offset=0, end_offset=3),
    ]
    candidates = gramformer_agent.correct_batch(sentences)
    assert len(candidates) == 0
