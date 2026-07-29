import json
import logging
import argparse
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from src.rag.contextual_analysis.models import InconsistencyIssue
from src.rag.contextual_analysis.inference_service import InferenceService
from src.rag.contextual_analysis.local_checks import LocalConsistencyChecker
from src.rag.contextual_analysis.agents import (
    CandidateBuilder, 
    ContextAnalysisAgent, 
    EvidenceCollector, 
    CitationValidator, 
    VerificationAgent
)
from src.rag.contextual_analysis.report_generator import ReportGenerator

logger = logging.getLogger("pipeline")

class ContextAnalysisPipeline:
    """
    Orchestrator for the Contextual Consistency Analysis pipeline.
    Coordinates local deterministic checks, LLM candidate builders,
    verification agents, evidence collection, and final report generation.
    """

    def __init__(self, model_name: str = "qwen2.5-coder:7b"):
        from src.rag.config import RagConfig
        from src.rag.contextual_analysis.semantic_retrieval_agent import SemanticRetrievalAgent
        
        self.config = RagConfig()
        self.retrieval_agent = SemanticRetrievalAgent(self.config)
        self.inference_service = InferenceService(model_name=model_name)
        self.analysis_agent = ContextAnalysisAgent(self.inference_service)
        self.verification_agent = VerificationAgent(self.inference_service)
        self.token_budget = getattr(self.config, "token_budget", 8000)

    def _update_status(self, doc_id: str, status: str, stage: str, progress: float, issues_count: int = 0, est_time: str = "N/A") -> None:
        try:
            from backend.services import JOBS, save_job_metadata
            import psutil
            import os
            if doc_id in JOBS:
                job = JOBS[doc_id]
                job["context_analysis_status"] = status
                job["context_analysis_stage"] = stage
                job["context_analysis_progress"] = progress
                job["context_analysis_issues_count"] = issues_count
                job["context_analysis_est_time"] = est_time
                
                try:
                    process = psutil.Process(os.getpid())
                    job["memory_usage"] = f"{process.memory_info().rss / 1024 / 1024:.1f} MB"
                    job["cpu_usage"] = f"{psutil.cpu_percent()}%"
                except Exception:
                    job["memory_usage"] = "N/A"
                    job["cpu_usage"] = "N/A"
                    
                save_job_metadata(doc_id)
        except Exception:
            pass

    def run_analysis(self, job_dir: Path, doc_id: str) -> None:
        logger.info(f"Starting Contextual Consistency Analysis for job: {doc_id}")
        
        # Smart Caching check
        report_json_path = job_dir / "report.json"
        report_html_path = job_dir / "report.html"
        business_html_path = job_dir / "business_report.html"
        
        if report_json_path.exists() and report_html_path.exists() and business_html_path.exists():
            logger.info("Contextual Consistency Report cache hit! Reusing existing reports.")
            issues_count = 0
            try:
                with open(report_json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    issues_count = len(data.get("issues", []))
            except Exception:
                pass
            self._update_status(doc_id, "completed", "Completed", 100.0, issues_count=issues_count)
            return

        self._update_status(doc_id, "running", "Loading Knowledge Objects", 10.0)
        
        # 1. Load knowledge_objects.json
        ko_path = job_dir / "03_knowledge_objects" / "knowledge_objects.json"
        if not ko_path.exists():
            ko_path = job_dir / "knowledge_objects.json"  # fallback
            
        if not ko_path.exists():
            self._update_status(doc_id, "failed", "knowledge_objects.json not found", 0.0)
            raise FileNotFoundError(f"knowledge_objects.json not found in job directory: {job_dir}")
            
        with open(ko_path, "r", encoding="utf-8") as f:
            objects = json.load(f)
            
        logger.info(f"Loaded {len(objects)} Knowledge Object(s) from {ko_path}")
        
        # Build lookup table of objects by ID
        objects_by_id = {o.get("knowledge_id"): o for o in objects if o.get("knowledge_id")}
        
        # Calculate page count
        page_count = max([o.get("page_number", 1) for o in objects]) if objects else 1
        source_file = objects[0].get("source_file", "unknown") if objects else "unknown"

        # 2. Stage 1: Semantic Retrieval & Clustering
        self._update_status(doc_id, "running", "Semantic Retrieval", 25.0)
        logger.info("Retrieving semantically similar Knowledge Objects from ChromaDB...")
        nodes, edges, neighbor_lists = self.retrieval_agent.retrieve_similar_pairs(doc_id)
        
        self._update_status(doc_id, "running", "Louvain Clustering", 40.0)
        if not nodes:
            logger.warning("Empty similarity graph from retrieval agent. Using section-based fallback groups.")
            sections = {}
            for obj in objects:
                sec = obj.get("section_path") or "Root"
                sections.setdefault(sec, []).append(obj.get("knowledge_id"))
            clusters = [oids for oids in sections.values() if len(oids) >= 2]
        else:
            from src.rag.contextual_analysis.clustering import LouvainClusterer
            logger.info(f"Running Louvain community detection over similarity graph with {len(nodes)} nodes and {len(edges)} edges...")
            clusterer = LouvainClusterer(nodes, edges)
            clusters = clusterer.get_clusters()
            
        logger.info(f"Clustering complete. Identified {len(clusters)} coarse group(s).")

        # 3. Stage 2: Local Deterministic Filtering
        self._update_status(doc_id, "running", "Running Local Checks", 55.0, issues_count=0)
        logger.info("Feeding clusters through deterministic local consistency checks...")
        local_checker = LocalConsistencyChecker(page_count=page_count)
        verified_issues: List[InconsistencyIssue] = []
        eligible_clusters = []

        from src.rag.contextual_analysis.report_generator import map_to_enterprise_category

        for cluster in clusters:
            cluster_objs = [objects_by_id[oid] for oid in cluster if oid in objects_by_id]
            if len(cluster_objs) < 2:
                continue
                
            local_issues = local_checker.check_all(cluster_objs)
            if local_issues:
                for issue in local_issues:
                    issue.category = map_to_enterprise_category(issue.category)
                verified_issues.extend(local_issues)
                logger.info(f"Resolved {len(local_issues)} deterministic issue(s) locally. Bypassing LLM.")
            else:
                eligible_clusters.append(cluster_objs)

        # 4. Pack Eligible Clusters into Token-Aware Batches
        self._update_status(doc_id, "running", "Token Packing", 65.0, issues_count=len(verified_issues))
        batches = []
        current_batch = []
        current_tokens = 0

        for cluster_objs in eligible_clusters:
            cluster_tokens = 0
            for obj in cluster_objs:
                text = obj.get("text", "")
                cluster_tokens += max(10, len(text) // 4)
                
            if current_tokens + cluster_tokens > self.token_budget:
                if current_batch:
                    batches.append(current_batch)
                current_batch = list(cluster_objs)
                current_tokens = cluster_tokens
            else:
                current_batch.extend(cluster_objs)
                current_tokens += cluster_tokens

        if current_batch:
            batches.append(current_batch)

        logger.info(f"Packed {len(eligible_clusters)} eligible clusters into {len(batches)} token-aware batch(es) (budget: {self.token_budget} tokens).")

        # 5. Run LLM Audits over Packed Batches (Parallelized)
        candidate_issues: List[InconsistencyIssue] = []
        from concurrent.futures import ThreadPoolExecutor

        def process_batch(item: Tuple[int, List[Dict[str, Any]]]) -> List[InconsistencyIssue]:
            idx, batch_objs = item
            title = f"Semantic Consistency Group {idx+1}"
            logger.info(f"Analyzing batch {idx+1}/{len(batches)} via InferenceService...")
            try:
                found = self.analysis_agent.analyze_group(title, batch_objs)
                return found or []
            except Exception as exc:
                logger.warning(f"Error analyzing batch {idx+1}: {exc}")
                return []

        if batches:
            max_batch_workers = min(4, len(batches))
            with ThreadPoolExecutor(max_workers=max_batch_workers) as executor:
                batch_results = list(executor.map(process_batch, enumerate(batches)))
            for found_issues in batch_results:
                candidate_issues.extend(found_issues)

        # Deduplicate candidate issues
        logger.info(f"Deduplicating {len(candidate_issues)} candidate issue(s)...")
        deduped_candidates: List[InconsistencyIssue] = []
        seen_issue_keys = set()
        for issue in candidate_issues:
            sorted_objs = tuple(sorted(issue.object_ids))
            key = (issue.category, sorted_objs)
            if key not in seen_issue_keys:
                seen_issue_keys.add(key)
                deduped_candidates.append(issue)
        candidate_issues = deduped_candidates

        # Optimization: Avoid verifying duplicate findings that are already resolved locally
        non_overlapping_candidates = []
        for issue in candidate_issues:
            is_duplicate = False
            for verified in verified_issues:
                if set(issue.object_ids) == set(verified.object_ids):
                    is_duplicate = True
                    break
            if not is_duplicate:
                non_overlapping_candidates.append(issue)
        candidate_issues = non_overlapping_candidates

        # 6. Verification and Evidence Collection (Parallelized)
        self._update_status(doc_id, "running", "Verification & Evidence Enrichment", 90.0, issues_count=len(verified_issues))
        logger.info(f"Verifying {len(candidate_issues)} unique candidate issues...")

        def process_verification(issue: InconsistencyIssue) -> Optional[InconsistencyIssue]:
            if not CitationValidator.validate_citation(issue, objects_by_id):
                logger.info(f"Discarding issue: citation validation failed for IDs {issue.object_ids}")
                return None
                
            EvidenceCollector.enrich_evidence(issue, objects_by_id)
            
            verified = self.verification_agent.verify_issue(issue, objects_by_id)
            if verified:
                verified.category = map_to_enterprise_category(verified.category)
                logger.info(f"Verified inconsistency: '{verified.description}'")
                return verified
            else:
                logger.info(f"Discarding false positive issue: '{issue.description}'")
                return None

        if candidate_issues:
            max_ver_workers = min(4, len(candidate_issues))
            with ThreadPoolExecutor(max_workers=max_ver_workers) as executor:
                ver_results = list(executor.map(process_verification, candidate_issues))
            for verified_item in ver_results:
                if verified_item:
                    verified_issues.append(verified_item)

        # 7. Save report.json and report.html
        logger.info(f"Generating final consistency reports inside {job_dir}...")
        json_p, html_p = ReportGenerator.generate_report(
            document_id=doc_id,
            source_file=source_file,
            issues=verified_issues,
            output_dir=job_dir
        )
        
        logger.info(f"Audit completed successfully. Report JSON: {json_p}, HTML: {html_p}")
        self._update_status(doc_id, "completed", "Completed", 100.0, issues_count=len(verified_issues))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Contextual Consistency Analysis on Ingested Knowledge Objects.")
    parser.add_argument("--job-dir", required=True, type=str, help="Absolute path to job output directory.")
    parser.add_argument("--job-id", required=True, type=str, help="Ingested document job ID.")
    parser.add_argument("--model", default="qwen2.5-coder:32b", type=str, help="Ollama model to use for audits.")
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO)
    pipeline = ContextAnalysisPipeline(model_name=args.model)
    pipeline.run_analysis(Path(args.job_dir), args.job_id)
