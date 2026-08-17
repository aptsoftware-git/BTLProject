"""
test_spell_candidate_protection.py
==================================
Unit and regression tests for Spell Candidate Protection/Filtering Stage.

Tests required cases:
  1. Todi → Todd              REJECT (PERSON_ENTITY / PROPER_NOUN)
  2. Fitchner → Fichtner      REJECT (ORG_ENTITY / PROPER_NOUN / DOMAIN_TERM)
  3. India → ...              REJECT (GPE_ENTITY)
  4. Deoghar → ...            REJECT (GPE_ENTITY / LOC_ENTITY)
  5. BTL EPC → ...            REJECT (ORG_ENTITY / ACRONYM)
  6. CNC/EPC/TREDS → ...      REJECT (ACRONYM)
  7. occuring → occurring      ACCEPT (Genuine spelling error)
  8. renior → senior          ACCEPT (Genuine spelling error)
  9. Bangaldesh → Bangladesh  ACCEPT (Genuine spelling error / misspelled country)

Also tests:
  - Batch sentence NER with nlp.pipe()
  - Preservation of raw spell_candidates.json
  - Generation of ner_entities.json, protected_terms.json, filtered_spell_candidates.json
  - Rejection reasons recorded accurately
"""

import json
from pathlib import Path
import pytest

from src.config import SpacyConfig
from src.models import Candidate, IssueType, Sentence, SourceAgent
from src.spell_filter import SpellCandidateFilter


@pytest.fixture
def spell_filter():
    return SpellCandidateFilter(spacy_config=SpacyConfig())


def test_todi_rejected_as_person(spell_filter):
    """Todi → Todd must be REJECTED (protected person/name)."""
    sentence = Sentence(
        sentence_id=1,
        paragraph_id=1,
        page=1,
        text="The managing director Ravi Todi reviewed the balance sheet.",
        start_offset=0,
        end_offset=58,
        doc_char_start=0,
        doc_char_end=58
    )
    cand = Candidate(
        sentence_id=1,
        char_start=27,
        char_end=31,
        original_text="Todi",
        suggested_text="Todd",
        issue_type=IssueType.SPELLING,
        source=SourceAgent.LANGUAGETOOL,
        reason="Possible spelling mistake",
    )
    res = spell_filter.run(sentences=[sentence], candidates=[cand])
    assert len(res["filtered_candidates"]) == 0
    assert len(res["rejected_candidates"]) == 1
    rej = res["rejected_candidates"][0]
    assert rej["original_text"] == "Todi"
    assert "PERSON" in rej["rejection_reason"] or "PROPER" in rej["rejection_reason"] or "ORG" in rej["rejection_reason"]


def test_fitchner_rejected_as_org_or_proper_noun(spell_filter):
    """Fitchner → Fichtner must be REJECTED (protected proper org/name)."""
    sentence = Sentence(
        sentence_id=2,
        paragraph_id=1,
        page=1,
        text="Technical feasibility study was conducted by Fitchner.",
        start_offset=0,
        end_offset=54,
        doc_char_start=60,
        doc_char_end=114
    )
    cand = Candidate(
        sentence_id=2,
        char_start=106,
        char_end=114,
        original_text="Fitchner",
        suggested_text="Fichtner",
        issue_type=IssueType.SPELLING,
        source=SourceAgent.SYMSPELL,
        reason="Possible spelling mistake",
    )
    res = spell_filter.run(sentences=[sentence], candidates=[cand])
    assert len(res["filtered_candidates"]) == 0
    assert len(res["rejected_candidates"]) == 1
    rej = res["rejected_candidates"][0]
    assert rej["original_text"] == "Fitchner"
    assert any(tag in rej["rejection_reason"] for tag in ("ORG", "PERSON", "PROPER", "DOMAIN"))


def test_india_rejected_as_gpe(spell_filter):
    """India → ... must be REJECTED (GPE entity)."""
    sentence = Sentence(
        sentence_id=3,
        paragraph_id=1,
        page=1,
        text="All operations across India were profitable this fiscal year.",
        start_offset=0,
        end_offset=61,
        doc_char_start=120,
        doc_char_end=181
    )
    cand = Candidate(
        sentence_id=3,
        char_start=142,
        char_end=147,
        original_text="India",
        suggested_text="Indiana",
        issue_type=IssueType.SPELLING,
        source=SourceAgent.LANGUAGETOOL,
        reason="Spelling suggestion",
    )
    res = spell_filter.run(sentences=[sentence], candidates=[cand])
    assert len(res["filtered_candidates"]) == 0
    assert len(res["rejected_candidates"]) == 1
    rej = res["rejected_candidates"][0]
    assert rej["original_text"] == "India"
    assert rej["rejection_reason"] == "GPE_ENTITY"


