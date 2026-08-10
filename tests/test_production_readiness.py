"""
test_production_readiness.py
==============================
Production Readiness Audit & Remediation Verification Suite.
Tests grounding, protected terms, scope restrictions, startup recovery model,
page mapping interpolation, and API action endpoints.
"""

import pytest
import logging
from pathlib import Path
from src.paragraph_builder import ParagraphBuilder
from src.protected_terms import ProtectedTermsBuilder
from src.config import SpacyConfig, ValidationConfig
from src.validation_agent import ValidationAgent
from src.models import Candidate, Paragraph, LayoutBlock, Document
from backend.routes import _normalize_issue_metadata


def test_normalize_bbox_validation():
    """Verify _normalize_bbox rejects zero/invalid coordinates and returns None."""
    pb = ParagraphBuilder(logging.getLogger("test"))
    assert pb._normalize_bbox({"x0": 0, "y0": 0, "x1": 0, "y1": 0}) is None
    assert pb._normalize_bbox({"x0": 10, "y0": 10, "x1": 5, "y1": 5}) is None
    assert pb._normalize_bbox(None) is None
    valid = pb._normalize_bbox({"x0": 10.5, "y0": 20.0, "x1": 100.0, "y1": 200.0})
    assert valid == {"x0": 10.5, "y0": 20.0, "x1": 100.0, "y1": 200.0}


def test_paragraph_page_interpolation():
    """Verify unmatched paragraphs interpolate page from neighboring paragraphs instead of defaulting to Page 1."""
    pb = ParagraphBuilder(logging.getLogger("test"))
    text = "Header text on page 5\n\nMiddle body paragraph\n\nFooter text on page 5"
    layout_paras = [
        LayoutBlock(block_id="b1", block_type="paragraph", text="Header text on page 5", page=5, bbox={"x0": 10, "y0": 10, "x1": 100, "y1": 50}, element_id="p1"),
        LayoutBlock(block_id="b2", block_type="paragraph", text="Footer text on page 5", page=5, bbox={"x0": 10, "y0": 500, "x1": 100, "y1": 550}, element_id="p3")
    ]
    doc = Document(name="doc1", source_path=Path("doc.pdf"), file_type="pdf", page_count=5, raw_text=text, normalized_text=text, layout_blocks=layout_paras)
    res_doc = pb.build(doc)
    assert len(res_doc.paragraphs) == 3
    # Middle paragraph should be interpolated to Page 5, NOT default Page 1!
    assert res_doc.paragraphs[1].page == 5


def test_protected_terms_enterprise_acronyms():
    """Verify enterprise & financial terms (SEBI, ICAI, UDIN, SCADA, SAP, HVDC) are protected."""
    text = "The SEBI and ICAI guidelines require UDIN verification for SCADA and SAP HVDC systems."
    builder = ProtectedTermsBuilder(spacy_config=SpacyConfig(), validation_config=ValidationConfig())
    terms = builder.build(text)
    protected_texts = {t.text for t in terms}
    
    assert "SEBI" in protected_texts
    assert "ICAI" in protected_texts
    assert "UDIN" in protected_texts
    assert "SCADA" in protected_texts
    assert "SAP" in protected_texts
    assert "HVDC" in protected_texts


def test_validation_agent_british_american_and_scope():
    """Verify British vs American spelling swaps and style rewrites are rejected."""
    agent = ValidationAgent(protected_terms=[])
    candidates = [
        Candidate(original_text="fertiliser", suggested_text="fertilizer", char_start=0, char_end=10, sentence_id="s1", issue_type="spelling", source="spell", reason="Spelling change"),
        Candidate(original_text="colour", suggested_text="color", char_start=0, char_end=6, sentence_id="s2", issue_type="spelling", source="spell", reason="Spelling change"),
        Candidate(original_text="good text", suggested_text="more formal text", char_start=0, char_end=9, sentence_id="s3", issue_type="style", source="llm", reason="Make tone more formal"),
        Candidate(original_text="receat", suggested_text="receipt", char_start=0, char_end=6, sentence_id="s4", issue_type="spelling", source="spell", reason="Spelling error")
    ]
    accepted, rejected = agent.validate(candidates)
    
    accepted_origs = {c.original_text for c in accepted}
    rejected_origs = {c.original_text for c in rejected}

    assert "receat" in accepted_origs
    assert "fertiliser" in rejected_origs
    assert "colour" in rejected_origs
    assert "good text" in rejected_origs


def test_normalize_issue_metadata_grounding_flag():
    """Verify location_verified is set correctly and bbox is null when unverified."""
    raw = [
        {"issue_id": "i1", "page": 2, "bbox": {"x0": 10, "y0": 20, "x1": 50, "y1": 60}},
        {"issue_id": "i2", "page": 2, "bbox": {"x0": 0, "y0": 0, "x1": 0, "y1": 0}},
        {"issue_id": "i3", "page": 3, "bbox": None}
    ]
    norm = _normalize_issue_metadata(raw)
    
    assert norm[0]["location_verified"] is True
    assert norm[0]["bbox"] == {"x0": 10.0, "y0": 20.0, "x1": 50.0, "y1": 60.0}
    
    assert norm[1]["location_verified"] is False
    assert norm[1]["bbox"] is None
    
    assert norm[2]["location_verified"] is False
    assert norm[2]["bbox"] is None
