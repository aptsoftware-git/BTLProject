import pytest
from pathlib import Path
import json

from src.rag.ambiguity_grounding_gate import verify_evidence, normalize_text_robust
from src.rag.ambiguity_taxonomy import normalize_category, APPROVED_CATEGORIES
from src.rag.ambiguity_context_filter import is_context_conflict_plausible, is_genuine_ambiguity


def test_null_status_handling():
    """Verify that None/null status does not crash formatting or string operations."""
    assert normalize_text_robust(None) == ""
    assert normalize_category(None) is None
    
    # Test excluded proofreading categories
    assert normalize_category("grammar issue") is None
    assert normalize_category("spelling error") is None
    assert normalize_category("writing clarity") is None
    assert normalize_category("undefined term") is None
    
    # Test valid approved category normalization
    assert normalize_category("contradiction") == "Cross-reference / contradiction"
    assert normalize_category("numeric inconsistency") == "Numerical inconsistency"


def test_robust_evidence_grounding():
    """Verify that normalization tolerates whitespace, curly quotes, dashes, ligatures, and resolves neighbor chunks."""
    chunk_map = {
        "chunk_001": {"text": "Operating segments of the company include Engineering, Agro Machinery, and Material Handling."},
        "chunk_002": {"text": "Note 14: Operating segments are listed as Engineering and Construction only\u2014showing a segment discrepancy."}
    }

    # 1. Exact quote match in cited chunk
    finding1 = {
        "chunk_id": "chunk_001",
        "quote": "Operating segments of the company include Engineering, Agro Machinery",
        "category": "Cross-reference / contradiction"
    }
    grounded1, reason1 = verify_evidence(finding1, chunk_map)
    assert grounded1 is True
    assert reason1 is None

    # 2. Quote with curly quotes, em-dash (\u2014), and whitespace drift
    finding2 = {
        "chunk_id": "chunk_002",
        "quote": "Operating segments are listed as \u201cEngineering and Construction only\u201d\u2014showing",
        "category": "Cross-reference / contradiction"
    }
    grounded2, reason2 = verify_evidence(finding2, chunk_map)
    assert grounded2 is True
    assert reason2 is None

    # 3. Quote cited on wrong chunk_id (chunk_001) but existing in neighbor chunk_002
    finding3 = {
        "chunk_id": "chunk_001",
        "quote": "Operating segments are listed as Engineering and Construction only",
        "category": "Cross-reference / contradiction"
    }
    grounded3, reason3 = verify_evidence(finding3, chunk_map)
    assert grounded3 is True
    assert reason3 is None
    assert finding3["chunk_id"] == "chunk_002"  # Location updated to actual source chunk!

    # 4. Completely hallucinated quote not present in any chunk
    finding4 = {
        "chunk_id": "chunk_001",
        "quote": "The company has 500 manufacturing plants across Antarctica.",
        "category": "Cross-reference / contradiction"
    }
    grounded4, reason4 = verify_evidence(finding4, chunk_map)
    assert grounded4 is False
    assert ("could not be located" in reason4 or "does not appear" in reason4)


def test_genuine_ambiguity_validation():
    """Verify that standalone factual statements without conflict are rejected, while genuine contradictions survive."""
    # 1. Standalone factual statement ALONE (Prompt Example)
    factual_finding = {
        "category": "Cross-reference / contradiction",
        "quote": "Operating segments include Engineering and Agro Machinery.",
        "title": "Operating Segments Overview",
        "claude_explanation": "Operating segments include Engineering and Agro Machinery.",
        "evidence": [{"chunk_id": "chunk_001", "quote": "Operating segments include Engineering and Agro Machinery."}]
    }
    is_valid, reason = is_genuine_ambiguity(factual_finding)
    assert is_valid is False
    assert "factual statement alone" in reason

    # 2. Genuine contradiction between two conflicting passages
    genuine_finding = {
        "category": "Cross-reference / contradiction",
        "quote": "Operating segments include Engineering and Agro Machinery.",
        "title": "Conflicting Segment Disclosures",
        "claude_explanation": "Section 2 states operating segments include Engineering and Agro Machinery, whereas Note 14 contradicts this by stating segments are Engineering and Construction only.",
        "evidence": [
            {"chunk_id": "chunk_001", "quote": "Operating segments include Engineering and Agro Machinery."},
            {"chunk_id": "chunk_002", "quote": "Operating segments are listed as Engineering and Construction only."}
        ]
    }
    is_valid_g, reason_g = is_genuine_ambiguity(genuine_finding)
    assert is_valid_g is True
    assert reason_g is None

    # 3. Writing style criticism
    style_finding = {
        "category": "Missing / conflicting context",
        "quote": "The results were obtained through testing.",
        "title": "Style Suggestion",
        "claude_explanation": "Consider rephrasing to active voice for better writing quality and readability.",
        "evidence": [{"chunk_id": "chunk_001", "quote": "The results were obtained through testing."}]
    }
    is_valid_s, reason_s = is_genuine_ambiguity(style_finding)
    assert is_valid_s is False
    assert "writing style advice" in reason_s

    # 4. Boilerplate heading
    boilerplate_finding = {
        "category": "Structural / convention inconsistency",
        "quote": "OUR VISION",
        "title": "OUR VISION",
        "claude_explanation": "The heading OUR VISION is presented standalone.",
        "evidence": [{"chunk_id": "chunk_001", "quote": "OUR VISION"}]
    }
    is_valid_b, reason_b = is_genuine_ambiguity(boilerplate_finding)
    assert is_valid_b is False
    assert "boilerplate heading" in reason_b


