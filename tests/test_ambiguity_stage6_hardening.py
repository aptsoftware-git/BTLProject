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
    assert "could not be located" in reason4


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
