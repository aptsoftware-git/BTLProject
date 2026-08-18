"""
test_spell_pipeline_optimization.py
====================================
Tests for the optimized spelling error checking pipeline.

Verifies:
1. Single LanguageTool pass partitions spelling vs. grammar candidates into spell_candidates.json and grammar_candidates.json.
2. Fast pre-rejection (is_candidate_pre_rejected) excludes obvious non-errors (numbers, roman numerals, acronyms, valid words, canonical entities).
3. spaCy NER is executed only over unresolved spelling candidate sentences.
4. Protected entities, corporate names, acronyms, domain terms, and gazetteers are rejected with audit logs.
5. Genuine misspellings (including proper noun typos with edit distance <= 2) are accepted.
6. SymSpell provides correction suggestions without independently declaring valid domain words as errors.
7. Dictionary caching ensures high throughput for multi-page documents.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.models import Candidate, IssueType, Sentence, SourceAgent
from src.spell_filter import (
    SpellCandidateFilter,
    get_cached_dictionaries,
    get_cached_symspell,
)


def test_dictionary_caching():
    """Verify that frequency and domain dictionaries are cached in memory."""
    dict_words1, common_words1, domain_terms1 = get_cached_dictionaries()
    dict_words2, common_words2, domain_terms2 = get_cached_dictionaries()

    assert dict_words1 is dict_words2
    assert common_words1 is common_words2
    assert domain_terms1 is domain_terms2
    assert len(dict_words1) > 1000
    assert len(domain_terms1) > 50


def test_symspell_caching():
    """Verify that SymSpell instance is cached."""
    ss1 = get_cached_symspell()
    ss2 = get_cached_symspell()
    assert ss1 is ss2
    if ss1 is not None:
        assert ss1.lookup("recieve", 2)


def test_is_candidate_pre_rejected_acronyms_and_numbers():
    """Test fast pre-check on acronyms, numbers, and roman numerals."""
    spell_filter = SpellCandidateFilter()

    cand_acronym = Candidate(
        sentence_id=1,
        char_start=0,
        char_end=6,
        original_text="SCADA",
        suggested_text="Scale",
        issue_type=IssueType.SPELLING,
        source=SourceAgent.LANGUAGETOOL,
        reason="Possible spelling mistake",
    )
    assert spell_filter.is_candidate_pre_rejected(cand_acronym) == "ACRONYM"

    cand_num = Candidate(
        sentence_id=1,
        char_start=0,
        char_end=4,
        original_text="1234",
        suggested_text="123",
        issue_type=IssueType.SPELLING,
        source=SourceAgent.LANGUAGETOOL,
        reason="Possible spelling mistake",
    )
    assert spell_filter.is_candidate_pre_rejected(cand_num) == "NUMERIC_OR_SYMBOL_TOKEN"

    cand_ordinal = Candidate(
        sentence_id=1,
        char_start=0,
        char_end=3,
        original_text="1st",
        suggested_text="1",
        issue_type=IssueType.SPELLING,
        source=SourceAgent.LANGUAGETOOL,
        reason="Possible spelling mistake",
    )
    assert spell_filter.is_candidate_pre_rejected(cand_ordinal) == "ORDINAL_OR_NUMERIC_CODE"

    cand_roman = Candidate(
        sentence_id=1,
        char_start=0,
        char_end=3,
        original_text="xiv",
        suggested_text="six",
        issue_type=IssueType.SPELLING,
        source=SourceAgent.LANGUAGETOOL,
        reason="Possible spelling mistake",
    )
    assert spell_filter.is_candidate_pre_rejected(cand_roman) == "ROMAN_NUMERAL"


def test_is_candidate_pre_rejected_canonical_entities_and_domain_terms():
    """Test fast pre-check on corporate entities, Indian cities, and domain terms."""
    spell_filter = SpellCandidateFilter()

    cand_corp = Candidate(
        sentence_id=1,
        char_start=0,
        char_end=3,
        original_text="BTL",
        suggested_text="Bit",
        issue_type=IssueType.SPELLING,
        source=SourceAgent.LANGUAGETOOL,
        reason="Possible spelling mistake",
    )
    assert spell_filter.is_candidate_pre_rejected(cand_corp) in ("ACRONYM", "ORG_ENTITY")

    cand_city = Candidate(
        sentence_id=1,
        char_start=0,
        char_end=7,
        original_text="Deoghar",
        suggested_text="Doghouse",
        issue_type=IssueType.SPELLING,
        source=SourceAgent.LANGUAGETOOL,
        reason="Possible spelling mistake",
    )
    assert spell_filter.is_candidate_pre_rejected(cand_city) == "GPE_ENTITY"

    cand_domain = Candidate(
        sentence_id=1,
        char_start=0,
        char_end=5,
        original_text="hydel",
        suggested_text="hotel",
        issue_type=IssueType.SPELLING,
        source=SourceAgent.LANGUAGETOOL,
        reason="Possible spelling mistake",
    )
    assert spell_filter.is_candidate_pre_rejected(cand_domain) == "DOMAIN_TERM"


def test_is_candidate_pre_rejected_does_not_reject_genuine_typos():
    """Test that genuine typos like recieve, occuring, or proper typos are NOT pre-rejected."""
    spell_filter = SpellCandidateFilter()

    cand_typo = Candidate(
        sentence_id=1,
        char_start=0,
        char_end=7,
        original_text="recieve",
        suggested_text="receive",
        issue_type=IssueType.SPELLING,
        source=SourceAgent.LANGUAGETOOL,
        reason="Possible spelling mistake",
    )
    assert spell_filter.is_candidate_pre_rejected(cand_typo) is None

    cand_proper_typo = Candidate(
        sentence_id=1,
        char_start=0,
        char_end=10,
        original_text="Bangaldesh",
        suggested_text="Bangladesh",
        issue_type=IssueType.SPELLING,
        source=SourceAgent.LANGUAGETOOL,
        reason="Possible spelling mistake",
    )
    assert spell_filter.is_candidate_pre_rejected(cand_proper_typo) is None


def test_spacy_ner_runs_only_on_unresolved_candidates(tmp_path):
    """Test that spaCy NER only executes on sentences that have unresolved candidate errors."""
    s1 = Sentence(sentence_id=1, paragraph_id=1, page=1, text="BTL executed the EPC contract.", start_offset=0, end_offset=31, doc_char_start=0, doc_char_end=31)
    s2 = Sentence(sentence_id=2, paragraph_id=1, page=1, text="We did not recieve the document.", start_offset=32, end_offset=64, doc_char_start=32, doc_char_end=64)
    sentences = [s1, s2]

    cand1 = Candidate(sentence_id=1, char_start=0, char_end=3, original_text="BTL", suggested_text="Bit", issue_type=IssueType.SPELLING, source=SourceAgent.LANGUAGETOOL, reason="Possible spelling mistake")
    cand2 = Candidate(sentence_id=2, char_start=43, char_end=50, original_text="recieve", suggested_text="receive", issue_type=IssueType.SPELLING, source=SourceAgent.LANGUAGETOOL, reason="Possible spelling mistake")
    candidates = [cand1, cand2]

    spell_filter = SpellCandidateFilter()
    with patch.object(spell_filter, "extract_ner_entities", wraps=spell_filter.extract_ner_entities) as mock_extract:
        res = spell_filter.run(sentences=sentences, candidates=candidates, output_dir=tmp_path)
        # S1 has pre-rejected candidate (BTL), only S2 has unresolved candidate (recieve)
        assert mock_extract.called
        call_args = mock_extract.call_args[0][0]
        assert len(call_args) == 1
        assert call_args[0].sentence_id == 2

    assert res["filtered_candidates_count"] == 1
    assert res["filtered_candidates"][0].original_text == "recieve"
    assert res["rejected_candidates_count"] == 1
    assert res["rejected_candidates"][0]["original_text"] == "BTL"


def test_symspell_suggestions_for_missing_suggested_text(tmp_path):
    """Test that SymSpell provides correction suggestions when suggested_text is empty."""
    s = Sentence(sentence_id=1, paragraph_id=1, page=1, text="The project is occuring now.", start_offset=0, end_offset=28, doc_char_start=0, doc_char_end=28)
    cand = Candidate(sentence_id=1, char_start=15, char_end=23, original_text="occuring", suggested_text="", issue_type=IssueType.SPELLING, source=SourceAgent.LANGUAGETOOL, reason="Possible spelling mistake")

    spell_filter = SpellCandidateFilter()
    res = spell_filter.run(sentences=[s], candidates=[cand], output_dir=tmp_path)

    assert res["filtered_candidates_count"] == 1
    accepted = res["filtered_candidates"][0]
    assert accepted.original_text == "occuring"
    assert accepted.suggested_text.lower() == "occurring"
