"""
debug_metadata_trace.py
========================
Runtime verification: Trace positional metadata (page, bbox) through the pipeline.

Instruments the pipeline to capture and display actual values for one element
as it flows through:
  LayoutBlock -> Paragraph -> Sentence -> Candidate -> ValidatedIssue -> MergedIssue

Shows filenames, classes, methods, and line numbers where metadata is present or becomes None.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import List, Optional, Dict, Any

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from src.config import PipelineConfig
from src.pipeline import ProofreadingPipeline
from src.models import (
    Document, Sentence, Paragraph, LayoutBlock, 
    Candidate, ValidatedIssue, MergedIssue
)


class MetadataTracer:
    """Traces a single element through the pipeline, recording metadata at each stage."""
    
    def __init__(self):
        self.trace_log = []
        self.traced_sentence_id = None
        self.traced_element_id = None
    
    def record(self, stage: str, obj: Any, cls_name: str, method: str, line: str):
        """Record metadata at a stage."""
        entry = {
            "stage": stage,
            "class": cls_name,
            "method": method,
            "line": line,
            "object_type": type(obj).__name__,
            "page": getattr(obj, "page", getattr(obj, "page_number", None)),
            "page_number": getattr(obj, "page_number", None),
            "bbox": getattr(obj, "bbox", None),
            "element_id": getattr(obj, "element_id", None),
            "original_text": getattr(obj, "original_text", getattr(obj, "text", None))[:50] if getattr(obj, "original_text", getattr(obj, "text", None)) else None,
            "sentence_id": getattr(obj, "sentence_id", None),
            "doc_char_start": getattr(obj, "doc_char_start", None),
        }
        self.trace_log.append(entry)
        return entry
    
    def print_trace(self):
        """Print the trace log in a readable format."""
        print("\n" + "="*120)
        print("METADATA TRACE LOG")
        print("="*120)
        
        for idx, entry in enumerate(self.trace_log):
            print(f"\n[{idx+1}] {entry['stage']}")
            print(f"    Class:         {entry['class']}")
            print(f"    Method:        {entry['method']}")
            print(f"    Line:          {entry['line']}")
            print(f"    Object Type:   {entry['object_type']}")
            print(f"    Sentence ID:   {entry['sentence_id']}")
            print(f"    page:          {entry['page']}")
            print(f"    page_number:   {entry['page_number']}")
            print(f"    bbox:          {entry['bbox']}")
            print(f"    element_id:    {entry['element_id']}")
            print(f"    original_text: {entry['original_text']}")
            print(f"    doc_char_start:{entry['doc_char_start']}")
            
            # Detect where bbox becomes None
            if idx > 0 and self.trace_log[idx-1]['bbox'] is not None and entry['bbox'] is None:
                print(f"    ⚠️  WARNING: bbox became None at this stage!")


# Global tracer instance
tracer = MetadataTracer()


def instrument_pipeline():
    """Monkey-patch key methods to trace metadata flow."""
    
    # Store original methods
    original_methods = {}
    
    # Global variable to track if we've already traced a candidate
    traced_state = {"traced_candidate": False}
    
    # =================================================================
    # Stage 5: Paragraph Builder
    # =================================================================
    from src.paragraph_builder import ParagraphBuilder
    original_pb_build = ParagraphBuilder.build
    
    def traced_pb_build(self, document: Document, job_dir: Optional[Path] = None) -> Document:
        result = original_pb_build(self, document, job_dir)
        # Trace first paragraph with content
        for para in result.paragraphs:
            if para.text.strip():
                tracer.record(
                    stage="Stage 5: Paragraph Builder",
                    obj=para,
                    cls_name="Paragraph",
                    method="build()",
                    line="src/paragraph_builder.py:47-51"
                )
                tracer.traced_element_id = para.element_id
                break
        return result
    
    ParagraphBuilder.build = traced_pb_build
    original_methods['ParagraphBuilder.build'] = original_pb_build
    
    # =================================================================
    # Stage 6: Sentence Splitter
    # =================================================================
    from src.sentence_splitter import SentenceSplitter
    original_ss_split = SentenceSplitter.split
    
    def traced_ss_split(self, document: Document) -> Document:
        result = original_ss_split(self, document)
        # Trace first sentence
        for para in result.paragraphs:
            for sent in para.sentences:
                tracer.traced_sentence_id = sent.sentence_id
                tracer.record(
                    stage="Stage 6: Sentence Splitter",
                    obj=sent,
                    cls_name="Sentence",
                    method="split()",
                    line="src/sentence_splitter.py:69-78"
                )
                return result
        return result
    
    SentenceSplitter.split = traced_ss_split
    original_methods['SentenceSplitter.split'] = original_ss_split
    
    # =================================================================
    # Stage 8-9: LanguageTool/SpellAgent - Candidate Creation
    # =================================================================
    from src.languagetool_agent import LanguageToolAgent
    from src.spell_agent import SpellAgent
    
    original_lt_run = LanguageToolAgent.run if hasattr(LanguageToolAgent, 'run') else None
    original_spell_run = SpellAgent.run if hasattr(SpellAgent, 'run') else None
    
    def traced_lt_run(self, sentence: Sentence) -> List[Candidate]:
        result = original_lt_run(self, sentence)
        # Trace first candidate with valid sentence_id
        if not traced_state["traced_candidate"]:
            for cand in result:
                if cand.sentence_id >= 0:
                    tracer.traced_sentence_id = cand.sentence_id
                    tracer.record(
                        stage="Stage 8-9: LanguageTool Agent (Candidate Creation)",
                        obj=cand,
                        cls_name="Candidate",
                        method="run()",
                        line="src/languagetool_agent.py:55-64"
                    )
                    traced_state["traced_candidate"] = True
                    break
        return result
    
    if original_lt_run:
        LanguageToolAgent.run = traced_lt_run
        original_methods['LanguageToolAgent.run'] = original_lt_run
    
    def traced_spell_run(self, sentence: Sentence, protected_spans) -> List[Candidate]:
        result = original_spell_run(self, sentence)
        # Trace first candidate with valid sentence_id
        if not traced_state["traced_candidate"]:
            for cand in result:
                if cand.sentence_id >= 0:
                    tracer.traced_sentence_id = cand.sentence_id
                    tracer.record(
                        stage="Stage 8-9: SpellAgent (Candidate Creation)",
                        obj=cand,
                        cls_name="Candidate",
                        method="run()",
                        line="src/spell_agent.py:170-180"
                    )
                    traced_state["traced_candidate"] = True
                    break
        return result
    
    if original_spell_run:
        SpellAgent.run = traced_spell_run
        original_methods['SpellAgent.run'] = original_spell_run
    
    # =================================================================
    # Stage 10: Validation Agent
    # =================================================================
    from src.validation_agent import ValidationAgent
    original_validate = ValidationAgent.validate
    
    def traced_validate(self, candidates: List[Candidate]) -> tuple[List[ValidatedIssue], List[ValidatedIssue]]:
        result_accepted, result_rejected = original_validate(self, candidates)
        # Find our traced candidate
        if tracer.traced_sentence_id is not None:
            for issue in result_accepted:
                if hasattr(issue, 'sentence_id') and issue.sentence_id == tracer.traced_sentence_id:
                    tracer.record(
                        stage="Stage 10: Validation Agent (ValidatedIssue)",
                        obj=issue,
                        cls_name="ValidatedIssue",
                        method="validate()",
                        line="src/validation_agent.py:33-40"
                    )
                    break
        return result_accepted, result_rejected
    
    ValidationAgent.validate = traced_validate
    original_methods['ValidationAgent.validate'] = original_validate
    
    # =================================================================
    # Stage 14: Merge Agent
    # =================================================================
    from src.merge_agent import MergeAgent
    original_merge = MergeAgent.merge
    
    def traced_merge(self, validated_issues: List[ValidatedIssue]) -> List[MergedIssue]:
        result = original_merge(self, validated_issues)
        # Find our traced issue
        if tracer.traced_sentence_id is not None:
            for merged in result:
                if hasattr(merged, 'sentence_id') and merged.sentence_id == tracer.traced_sentence_id:
                    tracer.record(
                        stage="Stage 14: Merge Agent (MergedIssue)",
                        obj=merged,
                        cls_name="MergedIssue",
                        method="merge()",
                        line="src/merge_agent.py:132-140"
                    )
                    break
        return result
    
    MergeAgent.merge = traced_merge
    original_methods['MergeAgent.merge'] = original_merge
    
    return original_methods


def main():
    """Run the pipeline with instrumentation."""
    
    print("="*120)
    print("RUNTIME METADATA VERIFICATION")
    print("="*120)
    
    config = PipelineConfig()
    input_dir = config.paths.data_input_dir
    
    # Find a simple test document
    test_files = [
        "test_document.txt",
        "sample_ambiguity_test_document.txt",
        "sample_paragraphs_with_intentional_errors.txt",
        "comprehensive_test_doc.txt",
    ]
    
    input_path = None
    for test_file in test_files:
        candidate = input_dir / test_file
        if candidate.exists():
            input_path = candidate
            break
    
    if not input_path:
        print(f"❌ No test document found in {input_dir}")
        print(f"   Available: {list(input_dir.glob('*.txt'))}")
        sys.exit(1)
    
    print(f"\n✓ Using test document: {input_path.name}")
    
    # Instrument the pipeline
    print("\n✓ Installing metadata instrumentation...")
    instrument_pipeline()
    
    # Run the pipeline
    print("✓ Running pipeline (this may take a minute)...\n")
    
    try:
        with ProofreadingPipeline(config) as pipeline:
            result = pipeline.run(input_path)
        
        print(f"\n✓ Pipeline completed")
        print(f"  Total issues found: {result['total_issues']}")
        print(f"  Accepted: {result['accepted']}")
        print(f"  Rejected (protected): {result['rejected_protected']}")
        print(f"  Rejected (semantic): {result['rejected_semantic']}")
        
    except Exception as e:
        print(f"❌ Pipeline failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # Print the trace
    tracer.print_trace()
    
    # Summary
    print("\n" + "="*120)
    print("ANALYSIS SUMMARY")
    print("="*120)
    
    if tracer.trace_log:
        first_bbox = tracer.trace_log[0]['bbox']
        last_bbox = tracer.trace_log[-1]['bbox']
        
        print(f"\n✓ Traced {len(tracer.trace_log)} stages")
        print(f"\n  First bbox value (Stage 5 Paragraph):  {first_bbox}")
        print(f"  Final bbox value (Stage 14 MergedIssue): {last_bbox}")
        
        # Find where bbox becomes None
        for idx, entry in enumerate(tracer.trace_log):
            if entry['bbox'] is None:
                print(f"\n⚠️  bbox is None starting at Stage {idx+1}: {entry['stage']}")
                if idx > 0:
                    prev = tracer.trace_log[idx-1]
                    print(f"   Previous stage: {prev['stage']}")
                    print(f"   Becomes None in: {entry['class']}.{entry['method']} at {entry['line']}")
                break
        else:
            print(f"\n✓ bbox maintained throughout all stages!")
    else:
        print("\n❌ No trace data collected. Check instrumentation.")


if __name__ == "__main__":
    main()
