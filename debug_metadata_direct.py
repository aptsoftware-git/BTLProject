"""
debug_metadata_direct.py
=========================
Direct metadata verification without full pipeline.

Traces one element through early stages (1-9) to verify page/bbox propagation.
Stages 1-6: Extract -> Sentence (fast)
Stage 8-9: Candidate Creation (fast)

Does NOT run validation, merge, or LLM stages to avoid delays.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import List, Optional, Dict, Any

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from src.config import PipelineConfig
from src.extractor import DocumentExtractor
from src.layout_analyzer import LayoutAnalyzer
from src.filter import RunningTextFilter
from src.preprocessing import TextPreprocessor
from src.paragraph_builder import ParagraphBuilder
from src.sentence_splitter import SentenceSplitter
from src.languagetool_agent import LanguageToolAgent
from src.spell_agent import SpellAgent
from src.models import (
    Document, Sentence, Paragraph, LayoutBlock, 
    Candidate, index_paragraph_doc_offsets, index_sentence_doc_offsets
)
from src.logger import get_logger


def trace_metadata(label: str, obj: Any, indent: str = "  "):
    """Print metadata for an object."""
    page = getattr(obj, "page", None)
    page_number = getattr(obj, "page_number", None)
    bbox = getattr(obj, "bbox", None)
    element_id = getattr(obj, "element_id", None)
    sentence_id = getattr(obj, "sentence_id", None)
    text = getattr(obj, "text", None)
    original_text = getattr(obj, "original_text", None)
    
    print(f"{indent}{label}")
    print(f"{indent}  Type:           {type(obj).__name__}")
    print(f"{indent}  sentence_id:    {sentence_id}")
    print(f"{indent}  page:           {page}")
    print(f"{indent}  page_number:    {page_number}")
    print(f"{indent}  element_id:     {element_id}")
    print(f"{indent}  bbox:           {bbox}")
    if text:
        print(f"{indent}  text[:50]:      {text[:50]}")
    if original_text:
        print(f"{indent}  original_text[:50]: {original_text[:50]}")
    print()


def main():
    """Direct verification without full pipeline."""
    
    print("="*120)
    print("DIRECT METADATA VERIFICATION (Stages 1-9)")
    print("="*120 + "\n")
    
    config = PipelineConfig()
    logger = get_logger("debug_trace")
    
    # Find test document
    input_dir = config.paths.data_input_dir
    input_path = input_dir / "test_document.txt"
    
    if not input_path.exists():
        print("ERROR: Test document not found: {}".format(input_path))
        sys.exit(1)
    
    print("OK: Using test document: {}\n".format(input_path.name))
    
    # =================================================================
    # Stage 1: Extract
    # =================================================================
    print("="*120)
    print("STAGE 1: Document Extractor")
    print("="*120)
    extractor = DocumentExtractor(logger=logger, enable_ocr=False, enable_table_extraction=False)
    document = extractor.extract(input_path)
    print("OK: Extracted: {} chars, {} page(s)\n".format(len(document.raw_text), document.page_count))
    
    # =================================================================
    # Stage 2: Layout Analyzer
    # =================================================================
    print("="*120)
    print("STAGE 2: Layout Analyzer")
    print("="*120)
    layout_analyzer = LayoutAnalyzer(logger=logger)
    document = layout_analyzer.analyze(document)
    print("OK: Created {} layout blocks".format(len(document.layout_blocks)))
    
    # Trace first meaningful LayoutBlock
    for block in document.layout_blocks:
        if len(block.text.strip()) > 10:
            trace_metadata(f"LayoutBlock (id={block.block_id})", block)
            traced_block = block
            break
    
    # =================================================================
    # Stage 3: Filter
    # =================================================================
    print("="*120)
    print("STAGE 3: Running Text Filter")
    print("="*120)
    running_text_filter = RunningTextFilter(logger=logger)
    document = running_text_filter.filter(document)
    print("OK: Filtered text: {} chars\n".format(len(document.filtered_text)))
    
    # =================================================================
    # Stage 4: Preprocessor
    # =================================================================
    print("="*120)
    print("STAGE 4: Text Preprocessor")
    print("="*120)
    preprocessor = TextPreprocessor(logger=logger)
    document = preprocessor.normalize(document)
    print("OK: Normalized text: {} chars\n".format(len(document.normalized_text)))
    
    # =================================================================
    # Stage 5: Paragraph Builder
    # =================================================================
    print("="*120)
    print("STAGE 5: Paragraph Builder")
    print("="*120)
    paragraph_builder = ParagraphBuilder(logger=logger)
    document = paragraph_builder.build(document)
    print("OK: Built {} paragraphs".format(len(document.paragraphs)))
    
    # Trace first meaningful Paragraph
    traced_para = None
    for para in document.paragraphs:
        if len(para.text.strip()) > 20:
            trace_metadata(f"Paragraph (id={para.paragraph_id})", para)
            traced_para = para
            break
    
    # =================================================================
    # Stage 6: Sentence Splitter
    # =================================================================
    print("="*120)
    print("STAGE 6: Sentence Splitter")
    print("="*120)
    
    import spacy
    try:
        nlp = spacy.load("en_core_web_sm")
    except:
        nlp = None
    
    sentence_splitter = SentenceSplitter(logger=logger, config=config.spacy, nlp=nlp)
    document = sentence_splitter.split(document)
    
    # Index offsets
    index_paragraph_doc_offsets(document)
    index_sentence_doc_offsets(document)
    
    all_sentences = [s for p in document.paragraphs for s in p.sentences]
    print("OK: Split into {} sentences".format(len(all_sentences)))
    
    # Trace first meaningful Sentence
    traced_sentence = None
    for sent in all_sentences:
        if len(sent.text.strip()) > 10:
            trace_metadata(f"Sentence (id={sent.sentence_id}, para_id={sent.paragraph_id})", sent)
            traced_sentence = sent
            break
    
    if not traced_sentence:
        print("ERROR: No suitable sentence found for tracing")
        sys.exit(1)
    
    # =================================================================
    # Stage 8: LanguageTool Agent (Candidate Creation)
    # =================================================================
    print("="*120)
    print("STAGE 8: LanguageTool Agent (Candidate Creation)")
    print("="*120)
    
    languagetool_agent = LanguageToolAgent(config.languagetool)
    
    # Run on traced sentence
    candidates_from_lt = languagetool_agent.run(traced_sentence)
    print("OK: LanguageTool created {} candidate(s) from sentence {}".format(len(candidates_from_lt), traced_sentence.sentence_id))
    
    if candidates_from_lt:
        trace_metadata(f"Candidate from LanguageTool", candidates_from_lt[0])
        traced_candidate = candidates_from_lt[0]
    
    # =================================================================
    # Stage 9: SpellAgent (Candidate Creation - Fallback)
    # =================================================================
    print("="*120)
    print("STAGE 9: SpellAgent (Candidate Creation - Fallback)")
    print("="*120)
    
    spell_agent = SpellAgent(config.symspell)
    
    # Run on traced sentence
    candidates_from_spell = spell_agent.run(traced_sentence, set())
    print("OK: SpellAgent created {} candidate(s) from sentence {}".format(len(candidates_from_spell), traced_sentence.sentence_id))
    
    if candidates_from_spell:
        trace_metadata(f"Candidate from SpellAgent", candidates_from_spell[0])
        if not candidates_from_lt:
            traced_candidate = candidates_from_spell[0]
    
    # =================================================================
    # SUMMARY
    # =================================================================
    print("="*120)
    print("ANALYSIS SUMMARY")
    print("="*120 + "\n")
    
    print("OK: Metadata Flow Analysis:\n")
    
    if traced_para:
        print(f"[Paragraph {traced_para.paragraph_id}]")
        print(f"  page:       {traced_para.page}")
        print(f"  bbox:       {traced_para.bbox}")
        print(f"  element_id: {traced_para.element_id}\n")
    
    if traced_sentence:
        print(f"[Sentence {traced_sentence.sentence_id}]")
        print(f"  page:       {traced_sentence.page}")
        print(f"  bbox:       {traced_sentence.bbox}")
        print(f"  doc_char_start: {traced_sentence.doc_char_start}\n")
    
    if candidates_from_lt or candidates_from_spell:
        cand = candidates_from_lt[0] if candidates_from_lt else candidates_from_spell[0]
        print(f"[Candidate from {cand.source.value}]")
        print(f"  sentence_id:   {cand.sentence_id}")
        print(f"  page_number:   {cand.page_number}")
        print(f"  bbox:          {cand.bbox}")
        print(f"  original_text: {cand.original_text[:50] if cand.original_text else None}\n")
    
    # =================================================================
    # CRITICAL FINDINGS
    # =================================================================
    print("="*120)
    print("CRITICAL FINDINGS")
    print("="*120 + "\n")
    
    findings = {
        "sentence_has_bbox": traced_sentence.bbox is not None if traced_sentence else False,
        "sentence_has_page": traced_sentence.page is not None if traced_sentence else False,
        "candidate_has_bbox": (candidates_from_lt[0].bbox if candidates_from_lt else candidates_from_spell[0].bbox if candidates_from_spell else None) is not None,
        "candidate_has_page_number": (candidates_from_lt[0].page_number if candidates_from_lt else candidates_from_spell[0].page_number if candidates_from_spell else None) is not None,
    }
    
    print("Status:")
    print("  [S] Sentence.bbox:           {}".format('PRESENT' if findings['sentence_has_bbox'] else 'MISSING/None'))
    print("  [S] Sentence.page:           {}".format('PRESENT' if findings['sentence_has_page'] else 'MISSING/None'))
    print("  [C] Candidate.bbox:          {}".format('PRESENT' if findings['candidate_has_bbox'] else 'MISSING/None'))
    print("  [C] Candidate.page_number:   {}".format('PRESENT' if findings['candidate_has_page_number'] else 'MISSING/None'))
    
    print("\nRisk Assessment:")
    if not findings['sentence_has_bbox']:
        print("  [WARN] Sentence.bbox is None - metadata lost at Stage 6")
        print("         Impact: Candidates will receive None for bbox")
    elif not findings['candidate_has_bbox']:
        print("  [WARN] Candidate.bbox is None - metadata lost at Stage 8-9")
        print("         Impact: ValidatedIssue and MergedIssue will not have bbox")
        print("         Location: src/languagetool_agent.py or src/spell_agent.py")
    else:
        print("  [OK] Positional metadata preserved through Stage 9!")
    
    # Close resources
    languagetool_agent.close()


if __name__ == "__main__":
    main()