def test_avik_mukherjee_designation_contradiction_stage6_regression():
    """
    Stage 6 Regression Test -- Avik Mukherjee Designation Contradiction & Pronoun Inconsistency.
    Verifies that:
    1. Multi-chunk conflicting designation evidence for Mr. Avik Mukherjee (DIN: 10706114) across
       pages 58, 94-95, 197, and Financial Statements is accepted as a VERIFIED HIGH-SEVERITY
       contextual finding under category 'Internal factual contradiction'.
    2. All occurrences of the designation contradiction cluster into ONE primary finding (not split into
       separate findings per Executive Director mention).
    3. The pronoun/entity inconsistency ('Mr. Avik Mukherjee ... has offered herself for re-appointment')
       is detected separately as a LOW-SEVERITY finding under 'Pronoun / entity-reference ambiguity'.
    """
    from src.rag.finding_filter import FindingRelevanceFilter

    chunk_map = {
        "chunk_058": {
            "text": "Post closure of Financial year, on 9th June 2025 ... Board further changed his designation from Executive Director to Wholetime Director ... followed by approval of the Members ... on 11th June 2025."
        },
        "chunk_094": {
            "text": "Mr. Avik Mukherjee Whole time Director (Change in designation wef. 01.04.2025)"
        },
        "chunk_197": {
            "text": "Avik Mukherjee - Executive Director (Appointed w.e.f. 17.07.2024)"
        },
        "chunk_financial": {
            "text": "Avik Mukherjee Executive Director DIN: 10706114"
        },
        "chunk_pronoun": {
            "text": "Mr. Avik Mukherjee ... has offered herself for re-appointment."
        }
    }

    # 1. Primary Designation Contradiction Finding
    designation_finding = {
        "finding_id": "find_avik_designation_01",
        "category": "Internal factual contradiction / designation inconsistency",
        "title": "Conflicting Designation and Effective Date for Mr. Avik Mukherjee",
        "claude_explanation": (
            "The Annual Report contains conflicting information regarding Mr. Avik Mukherjee's "
            "designation and the effective date of his change from Executive Director to Whole-time Director. "
            "Page 58 states the Board changed designation on 9th June 2025 (effective 11th June 2025), "
            "whereas pages 94-95 state change in designation wef. 01.04.2025, and later Financial "
            "Statements on page 197 and page 220 still identify him as Executive Director."
        ),
        "quote": "Board further changed his designation from Executive Director to Wholetime Director",
        "severity": "High",
        "confidence": 0.95,
        "evidence": [
            {
                "chunk_id": "chunk_058",
                "quote": "Board further changed his designation from Executive Director to Wholetime Director",
                "page": 58
            },
            {
                "chunk_id": "chunk_094",
                "quote": "Mr. Avik Mukherjee Whole time Director (Change in designation wef. 01.04.2025)",
                "page": 94
            },
            {
                "chunk_id": "chunk_197",
                "quote": "Avik Mukherjee - Executive Director (Appointed w.e.f. 17.07.2024)",
                "page": 197
            },
            {
                "chunk_id": "chunk_financial",
                "quote": "Avik Mukherjee Executive Director DIN: 10706114",
                "page": 220
            }
        ]
    }

    # Grounding check
    grounded, reason = verify_evidence(designation_finding, chunk_map)
    assert grounded is True, f"Grounding failed: {reason}"

    # Taxonomy normalization check
    norm_cat = normalize_category(designation_finding["category"])
    assert norm_cat == "Internal factual contradiction"

    # Genuine ambiguity validation check
    is_valid, val_reason = is_genuine_ambiguity(designation_finding)
    assert is_valid is True, f"Genuine ambiguity check failed: {val_reason}"

    # Context conflict plausibility check
    is_plausible, plaus_reason = is_context_conflict_plausible(designation_finding)
    assert is_plausible is True, f"Context conflict check failed: {plaus_reason}"

    # 2. Duplicate designation finding attempt (simulating another mention of Executive Director)
    designation_finding_duplicate = {
        "finding_id": "find_avik_designation_02",
        "category": "Internal factual contradiction",
        "title": "Conflicting Designation for Mr. Avik Mukherjee",
        "claude_explanation": "Avik Mukherjee identified as Executive Director in financial statements despite designation change.",
        "quote": "Avik Mukherjee Executive Director DIN: 10706114",
        "severity": "High",
        "confidence": 0.90,
        "evidence": [
            {
                "chunk_id": "chunk_financial",
                "quote": "Avik Mukherjee Executive Director DIN: 10706114",
                "page": 220
            }
        ]
    }

    # 3. Separate Pronoun Inconsistency Finding
    pronoun_finding = {
        "finding_id": "find_avik_pronoun_01",
        "category": "Pronoun / entity-reference ambiguity",
        "title": "Pronoun Gender Mismatch for Mr. Avik Mukherjee",
        "claude_explanation": "Mr. Avik Mukherjee is referenced as 'has offered herself for re-appointment' (expected 'himself', not 'herself').",
        "quote": "Mr. Avik Mukherjee ... has offered herself for re-appointment.",
        "severity": "Low",
        "confidence": 0.92,
        "evidence": [
            {
                "chunk_id": "chunk_pronoun",
                "quote": "Mr. Avik Mukherjee ... has offered herself for re-appointment.",
                "page": 60
            }
        ]
    }

    grounded_p, reason_p = verify_evidence(pronoun_finding, chunk_map)
    assert grounded_p is True, f"Pronoun evidence grounding failed: {reason_p}"

    norm_cat_p = normalize_category(pronoun_finding["category"])
    assert norm_cat_p == "Pronoun / entity-reference ambiguity"

    is_valid_p, val_reason_p = is_genuine_ambiguity(pronoun_finding)
    assert is_valid_p is True, f"Pronoun genuine ambiguity check failed: {val_reason_p}"

    # 4. Consolidation & Filtering Engine Check
    filter_engine = FindingRelevanceFilter(min_confidence=0.70)
    raw_findings = [designation_finding, designation_finding_duplicate, pronoun_finding]
    consolidated = filter_engine.filter_and_consolidate(raw_findings)

    # Must produce exactly 2 consolidated findings:
    # 1 high-severity designation contradiction and 1 low-severity pronoun ambiguity
    assert len(consolidated) == 2, f"Expected 2 consolidated findings, got {len(consolidated)}: {[f['title'] for f in consolidated]}"

    designation_res = next(f for f in consolidated if f["category"] == "Internal factual contradiction")
    pronoun_res = next(f for f in consolidated if f["category"] == "Pronoun / entity-reference ambiguity")

    # Verify designation finding severity & materiality
    assert designation_res["severity"] in ["HIGH", "CRITICAL"]
    assert designation_res["materiality"] == "Material"

    # Verify pronoun finding severity
    assert pronoun_res["severity"] == "LOW"