def test_deoghar_rejected_as_gpe_or_location(spell_filter):
    """Deoghar → ... must be REJECTED (GPE/LOC entity)."""
    sentence = Sentence(
        sentence_id=4,
        paragraph_id=2,
        page=1,
        text="The new substation at Deoghar was energized successfully.",
        start_offset=0,
        end_offset=57,
        doc_char_start=200,
        doc_char_end=257
    )
    cand = Candidate(
        sentence_id=4,
        char_start=222,
        char_end=229,
        original_text="Deoghar",
        suggested_text="Deodar",
        issue_type=IssueType.SPELLING,
        source=SourceAgent.SYMSPELL,
        reason="Spelling suggestion",
    )
    res = spell_filter.run(sentences=[sentence], candidates=[cand])
    assert len(res["filtered_candidates"]) == 0
    assert len(res["rejected_candidates"]) == 1
    rej = res["rejected_candidates"][0]
    assert rej["original_text"] == "Deoghar"
    assert "GPE" in rej["rejection_reason"] or "LOC" in rej["rejection_reason"] or "PROPER" in rej["rejection_reason"]


def test_btl_epc_rejected_as_org_or_acronym(spell_filter):
    """BTL EPC → ... must be REJECTED (ORG entity/acronym)."""
    sentence = Sentence(
        sentence_id=5,
        paragraph_id=2,
        page=1,
        text="BTL EPC was awarded the transmission line package.",
        start_offset=0,
        end_offset=50,
        doc_char_start=260,
        doc_char_end=310
    )
    cand = Candidate(
        sentence_id=5,
        char_start=260,
        char_end=267,
        original_text="BTL EPC",
        suggested_text="BTL EPIC",
        issue_type=IssueType.SPELLING,
        source=SourceAgent.LANGUAGETOOL,
        reason="Spelling suggestion",
    )
    res = spell_filter.run(sentences=[sentence], candidates=[cand])
    assert len(res["filtered_candidates"]) == 0
    assert len(res["rejected_candidates"]) == 1
    rej = res["rejected_candidates"][0]
    assert rej["original_text"] == "BTL EPC"
    assert any(tag in rej["rejection_reason"] for tag in ("ORG", "ACRONYM", "PROPER"))


def test_acronyms_rejected(spell_filter):
    """CNC/EPC/TREDS → ... must be REJECTED (ACRONYM)."""
    sentence = Sentence(
        sentence_id=6,
        paragraph_id=3,
        page=2,
        text="Payments processed through CNC, EPC, and TREDS platforms.",
        start_offset=0,
        end_offset=57,
        doc_char_start=320,
        doc_char_end=377
    )
    cands = [
        Candidate(
            sentence_id=6,
            char_start=347,
            char_end=350,
            original_text="CNC",
            suggested_text="CNN",
            issue_type=IssueType.SPELLING,
            source=SourceAgent.LANGUAGETOOL,
            reason="Spelling suggestion",
        ),
        Candidate(
            sentence_id=6,
            char_start=352,
            char_end=355,
            original_text="EPC",
            suggested_text="ETC",
            issue_type=IssueType.SPELLING,
            source=SourceAgent.LANGUAGETOOL,
            reason="Spelling suggestion",
        ),
        Candidate(
            sentence_id=6,
            char_start=361,
            char_end=366,
            original_text="TREDS",
            suggested_text="TRENDS",
            issue_type=IssueType.SPELLING,
            source=SourceAgent.SYMSPELL,
            reason="Spelling suggestion",
        ),
        Candidate(
            sentence_id=6,
            char_start=320,
            char_end=333,
            original_text="CNC/EPC/TREDS",
            suggested_text="CNC EPC TREDS",
            issue_type=IssueType.SPELLING,
            source=SourceAgent.LANGUAGETOOL,
            reason="Spelling suggestion",
        )
    ]
    res = spell_filter.run(sentences=[sentence], candidates=cands)
    assert len(res["filtered_candidates"]) == 0
    assert len(res["rejected_candidates"]) == 4
    for rej in res["rejected_candidates"]:
        assert rej["rejection_reason"] in ("ACRONYM", "DOMAIN_TERM", "ORG_ENTITY")


def test_occuring_accepted_as_genuine_misspelling(spell_filter):
    """occuring → occurring must be ACCEPTED (genuine spelling error)."""
    sentence = Sentence(
        sentence_id=7,
        paragraph_id=3,
        page=2,
        text="The issue is occuring frequently during peak load.",
        start_offset=0,
        end_offset=50,
        doc_char_start=380,
        doc_char_end=430
    )
    cand = Candidate(
        sentence_id=7,
        char_start=393,
        char_end=401,
        original_text="occuring",
        suggested_text="occurring",
        issue_type=IssueType.SPELLING,
        source=SourceAgent.LANGUAGETOOL,
        reason="Possible spelling mistake",
    )
    res = spell_filter.run(sentences=[sentence], candidates=[cand])
    assert len(res["filtered_candidates"]) == 1
    assert len(res["rejected_candidates"]) == 0
    assert res["filtered_candidates"][0].original_text == "occuring"
    assert res["filtered_candidates"][0].suggested_text == "occurring"


