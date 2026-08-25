"""
test_false_positive_rejection.py
=================================
Comprehensive regression test suite for the False Positive Rejection Layer.
Tests:
  1. Valid financial/currency expressions: USD 5 trillion, ₹ 10 crore, $1.5 million, INR 20,000, EUR 3.2 billion
  2. Valid percentages: 80% of job, 15.5%, 100 bps
  3. Valid dates and fiscal years: FY 2024-25, 2023-24, Q1 FY25, 31st March 2024
  4. Valid units and measurements: MW, GW, kV, TPH, MT, sq ft
  5. Valid company names, person names, abbreviations, and technical terms
  6. Suggestion quality gates (capitalization, British-American, notation, OCR fragments)
  7. Genuine error detection preservation (SVA, tense, spelling, punctuation, word forms)
"""

import pytest
from src.config import SpacyConfig, ValidationConfig
from src.false_positive_rejection import FalsePositiveRejectionLayer
from src.finding_mapper import build_findings
from src.models import Candidate, IssueType, ProtectedTerm, SourceAgent
from src.protected_terms import ProtectedTermsBuilder
from src.validation_agent import ValidationAgent


@pytest.fixture
def rejection_layer():
    protected = [
        ProtectedTerm(text="Sunil Kumar Mittra", char_start=0, char_end=18, reason="PERSON_NAME"),
        ProtectedTerm(text="Ravi Todi", char_start=20, char_end=29, reason="PERSON_NAME"),
        ProtectedTerm(text="BTL EPC Limited", char_start=30, char_end=45, reason="ORGANIZATION"),
    ]
    return FalsePositiveRejectionLayer(protected_terms=protected, spelling_standard="both")


# ---------------------------------------------------------------------------
# 1. Financial & Currency Expressions Protection
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("expr", [
    "USD 5 trillion",
    "₹ 10 crore",
    "₹10 crore",
    "$1.5 million",
    "INR 20,000",
    "EUR 3.2 billion",
    "Rs. 500",
    "Rs 500",
    "10 Lakhs",
    "5 Crores",
    "1.2 Mn",
    "3.4 Bn",
])
def test_financial_expressions_protected(rejection_layer, expr):
    sent = f"The company allocated {expr} for new capital expenditure."
    is_rej, reason, _ = rejection_layer.evaluate_candidate(
        original=expr,
        suggestion="5 trillion dollars",
        sentence_text=sent,
        issue_type="grammar",
    )
    assert is_rej is True
    assert "PROTECTED" in reason or "FINANCIAL" in reason or "CURRENCY" in reason


def test_individual_currency_codes_protected(rejection_layer):
    for code in ["USD", "INR", "EUR", "GBP", "₹", "$", "Rs."]:
        sent = f"Total revenue in {code} was reported accurately."
        is_rej, reason, _ = rejection_layer.evaluate_candidate(
            original=code,
            suggestion=code.lower(),
            sentence_text=sent,
            issue_type="spelling",
        )
        assert is_rej is True


# ---------------------------------------------------------------------------
# 2. Percentage Expressions Protection
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("pct_expr", [
    "80% of job",
    "80%",
    "80 %",
    "15.5%",
    "100 bps",
    "5.2 percentage points",
])
def test_percentages_protected(rejection_layer, pct_expr):
    sent = f"The team completed {pct_expr} ahead of schedule."
    is_rej, reason, _ = rejection_layer.evaluate_candidate(
        original=pct_expr,
        suggestion="80 percent of the job",
        sentence_text=sent,
        issue_type="grammar",
    )
    assert is_rej is True
    assert "PROTECTED" in reason or "PERCENTAGE" in reason


# ---------------------------------------------------------------------------
# 3. Dates, Fiscal Years & Quarters Protection
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("date_expr", [
    "FY 2024-25",
    "2024-25",
    "2023-2024",
    "FY24",
    "Q1 FY25",
    "31st March 2024",
    "March 31, 2024",
    "31/03/2024",
])
def test_dates_and_fiscal_years_protected(rejection_layer, date_expr):
    sent = f"Financial statements for {date_expr} were audited by statutory auditors."
    is_rej, reason, _ = rejection_layer.evaluate_candidate(
        original=date_expr,
        suggestion="2025",
        sentence_text=sent,
        issue_type="spelling",
    )
    assert is_rej is True
    assert "PROTECTED" in reason or "DATE" in reason or "FISCAL" in reason


# ---------------------------------------------------------------------------
# 4. Units & Measurements Protection
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("unit_expr", [
    "500 MW",
    "100 GW",
    "220 kV",
    "1500 TPH",
    "5000 MT",
    "20,000 sq ft",
    "50 km",
    "45 °C",
])
def test_units_and_measurements_protected(rejection_layer, unit_expr):
    sent = f"The substation handles {unit_expr} capacity reliably."
    is_rej, reason, _ = rejection_layer.evaluate_candidate(
        original=unit_expr,
        suggestion="capacity",
        sentence_text=sent,
        issue_type="spelling",
    )
    assert is_rej is True
    assert "PROTECTED" in reason or "MEASUREMENT" in reason