def test_mismatched_evidence_rejection():
    """Requirement 7: Verify that a finding claiming Management Committee vs Audit Committee with Foreign Exchange / Interest Rate Risk evidence is REJECTED as mismatched."""
    mismatched_finding = {
        "finding_id": "find_mismatched_01",
        "category": "Internal factual contradiction",
        "title": "Management Committee vs Audit Committee Governance Conflict",
        "claude_explanation": "Discrepancy in oversight responsibilities between the Management Committee and Audit Committee.",
        "quote": "Foreign Exchange Risk is managed by the treasury team.",
        "severity": "High",
        "confidence": 0.90,
        "evidence": [
            {
                "chunk_id": "chunk_01",
                "quote": "Foreign Exchange Risk is managed by the treasury team.",
                "page": 12
            },
            {
                "chunk_id": "chunk_02",
                "quote": "Interest Rate Risk is reviewed quarterly by the risk manager.",
                "page": 14
            }
        ]
    }

    is_valid, reason = is_genuine_ambiguity(mismatched_finding)
    assert is_valid is False, f"Expected mismatched finding to be rejected, but passed with reason: {reason}"
    assert "mismatched evidence" in reason, f"Unexpected rejection reason: {reason}"


def test_grounding_gate_unmapped_chunk_id():
    """Requirement 1: Verify that missing or synthetic chunk_id does not break document-wide quote search."""
    chunk_map = {
        "14": {"text": "Mr. Avik Mukherjee ... offered herself for re-appointment."}
    }

    finding_synthetic_cid = {
        "chunk_id": "cluster_001_issue_000",  # Synthetic chunk_id not in chunk_map
        "quote": "Mr. Avik Mukherjee ... offered herself for re-appointment.",
        "category": "Pronoun / entity-reference ambiguity",
        "evidence": [{"chunk_id": "cluster_001_issue_000", "quote": "Mr. Avik Mukherjee ... offered herself for re-appointment."}]
    }

    grounded, reason = verify_evidence(finding_synthetic_cid, chunk_map)
    assert grounded is True, f"Grounding failed for synthetic chunk_id: {reason}"
    assert finding_synthetic_cid["chunk_id"] == "14", f"Expected chunk_id to be re-anchored to '14', got: {finding_synthetic_cid['chunk_id']}"


