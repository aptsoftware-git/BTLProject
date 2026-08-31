"""
test_ambiguity_same_subject_check.py
=====================================
Regression tests for the "different people/entities incorrectly flagged as
a terminology (or other) inconsistency" false-positive class in Ambiguity
Analysis.

Root cause: ambiguity_context_filter.is_genuine_ambiguity()'s old
"Terminology inconsistency" validation only checked whether the LLM's own
explanation text happened to contain generic words like "same", "differs",
or "refer" -- words that appear in almost any English explanation of any
comparison, genuine or not. It never verified the two pieces of cited
evidence actually concern the same real-world entity, so an LLM mixing up
two different named people (or organizations) and mislabeling the mismatch
as "the same role described inconsistently" sailed straight through.

is_same_subject_across_evidence() adds a real, generic (no hardcoded
names/roster) check: when 2+ evidence items are cited and each side names a
specific person/organization, those names must overlap after
normalization -- otherwise this reads as two distinct entities, not one
entity described inconsistently, and the finding is rejected.
"""

from src.rag.ambiguity_context_filter import (
    is_same_subject_across_evidence,
    is_genuine_ambiguity,
)


def test_different_people_rejected_as_false_terminology_inconsistency():
    """The exact false-positive class reported: two DIFFERENT people, each
    genuinely described in the document, incorrectly flagged as if one
    person's role/title were described inconsistently."""
    finding = {
        "category": "Terminology inconsistency",
        "title": "Inconsistent designation terminology",
        "highlighted_ambiguity": "Managing Director",
        "claude_explanation": (
            "The designation differs across the document for the same leadership role -- "
            "one passage uses 'Managing Director' while another uses a different title, "
            "suggesting inconsistent terminology for the same entity."
        ),
        "evidence": [
            {"chunk_id": "c1", "page": 49, "quote": "Mr. Ravi Todi serves as the Managing Director of the Company."},
            {"chunk_id": "c2", "page": 50, "quote": "Ms. Rhea Todi holds the position of Whole Time Director."},
        ],
    }

    # Sanity check: under the OLD keyword-only rule this would have passed,
    # since the explanation contains "differs", "same", and "for the same
    # entity" -- proving this is a real regression fix, not a redundant test.
    old_rule_keywords = ["same", "concept", "entity", "naming", "variant", "refer", "inconsistent", "differs", "varies", "across"]
    explanation_text = finding["claude_explanation"].lower()
    assert any(kw in explanation_text for kw in old_rule_keywords), (
        "test fixture must reproduce the old false-positive trigger condition"
    )

    subject_ok, reason = is_same_subject_across_evidence(finding)
    assert subject_ok is False
    assert "Ravi Todi" in reason or "ravi todi" in reason.lower()
    assert "Rhea Todi" in reason or "rhea todi" in reason.lower()

    genuine, genuine_reason = is_genuine_ambiguity(finding)
    assert genuine is False
    assert "distinct" in genuine_reason or "different" in genuine_reason


def test_same_person_different_title_forms_still_passes():
    """Control case: a genuine terminology inconsistency about ONE person
    (same name, different honorific/word-order forms) must still be
    accepted -- this check must not reject legitimate same-entity findings."""
    finding = {
        "category": "Terminology inconsistency",
        "title": "Inconsistent designation terminology for the same director",
        "highlighted_ambiguity": "Managing Director",
        "claude_explanation": "The same person's designation differs: 'Managing Director' vs 'MD' across sections.",
        "evidence": [
            {"chunk_id": "c1", "page": 49, "quote": "Mr. Ravi Todi serves as the Managing Director."},
            {"chunk_id": "c2", "page": 60, "quote": "Ravi Todi (MD) approved the budget on this date."},
        ],
    }
    subject_ok, reason = is_same_subject_across_evidence(finding)
    assert subject_ok is True
    assert reason is None

    genuine, genuine_reason = is_genuine_ambiguity(finding)
    assert genuine is True


def test_different_organizations_rejected_generically_not_just_people():
    """The same check must be fully generic -- it must catch a
    different-ORGANIZATION mixup exactly the same way, not just people."""
    finding = {
        "category": "Internal factual contradiction",
        "title": "Conflicting registered office address",
        "highlighted_ambiguity": "registered office",
        "claude_explanation": "The registered office address differs between these two statements about the same entity.",
        "evidence": [
            {"chunk_id": "c1", "page": 2, "quote": "BTL EPC Limited has its registered office in Kolkata."},
            {"chunk_id": "c2", "page": 88, "quote": "Shrachi Realty Private Limited has its registered office in Mumbai."},
        ],
    }
    subject_ok, reason = is_same_subject_across_evidence(finding)
    assert subject_ok is False


def test_generic_terminology_with_no_named_entities_is_not_blocked():
    """When neither side names a specific person/organization (a genuinely
    generic term-vs-term comparison, e.g. "the Company" vs "the
    Corporation"), this check must not apply -- it has nothing to compare
    and must defer to the other gates."""
    finding = {
        "category": "Terminology inconsistency",
        "title": "Inconsistent entity terminology",
        "highlighted_ambiguity": "the Company",
        "claude_explanation": "The same entity is referred to inconsistently as 'the Company' in one place and 'the Corporation' elsewhere.",
        "evidence": [
            {"chunk_id": "c1", "page": 5, "quote": "The Company shall indemnify all directors."},
            {"chunk_id": "c2", "page": 40, "quote": "The Corporation shall indemnify all directors."},
        ],
    }
    subject_ok, reason = is_same_subject_across_evidence(finding)
    assert subject_ok is True
    assert reason is None


def test_single_evidence_item_is_not_blocked():
    finding = {
        "category": "Terminology inconsistency",
        "evidence": [{"chunk_id": "c1", "page": 5, "quote": "Mr. Ravi Todi serves as the Managing Director."}],
    }
    subject_ok, reason = is_same_subject_across_evidence(finding)
    assert subject_ok is True


def test_one_sided_name_detection_is_not_blocked():
    """Only one side has a detectable proper-noun candidate -- not enough
    information to call this a mixup, so this check defers rather than
    guessing."""
    finding = {
        "category": "Terminology inconsistency",
        "evidence": [
            {"chunk_id": "c1", "page": 5, "quote": "Mr. Ravi Todi serves as the Managing Director."},
            {"chunk_id": "c2", "page": 6, "quote": "The managing director approved the annual budget."},
        ],
    }
    subject_ok, reason = is_same_subject_across_evidence(finding)
    assert subject_ok is True