# ---------------------------------------------------------------------------
# 5. Proper Nouns, Company Names, Abbreviations & Technical Terms
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("term,cat", [
    ("BTL EPC Limited", "ORG"),
    ("Shrachi Group", "ORG"),
    ("Fichtner Consulting", "ORG"),
    ("Fitchner", "ORG"),
    ("Wartsila", "ORG"),
    ("Sunil Kumar Mittra", "PERSON"),
    ("Ravi Todi", "PERSON"),
    ("Rhea Todi", "PERSON"),
    ("EBITDA", "ACRONYM"),
    ("PAT", "ACRONYM"),
    ("CIN", "REGULATORY"),
    ("DIN", "REGULATORY"),
    ("UDIN", "REGULATORY"),
    ("SEBI", "REGULATORY"),
    ("BSE", "REGULATORY"),
    ("NSE", "REGULATORY"),
    ("SCADA", "TECH"),
    ("HVDC", "TECH"),
    ("feedforward", "TECH"),
    ("layernorm", "TECH"),
    ("switchyard", "TECH"),
    ("substation", "TECH"),
    ("discom", "TECH"),
])
def test_proper_nouns_and_technical_terms_protected(rejection_layer, term, cat):
    sent = f"The operations of {term} were reviewed in detail."
    is_rej, reason, _ = rejection_layer.evaluate_candidate(
        original=term,
        suggestion="General Term",
        sentence_text=sent,
        issue_type="spelling",
    )
    assert is_rej is True
    assert "PROTECTED" in reason


# ---------------------------------------------------------------------------
# 6. Suggestion Quality Gate Tests
# ---------------------------------------------------------------------------

def test_identical_text_rejected(rejection_layer):
    is_rej, reason, _ = rejection_layer.evaluate_candidate(
        original="growing",
        suggestion="growing",
        sentence_text="The company is growing rapidly.",
        issue_type="grammar",
    )
    assert is_rej is True
    assert "IDENTICAL" in reason


def test_capitalization_preference_suppressed(rejection_layer):
    is_rej, reason, _ = rejection_layer.evaluate_candidate(
        original="EBITDA",
        suggestion="Ebitda",
        sentence_text="The EBITDA margin expanded by 200 bps.",
        issue_type="grammar",
    )
    assert is_rej is True
    assert "CAPITALIZATION" in reason or "PROTECTED" in reason


def test_british_american_spelling_preference_suppressed(rejection_layer):
    is_rej, reason, _ = rejection_layer.evaluate_candidate(
        original="colour",
        suggestion="color",
        sentence_text="The colour of the logo is blue.",
        issue_type="spelling",
    )
    assert is_rej is True
    assert "British/American" in reason or "REGIONAL_SPELLING" in reason or "BRITISH" in str(reason).upper()


def test_formatting_notation_diff_suppressed(rejection_layer):
    is_rej, reason, _ = rejection_layer.evaluate_candidate(
        original="₹ 10 crore",
        suggestion="₹10 crore",
        sentence_text="The project cost ₹ 10 crore.",
        issue_type="grammar",
    )
    assert is_rej is True


def test_fragment_leading_dash_suppressed(rejection_layer):
    is_rej, reason, _ = rejection_layer.evaluate_candidate(
        original="-growth",
        suggestion="growth",
        sentence_text="-growth in revenue",
        issue_type="grammar",
    )
    assert is_rej is True
    assert "FRAGMENT" in reason or "INSUFFICIENT" in reason


# ---------------------------------------------------------------------------
# 7. Genuine Error Detection Preservation Tests
# ---------------------------------------------------------------------------

def test_genuine_subject_verb_agreement_preserved(rejection_layer):
    # SVA error: "The company are growing" -> "The company is growing"
    is_rej, reason, score = rejection_layer.evaluate_candidate(
        original="are",
        suggestion="is",
        sentence_text="The company are growing rapidly in domestic markets.",
        issue_type="grammar",
        confidence=0.90,
    )
    assert is_rej is False
    assert reason is None
    assert score >= 85


def test_genuine_sva_he_go_preserved(rejection_layer):
    # SVA error: "He go to office" -> "He goes to office"
    is_rej, reason, score = rejection_layer.evaluate_candidate(
        original="go",
        suggestion="goes",
        sentence_text="He go to office every morning.",
        issue_type="grammar",
        confidence=0.92,
    )
    assert is_rej is False
    assert reason is None


def test_genuine_sva_directors_has_approved_preserved(rejection_layer):
    # SVA error: "The directors has approved" -> "have approved"
    is_rej, reason, score = rejection_layer.evaluate_candidate(
        original="has approved",
        suggestion="have approved",
        sentence_text="The directors has approved the financial statements.",
        issue_type="grammar",
        confidence=0.95,
    )
    assert is_rej is False
    assert reason is None


