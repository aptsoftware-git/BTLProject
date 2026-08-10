"""
test_ambiguity_taxonomy.py
=============================
Regression tests for the single canonical Ambiguity Analysis taxonomy
(src/rag/ambiguity_taxonomy.py). Locks in that grammar/spelling/style/
vague-wording/undefined-term never map to an approved category, and that
known raw category strings from every upstream producer (Claude prompt
output, cluster_analyzer, chunk_analyzer, legacy finding_filter names)
resolve to one of the 9 approved categories.
"""

import pytest

from src.rag.ambiguity_taxonomy import APPROVED_CATEGORIES, normalize_category


def test_exactly_nine_approved_categories():
    assert len(APPROVED_CATEGORIES) == 9


@pytest.mark.parametrize("raw", [
    "Grammar Issue", "grammar error", "Spelling Issue", "spelling error",
    "Writing Clarity", "writing quality", "vague wording", "Ambiguities",
    "Undefined Term", "Undefined Acronym", "style", "stylistic",
])
def test_proofreading_categories_are_rejected(raw):
    assert normalize_category(raw) is None


@pytest.mark.parametrize("raw,expected", [
    ("Possible Contradiction", "Cross-reference / contradiction"),
    ("Contradictory Statement", "Cross-reference / contradiction"),
    ("Cross-reference Issue", "Cross-reference / contradiction"),
    ("Numeric Inconsistency", "Numerical inconsistency"),
    ("Cross-chunk numerical inconsistency", "Numerical inconsistency"),
    ("Pronoun Ambiguity", "Pronoun / entity-reference ambiguity"),
    ("Referential Ambiguity", "Pronoun / entity-reference ambiguity"),
    ("Terminology Conflict", "Terminology inconsistency"),
    ("Terminology Issue", "Terminology inconsistency"),
    ("Date Conflicts", "Date / timeline inconsistency"),
    ("temporal ambiguity", "Date / timeline inconsistency"),
    ("Unit Inconsistency", "Unit / measurement inconsistency"),
    ("Policy Conflict", "Internal factual contradiction"),
    ("Duplicate Guidance", "Internal factual contradiction"),
    ("Structural Inconsistency", "Structural / convention inconsistency"),
    ("Missing Context", "Missing / conflicting context"),
    ("Missing Information", "Missing / conflicting context"),
])
def test_known_aliases_resolve_to_approved_category(raw, expected):
    result = normalize_category(raw)
    assert result == expected
    assert result in APPROVED_CATEGORIES


def test_already_canonical_category_is_idempotent():
    for cat in APPROVED_CATEGORIES:
        assert normalize_category(cat) == cat


def test_unknown_category_is_rejected_not_defaulted():
    assert normalize_category("Completely Unknown Category XYZ") is None


def test_empty_or_none_category_is_rejected():
    assert normalize_category(None) is None
    assert normalize_category("") is None
