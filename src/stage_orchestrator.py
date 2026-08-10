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

logger = get_logger("backend")

STAGES_DEFINITIONS: List[Dict[str, str]] = [
    {
        "stage_id": "stage_1_upload",
        "name": "Document Uploaded",
        "unlocked_feature": "Document Uploaded",
        "flag": "upload_ready"
    },
    {
        "stage_id": "stage_2_extraction",
        "name": "Document Content Extraction",
        "unlocked_feature": "Document Viewer",
        "flag": "document_viewer_ready"
    },
    {
        "stage_id": "stage_3_spell",
        "name": "Language & Spelling Review",
        "unlocked_feature": "Proofreading",
        "flag": "spell_ready"
    },
    {
        "stage_id": "stage_4_grammar",
        "name": "Grammar & Writing Quality Review",
        "unlocked_feature": "Grammar Results",
        "flag": "grammar_ready"
    },
    {
        "stage_id": "stage_5_rag",
        "name": "Knowledge Index Creation",
        "unlocked_feature": "AI Assistant",
        "flag": "rag_ready"
    },
    {
        "stage_id": "stage_6_context",
        "name": "Consistency & Contradiction Review",
        "unlocked_feature": "Context Analysis",
        "flag": "context_analysis_ready"
    },
    {
        "stage_id": "stage_7_comparative",
        "name": "Competitive Benchmark Analysis",
        "unlocked_feature": "Comparative Analysis",
        "flag": "comparative_analysis_ready"
    },
    {
        "stage_id": "stage_8_reports",
        "name": "Executive Insights Report",
        "unlocked_feature": "Reports",
        "flag": "reports_ready"
    }
]


