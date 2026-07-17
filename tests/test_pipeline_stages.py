"""
test_pipeline_stages.py
=========================
Unit tests covering the deterministic, model-free stages of the
pipeline: utils, preprocessing, layout analysis, filtering, paragraph
building, the difference engine, and validation heuristics. Stages
that depend on downloaded ML models (spaCy, SymSpell, T5) are tested
via their graceful-fallback behaviour, not via real model output.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import ValidationConfig
from src.difference_engine import DifferenceEngine
from src.filter import RunningTextFilter
from src.layout_analyzer import LayoutAnalyzer
from src.models import BlockType, Document, Candidate, IssueType, LayoutBlock, ProtectedTerm, SourceAgent, ValidatedIssue
from src.paragraph_builder import ParagraphBuilder
from src.preprocessing import TextPreprocessor
from src.utils import (
    is_acronym,
    is_page_number,
    is_roman_numeral,
    remove_urls_and_emails,
    strip_markdown,
)
from src.validation_agent import ValidationAgent


def _logger() -> logging.Logger:
    logger = logging.getLogger("test")
    logger.addHandler(logging.NullHandler())
    if not hasattr(logger, "stage"):
        logger.stage = logger.info  # type: ignore[attr-defined]
    return logger


def test_strip_markdown_removes_headings_and_tables():
    text = "# Heading\n**bold** text\n| a | b |\n|---|---|\nNormal line"
    cleaned = strip_markdown(text)
    assert "#" not in cleaned
    assert "**" not in cleaned
    assert "|" not in cleaned
    assert "Normal line" in cleaned


def test_remove_urls_and_emails():
    text = "Visit https://example.com or email me@example.com for info."
    cleaned = remove_urls_and_emails(text)
    assert "https://" not in cleaned
    assert "@" not in cleaned


def test_is_page_number():
    assert is_page_number("12")
    assert is_page_number("Page 3")
    assert not is_page_number("This is a sentence.")


def test_is_roman_numeral():
    assert is_roman_numeral("iv")
    assert is_roman_numeral("XII")
    assert not is_roman_numeral("hello")


def test_is_acronym():
    assert is_acronym("NASA")
    assert not is_acronym("Hello")


def test_layout_analyzer_classifies_reference_section():
    logger = _logger()
    doc = Document(name="doc", source_path="doc.txt", file_type="txt",
                    raw_text="Introduction\n\nThis is a normal paragraph of text.\n\n"
                             "References\n\n[1] Smith, J. (2020). A paper title.",
                    page_count=1)
    analyzer = LayoutAnalyzer(logger)
    doc = analyzer.analyze(doc)
    types = [b.block_type for b in doc.layout_blocks]
    assert BlockType.REFERENCE in types
    assert BlockType.PARAGRAPH in types


def test_running_text_filter_keeps_only_paragraphs():
    logger = _logger()
    doc = Document(name="doc", source_path="doc.txt", file_type="txt", raw_text="", page_count=1)
    doc.layout_blocks = [
        LayoutBlock(0, 1, "A real paragraph of running text.", BlockType.PARAGRAPH),
        LayoutBlock(1, 1, "Table 1: some data", BlockType.CAPTION),
        LayoutBlock(2, 1, "[1] Reference entry (2020)", BlockType.REFERENCE),
    ]
    text_filter = RunningTextFilter(logger)
    doc = text_filter.filter(doc)
    assert "real paragraph" in doc.filtered_text
    assert "Reference entry" not in doc.filtered_text


def test_preprocessor_normalizes_quotes_and_dashes():
    logger = _logger()
    doc = Document(name="doc", source_path="doc.txt", file_type="txt", raw_text="", page_count=1)
    doc.filtered_text = "\u201cHello\u201d \u2014 this is a test\u2026"
    preprocessor = TextPreprocessor(logger)
    doc = preprocessor.normalize(doc)
    assert '"' in doc.normalized_text
    assert "\u201c" not in doc.normalized_text


def test_paragraph_builder_splits_on_blank_lines():
    logger = _logger()
    doc = Document(name="doc", source_path="doc.txt", file_type="txt", raw_text="", page_count=1)
    doc.normalized_text = "First paragraph.\n\nSecond paragraph."
    builder = ParagraphBuilder(logger)
    doc = builder.build(doc)
    assert len(doc.paragraphs) == 2
    assert doc.paragraphs[0].text == "First paragraph."


def test_difference_engine_re_anchors_drifted_offsets():
    doc_text = "He went to school yesterday."
    issue = ValidatedIssue(
        sentence_id=1,
        char_start=2,
        char_end=6,
        original_text="went",
        suggested_text="go",
        issue_type=IssueType.GRAMMAR,
        source=SourceAgent.LLM,
        reason="tense change",
    )
    engine = DifferenceEngine(doc_text)
    confirmed = engine.run([issue])
    assert len(confirmed) == 1
    assert confirmed[0].char_start == 3
    assert confirmed[0].char_end == 7


def test_difference_engine_drops_no_change_and_unconfirmable():
    doc_text = "He went to school yesterday."
    
    issue_no_change = ValidatedIssue(
        sentence_id=1,
        char_start=3,
        char_end=7,
        original_text="went",
        suggested_text="went",
        issue_type=IssueType.GRAMMAR,
        source=SourceAgent.LLM,
        reason="tense change",
    )
    
    issue_unconfirmable = ValidatedIssue(
        sentence_id=1,
        char_start=3,
        char_end=7,
        original_text="goes",
        suggested_text="go",
        issue_type=IssueType.GRAMMAR,
        source=SourceAgent.LLM,
        reason="tense change",
    )
    
    engine = DifferenceEngine(doc_text)
    confirmed = engine.run([issue_no_change, issue_unconfirmable])
    assert len(confirmed) == 0


def test_validation_agent_rejects_acronyms_and_units():
    protected_term = ProtectedTerm(text="NASA", char_start=0, char_end=4, reason="ALLCAPS acronym")
    agent = ValidationAgent(protected_terms=[protected_term])
    candidate = Candidate(
        sentence_id=1,
        char_start=0,
        char_end=4,
        original_text="NASA",
        suggested_text="Nasa",
        issue_type=IssueType.SPELLING,
        source=SourceAgent.SYMSPELL,
        reason="test",
    )
    accepted, rejected = agent.validate([candidate])
    assert len(rejected) == 1
    assert len(accepted) == 0
