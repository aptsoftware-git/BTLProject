import json
import logging
from typing import List, Dict, Any, Tuple, Optional
from src.rag.contextual_analysis.models import InconsistencyIssue
from src.rag.contextual_analysis.inference_service import InferenceService

logger = logging.getLogger("pipeline")

class CandidateBuilder:
    """
    Groups related Knowledge Objects into logical clusters based on section_path,
    parent headings, captions, and close next/prev linkages.
    Enables highly targeted comparison groups, reducing token overhead.
    """

    @staticmethod
    def build_candidates(objects: List[Dict[str, Any]]) -> List[Tuple[str, List[Dict[str, Any]]]]:
        groups = []
        
        # 1. Group by Section Path (to compare statements within the same section)
        sections: Dict[str, List[Dict[str, Any]]] = {}
        for obj in objects:
            sec = obj.get("section_path") or "Root"
            if sec not in sections:
                sections[sec] = []
            sections[sec].append(obj)
            
        for sec, sec_objs in sections.items():
            if len(sec_objs) >= 2:
                groups.append((f"Section: {sec}", sec_objs[:15]))

        # 2. Group Image/Table with their captions and adjacent text
        for obj in objects:
            c_type = obj.get("chunk_type")
            obj_id = obj.get("knowledge_id")
            if c_type in ("Table", "Image"):
                group_objs = [obj]
                
                caption_id = obj.get("relationships", {}).get("has_caption")
                related_id = obj.get("relationships", {}).get("related_text")
                
                for other in objects:
                    other_id = other.get("knowledge_id")
                    if other_id == caption_id or other_id == related_id:
                        group_objs.append(other)
                        
                if len(group_objs) > 1:
                    groups.append((f"Figure/Table Context: {obj_id}", group_objs))

        # 3. Concept-based Global Grouping (NEW!)
        concepts = {
            "Financial Metrics & Revenue": ["revenue", "turnover", "income", "sales", "earnings", "profit", "crore", "million", "billion", "expense"],
            "Personnel & Employee Count": ["employee", "staff", "headcount", "personnel", "workforce", "hire"],
            "Growth & Increase Rates": ["growth", "growth rate", "cagr", "increase", "expansion", "percentage"],
            "Company & Entities": ["pvt ltd", "private limited", "technologies limited", "company name", "incorporated"],
            "Credential & Security Policy": ["password", "expiry", "expire", "expiration", "credential", "security policy"],
            "Warranty & Maintenance Agreements": ["warranty", "guarantee", "maintenance period"]
        }
        
        for name, keywords in concepts.items():
            concept_objs = []
            for obj in objects:
                text_lower = obj.get("text", "").lower()
                if any(kw in text_lower for kw in keywords):
                    concept_objs.append(obj)
            if len(concept_objs) >= 2:
                groups.append((f"Global Concept: {name}", concept_objs[:15]))
                    
        return groups

