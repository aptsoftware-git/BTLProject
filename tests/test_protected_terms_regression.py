"""
test_protected_terms_regression.py
===================================
Regression tests for ProtectedTermsBuilder and ValidationAgent to ensure proper nouns,
surnames, domain terminology, and multi-word terms are protected from false-positive corrections.
"""

from pathlib import Path
from src.config import SpacyConfig, ValidationConfig
from src.models import Candidate, IssueType, SourceAgent
from src.protected_terms import ProtectedTermsBuilder
from src.validation_agent import ValidationAgent


def get_builder():
    return ProtectedTermsBuilder(spacy_config=SpacyConfig(), validation_config=ValidationConfig())


def test_fitchner_protected_as_person_or_proper_noun():
    builder = get_builder()
    text = "The report was submitted by Fitchner for the project review."
    protected = builder.build(text)

    protected_texts = [p.text for p in protected]
    assert "Fitchner" in protected_texts

    pt = next(p for p in protected if p.text == "Fitchner")
    assert pt.reason in ("PERSON_NAME", "PROPER_NOUN", "ORGANIZATION")


def test_hydel_plant_protected_as_domain_term():
    builder = get_builder()
    text = "The hydel plant was commissioned to supply power to the grid."
    protected = builder.build(text)

    protected_texts = [p.text.lower() for p in protected]
    assert "hydel plant" in protected_texts or "hydel" in protected_texts

    validator = ValidationAgent(protected)
    cand = Candidate(
        sentence_id=1,
        char_start=4,
        char_end=9,
        original_text="hydel",
        suggested_text="hybrid",
        issue_type=IssueType.SPELLING,
        source=SourceAgent.SYMSPELL,
        reason="Spelling suggestion",
    )
    accepted, rejected = validator.validate([cand])
    assert len(accepted) == 0
    assert len(rejected) == 1
    assert "PROTECTED_" in rejected[0].protected_reason


def test_normal_misspelling_recieve_still_detected():
    builder = get_builder()
    text = "We will recieve the document tomorrow."
    protected = builder.build(text)

    validator = ValidationAgent(protected)
    cand = Candidate(
        sentence_id=1,
        char_start=8,
        char_end=15,
        original_text="recieve",
        suggested_text="receive",
        issue_type=IssueType.SPELLING,
        source=SourceAgent.SYMSPELL,
        reason="Spelling suggestion",
    )
    accepted, rejected = validator.validate([cand])
    assert len(accepted) == 1
    assert len(rejected) == 0
    assert accepted[0].original_text == "recieve"


def test_sentence_initial_misspelling_recieve_still_detected():
    builder = get_builder()
    text = "Recieve the final report before submitting."
    protected = builder.build(text)

    validator = ValidationAgent(protected)
    cand = Candidate(
        sentence_id=1,
        char_start=0,
        char_end=7,
        original_text="Recieve",
        suggested_text="Receive",
        issue_type=IssueType.SPELLING,
        source=SourceAgent.SYMSPELL,
        reason="Spelling suggestion",
    )
    accepted, rejected = validator.validate([cand])
    assert len(accepted) == 1
    assert len(rejected) == 0
    assert accepted[0].original_text == "Recieve"


def test_company_name_protected():
    builder = get_builder()
    text = "Fichtner Consulting was awarded the feasibility study contract."
    protected = builder.build(text)

    validator = ValidationAgent(protected)
    cand = Candidate(
        sentence_id=1,
        char_start=0,
        char_end=8,
        original_text="Fichtner",
        suggested_text="Fletcher",
        issue_type=IssueType.SPELLING,
        source=SourceAgent.SYMSPELL,
        reason="Spelling suggestion",
    )
    accepted, rejected = validator.validate([cand])
    assert len(accepted) == 0
    assert len(rejected) == 1


def test_location_name_protected():
    builder = get_builder()
    text = "The team visited Kovalam substation near Trivandrum."
    protected = builder.build(text)

    validator = ValidationAgent(protected)
    cand = Candidate(
        sentence_id=1,
        char_start=16,
        char_end=23,
        original_text="Kovalam",
        suggested_text="Kavalam",
        issue_type=IssueType.SPELLING,
        source=SourceAgent.SYMSPELL,
        reason="Spelling suggestion",
    )
    accepted, rejected = validator.validate([cand])
    assert len(accepted) == 0
    assert len(rejected) == 1


def test_multiword_domain_term_protected():
    builder = get_builder()
    text = "The National Infrastructure Pipeline project is progressing rapidly."
    protected = builder.build(text)

    validator = ValidationAgent(protected)
    cand = Candidate(
        sentence_id=1,
        char_start=4,
        char_end=12,
        original_text="National",
        suggested_text="Notional",
        issue_type=IssueType.SPELLING,
        source=SourceAgent.SYMSPELL,
        reason="Spelling suggestion",
    )
    accepted, rejected = validator.validate([cand])
    assert len(accepted) == 0
    assert len(rejected) == 1


def test_technical_word_not_treated_as_error():
    builder = get_builder()
    text = "The SCADA system manages transmission lines and HVDC converters."
    protected = builder.build(text)

    validator = ValidationAgent(protected)
    cand = Candidate(
        sentence_id=1,
        char_start=4,
        char_end=9,
        original_text="SCADA",
        suggested_text="SCALE",
        issue_type=IssueType.SPELLING,
        source=SourceAgent.SYMSPELL,
        reason="Spelling suggestion",
    )
    accepted, rejected = validator.validate([cand])
    assert len(accepted) == 0
    assert len(rejected) == 1


def test_protected_term_overlap_causes_rejection():
    builder = get_builder()
    text = "Consultant Fitchner performed the technical audit."
    protected = builder.build(text)

    validator = ValidationAgent(protected)
    cand = Candidate(
        sentence_id=1,
        char_start=11,
        char_end=19,
        original_text="Fitchner",
        suggested_text="Faulkner",
        issue_type=IssueType.SPELLING,
        source=SourceAgent.SYMSPELL,
        reason="Spelling suggestion",
    )
    accepted, rejected = validator.validate([cand])
    assert len(accepted) == 0
    assert len(rejected) == 1
    assert "PROTECTED_" in rejected[0].protected_reason


def test_british_american_spelling_behavior_unchanged():
    validator = ValidationAgent([])
    cand = Candidate(
        sentence_id=1,
        char_start=0,
        char_end=6,
        original_text="colour",
        suggested_text="color",
        issue_type=IssueType.SPELLING,
        source=SourceAgent.LANGUAGETOOL,
        reason="Spelling suggestion",
    )
    accepted, rejected = validator.validate([cand])
    assert len(accepted) == 0
    assert len(rejected) == 1
    assert "British/American" in rejected[0].protected_reason
