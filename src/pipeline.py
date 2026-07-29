"""
pipeline.py
============
Orchestrator that wires together all 16 stages of the proofreading pipeline:

  1.  DocumentExtractor        (extractor.py)
  2.  LayoutAnalyzer            (layout_analyzer.py)
  3.  RunningTextFilter         (filter.py)
  4.  TextPreprocessor          (preprocessing.py)
  5.  ParagraphBuilder          (paragraph_builder.py)
  6.  SentenceSplitter          (sentence_splitter.py)
  7.  ProtectedTermsBuilder     (protected_terms.py)
  8.  LanguageToolAgent         (languagetool_agent.py)
  9.  SpellAgent (fallback)     (spell_agent.py)
  10. ValidationAgent           (validation_agent.py)
  11. GrammarAgent (LLM)        (grammar_agent.py)
  12. SemanticValidator         (semantic_validator.py)
  13. DifferenceEngine          (difference_engine.py)
  14. MergeAgent                (merge_agent.py)
  15. Annotator                 (annotator.py)
  16. ReportGenerator           (report_generator.py)

Each stage's constructor receives exactly the config dataclass slice it
needs (dependency injection via config.PipelineConfig), so no module here
or downstream reaches back into config.py for a module-level constant.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Set, Tuple

from src.annotator import Annotator
from src.config import PipelineConfig
from src.difference_engine import DifferenceEngine
from src.extractor import DocumentExtractor
from src.filter import RunningTextFilter
from src.grammar_agent import GrammarAgent
from src.languagetool_agent import LanguageToolAgent
from src.layout_analyzer import LayoutAnalyzer
from src.logger import get_logger
from src.merge_agent import MergeAgent
from src.models import (
    Candidate,
    MergedIssue,
    Sentence,
    index_paragraph_doc_offsets,
    index_sentence_doc_offsets,
)
from src.paragraph_builder import ParagraphBuilder
from src.preprocessing import TextPreprocessor
from src.protected_terms import ProtectedTermsBuilder
from src.report_generator import ReportGenerator
from src.semantic_validator import SemanticValidator
from src.sentence_splitter import SentenceSplitter
from src.spell_agent import SpellAgent
from src.text_writer import TextWriter
from src.utils import save_json, save_text, timestamp
from src.validation_agent import ValidationAgent


class ProofreadingPipeline:
    """Runs a single document through all 16 proofreading stages."""

    def __init__(self, config: PipelineConfig | None = None) -> None:
        self.config = config or PipelineConfig()
        self.logger = get_logger("pipeline")

        # Load spaCy model once to avoid duplicate loading
        import spacy
        try:
            self.nlp = spacy.load(self.config.spacy.model_name)
        except Exception as exc:
            self.logger.warning("Could not load spaCy model: %s", exc)
            self.nlp = None

        # Stateless / cheap stages -- constructed once up front.
        self.extractor = DocumentExtractor(
            logger=self.logger,
            enable_ocr=self.config.docling.enable_ocr,
            enable_table_extraction=self.config.docling.enable_table_extraction,
        )
        self.layout_analyzer = LayoutAnalyzer(logger=self.logger)
        self.running_text_filter = RunningTextFilter(logger=self.logger)
        self.preprocessor = TextPreprocessor(logger=self.logger)
        self.paragraph_builder = ParagraphBuilder(logger=self.logger)
        self.sentence_splitter = SentenceSplitter(logger=self.logger, config=self.config.spacy, nlp=self.nlp)

        # Stages backed by external resources (spaCy model, Java server,
        # dictionary file, Ollama) -- constructed once here too, so the
        # expensive setup (loading models, starting the LanguageTool JVM)
        # happens once per pipeline instance rather than once per document.
        self.protected_terms_builder = ProtectedTermsBuilder(
            spacy_config=self.config.spacy, validation_config=self.config.validation, nlp=self.nlp
        )
        self.languagetool_agent = LanguageToolAgent(self.config.languagetool)
        self.spell_agent = SpellAgent(self.config.symspell)
        self.grammar_agent = GrammarAgent(self.config.ollama)
        self.semantic_validator = SemanticValidator(self.config.ollama)
        self.merge_agent = MergeAgent(self.config.merge)

    def close(self) -> None:
        """Release external resources (the LanguageTool JVM process)."""
        self.languagetool_agent.close()

    def __enter__(self) -> "ProofreadingPipeline":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    # ------------------------------------------------------------------
    def run(self, input_path: Path, run_id: str | None = None) -> dict:
        from src.rag.cache_manager import DocumentCacheManager, compute_file_hash

        run_id = run_id or f"{input_path.stem}_{timestamp()}"
        run_dir = self.config.paths.data_output_dir / run_id
        stage_dirs = {name: run_dir / name for name in self.config.stage_folders}
        for path in stage_dirs.values():
            path.mkdir(parents=True, exist_ok=True)

        # SHA-256 Cache Check (Requirement 1 & Primary Objective)
        doc_hash = compute_file_hash(input_path)
        cache_mgr = DocumentCacheManager(doc_hash, input_path.name)
        cache_mgr.sync_to_job_dir(run_dir)

        log_file = stage_dirs["logs"] / "pipeline.log"
        self.logger = get_logger("pipeline", log_file=log_file)

        proof_report_file = stage_dirs["10_final"] / "report.json"
        if proof_report_file.exists() and proof_report_file.stat().st_size > 0:
            self.logger.info("[CACHE HIT] Proofreading stage is already completed for document %s. Skipping re-execution.", doc_hash[:10])
            import json
            try:
                with open(proof_report_file, "r", encoding="utf-8") as f:
                    cached_report = json.load(f)
                    return {
                        "run_dir": str(run_dir),
                        "total_issues": cached_report.get("total_issues", 0),
                        "accepted": len(cached_report.get("issues", [])),
                        "rejected_protected": 0,
                        "rejected_semantic": 0,
                        "rejected_confidence": 0,
                    }
            except Exception as e:
                self.logger.warning("Could not read cached proofreading report: %s. Re-running...", e)

        # --- Stages 1-4: extract, layout, filter, preprocess -----------
        document = self.extractor.extract(input_path, output_dir=run_dir)
        save_text(document.raw_text, stage_dirs["01_raw"] / "raw_text.txt")

        document = self.layout_analyzer.analyze(document)
        document = self.running_text_filter.filter(document)
        save_text(document.filtered_text, stage_dirs["02_filtered"] / "filtered_text.txt")

        document = self.preprocessor.normalize(document)
        save_text(document.normalized_text, stage_dirs["03_preprocessed"] / "normalized_text.txt")

        # --- Stages 5-6: paragraphs + sentences -------------------------
        document = self.paragraph_builder.build(document)
        document = self.sentence_splitter.split(document)
        index_paragraph_doc_offsets(document)
        index_sentence_doc_offsets(document)
        all_sentences: List[Sentence] = [s for p in document.paragraphs for s in p.sentences]
        save_json(all_sentences, stage_dirs["04_sentences"] / "sentences.json")
        self.logger.info(
            "Paragraphs: %d | Sentences: %d", len(document.paragraphs), len(all_sentences)
        )

        # --- Stage 7: Protected Terms Builder ---------------------------
        self.logger.stage("Building protected terms")
        # Load user-defined whitelist terms if they exist
        whitelist_path = self.config.paths.data_input_dir.parent / "protected_terms_whitelist.json"
        whitelist_extra = []
        if whitelist_path.exists():
            import json
            try:
                with open(whitelist_path, "r", encoding="utf-8") as f:
                    whitelist_extra = json.load(f)
            except Exception as e:
                self.logger.warning("Error loading whitelist: %s", e)
        self.protected_terms_builder.whitelist_extra = set(whitelist_extra)

        protected_terms = self.protected_terms_builder.build(document.normalized_text)
        save_json(protected_terms, stage_dirs["05_protected_terms"] / "protected_terms.json")
        self.logger.info("Protected terms: %d", len(protected_terms))

        # --- Stages 8-9: LanguageTool (primary), SymSpell (fallback) ----
        self.logger.stage("Spell / grammar detection (LanguageTool + SymSpell)")
        all_candidates: List[Candidate] = []
        flagged_spans_by_sentence: Dict[int, Set[Tuple[int, int]]] = {}
        
        lt_available = getattr(self.languagetool_agent, "available", False)
        
        from concurrent.futures import ThreadPoolExecutor

        def process_sentence(sent):
            if lt_available:
                try:
                    candidates = self.languagetool_agent.run(sent)
                    return sent.sentence_id, candidates, None
                except Exception as exc:
                    return sent.sentence_id, [], exc
            else:
                candidates = self.spell_agent.run(sent, set())
                return sent.sentence_id, candidates, None

        if all_sentences:
            max_lt_workers = min(8, len(all_sentences))
            with ThreadPoolExecutor(max_workers=max_lt_workers) as executor:
                sent_results = list(executor.map(process_sentence, all_sentences))

            for sent_id, candidates, exc in sent_results:
                if exc:
                    self.logger.warning("LanguageTool failed on sentence %d: %s. Falling back to SymSpell.", sent_id, exc)
                all_candidates.extend(candidates)
                if candidates:
                    flagged_spans_by_sentence[sent_id] = {(c.char_start, c.char_end) for c in candidates}

        save_json(all_candidates, stage_dirs["06_spell"] / "spell_candidates.json")
        self.logger.info("Spell/grammar candidates so far: %d", len(all_candidates))

        # --- Stage 11: LLM Paragraph Reviewer (Level-2 grammar model) ---
        self.logger.stage("Grammar review (local LLM)")

        if self.config.ollama.model and self.config.ollama.model.lower() != "none":
            def sentence_id_for_offset(doc_offset: int) -> int:
                for sentence in all_sentences:
                    if sentence.doc_char_start <= doc_offset < sentence.doc_char_end:
                        return sentence.sentence_id
                return -1

            def process_paragraph(paragraph):
                para_start = paragraph.doc_char_start or 0
                para_end = para_start + len(paragraph.text)
                terms_in_paragraph = [
                    t for t in protected_terms if t.char_start < para_end and t.char_end > para_start
                ]
                try:
                    return self.grammar_agent.run(
                        paragraph.text, para_start, sentence_id_for_offset, terms_in_paragraph
                    )
                except Exception as exc:
                    self.logger.warning("Grammar review (Ollama) failed: %s. Continuing...", exc)
                    return []

            if document.paragraphs:
                max_para_workers = min(4, len(document.paragraphs))
                with ThreadPoolExecutor(max_workers=max_para_workers) as executor:
                    para_candidates_list = list(executor.map(process_paragraph, document.paragraphs))

                for candidates in para_candidates_list:
                    all_candidates.extend(candidates)
        else:
            self.logger.info("Skipping grammar review (Ollama) because model is 'none'")
        save_json(all_candidates, stage_dirs["07_grammar"] / "grammar_candidates.json")
        self.logger.info("Total candidates after grammar review: %d", len(all_candidates))

        # --- Stage 10: Validation Agent (single gatekeeper, all sources) ----
        self.logger.stage("Validation (protected-terms gate)")
        validator = ValidationAgent(protected_terms)
        accepted, rejected = validator.validate(all_candidates)
        save_json(accepted, stage_dirs["08_validation"] / "accepted.json")
        save_json(rejected, stage_dirs["08_validation"] / "rejected.json")
        self.logger.info("Validation: %d accepted, %d rejected", len(accepted), len(rejected))

        # --- Stage 12: Semantic Validator --------------------------------
        self.logger.stage("Semantic validation")

        semantically_passed = accepted
        semantically_failed = []

        if self.config.ollama.model and self.config.ollama.model.lower() != "none":
            def sentence_text_lookup(sentence_id: int) -> str:
                for sentence in all_sentences:
                    if sentence.sentence_id == sentence_id:
                        return sentence.text
                return ""
            try:
                semantic_results = self.semantic_validator.run(accepted, sentence_text_lookup)
                semantically_passed, semantically_failed = self.semantic_validator.filter_passed(
                    accepted, semantic_results
                )
            except Exception as exc:
                self.logger.warning("Semantic validation (Ollama) failed: %s. Continuing...", exc)
        else:
            self.logger.info("Skipping semantic validation (Ollama) because model is 'none'")

        save_json(semantically_failed, stage_dirs["09_semantic"] / "semantic_failed.json")
        self.logger.info("Semantic validation: %d passed", len(semantically_passed))

        # --- Stage 13: Difference Engine (span sanity re-check) ---------
        diff_engine = DifferenceEngine(document.normalized_text)
        confirmed_issues = diff_engine.run(semantically_passed)

        # --- Stage 14: Merge Agent ----------------------------------------
        merged_issues: List[MergedIssue] = self.merge_agent.merge(confirmed_issues)

        # Filter issues by confidence: reject if final_confidence <= 0.50
        high_confidence_issues = []
        low_confidence_issues = []
        for issue in merged_issues:
            if issue.final_confidence <= 0.50:
                issue.is_protected = True
                issue.protected_reason = "Low Confidence"
                # Keep original reason or overwrite with Low Confidence? 
                # Let's set the reason/protected_reason appropriately
                issue.reason = "Low Confidence"
                low_confidence_issues.append(issue)
            else:
                high_confidence_issues.append(issue)

        save_json(low_confidence_issues, stage_dirs["10_final"] / "rejected.json")
        self.logger.info("Confidence filtering: %d accepted, %d rejected", len(high_confidence_issues), len(low_confidence_issues))

        # --- Stage 15: Annotation Engine -----------------------------------
        self.logger.stage("Generating annotated HTML")
        annotator = Annotator(document.normalized_text)
        annotated_html, corrected_html = annotator.build(high_confidence_issues)
        save_text(annotated_html, stage_dirs["10_final"] / "annotated_original.html")
        save_text(corrected_html, stage_dirs["10_final"] / "corrected_document.html")

        # --- Stage 16: Report Generator ------------------------------------
        self.logger.stage("Generating reports")
        report_generator = ReportGenerator(document.normalized_text, all_sentences)
        report_json, changes_md, summary_csv = report_generator.build(high_confidence_issues)
        save_json(report_json, stage_dirs["10_final"] / "report.json")
        TextWriter.write(changes_md, stage_dirs["10_final"] / "changes.md")
        TextWriter.write(summary_csv, stage_dirs["10_final"] / "summary.csv")

        self.logger.stage("Completed")

        return {
            "run_dir": str(run_dir),
            "total_issues": len(high_confidence_issues),
            "accepted": len(accepted),
            "rejected_protected": len(rejected),
            "rejected_semantic": len(semantically_failed),
            "rejected_confidence": len(low_confidence_issues),
        }