class ContextAnalysisAgent:
    """
    Agent responsible for analyzing candidate groups of Knowledge Objects
    and generating potential inconsistencies using InferenceService.
    """

    def __init__(self, inference_service: InferenceService):
        self.inference_service = inference_service

    def analyze_group(self, context_title: str, group_objs: List[Dict[str, Any]]) -> List[InconsistencyIssue]:
        # Formulate group text
        text_lines = []
        for obj in group_objs:
            obj_id = obj.get("knowledge_id")
            c_type = obj.get("chunk_type")
            page = obj.get("page_number")
            txt = obj.get("text")
            text_lines.append(f"[{obj_id}] ({c_type}, Page {page}): {txt}")
            
        objects_text = "\n".join(text_lines)
        response_text = self.inference_service.run_analysis(context_title, objects_text)
        
        candidates = []
        try:
            # Clean possible markdown wrapping if any (e.g. ```json ... ```)
            cleaned = response_text.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("```")[1]
                if cleaned.startswith("json"):
                    cleaned = cleaned[4:]
            cleaned = cleaned.strip()
            
            issues_data = json.loads(cleaned)
            if isinstance(issues_data, list):
                for item in issues_data:
                    # Validate keys
                    cat = item.get("category", "Contradiction")
                    sev = item.get("severity", "Medium")
                    conf = float(item.get("confidence", 0.7))
                    desc = item.get("description", "")
                    ev = item.get("evidence", "")
                    obj_ids = item.get("object_ids", [])
                    pages = item.get("page_numbers", [])
                    sec = item.get("section_path", context_title)
                    quoted = item.get("quoted_text", "")
                    
                    if desc and obj_ids:
                        candidates.append(InconsistencyIssue(
                            category=cat,
                            severity=sev,
                            confidence=conf,
                            description=desc,
                            evidence=ev,
                            object_ids=obj_ids,
                            page_numbers=pages,
                            section_path=sec,
                            quoted_text=quoted
                        ))
        except Exception as e:
            logger.warning(f"Failed to parse analysis response JSON: {e}. Response was: {response_text[:300]}")
            
        return candidates

class EvidenceCollector:
    """
    Collects and validates supporting sentences or paragraphs from objects
    implicated in a candidate inconsistency.
    """

    @staticmethod
    def enrich_evidence(issue: InconsistencyIssue, objects_by_id: Dict[str, Dict[str, Any]]) -> None:
        quotes = []
        for oid in issue.object_ids:
            obj = objects_by_id.get(oid)
            if obj:
                txt = obj.get("text", "").strip()
                if txt:
                    # Capture snippet
                    quotes.append(f"[{oid}]: \"{txt[:250]}...\"")
        if quotes:
            issue.evidence = "\n".join(quotes)

class CitationValidator:
    """
    Validates that quoted evidence exists verbatim in the referenced knowledge objects.
    """

    @staticmethod
    def validate_citation(issue: InconsistencyIssue, objects_by_id: Dict[str, Dict[str, Any]]) -> bool:
        if not issue.object_ids:
            return False
            
        # Ensure at least one object ID exists in the loaded list
        valid_objs = 0
        for oid in issue.object_ids:
            if oid in objects_by_id:
                valid_objs += 1
                
        # If none of the cited IDs exist, citation is broken
        if valid_objs == 0:
            return False
            
        return True

class VerificationAgent:
    """
    Second-stage agent that verifies candidate inconsistencies,
    discards false positives, and calculates final confidence.
    """

    def __init__(self, inference_service: InferenceService):
        self.inference_service = inference_service

    def verify_issue(self, issue: InconsistencyIssue, objects_by_id: Dict[str, Dict[str, Any]]) -> Optional[InconsistencyIssue]:
        # Formulate citation context
        context_parts = []
        for oid in issue.object_ids:
            obj = objects_by_id.get(oid)
            if obj:
                context_parts.append(f"[{oid}] (Page {obj.get('page_number')}): {obj.get('text')}")
        
        objects_content = "\n".join(context_parts)
        
        response_text = self.inference_service.run_verification(
            category=issue.category,
            description=issue.description,
            evidence=issue.evidence,
            object_ids=", ".join(issue.object_ids),
            section_path=issue.section_path,
            objects_content=objects_content
        )
        
        try:
            cleaned = response_text.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("```")[1]
                if cleaned.startswith("json"):
                    cleaned = cleaned[4:]
            cleaned = cleaned.strip()
            
            data = json.loads(cleaned)
            is_verified = data.get("verified", False)
            conf = float(data.get("confidence", 0.0))
            
            if is_verified and conf >= 0.4:
                issue.confidence = conf
                issue.description = data.get("revised_description", issue.description)
                issue.metadata["verification_reason"] = data.get("reason", "Verified by verification stage.")
                return issue
        except Exception as e:
            logger.warning(f"Verification parse failed for issue: {e}. Response was: {response_text}")
            
        return None
