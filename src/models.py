"""
models.py
=========
Dataclass-based data contracts for the proofreading pipeline.

Section 1 (Document / LayoutBlock / Paragraph / Sentence) is the contract
stages 1-6 (extractor, layout_analyzer, filter, preprocessing,
paragraph_builder, sentence_splitter) read and write.

Section 2 (ProtectedTerm / Candidate / ValidatedIssue / MergedIssue /
SemanticCheckResult) is the contract stages 7-16 (protected terms builder,
spell/grammar agents, validation, difference engine, merge, annotator,
report generator) use.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


# ---------------------------------------------------------------------------
# Section 1: document structure (stages 1-6)
# ---------------------------------------------------------------------------

class BlockType(str, Enum):
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    TABLE = "table"
    CAPTION = "caption"
    FIGURE = "figure"
    HEADER = "header"
    FOOTER = "footer"
    REFERENCE = "reference"
    PAGE_NUMBER = "page_number"


@dataclass
class LayoutBlock:
    block_id: int
    page: int
    text: str
    block_type: BlockType


@dataclass
class Sentence:
    sentence_id: int
    paragraph_id: int
    page: int
    text: str
    start_offset: int  # offset relative to the PARAGRAPH's text
    end_offset: int

    # Document-level offsets. Left as None until index_sentence_doc_offsets()
    # is run (once, right after paragraph doc-offsets are known); every
    # stage-7+ agent (LanguageTool, SymSpell, protected-terms overlap checks)
    # reads these two fields directly rather than re-deriving them.
    doc_char_start: Optional[int] = None
    doc_char_end: Optional[int] = None


@dataclass
class Paragraph:
    paragraph_id: int
    page: int
    text: str
    sentences: List[Sentence] = field(default_factory=list)

    # Filled in once by index_paragraph_doc_offsets() so downstream stages
    # that need a *document-level* character offset (protected-terms spans,
    # annotator highlighting) don't have to re-derive it themselves.
    doc_char_start: Optional[int] = None


@dataclass
class Document:
    name: str
    source_path: str
    file_type: str
    raw_text: str
    page_count: int

    layout_blocks: List[LayoutBlock] = field(default_factory=list)
    filtered_text: str = ""
    normalized_text: str = ""
    paragraphs: List[Paragraph] = field(default_factory=list)


def index_paragraph_doc_offsets(document: Document) -> None:
    """
    Populate Paragraph.doc_char_start for every paragraph, by locating each
    paragraph's text within document.normalized_text in order. Call this
    once, right after paragraph_builder / sentence_splitter have run and
    before any stage-7+ agent needs a document-level offset.

    Paragraphs are joined by "\\n\\n" in paragraph_builder, and each
    paragraph's text is stripped, so a simple sequential .find() (starting
    the search after the end of the previous match) reconstructs the real
    offsets without assuming a fixed separator width.
    """
    cursor = 0
    for paragraph in document.paragraphs:
        idx = document.normalized_text.find(paragraph.text, cursor)
        if idx == -1:
            # Should not normally happen (paragraphs come from splitting this
            # same text), but fail safe rather than crash the whole pipeline.
            paragraph.doc_char_start = cursor
            continue
        paragraph.doc_char_start = idx
        cursor = idx + len(paragraph.text)


def index_sentence_doc_offsets(document: Document) -> None:
    """
    Populate Sentence.doc_char_start / doc_char_end for every sentence in
    every paragraph, using each paragraph's already-computed
    doc_char_start plus the sentence's paragraph-relative offsets.

    Must be called AFTER index_paragraph_doc_offsets().
    """
    for paragraph in document.paragraphs:
        base = paragraph.doc_char_start or 0
        for sentence in paragraph.sentences:
            sentence.doc_char_start = base + sentence.start_offset
            sentence.doc_char_end = base + sentence.end_offset


def sentence_doc_offsets(paragraph: Paragraph, sentence: Sentence) -> tuple[int, int]:
    """Convert a Sentence's paragraph-relative offsets into full-document offsets."""
    base = paragraph.doc_char_start or 0
    return base + sentence.start_offset, base + sentence.end_offset


# ---------------------------------------------------------------------------
# Section 2: detection / validation / merge contracts (stages 7-16)
# ---------------------------------------------------------------------------

class IssueType(str, Enum):
    SPELLING = "spelling"
    GRAMMAR = "grammar"
    TENSE = "tense"
    PUNCTUATION = "punctuation"
    STYLE = "style"


class SourceAgent(str, Enum):
    SYMSPELL = "symspell"
    LANGUAGETOOL = "languagetool"
    LLM = "llm"
    T5 = "t5"


@dataclass
class ProtectedTerm:
    text: str
    char_start: int  # document-level offset
    char_end: int
    reason: str


@dataclass
class Candidate:
    """Raw output from a single detection agent, before validation."""
    sentence_id: int
    char_start: int  # document-level offset
    char_end: int
    original_text: str
    suggested_text: str
    issue_type: IssueType
    source: SourceAgent
    reason: str
    confidence: float = 0.5


@dataclass
class ValidatedIssue(Candidate):
    is_protected: bool = False
    protected_reason: Optional[str] = None


@dataclass
class MergedIssue(ValidatedIssue):
    agreement_count: int = 1
    final_confidence: float = 0.5
    contributing_sources: List[SourceAgent] = field(default_factory=list)
    severity: str = "medium"


@dataclass
class SemanticCheckResult:
    candidate_index: int
    meaning_preserved: bool
    grammatically_correct: bool
    notes: str = ""
