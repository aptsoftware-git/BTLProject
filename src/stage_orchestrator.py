"""
stage_orchestrator.py
======================
Production-grade asynchronous stage orchestration engine for the AI Document Intelligence Platform.

Orchestrates 8 independent execution stages:
  Stage 1: Upload Complete               -> Unlocks: Document Uploaded
  Stage 2: Document Extraction            -> Unlocks: Document Viewer
  Stage 3: Spell Checking                 -> Unlocks: Proofreading (Spell)
  Stage 4: Grammar Checking               -> Unlocks: Grammar Results / Proofreading
  Stage 5: RAG Index Construction        -> Unlocks: AI Assistant
  Stage 6: Contextual Consistency Analysis-> Unlocks: Context Analysis
  Stage 7: Comparative Analysis           -> Unlocks: Comparative Analysis
  Stage 8: Executive Report Generation    -> Unlocks: Executive Reports

Each stage records start_time, end_time, duration, errors, output_location,
updates job state, and immediately unlocks corresponding features.
"""

from __future__ import annotations

import json
import logging
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.config import PipelineConfig, ROOT_DIR
from src.logger import get_logger

logger = logging.getLogger("backend")

STAGES_DEFINITIONS: List[Dict[str, str]] = [
    {
        "stage_id": "stage_1_upload",
        "name": "Upload Complete",
        "unlocked_feature": "Document Uploaded",
        "flag": "upload_ready"
    },
    {
        "stage_id": "stage_2_extraction",
        "name": "Document Extraction",
        "unlocked_feature": "Document Viewer",
        "flag": "document_viewer_ready"
    },
    {
        "stage_id": "stage_3_spell",
        "name": "Spell Checking",
        "unlocked_feature": "Proofreading",
        "flag": "spell_ready"
    },
    {
        "stage_id": "stage_4_grammar",
        "name": "Grammar Checking",
        "unlocked_feature": "Grammar Results",
        "flag": "grammar_ready"
    },
    {
        "stage_id": "stage_5_rag",
        "name": "RAG Index Construction",
        "unlocked_feature": "AI Assistant",
        "flag": "rag_ready"
    },
    {
        "stage_id": "stage_6_context",
        "name": "Contextual Consistency Analysis",
        "unlocked_feature": "Context Analysis",
        "flag": "context_analysis_ready"
    },
    {
        "stage_id": "stage_7_comparative",
        "name": "Comparative Analysis",
        "unlocked_feature": "Comparative Analysis",
        "flag": "comparative_analysis_ready"
    },
    {
        "stage_id": "stage_8_reports",
        "name": "Executive Report Generation",
        "unlocked_feature": "Reports",
        "flag": "reports_ready"
    }
]


def initialize_job_stages(created_at: str | None = None) -> List[Dict[str, Any]]:
    """Generates the initial 8-stage state array for a new job."""
    now_str = created_at or datetime.now().isoformat()
    stages = []
    for index, cfg in enumerate(STAGES_DEFINITIONS):
        if cfg["stage_id"] == "stage_1_upload":
            stages.append({
                "stage_id": cfg["stage_id"],
                "name": cfg["name"],
                "unlocked_feature": cfg["unlocked_feature"],
                "status": "Completed",
                "start_time": now_str,
                "end_time": now_str,
                "duration": 0.01,
                "errors": None,
                "output_location": "data/input/"
            })
        else:
            stages.append({
                "stage_id": cfg["stage_id"],
                "name": cfg["name"],
                "unlocked_feature": cfg["unlocked_feature"],
                "status": "Pending",
                "start_time": None,
                "end_time": None,
                "duration": None,
                "errors": None,
                "output_location": None
            })
    return stages