def test_genuine_tense_error_has_went_preserved(rejection_layer):
    # Tense error: "They has went to the site" -> "have gone"
    is_rej, reason, score = rejection_layer.evaluate_candidate(
        original="has went",
        suggestion="has gone",
        sentence_text="They has went to the site yesterday.",
        issue_type="tense",
        confidence=0.90,
    )
    assert is_rej is False
    assert reason is None


def test_genuine_misspellings_preserved(rejection_layer):
    misspellings = [
        ("definitiely", "definitely"),
        ("recieve", "receive"),
        ("comapny", "company"),
        ("annnual", "annual"),
        ("proffreading", "proofreading"),
        ("succesful", "successful"),
    ]
    for orig, sug in misspellings:
        sent = f"We will {orig} the report tomorrow."
        is_rej, reason, score = rejection_layer.evaluate_candidate(
            original=orig,
            suggestion=sug,
            sentence_text=sent,
            issue_type="spelling",
            confidence=0.95,
        )
        assert is_rej is False, f"Failed for misspelling: {orig}"
        assert reason is None


def test_genuine_punctuation_error_preserved(rejection_layer):
    # Double period error ".." -> "."
    is_rej, reason, score = rejection_layer.evaluate_candidate(
        original="..",
        suggestion=".",
        sentence_text="The audit was concluded successfully..",
        issue_type="punctuation",
        confidence=0.90,
    )
    assert is_rej is False
    assert reason is None


def test_invalid_word_forms_preserved(rejection_layer):
    invalid_forms = [
        ("more better", "better"),
        ("irregardless", "regardless"),
    ]
    for orig, sug in invalid_forms:
        sent = f"This approach is {orig} for the project."
        is_rej, reason, score = rejection_layer.evaluate_candidate(
            original=orig,
            suggestion=sug,
            sentence_text=sent,
            issue_type="grammar",
            confidence=0.90,
        )
        assert is_rej is False, f"Failed for invalid form: {orig}"
        assert reason is None


# ---------------------------------------------------------------------------
# 8. End-to-End build_findings Integration Quality Gate
# ---------------------------------------------------------------------------

def test_build_findings_e2e_rejection_and_retention():
    lookup_index = {
        "101": {
            "sentence_id": 101,
            "text": "The company allocated USD 5 trillion and ₹ 10 crore for expansion in FY 2024-25.",
            "page_number": 5,
            "source_element_id": "el_101",
            "source_bbox": {"x0": 50, "y0": 100, "x1": 400, "y1": 120}
        },
        "102": {
            "sentence_id": 102,
            "text": "We will recieve the annnual report and the directors has approved it.",
            "page_number": 6,
            "source_element_id": "el_102",
            "source_bbox": {"x0": 50, "y0": 130, "x1": 450, "y1": 150}
        }
    }

    report_issues = [
        # False Positive 1: USD 5 trillion
        {
            "sentence_id": 101,
            "original_text": "USD 5 trillion",
            "suggested_text": "5 trillion USD",
            "issue_type": "grammar",
            "confidence": 0.85,
            "sentence_text": lookup_index["101"]["text"]
        },
        # False Positive 2: ₹ 10 crore
        {
            "sentence_id": 101,
            "original_text": "₹ 10 crore",
            "suggested_text": "₹10 crore",
            "issue_type": "grammar",
            "confidence": 0.80,
            "sentence_text": lookup_index["101"]["text"]
        },
        # False Positive 3: FY 2024-25
        {
            "sentence_id": 101,
            "original_text": "FY 2024-25",
            "suggested_text": "2024-2025",
            "issue_type": "spelling",
            "confidence": 0.75,
            "sentence_text": lookup_index["101"]["text"]
        },
        # Real Error 1: recieve -> receive
        {
            "sentence_id": 102,
            "original_text": "recieve",
            "suggested_text": "receive",
            "issue_type": "spelling",
            "confidence": 0.95,
            "sentence_text": lookup_index["102"]["text"]
        },
        # Real Error 2: annnual -> annual
        {
            "sentence_id": 102,
            "original_text": "annnual",
            "suggested_text": "annual",
            "issue_type": "spelling",
            "confidence": 0.95,
            "sentence_text": lookup_index["102"]["text"]
        },
        # Real Error 3: has approved -> have approved
        {
            "sentence_id": 102,
            "original_text": "has approved",
            "suggested_text": "have approved",
            "issue_type": "grammar",
            "confidence": 0.92,
            "sentence_text": lookup_index["102"]["text"]
        }
    ]

    findings, auto_rejected = build_findings(
        report_issues=report_issues,
        lookup_index=lookup_index,
        decisions={},
        protected_terms=[],
        spelling_standard="both"
    )

    # Verify 3 false positives were rejected
    assert len(auto_rejected) == 3
    rejected_originals = [r["original"] for r in auto_rejected]
    assert "USD 5 trillion" in rejected_originals
    assert "₹ 10 crore" in rejected_originals
    assert "FY 2024-25" in rejected_originals

    # Verify 3 real errors were accepted
    assert len(findings) == 3
    accepted_originals = [f["original"] for f in findings]
    assert "recieve" in accepted_originals
    assert "annnual" in accepted_originals
    assert "has approved" in accepted_originals