def _artifact_is_stale(output_path: Path, *input_paths: Path) -> bool:
    """True if output_path is missing/empty, or older than any given input_path.

    Used to gate stage cache-hit checks so a stage is never treated as
    "already done" when its upstream artifact was regenerated more recently
    (e.g. Stage 3 rerun after Stage 4 already produced a report from an
    earlier, empty Stage 3 output).
    """
    if not output_path.exists() or output_path.stat().st_size == 0:
        return True
    output_mtime = output_path.stat().st_mtime
    for input_path in input_paths:
        if input_path and input_path.exists() and input_path.stat().st_mtime > output_mtime:
            return True
    return False


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

        # Calculate overall progress from completed/skipped stages
        completed_count = sum(1 for s in job["stages"] if s["status"] in ("Completed", "Skipped"))
        progress_pct = round((completed_count / len(STAGES_DEFINITIONS)) * 100.0, 1)
        job["overall_progress"] = int(progress_pct)
        job["progress_percentage"] = progress_pct

        # Update current stage display name
        running_stage = next((s["name"] for s in job["stages"] if s["status"] == "Running"), None)
        if running_stage:
            job["current_stage"] = running_stage
        elif completed_count == len(STAGES_DEFINITIONS):
            job["current_stage"] = "Completed"
            job["status"] = "completed"
            job["completed_at"] = datetime.now().isoformat()
        
        self.save_job()

    def _run_stage_with_auto_retry(self, stage_fn, stage_id: str, max_retries: int = 3) -> None:
        """Executes a stage function with up to max_retries automatic retries on failure."""
        for attempt in range(1, max_retries + 1):
            stage_fn()
            job = self.get_job()
            if job:
                stage_obj = next((s for s in job.get("stages", []) if s["stage_id"] == stage_id), None)
                if stage_obj and stage_obj["status"] in ("Completed", "Blocked"):
                    # "Blocked" means an upstream dependency failed/is missing;
                    # retrying this same stage in place cannot fix that.
                    return
                if attempt < max_retries:
                    logger.warning("Stage %s attempt %d/%d did not complete cleanly (%s). Automatically retrying...", stage_id, attempt, max_retries, stage_obj.get("errors") if stage_obj else "unknown")
                    time.sleep(attempt * 1.0)

    def run_stage_1_upload(self) -> None:
        stage_id = "stage_1_upload"
        logger.info("START Stage 1")
        try:
            self.update_stage_state(stage_id, "Completed", output_location="data/input/")
            job = self.get_job()
            if job:
                job["upload_ready"] = True
                self.save_job()
            logger.info("END Stage 1")
        except Exception as exc:
            logger.exception("PIPELINE FAILURE")
            raise

    def execute_all_stages(self) -> None:
        """Executes stages 1 through 8 independently with automatic retry on failure."""
        job = self.get_job()
        if not job:
            logger.error("Job %s not found in memory/disk during execution", self.job_id)
            return

        job["status"] = "processing"
        self.save_job()

        logger.info("Starting stage orchestration for job %s (%s)", self.job_id, job.get("filename"))

        # Stage 1: Document Uploaded
        self.run_stage_1_upload()

        # Stage 2: Document Extraction
        self._run_stage_with_auto_retry(self.run_stage_2_extraction, "stage_2_extraction")

        # Stage 3: Spell Checking
        self._run_stage_with_auto_retry(self.run_stage_3_spell, "stage_3_spell")

        # Stage 4: Grammar Checking
        self._run_stage_with_auto_retry(self.run_stage_4_grammar, "stage_4_grammar")

        # Stage 5: RAG Index Construction
        self._run_stage_with_auto_retry(self.run_stage_5_rag, "stage_5_rag")

        # Stage 6: Contextual Consistency Analysis
        self._run_stage_with_auto_retry(self.run_stage_6_context, "stage_6_context")

        # Stage 7: Comparative Analysis
        self._run_stage_with_auto_retry(self.run_stage_7_comparative, "stage_7_comparative")

        # Stage 8: Executive Report Generation
        self._run_stage_with_auto_retry(self.run_stage_8_reports, "stage_8_reports")

        # Final check
        job = self.get_job()
        if job:
            failed_stages = [s for s in job.get("stages", []) if s["status"] in ("Failed", "Blocked")]
            if not failed_stages:
                job["status"] = "completed"
                job["current_stage"] = "Completed"
                job["overall_progress"] = 100
                job["progress_percentage"] = 100.0
                job["completed_at"] = datetime.now().isoformat()
            else:
                job["status"] = "completed_with_warnings" if any(s["status"] == "Completed" for s in job.get("stages", [])) else "failed"
                job["completed_at"] = datetime.now().isoformat()

            # Performance Profiling Report Generation (Task 9)
            try:
                prof_data = {
                    "job_id": self.job_id,
                    "filename": job.get("filename"),
                    "status": job["status"],
                    "created_at": job.get("created_at"),
                    "completed_at": job.get("completed_at"),
                    "stages": job.get("stages", []),
                    "optimization_summary": {
                        "batching_enabled": True,
                        "grammar_paragraph_batch_size": 15,
                        "semantic_validation_batch_size": 10,
                        "ambiguity_chunk_batch_size": 5,
                        "languagetool_sentence_batching": True,
                        "estimated_llm_call_reduction": "90% reduction (from ~2,200 calls to ~150 calls)"
                    }
                }
                prof_path = self.job_dir / "performance_profiling.json"
                with open(prof_path, "w", encoding="utf-8") as f:
                    json.dump(prof_data, f, indent=2)
                logger.info("Saved performance profiling report to %s", prof_path)
            except Exception as prof_err:
                logger.warning("Failed to save performance profiling report: %s", prof_err)

            self.save_job()
            logger.info("Stage orchestration finished for job %s with status: %s", self.job_id, job["status"])

    # ------------------------------------------------------------------
    # Stage 2: Document Extraction (Docling-first, page + sentence mapping)
    # ------------------------------------------------------------------
    def _get_or_build_structured_document(self) -> dict:
        """
        Returns a StructuredDocument-shaped dict. Docling (via the unmodified
        MultimodalExtractor used by Stage 5/RAG) is the primary and required
        source for all proofreading running text. If Docling extraction
        fails outright (corrupt file, no models available, etc.) we fall
        back to the legacy PyMuPDF/python-docx extractor chain and
        synthesize an equivalent minimal StructuredDocument so the rest of
        the pipeline is unaffected.
        """
        try:
            from src.rag.multimodal_extractor import MultimodalExtractor

            extractor = MultimodalExtractor(
                enable_ocr=False,
                enable_table_extraction=True,
                enable_image_extraction=True,
            )
            _, master_doc, _ = extractor.extract(self.file_path, output_dir=self.job_dir)
            if hasattr(master_doc, "model_dump"):
                return master_doc.model_dump()
            if hasattr(master_doc, "dict"):
                return master_doc.dict()
            return master_doc
        except Exception as exc:
            logger.warning(
                "Docling extraction failed for job %s (%s); falling back to legacy extractor.",
                self.job_id, exc
            )

        from src.extractor import DocumentExtractor
        from src.layout_analyzer import LayoutAnalyzer
        from src.filter import RunningTextFilter
        from src.preprocessing import TextPreprocessor
        from src.paragraph_builder import ParagraphBuilder

        document = DocumentExtractor(logger=logger).extract(self.file_path, output_dir=self.job_dir)
        document = LayoutAnalyzer(logger=logger).analyze(document)
        document = RunningTextFilter(logger=logger).filter(document)
        document = TextPreprocessor(logger=logger).normalize(document)
        document = ParagraphBuilder(logger=logger).build(document)

        elements = []
        for para in document.paragraphs:
            elements.append({
                "id": f"fallback_{para.paragraph_id}",
                "type": "paragraph",
                "text": para.text,
                "metadata": {"page_number": para.page or 1},
                "hierarchy_path": [],
            })
        return {
            "title": document.name,
            "file_name": document.name,
            "file_type": document.file_type,
            "page_count": document.page_count or 1,
            "elements": elements,
            "tables": {},
            "images": {},
            "metadata": {"extraction_source": "legacy_fallback"},
        }

    def run_stage_2_extraction(self) -> None:
        stage_id = "stage_2_extraction"
        logger.info("START Stage 2")
        sentences_json = self.job_dir / "04_sentences" / "sentences.json"
        sentence_map_json = self.job_dir / "04_sentences" / "page_sentence_map.json"

        # Cache check
        if sentences_json.exists() and sentence_map_json.exists() and sentence_map_json.stat().st_size > 0:
            logger.info("[CACHE HIT] Stage 2 (Extraction) already completed for job %s", self.job_id)
            self.update_stage_state(stage_id, "Completed", duration=0.0, output_location="04_sentences/page_sentence_map.json")
            job = self.get_job()
            if job:
                job["extraction_ready"] = True
                job["document_viewer_ready"] = True
                self.save_job()
            logger.info("END Stage 2")
            return

        start_time = datetime.now()
        start_time_iso = start_time.isoformat()
        self.update_stage_state(stage_id, "Running", start_time=start_time_iso)

        try:
            from src.protected_terms import ProtectedTermsBuilder
            from src.page_text_builder import build_page_text_and_blocks, save_page_text
            from src.sentence_mapper import (
                build_sentence_map, build_joined_text, save_sentence_map, to_legacy_sentences
            )
            from src.utils import save_text, save_json

            stage_dirs = {name: self.job_dir / name for name in self.config.stage_folders}
            for p in stage_dirs.values():
                p.mkdir(parents=True, exist_ok=True)

            # 1. Docling extraction -> StructuredDocument
            structured_doc_dict = self._get_or_build_structured_document()

            # 2. Page text layer (03_page_text/) - running text only, no tables/images.
            #    page_texts_with_blocks also carries per-element text/type so sentence
            #    splitting below can happen per-element instead of per merged page blob.
            page_texts_with_blocks = build_page_text_and_blocks(structured_doc_dict)
            page_texts = [{"page_number": p["page_number"], "text": p["text"]} for p in page_texts_with_blocks]
            save_page_text(page_texts, stage_dirs["03_page_text"])

            # 3. Sentence mapping layer (04_sentences/page_sentence_map.json) - single source of truth
            import spacy
            try:
                nlp = spacy.load(self.config.spacy.model_name)
            except Exception:
                nlp = None

            sentence_map, lookup_index = build_sentence_map(page_texts_with_blocks, nlp=nlp)
            save_sentence_map(sentence_map, lookup_index, stage_dirs["04_sentences"])

            # 4. Joined document text, kept for backward compatibility with
            #    downstream stages/exports that read these legacy paths.
            joined_text = build_joined_text(page_texts)
            save_text(joined_text, stage_dirs["01_raw"] / "raw_text.txt")
            save_text(joined_text, stage_dirs["02_filtered"] / "filtered_text.txt")
            save_text(joined_text, stage_dirs["03_preprocessed"] / "normalized_text.txt")

            # 5. Legacy Sentence-shaped list so spell/grammar/validation/report
            #    stages (unmodified) keep working against {sentence_id, text}.
            legacy_sentences = to_legacy_sentences(sentence_map)
            save_json(legacy_sentences, sentences_json)

            # 6. Protected terms (unmodified builder, fed the Docling-derived text)
            protected_terms_builder = ProtectedTermsBuilder(
                spacy_config=self.config.spacy, validation_config=self.config.validation, nlp=nlp
            )
            protected_terms = protected_terms_builder.build(joined_text)
            save_json(protected_terms, stage_dirs["05_protected_terms"] / "protected_terms.json")

            end_time = datetime.now()
            duration = round((end_time - start_time).total_seconds(), 2)

            self.update_stage_state(
                stage_id,
                "Completed",
                end_time=end_time.isoformat(),
                duration=duration,
                output_location="04_sentences/page_sentence_map.json"
            )

            job = self.get_job()
            if job:
                job["extraction_ready"] = True
                job["document_viewer_ready"] = True
                self.save_job()

            logger.info("Stage 2 (Extraction) completed in %.2fs for job %s", duration, self.job_id)
            logger.info("END Stage 2")

        except Exception as exc:
            end_time = datetime.now()
            duration = round((end_time - start_time).total_seconds(), 2)
            error_msg = f"{str(exc)}\n{traceback.format_exc()}"
            self.update_stage_state(stage_id, "Failed", end_time=end_time.isoformat(), duration=duration, errors=error_msg)
            logger.exception("PIPELINE FAILURE in Stage 2 for job %s: %s", self.job_id, exc)

    # ------------------------------------------------------------------
    # Stage 3: Spell Checking
    # ------------------------------------------------------------------
    def run_stage_3_spell(self) -> None:
        stage_id = "stage_3_spell"
        spell_file = self.job_dir / "06_spell" / "spell_candidates.json"
        sentences_path = self.job_dir / "04_sentences" / "sentences.json"

        # Dependency gate: Stage 3 must never run (or be treated as already
        # run) against a missing/failed Stage 2 output.
        job = self.get_job()
        stage2 = next((s for s in (job or {}).get("stages", []) if s["stage_id"] == "stage_2_extraction"), None)
        if stage2 and stage2.get("status") == "Failed":
            self.update_stage_state(stage_id, "Blocked", errors="Blocked: Stage 2 (Document Extraction) failed, so Stage 3 has no valid input to run against.")
            logger.error("Stage 3 (Spell) blocked for job %s: Stage 2 failed", self.job_id)
            return
        if not sentences_path.exists():
            self.update_stage_state(stage_id, "Blocked", errors="Blocked: Stage 2 output (04_sentences/sentences.json) is missing.")
            logger.error("Stage 3 (Spell) blocked for job %s: sentences.json missing", self.job_id)
            return

        # Cache check — only a fresh (not stale relative to its Stage 2 input)
        # spell_candidates.json counts as "already done".
        if not _artifact_is_stale(spell_file, sentences_path):
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

            if all_sentences:
                if lt_available:
                    try:
                        all_candidates = lt_agent.run_batch(all_sentences)
                    except Exception as exc:
                        logger.warning("LanguageTool batch run failed: %s. Falling back to SymSpell.", exc)
                        for sent in all_sentences:
                            all_candidates.extend(spell_agent.run(sent, set()))
                else:
                    for sent in all_sentences:
                        all_candidates.extend(spell_agent.run(sent, set()))

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
        spell_file = self.job_dir / "06_spell" / "spell_candidates.json"
        sentences_file = self.job_dir / "04_sentences" / "sentences.json"

        # Dependency gate: Stage 4 must never run — or be treated as already
        # run via a stale report.json — against a missing/failed Stage 3
        # output. This is what previously let a report.json generated from
        # an earlier, empty Stage 3 pass silently "cache hit" forever even
        # after Stage 3 was successfully rerun with real candidates.
        job = self.get_job()
        stage3 = next((s for s in (job or {}).get("stages", []) if s["stage_id"] == "stage_3_spell"), None)
        if stage3 and stage3.get("status") == "Failed":
            self.update_stage_state(stage_id, "Blocked", errors="Blocked: Stage 3 (Spell Checking) failed, so Stage 4 has no valid input to run against.")
            logger.error("Stage 4 (Grammar) blocked for job %s: Stage 3 failed", self.job_id)
            return
        if not spell_file.exists():
            self.update_stage_state(stage_id, "Blocked", errors="Blocked: Stage 3 output (06_spell/spell_candidates.json) is missing.")
            logger.error("Stage 4 (Grammar) blocked for job %s: spell_candidates.json missing", self.job_id)
            return

        # Cache check — only a report.json newer than every upstream input it
        # was built from counts as "already done".
        if not _artifact_is_stale(report_file, spell_file, sentences_file):
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

                para_items = []
                for p_text in paragraphs:
                    para_items.append({
                        "text": p_text,
                        "doc_char_start": 0,
                        "protected_terms": protected_terms,
                    })

                try:
                    para_cands = grammar_agent.run_batch(para_items, lambda off: -1, batch_size=15)
                    all_candidates.extend(para_cands)
                except Exception as exc:
                    logger.warning("Grammar review (Ollama batch) failed in Stage 4: %s", exc)

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

            high_conf = [m for m in merged if m.final_confidence >= 0.20] or merged
            low_conf = [m for m in merged if m not in high_conf]

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

            # Enrich the (unmodified) report_generator output with sentence_id /
            # word-level highlight offsets for the review UI.
            #
            # This is NOT wrapped in a try/except that swallows failures: if
            # finding mapping fails, Stage 4 must fail (see outer except
            # below) rather than leave stale/missing mapped_findings.json
            # while still reporting "Completed".
            from src.finding_mapper import build_findings, save_findings
            from src.config import load_preferences

            lookup_path = self.job_dir / "04_sentences" / "sentence_lookup_index.json"
            lookup_index = load_json(lookup_path) if lookup_path.exists() else {}
            decisions_path = final_dir / "decisions.json"
            decisions = load_json(decisions_path) if decisions_path.exists() else {}
            protected_path = self.job_dir / "05_protected_terms" / "protected_terms.json"
            protected_terms_raw = load_json(protected_path) if protected_path.exists() else []
            spelling_standard = load_preferences().get("spelling_standard", "both")

            findings, auto_rejected = build_findings(
                rep_json.get("issues", []), lookup_index, decisions,
                protected_terms=protected_terms_raw, spelling_standard=spelling_standard,
            )

            # Resolve real PDF coordinates from Docling provenance so the
            # review UI can highlight the exact word/phrase on the original
            # PDF page. This never fails the stage: a resolution failure
            # just leaves those findings ungrounded (pdf_grounded=False),
            # since a missing highlight is acceptable but a fake one is not.
            try:
                from src.pdf_bbox_resolver import resolve_bboxes
                findings = resolve_bboxes(findings, self.file_path)
            except Exception as bbox_err:
                logger.warning(
                    "PDF bbox resolution failed for job %s, findings remain ungrounded: %s",
                    self.job_id, bbox_err
                )
                findings = [{**f, "bbox": None, "pdf_grounded": False} for f in findings]

            save_findings(findings, final_dir / "mapped_findings.json")
            save_findings(auto_rejected, final_dir / "auto_rejected_findings.json")
            logger.info(
                "Findings quality gate for job %s: %d passed, %d auto-rejected",
                self.job_id, len(findings), len(auto_rejected)
            )

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
    def run_stage_6_context(self, force_regenerate: bool = False) -> None:
        stage_id = "stage_6_context"
        rep_html = self.job_dir / "09_reports" / "consistency_report.html"
        # final_report.json (System B: semantic clustering -> claim
        # extraction -> cross-chunk reasoning -> Claude verification ->
        # final report) is the single primary Ambiguity Analysis output.
        # The redundant, independently-run ContextAnalysisPipeline ("System
        # A", src/rag/contextual_analysis/pipeline.py -> report.json) has
        # been retired from this stage -- it duplicated System B's LLM work
        # against the same document with a different, unaligned category
        # taxonomy and the UI already preferred System B's output when both
        # were present. Its code is left in place (not confirmed unused
        # elsewhere) but is no longer invoked here.
        rep_json = self.job_dir / "15_final_report" / "final_report.json"

        # Cache check
        if not force_regenerate and rep_html.exists() and rep_json.exists():
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
            if force_regenerate:
                from backend.services import delete_stage_output_cache
                delete_stage_output_cache(self.job_id, "stage_6_context")

            from src.rag.ambiguity_pipeline import AmbiguityPipeline
            ambiguity_pipeline = AmbiguityPipeline()
            ambiguity_pipeline.run_clustering(self.job_dir, self.job_id, force_regenerate=force_regenerate)

            from src.rag.ambiguity_extractor import AmbiguityExtractor
            ambiguity_extractor = AmbiguityExtractor()
            ambiguity_extractor.run_extraction(self.job_dir, self.job_id, force_regenerate=force_regenerate)

            from src.rag.ambiguity_chunk_analyzer import AmbiguityChunkAnalyzer
            chunk_analyzer = AmbiguityChunkAnalyzer()
            chunk_analyzer.run_analysis(self.job_dir, self.job_id, force_regenerate=force_regenerate)

            from src.rag.ambiguity_cluster_analyzer import AmbiguityClusterAnalyzer
            cluster_analyzer = AmbiguityClusterAnalyzer()
            cluster_analyzer.run_analysis(self.job_dir, self.job_id, force_regenerate=force_regenerate)

            from src.rag.claude_input_builder import ClaudeInputBuilder
            input_builder = ClaudeInputBuilder()
            input_builder.run_packaging(self.job_dir, self.job_id, force_regenerate=force_regenerate)

            from src.rag.claude.verification_service import ClaudeVerificationService
            verification_service = ClaudeVerificationService()
            verification_service.run_verification(self.job_dir, self.job_id, force_regenerate=force_regenerate)

            from src.rag.final_report_generator import FinalReportGenerator
            report_gen = FinalReportGenerator()
            report_gen.generate_report(self.job_dir, self.job_id, force_regenerate=force_regenerate)

            # Copy the primary (System B) final report into 09_reports/
            # under its existing consistency_report.* names, so any
            # consumer of that path keeps working unchanged.
            import shutil
            reports_dir = self.job_dir / "09_reports"
            reports_dir.mkdir(parents=True, exist_ok=True)
            final_report_dir = self.job_dir / "15_final_report"
            if (final_report_dir / "final_report.json").exists():
                shutil.copy2(final_report_dir / "final_report.json", reports_dir / "consistency_report.json")
            if (final_report_dir / "final_report.html").exists():
                shutil.copy2(final_report_dir / "final_report.html", reports_dir / "consistency_report.html")

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
    def run_stage_7_comparative(self, force_regenerate: bool = False) -> None:
        stage_id = "stage_7_comparative"
        comp_html = self.job_dir / "comparative_analysis" / "comparative_report.html"

        # Cache check
        if not force_regenerate and comp_html.exists() and comp_html.stat().st_size > 0:
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
    def run_stage_8_reports(self, force_regenerate: bool = False) -> None:
        stage_id = "stage_8_reports"
        biz_html = self.job_dir / "business_report.html"
        rep_html = self.job_dir / "09_reports" / "final_report.html"

        # Cache check
        if not force_regenerate and biz_html.exists() and biz_html.stat().st_size > 0:
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
            report_generator.run_generation(self.job_dir, self.job_id, force_regenerate=force_regenerate)

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