class StageOrchestrator:
    """Orchestrates independent background stage execution with progress reporting,
    resumability, and artifact persistence."""

    def __init__(self, job_id: str, job_dir: Path, file_path: Path):
        self.job_id = job_id
        self.job_dir = job_dir
        self.file_path = file_path
        self.config = PipelineConfig()

    def get_job(self) -> Dict[str, Any] | None:
        from backend.services import get_job
        return get_job(self.job_id)

    def save_job(self) -> None:
        from backend.services import save_job_metadata
        save_job_metadata(self.job_id)

    def update_stage_state(
        self,
        stage_id: str,
        status: str,
        start_time: str | None = None,
        end_time: str | None = None,
        duration: float | None = None,
        errors: str | None = None,
        output_location: str | None = None
    ) -> None:
        job = self.get_job()
        if not job:
            return

        if "stages" not in job or not isinstance(job["stages"], list):
            job["stages"] = initialize_job_stages(job.get("created_at"))

        for s in job["stages"]:
            if s["stage_id"] == stage_id:
                s["status"] = status
                if start_time is not None:
                    s["start_time"] = start_time
                if end_time is not None:
                    s["end_time"] = end_time
                if duration is not None:
                    s["duration"] = duration
                if errors is not None:
                    s["errors"] = errors
                if output_location is not None:
                    s["output_location"] = output_location
                break

        # Calculate overall progress
        completed_count = sum(1 for s in job["stages"] if s["status"] in ("Completed", "Skipped"))
        job["overall_progress"] = int((completed_count / len(STAGES_DEFINITIONS)) * 100)
        job["progress_percentage"] = float(job["overall_progress"])

        # Update current stage display name
        running_stage = next((s["name"] for s in job["stages"] if s["status"] == "Running"), None)
        if running_stage:
            job["current_stage"] = running_stage
        elif completed_count == len(STAGES_DEFINITIONS):
            job["current_stage"] = "Completed"
            job["status"] = "completed"
            job["completed_at"] = datetime.now().isoformat()
        
        self.save_job()

    def execute_all_stages(self) -> None:
        """Executes stages 2 through 8 independently."""
        job = self.get_job()
        if not job:
            logger.error("Job %s not found in memory/disk during execution", self.job_id)
            return

        job["status"] = "processing"
        self.save_job()

        logger.info("Starting stage orchestration for job %s (%s)", self.job_id, job.get("filename"))

        # Stage 2: Document Extraction
        self.run_stage_2_extraction()

        # Stage 3: Spell Checking
        self.run_stage_3_spell()

        # Stage 4: Grammar Checking
        self.run_stage_4_grammar()

        # Stage 5: RAG Index Construction
        self.run_stage_5_rag()

        # Stage 6: Contextual Consistency Analysis
        self.run_stage_6_context()

        # Stage 7: Comparative Analysis
        self.run_stage_7_comparative()

        # Stage 8: Executive Report Generation
        self.run_stage_8_reports()

        # Final check
        job = self.get_job()
        if job:
            failed_stages = [s for s in job.get("stages", []) if s["status"] == "Failed"]
            if not failed_stages:
                job["status"] = "completed"
                job["current_stage"] = "Completed"
                job["overall_progress"] = 100
                job["progress_percentage"] = 100.0
                job["completed_at"] = datetime.now().isoformat()
            else:
                job["status"] = "completed_with_warnings" if any(s["status"] == "Completed" for s in job.get("stages", [])) else "failed"
                job["completed_at"] = datetime.now().isoformat()
            self.save_job()
            logger.info("Stage orchestration finished for job %s with status: %s", self.job_id, job["status"])

    # ------------------------------------------------------------------
    # Stage 2: Document Extraction
    # ------------------------------------------------------------------
    def run_stage_2_extraction(self) -> None:
        stage_id = "stage_2_extraction"
        doc_json = self.job_dir / "structured_document.json"
        raw_txt = self.job_dir / "01_raw" / "raw_text.txt"
        sentences_json = self.job_dir / "04_sentences" / "sentences.json"

        # Cache check
        if doc_json.exists() and sentences_json.exists() and sentences_json.stat().st_size > 0:
            logger.info("[CACHE HIT] Stage 2 (Extraction) already completed for job %s", self.job_id)
            self.update_stage_state(stage_id, "Completed", duration=0.0, output_location="structured_document.json")
            job = self.get_job()
            if job:
                job["extraction_ready"] = True
                job["document_viewer_ready"] = True
                self.save_job()
            return

        start_time = datetime.now()
        start_time_iso = start_time.isoformat()
        self.update_stage_state(stage_id, "Running", start_time=start_time_iso)

        try:
            from src.extractor import DocumentExtractor
            from src.layout_analyzer import LayoutAnalyzer
            from src.filter import RunningTextFilter
            from src.preprocessing import TextPreprocessor
            from src.paragraph_builder import ParagraphBuilder
            from src.sentence_splitter import SentenceSplitter
            from src.protected_terms import ProtectedTermsBuilder
            from src.models import index_paragraph_doc_offsets, index_sentence_doc_offsets
            from src.utils import save_text, save_json

            # Initialize reusable stages
            extractor = DocumentExtractor(logger=logger)
            layout_analyzer = LayoutAnalyzer(logger=logger)
            running_text_filter = RunningTextFilter(logger=logger)
            preprocessor = TextPreprocessor(logger=logger)
            paragraph_builder = ParagraphBuilder(logger=logger)

            import spacy
            try:
                nlp = spacy.load(self.config.spacy.model_name)
            except Exception:
                nlp = None

            sentence_splitter = SentenceSplitter(logger=logger, config=self.config.spacy, nlp=nlp)
            protected_terms_builder = ProtectedTermsBuilder(
                spacy_config=self.config.spacy, validation_config=self.config.validation, nlp=nlp
            )

            stage_dirs = {name: self.job_dir / name for name in self.config.stage_folders}
            for p in stage_dirs.values():
                p.mkdir(parents=True, exist_ok=True)

            document = extractor.extract(self.file_path, output_dir=self.job_dir)
            save_text(document.raw_text, stage_dirs["01_raw"] / "raw_text.txt")

            document = layout_analyzer.analyze(document)
            document = running_text_filter.filter(document)
            save_text(document.filtered_text, stage_dirs["02_filtered"] / "filtered_text.txt")

            document = preprocessor.normalize(document)
            save_text(document.normalized_text, stage_dirs["03_preprocessed"] / "normalized_text.txt")

            document = paragraph_builder.build(document)
            document = sentence_splitter.split(document)
            index_paragraph_doc_offsets(document)
            index_sentence_doc_offsets(document)

            all_sentences = [s for p in document.paragraphs for s in p.sentences]
            save_json(all_sentences, stage_dirs["04_sentences"] / "sentences.json")

            protected_terms = protected_terms_builder.build(document.normalized_text)
            save_json(protected_terms, stage_dirs["05_protected_terms"] / "protected_terms.json")

            end_time = datetime.now()
            duration = round((end_time - start_time).total_seconds(), 2)

            self.update_stage_state(
                stage_id,
                "Completed",
                end_time=end_time.isoformat(),
                duration=duration,
                output_location="structured_document.json"
            )

            job = self.get_job()
            if job:
                job["extraction_ready"] = True
                job["document_viewer_ready"] = True
                self.save_job()

            logger.info("Stage 2 (Extraction) completed in %.2fs for job %s", duration, self.job_id)

        except Exception as exc:
            end_time = datetime.now()
            duration = round((end_time - start_time).total_seconds(), 2)
            error_msg = f"{str(exc)}\n{traceback.format_exc()}"
            self.update_stage_state(stage_id, "Failed", end_time=end_time.isoformat(), duration=duration, errors=error_msg)
            logger.error("Stage 2 (Extraction) failed for job %s: %s", self.job_id, exc)

    # ------------------------------------------------------------------
    # Stage 3: Spell Checking
    # ------------------------------------------------------------------
    def run_stage_3_spell(self) -> None:
        stage_id = "stage_3_spell"
        spell_file = self.job_dir / "06_spell" / "spell_candidates.json"

        # Cache check
        if spell_file.exists() and spell_file.stat().st_size > 0:
            logger.info("[CACHE HIT] Stage 3 (Spell) already completed for job %s", self.job_id)
            self.update_stage_state(stage_id, "Completed", duration=0.0, output_location="06_spell/spell_candidates.json")
            job = self.get_job()
            if job:
                job["spell_ready"] = True
                self.save_job()
            return

        start_time = datetime.now()
        self.update_stage_state(stage_id, "Running", start_time=start_time.isoformat())

        try:
            from src.languagetool_agent import LanguageToolAgent
            from src.spell_agent import SpellAgent
            from src.models import Sentence
            from src.utils import save_json, load_json
            from concurrent.futures import ThreadPoolExecutor

            sentences_path = self.job_dir / "04_sentences" / "sentences.json"
            if not sentences_path.exists():
                raise FileNotFoundError(f"Missing sentences file: {sentences_path}")

            sentences_data = load_json(sentences_path)
            all_sentences = [Sentence(**s) if isinstance(s, dict) else s for s in sentences_data]

            lt_agent = LanguageToolAgent(self.config.languagetool)
            spell_agent = SpellAgent(self.config.symspell)
            lt_available = getattr(lt_agent, "available", False)

            all_candidates = []

            def process_sentence(sent):
                if lt_available:
                    try:
                        cands = lt_agent.run(sent)
                        return sent.sentence_id, cands, None
                    except Exception as exc:
                        return sent.sentence_id, [], exc
                else:
                    cands = spell_agent.run(sent, set())
                    return sent.sentence_id, cands, None

            if all_sentences:
                max_workers = min(8, len(all_sentences))
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    results = list(executor.map(process_sentence, all_sentences))

                for sent_id, cands, exc in results:
                    all_candidates.extend(cands)

            lt_agent.close()

            spell_dir = self.job_dir / "06_spell"
            spell_dir.mkdir(parents=True, exist_ok=True)
            save_json(all_candidates, spell_file)

            end_time = datetime.now()
            duration = round((end_time - start_time).total_seconds(), 2)

            self.update_stage_state(
                stage_id,
                "Completed",
                end_time=end_time.isoformat(),
                duration=duration,
                output_location="06_spell/spell_candidates.json"
            )

            job = self.get_job()
            if job:
                job["spell_ready"] = True
                self.save_job()

            logger.info("Stage 3 (Spell) completed in %.2fs for job %s", duration, self.job_id)

        except Exception as exc:
            end_time = datetime.now()
            duration = round((end_time - start_time).total_seconds(), 2)
            error_msg = f"{str(exc)}\n{traceback.format_exc()}"
            self.update_stage_state(stage_id, "Failed", end_time=end_time.isoformat(), duration=duration, errors=error_msg)
            logger.error("Stage 3 (Spell) failed for job %s: %s", self.job_id, exc)

    # ------------------------------------------------------------------
    # Stage 4: Grammar Checking
    # ------------------------------------------------------------------
    def run_stage_4_grammar(self) -> None:
        stage_id = "stage_4_grammar"
        report_file = self.job_dir / "10_final" / "report.json"

        # Cache check
        if report_file.exists() and report_file.stat().st_size > 0:
            logger.info("[CACHE HIT] Stage 4 (Grammar) already completed for job %s", self.job_id)
            self.update_stage_state(stage_id, "Completed", duration=0.0, output_location="10_final/report.json")
            job = self.get_job()
            if job:
                job["grammar_ready"] = True
                job["proofreading_ready"] = True
                job["proofreading_status"] = "completed"
                self.save_job()
            return

        start_time = datetime.now()
        self.update_stage_state(stage_id, "Running", start_time=start_time.isoformat())

        try:
            from src.grammar_agent import GrammarAgent
            from src.validation_agent import ValidationAgent
            from src.semantic_validator import SemanticValidator
            from src.difference_engine import DifferenceEngine
            from src.merge_agent import MergeAgent
            from src.annotator import Annotator
            from src.report_generator import ReportGenerator
            from src.text_writer import TextWriter
            from src.models import Candidate, Sentence, ProtectedTerm
            from src.utils import save_json, load_json, save_text
            from concurrent.futures import ThreadPoolExecutor

            spell_file = self.job_dir / "06_spell" / "spell_candidates.json"
            sentences_file = self.job_dir / "04_sentences" / "sentences.json"
            protected_file = self.job_dir / "05_protected_terms" / "protected_terms.json"
            norm_text_file = self.job_dir / "03_preprocessed" / "normalized_text.txt"

            spell_cands_raw = load_json(spell_file) if spell_file.exists() else []
            all_candidates = [Candidate(**c) if isinstance(c, dict) else c for c in spell_cands_raw]

            sentences_raw = load_json(sentences_file) if sentences_file.exists() else []
            all_sentences = [Sentence(**s) if isinstance(s, dict) else s for s in sentences_raw]

            protected_raw = load_json(protected_file) if protected_file.exists() else []
            protected_terms = [ProtectedTerm(**pt) if isinstance(pt, dict) else pt for pt in protected_raw]

            norm_text = norm_text_file.read_text(encoding="utf-8") if norm_text_file.exists() else ""

            # LLM Grammar Agent
            grammar_agent = GrammarAgent(self.config.ollama)
            if self.config.ollama.model and self.config.ollama.model.lower() != "none":
                # Divide sentences into paragraph chunks
                paragraphs = []
                current_p = []
                for s in all_sentences:
                    current_p.append(s.text)
                    if len(current_p) >= 3:
                        paragraphs.append(" ".join(current_p))
                        current_p = []
                if current_p:
                    paragraphs.append(" ".join(current_p))

                def process_p(p_text):
                    try:
                        return grammar_agent.run(p_text, 0, lambda off: -1, protected_terms)
                    except Exception:
                        return []

                if paragraphs:
                    max_w = min(4, len(paragraphs))
                    with ThreadPoolExecutor(max_workers=max_w) as ex:
                        para_res = list(ex.map(process_p, paragraphs))
                    for cands in para_res:
                        all_candidates.extend(cands)

            grammar_dir = self.job_dir / "07_grammar"
            grammar_dir.mkdir(parents=True, exist_ok=True)
            save_json(all_candidates, grammar_dir / "grammar_candidates.json")

            # Validation
            validator = ValidationAgent(protected_terms)
            accepted, rejected = validator.validate(all_candidates)
            save_json(accepted, self.job_dir / "08_validation" / "accepted.json")
            save_json(rejected, self.job_dir / "08_validation" / "rejected.json")

            # Semantic Validator
            semantic_validator = SemanticValidator(self.config.ollama)
            semantically_passed = accepted
            semantically_failed = []

            if self.config.ollama.model and self.config.ollama.model.lower() != "none":
                try:
                    def lookup_sent(sid):
                        return next((s.text for s in all_sentences if s.sentence_id == sid), "")
                    sem_res = semantic_validator.run(accepted, lookup_sent)
                    semantically_passed, semantically_failed = semantic_validator.filter_passed(accepted, sem_res)
                except Exception as sem_err:
                    logger.warning("Semantic validation failed: %s", sem_err)

            save_json(semantically_failed, self.job_dir / "09_semantic" / "semantic_failed.json")

            # Difference Engine & Merge Agent
            diff_engine = DifferenceEngine(norm_text)
            confirmed = diff_engine.run(semantically_passed)
            merge_agent = MergeAgent(self.config.merge)
            merged = merge_agent.merge(confirmed)

            high_conf = [m for m in merged if m.final_confidence > 0.50]
            low_conf = [m for m in merged if m.final_confidence <= 0.50]

            final_dir = self.job_dir / "10_final"
            final_dir.mkdir(parents=True, exist_ok=True)
            save_json(low_conf, final_dir / "rejected.json")

            # Annotator & Reports
            annotator = Annotator(norm_text)
            ann_html, corr_html = annotator.build(high_conf)
            save_text(ann_html, final_dir / "annotated_original.html")
            save_text(corr_html, final_dir / "corrected_document.html")

            rep_gen = ReportGenerator(norm_text, all_sentences)
            rep_json, changes_md, summary_csv = rep_gen.build(high_conf)
            save_json(rep_json, final_dir / "report.json")
            TextWriter.write(changes_md, final_dir / "changes.md")
            TextWriter.write(summary_csv, final_dir / "summary.csv")

            end_time = datetime.now()
            duration = round((end_time - start_time).total_seconds(), 2)

            self.update_stage_state(
                stage_id,
                "Completed",
                end_time=end_time.isoformat(),
                duration=duration,
                output_location="10_final/report.json"
            )

            job = self.get_job()
            if job:
                job["grammar_ready"] = True
                job["proofreading_ready"] = True
                job["proofreading_status"] = "completed"
                job["result"] = {"total_issues": len(high_conf), "accepted": len(accepted)}
                self.save_job()

            logger.info("Stage 4 (Grammar) completed in %.2fs for job %s", duration, self.job_id)

        except Exception as exc:
            end_time = datetime.now()
            duration = round((end_time - start_time).total_seconds(), 2)
            error_msg = f"{str(exc)}\n{traceback.format_exc()}"
            self.update_stage_state(stage_id, "Failed", end_time=end_time.isoformat(), duration=duration, errors=error_msg)
            logger.error("Stage 4 (Grammar) failed for job %s: %s", self.job_id, exc)

    # ------------------------------------------------------------------
    # Stage 5: RAG Index Construction
    # ------------------------------------------------------------------
    def run_stage_5_rag(self) -> None:
        stage_id = "stage_5_rag"
        ko_file = self.job_dir / "03_knowledge_objects" / "knowledge_objects.json"
        chunks_file = self.job_dir / "06_chunks" / "document_chunks.json"
        if not chunks_file.exists():
            chunks_file = self.job_dir / "document_chunks.json"

        # Cache check
        if ko_file.exists() and chunks_file.exists():
            logger.info("[CACHE HIT] Stage 5 (RAG Index Construction) already completed for job %s", self.job_id)
            self.update_stage_state(stage_id, "Completed", duration=0.0, output_location="03_knowledge_objects/knowledge_objects.json")
            job = self.get_job()
            if job:
                job["rag_ready"] = True
                job["rag_status"] = "completed"
                self.save_job()
            return

        start_time = datetime.now()
        self.update_stage_state(stage_id, "Running", start_time=start_time.isoformat())

        try:
            from src.rag.multimodal_extractor import MultimodalExtractor

            extractor = MultimodalExtractor(
                enable_ocr=False,
                enable_table_extraction=True,
                enable_image_extraction=True
            )
            raw_text, master_doc, total_pages = extractor.extract(self.file_path, output_dir=self.job_dir)

            end_time = datetime.now()
            duration = round((end_time - start_time).total_seconds(), 2)

            self.update_stage_state(
                stage_id,
                "Completed",
                end_time=end_time.isoformat(),
                duration=duration,
                output_location="03_knowledge_objects/knowledge_objects.json"
            )

            job = self.get_job()
            if job:
                job["rag_ready"] = True
                job["rag_status"] = "completed"
                self.save_job()

            logger.info("Stage 5 (RAG) completed in %.2fs for job %s", duration, self.job_id)

        except Exception as exc:
            end_time = datetime.now()
            duration = round((end_time - start_time).total_seconds(), 2)
            error_msg = f"{str(exc)}\n{traceback.format_exc()}"
            self.update_stage_state(stage_id, "Failed", end_time=end_time.isoformat(), duration=duration, errors=error_msg)
            logger.error("Stage 5 (RAG) failed for job %s: %s", self.job_id, exc)

    # ------------------------------------------------------------------
    # Stage 6: Contextual Consistency Analysis
    # ------------------------------------------------------------------
    def run_stage_6_context(self) -> None:
        stage_id = "stage_6_context"
        rep_html = self.job_dir / "09_reports" / "consistency_report.html"
        rep_json = self.job_dir / "report.json"

        # Cache check
        if rep_html.exists() and rep_json.exists():
            logger.info("[CACHE HIT] Stage 6 (Context Analysis) already completed for job %s", self.job_id)
            self.update_stage_state(stage_id, "Completed", duration=0.0, output_location="09_reports/consistency_report.html")
            job = self.get_job()
            if job:
                job["context_analysis_ready"] = True
                job["context_analysis_status"] = "completed"
                self.save_job()
            return

        start_time = datetime.now()
        self.update_stage_state(stage_id, "Running", start_time=start_time.isoformat())

        try:
            from src.rag.contextual_analysis.pipeline import ContextAnalysisPipeline
            from src.config import load_preferences

            prefs = load_preferences()
            model_name = prefs.get("ollama", {}).get("model", "qwen2.5-coder:7b")

            consistency_pipeline = ContextAnalysisPipeline(model_name=model_name)
            consistency_pipeline.run_analysis(self.job_dir, self.job_id)

            from src.rag.ambiguity_pipeline import AmbiguityPipeline
            ambiguity_pipeline = AmbiguityPipeline()
            ambiguity_pipeline.run_clustering(self.job_dir, self.job_id)

            from src.rag.ambiguity_extractor import AmbiguityExtractor
            ambiguity_extractor = AmbiguityExtractor()
            ambiguity_extractor.run_extraction(self.job_dir, self.job_id)

            from src.rag.ambiguity_chunk_analyzer import AmbiguityChunkAnalyzer
            chunk_analyzer = AmbiguityChunkAnalyzer()
            chunk_analyzer.run_analysis(self.job_dir, self.job_id)

            from src.rag.ambiguity_cluster_analyzer import AmbiguityClusterAnalyzer
            cluster_analyzer = AmbiguityClusterAnalyzer()
            cluster_analyzer.run_analysis(self.job_dir, self.job_id)

            from src.rag.claude_input_builder import ClaudeInputBuilder
            input_builder = ClaudeInputBuilder()
            input_builder.run_packaging(self.job_dir, self.job_id)

            from src.rag.claude.verification_service import ClaudeVerificationService
            verification_service = ClaudeVerificationService()
            verification_service.run_verification(self.job_dir, self.job_id)

            # Copy to 09_reports
            import shutil
            reports_dir = self.job_dir / "09_reports"
            reports_dir.mkdir(parents=True, exist_ok=True)
            if (self.job_dir / "report.json").exists():
                shutil.copy2(self.job_dir / "report.json", reports_dir / "consistency_report.json")
            if (self.job_dir / "business_report.html").exists():
                shutil.copy2(self.job_dir / "business_report.html", reports_dir / "consistency_report.html")

            end_time = datetime.now()
            duration = round((end_time - start_time).total_seconds(), 2)

            self.update_stage_state(
                stage_id,
                "Completed",
                end_time=end_time.isoformat(),
                duration=duration,
                output_location="09_reports/consistency_report.html"
            )

            job = self.get_job()
            if job:
                job["context_analysis_ready"] = True
                job["context_analysis_status"] = "completed"
                self.save_job()

            logger.info("Stage 6 (Context Analysis) completed in %.2fs for job %s", duration, self.job_id)

        except Exception as exc:
            end_time = datetime.now()
            duration = round((end_time - start_time).total_seconds(), 2)
            error_msg = f"{str(exc)}\n{traceback.format_exc()}"
            self.update_stage_state(stage_id, "Failed", end_time=end_time.isoformat(), duration=duration, errors=error_msg)
            logger.error("Stage 6 (Context Analysis) failed for job %s: %s", self.job_id, exc)

    # ------------------------------------------------------------------
    # Stage 7: Comparative Analysis
    # ------------------------------------------------------------------
    def run_stage_7_comparative(self) -> None:
        stage_id = "stage_7_comparative"
        comp_html = self.job_dir / "comparative_analysis" / "comparative_report.html"

        # Cache check
        if comp_html.exists() and comp_html.stat().st_size > 0:
            logger.info("[CACHE HIT] Stage 7 (Comparative Analysis) already completed for job %s", self.job_id)
            self.update_stage_state(stage_id, "Completed", duration=0.0, output_location="comparative_analysis/comparative_report.html")
            job = self.get_job()
            if job:
                job["comparative_analysis_ready"] = True
                job["comparative_analysis_status"] = "completed"
                self.save_job()
            return

        start_time = datetime.now()
        self.update_stage_state(stage_id, "Running", start_time=start_time.isoformat())

        try:
            from src.comparative_analysis.service import ComparativeAnalysisService
            from src.comparative_analysis.models import ComparativeAnalysisRequest

            comp_service = ComparativeAnalysisService()
            comp_req = ComparativeAnalysisRequest(document_id=self.job_id)
            comp_resp = comp_service.run_analysis(comp_req)

            import shutil
            reports_dir = self.job_dir / "09_reports"
            reports_dir.mkdir(parents=True, exist_ok=True)
            if comp_html.exists():
                shutil.copy2(comp_html, reports_dir / "comparative_report.html")

            end_time = datetime.now()
            duration = round((end_time - start_time).total_seconds(), 2)

            self.update_stage_state(
                stage_id,
                "Completed",
                end_time=end_time.isoformat(),
                duration=duration,
                output_location="comparative_analysis/comparative_report.html"
            )

            job = self.get_job()
            if job:
                job["comparative_analysis_ready"] = True
                job["comparative_analysis_status"] = comp_resp.status
                self.save_job()

            logger.info("Stage 7 (Comparative Analysis) completed in %.2fs for job %s", duration, self.job_id)

        except Exception as exc:
            end_time = datetime.now()
            duration = round((end_time - start_time).total_seconds(), 2)
            error_msg = f"{str(exc)}\n{traceback.format_exc()}"
            self.update_stage_state(stage_id, "Failed", end_time=end_time.isoformat(), duration=duration, errors=error_msg)
            logger.error("Stage 7 (Comparative Analysis) failed for job %s: %s", self.job_id, exc)

    # ------------------------------------------------------------------
    # Stage 8: Executive Report Generation
    # ------------------------------------------------------------------
    def run_stage_8_reports(self) -> None:
        stage_id = "stage_8_reports"
        biz_html = self.job_dir / "business_report.html"
        rep_html = self.job_dir / "09_reports" / "final_report.html"

        # Cache check
        if biz_html.exists() and biz_html.stat().st_size > 0:
            logger.info("[CACHE HIT] Stage 8 (Executive Report Generation) already completed for job %s", self.job_id)
            self.update_stage_state(stage_id, "Completed", duration=0.0, output_location="business_report.html")
            job = self.get_job()
            if job:
                job["reports_ready"] = True
                self.save_job()
            return

        start_time = datetime.now()
        self.update_stage_state(stage_id, "Running", start_time=start_time.isoformat())

        try:
            from src.rag.final_report_generator import FinalReportGenerator

            report_generator = FinalReportGenerator()
            report_generator.run_generation(self.job_dir, self.job_id)

            import shutil
            reports_dir = self.job_dir / "09_reports"
            reports_dir.mkdir(parents=True, exist_ok=True)
            if biz_html.exists():
                shutil.copy2(biz_html, reports_dir / "final_report.html")

            end_time = datetime.now()
            duration = round((end_time - start_time).total_seconds(), 2)

            self.update_stage_state(
                stage_id,
                "Completed",
                end_time=end_time.isoformat(),
                duration=duration,
                output_location="business_report.html"
            )

            job = self.get_job()
            if job:
                job["reports_ready"] = True
                self.save_job()

            logger.info("Stage 8 (Executive Report Generation) completed in %.2fs for job %s", duration, self.job_id)

        except Exception as exc:
            end_time = datetime.now()
            duration = round((end_time - start_time).total_seconds(), 2)
            error_msg = f"{str(exc)}\n{traceback.format_exc()}"
            self.update_stage_state(stage_id, "Failed", end_time=end_time.isoformat(), duration=duration, errors=error_msg)
            logger.error("Stage 8 (Executive Report Generation) failed for job %s: %s", self.job_id, exc)
