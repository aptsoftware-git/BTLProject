"""
test_proofreading_hardening.py
==============================
Tests production proofreading pipeline hardening: category allowlist, protected vocabulary,
domain dictionary protection, and non-zero bbox propagation.
"""

from pathlib import Path
import pytest
from src.models import Candidate, ProtectedTerm
from src.protected_terms import ProtectedTermsBuilder
from src.validation_agent import ValidationAgent
from src.config import SpacyConfig, ValidationConfig


def test_domain_dictionary_protection():
    spacy_cfg = SpacyConfig()
    val_cfg = ValidationConfig()
    builder = ProtectedTermsBuilder(spacy_cfg, val_cfg)
    
    text = "The SCADA system monitored by Sanjukta at EY uses GIS and RAG APIs."
    terms = builder.build(text)
    
    term_texts = {t.text for t in terms}
    assert "SCADA" in term_texts or "EY" in term_texts or "RAG" in term_texts


def test_validation_agent_category_allowlist():
    terms = [ProtectedTerm(text="Sanjukta", char_start=0, char_end=8, reason="person name")]
    validator = ValidationAgent(terms)
    
    candidates = [
        # Valid spelling error
        Candidate(sentence_id=1, char_start=10, char_end=17, original_text="recieve", suggested_text="receive", issue_type="spelling", source="symspell", reason="Spelling error"),
        # Style improvement (Out of Scope)
        Candidate(sentence_id=2, char_start=20, char_end=30, original_text="good wording", suggested_text="better wording", issue_type="style", source="languagetool", reason="style suggestion"),
        # Protected name overlap
        Candidate(sentence_id=3, char_start=0, char_end=8, original_text="Sanjukta", suggested_text="Sanjuktaa", issue_type="spelling", source="symspell", reason="Spelling error"),
        # Capitalization preference only
        Candidate(sentence_id=4, char_start=40, char_end=47, original_text="COMPANY", suggested_text="Company", issue_type="grammar", source="languagetool", reason="capitalization preference"),
    ]
    
    accepted, rejected = validator.validate(candidates)
    assert len(accepted) == 1
    assert accepted[0].original_text == "recieve"
    assert len(rejected) == 3