def test_renior_accepted_as_genuine_misspelling(spell_filter):
    """renior → senior must be ACCEPTED (genuine spelling error)."""
    sentence = Sentence(
        sentence_id=8,
        paragraph_id=4,
        page=2,
        text="He was appointed as renior engineer in the division.",
        start_offset=0,
        end_offset=52,
        doc_char_start=440,
        doc_char_end=492
    )
    cand = Candidate(
        sentence_id=8,
        char_start=460,
        char_end=466,
        original_text="renior",
        suggested_text="senior",
        issue_type=IssueType.SPELLING,
        source=SourceAgent.SYMSPELL,
        reason="Possible spelling mistake",
    )
    res = spell_filter.run(sentences=[sentence], candidates=[cand])
    assert len(res["filtered_candidates"]) == 1
    assert len(res["rejected_candidates"]) == 0
    assert res["filtered_candidates"][0].original_text == "renior"
    assert res["filtered_candidates"][0].suggested_text == "senior"


def test_bangladesh_misspelling_accepted(spell_filter):
    """Bangaldesh → Bangladesh must be ACCEPTED (genuine spelling error / misspelled country)."""
    sentence = Sentence(
        sentence_id=9,
        paragraph_id=4,
        page=2,
        text="The cross-border transmission project to Bangaldesh is underway.",
        start_offset=0,
        end_offset=64,
        doc_char_start=500,
        doc_char_end=564
    )
    cand = Candidate(
        sentence_id=9,
        char_start=541,
        char_end=551,
        original_text="Bangaldesh",
        suggested_text="Bangladesh",
        issue_type=IssueType.SPELLING,
        source=SourceAgent.LANGUAGETOOL,
        reason="Possible spelling mistake",
    )
    res = spell_filter.run(sentences=[sentence], candidates=[cand])
    assert len(res["filtered_candidates"]) == 1
    assert len(res["rejected_candidates"]) == 0
    assert res["filtered_candidates"][0].original_text == "Bangaldesh"
    assert res["filtered_candidates"][0].suggested_text == "Bangladesh"


def test_batch_ner_and_artifact_generation(tmp_path, spell_filter):
    """Test batch NER with nlp.pipe() and generated JSON artifacts."""
    sentences = [
        Sentence(sentence_id=1, paragraph_id=1, page=1, text="Ravi Todi visited Deoghar in India.", start_offset=0, end_offset=35, doc_char_start=0, doc_char_end=35),
        Sentence(sentence_id=2, paragraph_id=1, page=1, text="BTL EPC contracted Fitchner for SCADA.", start_offset=0, end_offset=38, doc_char_start=36, doc_char_end=74),
        Sentence(sentence_id=3, paragraph_id=2, page=1, text="An error is occuring in Bangaldesh.", start_offset=0, end_offset=35, doc_char_start=75, doc_char_end=110),
    ]
    candidates = [
        Candidate(sentence_id=1, char_start=5, char_end=9, original_text="Todi", suggested_text="Todd", issue_type=IssueType.SPELLING, source=SourceAgent.LANGUAGETOOL, reason="Typo"),
        Candidate(sentence_id=1, char_start=18, char_end=25, original_text="Deoghar", suggested_text="Deodar", issue_type=IssueType.SPELLING, source=SourceAgent.SYMSPELL, reason="Typo"),
        Candidate(sentence_id=2, char_start=67, char_end=72, original_text="SCADA", suggested_text="SCALE", issue_type=IssueType.SPELLING, source=SourceAgent.LANGUAGETOOL, reason="Typo"),
        Candidate(sentence_id=3, char_start=87, char_end=95, original_text="occuring", suggested_text="occurring", issue_type=IssueType.SPELLING, source=SourceAgent.LANGUAGETOOL, reason="Typo"),
        Candidate(sentence_id=3, char_start=99, char_end=109, original_text="Bangaldesh", suggested_text="Bangladesh", issue_type=IssueType.SPELLING, source=SourceAgent.LANGUAGETOOL, reason="Typo"),
    ]

    out_dir = tmp_path / "06_spell"
    res = spell_filter.run(sentences=sentences, candidates=candidates, output_dir=out_dir)

    # Verify generated files
    assert (out_dir / "ner_entities.json").exists()
    assert (out_dir / "protected_terms.json").exists()
    assert (out_dir / "filtered_spell_candidates.json").exists()
    assert (out_dir / "rejected_spell_candidates.json").exists()

    # Verify counts: 2 accepted (occuring, Bangaldesh), 3 rejected (Todi, Deoghar, SCADA)
    assert res["raw_candidates_count"] == 5
    assert res["filtered_candidates_count"] == 2
    assert res["rejected_candidates_count"] == 3

    filtered_cands = json.loads((out_dir / "filtered_spell_candidates.json").read_text(encoding="utf-8"))
    assert len(filtered_cands) == 2
    orig_texts = {c["original_text"] for c in filtered_cands}
    assert orig_texts == {"occuring", "Bangaldesh"}
