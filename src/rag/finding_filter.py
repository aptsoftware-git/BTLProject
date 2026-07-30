"""
finding_filter.py
=================
Executive Finding Filtering, Taxonomy Mapping, Severity Scoring,
and Consolidation Engine.

Enforces Parts 1-6 and 12-14 of the Quality Transformation Initiative:
1. Suppresses low-value findings (headers, page titles, contact info, standalone company names).
2. Filters out low-confidence findings (< 0.70).
3. Classifies findings into Critical, High, Medium, Low, Informational based on business impact.
4. Consolidates duplicate/similar findings into 4-10 executive-grade observations.
5. Standardizes findings under 15 business-focused categories.
"""

from __future__ import annotations

import re
import logging
from typing import List, Dict, Any, Optional
from collections import Counter

logger = logging.getLogger("pipeline")

# Phase 4: Business Taxonomy (12 Executive Categories)
TAXONOMY_CATEGORIES = {
    "Numerical Inconsistency",
    "Cross-Reference Error",
    "Undefined Term",
    "Undefined Acronym",
    "Unsupported Claim",
    "Policy Conflict",
    "Governance Inconsistency",
    "Compliance Risk",
    "Regulatory Risk",
    "Missing Evidence",
    "Business Logic Conflict",
    "Contradictory Statement",
}

# Mapping legacy / raw LLM category strings to the 12 standard business categories
CATEGORY_MAPPINGS = {
    "vague wording": "Undefined Term",
    "Writing Clarity": "Undefined Term",
    "undefined terminology": "Undefined Term",
    "Undefined Term": "Undefined Term",
    "undefined acronym": "Undefined Acronym",
    "acronym definition": "Undefined Acronym",
    "Acronym Definition": "Undefined Acronym",
    "policy conflict": "Policy Conflict",
    "Policy Conflict": "Policy Conflict",
    "contradiction": "Contradictory Statement",
    "Contradictory Statements": "Contradictory Statement",
    "Contradictory Statement": "Contradictory Statement",
    "numerical ambiguity": "Numerical Inconsistency",
    "Numerical Mismatch": "Numerical Inconsistency",
    "Numerical Consistency": "Numerical Inconsistency",
    "temporal ambiguity": "Contradictory Statement",
    "Reference Conflict": "Cross-Reference Error",
    "Cross-Reference Mismatch": "Cross-Reference Error",
    "weak instructions": "Business Logic Conflict",
    "pronoun ambiguity": "Undefined Term",
    "Compliance Risk": "Compliance Risk",
    "Regulatory Risk": "Regulatory Risk",
    "Governance Inconsistency": "Governance Inconsistency",
    "Business Logic Conflict": "Business Logic Conflict",
    "Unsupported Claim": "Unsupported Claim",
    "Data Quality": "Numerical Inconsistency",
    "Missing Evidence": "Missing Evidence",
    "Market Overlap": "Business Logic Conflict",
    "Duplicate Info": "Contradictory Statement",
    "Incomplete Info": "Missing Evidence",
}

# PART 1: Suppressed Terms, Section Headers, Contact Details, Standalone Entities & Boilerplate Sections
SUPPRESSED_EXACT_PATTERNS = {
    "OUR VISION", "OUR MISSION", "VISION", "MISSION", "PROJECTS", "OVERVIEW",
    "STRENGTHS", "CONTENT", "DOCUMENT", "SECTION", "OUR HERITAGE", "TABLE OF CONTENTS",
    "CONTENTS PAGE", "INDEX PAGE", "CHAIRMAN'S MESSAGE", "CORPORATE PHILOSOPHY",
    "ACKNOWLEDGEMENTS", "FORWARD LOOKING STATEMENTS", "COMPANY PROFILE", "CONTACT",
    "CONTACT US", "INDUSTRY", "HEADQUARTERS", "BOARD & KEY LEADERSHIP",
    "BOARD AND KEY LEADERSHIP", "KEY LEADERSHIP", "WEBSITE", "EMAIL", "ADDRESS",
    "ABOUT US", "EXECUTIVE SUMMARY", "INTRODUCTION", "FINANCIAL PERFORMANCE",
    "SERVICES", "PRODUCTS", "LEADERSHIP", "MANAGEMENT", "CORPORATE INFORMATION",
    "REGISTERED OFFICE", "FINANCIAL ASSETS", "NET DEBT", "TOTAL EQUITY", "SENSITIVITY ANALYSIS",
    "TABLE 1", "APPENDIX"
}

PLACEHOLDER_TEXT_PATTERNS = [
    "the model processes", "example text", "sample content", "placeholder",
    "lorem ipsum", "internal test", "test string", "sample paragraph"
]

EXCLUDED_BOILERPLATE_SECTIONS = [
    "chairman's message", "vision", "mission", "corporate philosophy",
    "acknowledgements", "forward looking statements", "contents page", "index page"
]

SUPPRESSED_REGEXES = [
    re.compile(r"^\s*(?:our vision|our mission|vision|mission|projects|overview|strengths|content|document|section|our heritage|company profile|contact|industry|headquarters|board|leadership|website|email|address|phone|tel|fax|about us|table\s*\d+|appendix)\s*$", re.IGNORECASE),
    re.compile(r"^\s*(?:https?://|www\.|[\w.+-]+@[\w-]+\.[\w.-]+)\s*$", re.IGNORECASE),
    re.compile(r"^\s*(?:page\s*\d+|section\s*\d+(?:\.\d+)*)\s*$", re.IGNORECASE),
    re.compile(r"^\s*\w+\s*(?:is|lacks|undefined|vague|not defined|lacks explanation|lacks context)\s*$", re.IGNORECASE),
]


class FindingRelevanceFilter:
    """
    Filtering, scoring, deduplication, and consolidation engine for Context Analysis & Executive Reports.
    Enforces Context Analysis Quality & Claude Verification Overhaul (Phases 1-9).
    """

    def __init__(self, min_confidence: float = 0.70, max_findings: int = 30, min_findings: int = 5):
        self.min_confidence = min_confidence
        self.max_findings = max_findings
        self.min_findings = min_findings

    def is_placeholder(self, text: str) -> bool:
        """Phase 1: Detects and rejects internal system/placeholder text leakage."""
        if not text:
            return False
        text_lower = text.lower()
        return any(pattern in text_lower for pattern in PLACEHOLDER_TEXT_PATTERNS)

    def is_boilerplate_heading_or_table(self, quote: str, title: str = "", section: str = "") -> bool:
        """Phase 1: Detects section titles, headings, TOC entries, tables, and boilerplate sections."""
        q_clean = quote.strip().upper()
        t_clean = title.strip().upper()
        s_clean = section.strip().lower()

        # Reject boilerplate annual report sections
        if any(b_sec in s_clean or b_sec in q_clean.lower() or b_sec in t_clean.lower() for b_sec in EXCLUDED_BOILERPLATE_SECTIONS):
            return True

        # Reject single-word headings, TOC labels, section titles, table labels
        if q_clean in SUPPRESSED_EXACT_PATTERNS or t_clean in SUPPRESSED_EXACT_PATTERNS:
            return True

        # Skip financial tables and data grids
        if re.search(r"\|\s*[\d,.-]+\s*\|", quote) or re.search(r"financial assets|net debt|total equity|sensitivity analysis", q_clean, re.IGNORECASE):
            return True

        # Check regex suppressions
        for pattern in SUPPRESSED_REGEXES:
            if pattern.search(quote) or pattern.search(title):
                return True

        # Phase 1: Suppress short quotes (< 15 chars) without action verbs
        if len(quote.strip()) < 15 and not re.search(r"\b(?:is|are|was|were|has|have|will|must|should|cannot)\b", quote, re.IGNORECASE):
            return True

        return False

    def is_suppressed(self, quote: str, title: str = "", explanation: str = "", section: str = "") -> bool:
        """Determines if a finding is low-value noise or suppressed content."""
        if self.is_placeholder(quote) or self.is_placeholder(title) or self.is_placeholder(explanation):
            return True

        e_clean = (explanation + " " + title).lower()
        if any(term in e_clean for term in ["numeric", "mismatch", "broken", "reference", "page reference", "section reference", "parentheses"]):
            return False

        if self.is_boilerplate_heading_or_table(quote, title, section):
            return True

        return False

    def normalize_category(self, raw_category: str) -> str:
        """Phase 4: Maps raw category strings into the 12 standard business taxonomy categories."""
        if raw_category in TAXONOMY_CATEGORIES:
            return raw_category
        return CATEGORY_MAPPINGS.get(raw_category, "Undefined Term")

    def generate_specific_business_impact(self, category: str, title: str = "", text: str = "") -> str:
        """Phase 5: Generates category-specific business impacts."""
        cat_lower = category.lower()

        if "numerical" in cat_lower:
            return "May affect financial reporting accuracy and stakeholder trust."
        if "acronym" in cat_lower:
            return "May cause interpretation inconsistencies among readers."
        if "cross-reference" in cat_lower or "reference" in cat_lower:
            return "May reduce document traceability during audits and reviews."
        if "unsupported" in cat_lower:
            return "Unsubstantiated statement creates credibility risk during regulatory or investor audit."
        if "policy" in cat_lower:
            return "May create compliance exposure and departmental misalignment."
        if "governance" in cat_lower:
            return "Inconsistent governance rules create operational execution risk across units."
        if "compliance" in cat_lower:
            return "Statutory or internal compliance gap introduces potential audit penalty."
        if "regulatory" in cat_lower:
            return "Non-aligned regulatory statement introduces statutory exposure."
        if "missing evidence" in cat_lower:
            return "Missing empirical evidence weakens document authority and audit readiness."
        if "logic" in cat_lower:
            return "Logical inconsistency in business rules introduces operational errors."
        if "contradictory" in cat_lower:
            return "Conflicting disclosures degrade executive clarity and audit reliability."
        return "Operational execution deviation & stakeholder ambiguity."

    def generate_specific_recommendation(self, category: str, title: str = "", text: str = "") -> str:
        """Phase 6: Generates category-specific actionable recommendations."""
        cat_lower = category.lower()

        if "acronym" in cat_lower:
            return "Define the acronym at its first occurrence and use it consistently thereafter."
        if "numerical" in cat_lower:
            return "Reconcile the reported values across referenced sections and update the source figures."
        if "unsupported" in cat_lower:
            return "Add supporting evidence, references, or metrics to substantiate the claim."
        if "cross-reference" in cat_lower or "reference" in cat_lower:
            return "Correct section, note, and page cross-references across all document chapters."
        if "policy" in cat_lower:
            return "Harmonize policy language across departments to establish a single authoritative rule."
        if "governance" in cat_lower:
            return "Align governance directives across operational chapters."
        if "compliance" in cat_lower:
            return "Remediate compliance clause to satisfy statutory audit standards."
        if "regulatory" in cat_lower:
            return "Align disclosure text with regulatory mandate."
        if "missing evidence" in cat_lower:
            return "Provide empirical supporting data, citations, or audit notes."
        if "logic" in cat_lower:
            return "Reconcile business rule logic across process descriptions."
        if "contradictory" in cat_lower:
            return "Reconcile contradictory statements into a unified authoritative narrative."
        return "Add explicit definition in glossary or at first occurrence in text."

    def calculate_severity(
        self,
        category: str,
        confidence: float,
        explanation: str = "",
        impact: str = "",
        occurrence_count: int = 1
    ) -> str:
        """Issue 7: Assigns 5-tier severity (Critical, High, Medium, Low, Informational)."""
        text_block = (explanation + " " + impact).lower()

        if any(w in text_block for w in ["regulatory audit failure", "legal liability", "contract breach", "penalty", "statutory violation"]):
            return "Critical"
        if category in ("Regulatory Risk", "Compliance Risk") and occurrence_count > 1:
            return "Critical"

        if category in ("Contradictory Statements", "Numerical Consistency", "Strategic Risk") or any(w in text_block for w in ["financial mismatch", "contradiction", "discrepancy"]):
            return "High"

        if category in ("Operational Ambiguity", "Cross-Reference Mismatch", "Missing Evidence", "Market Positioning Conflict", "Incomplete Information"):
            return "Medium"

        if category in ("Acronym Definition", "Data Quality", "Duplicate Information", "Document Structure"):
            return "Low"

        if confidence < 0.75:
            return "Informational"

        return "Medium"

    def filter_and_consolidate(self, raw_findings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Executes Context Analysis Quality Overhaul (Issues 1-12):
        - Filters out noise, placeholders, tables, & headings.
        - Enforces confidence threshold >= 0.70.
        - Performs semantic deduplication & aggregates page locations.
        - Generates specific impacts & recommendations.
        - Consolidates findings down to 15-40 high-signal items for 200+ page reports.
        """
        valid_findings = []

        for f in raw_findings:
            quote = f.get("quote") or f.get("highlighted_ambiguity") or f.get("suspected_text") or f.get("original_text") or ""
            title = f.get("title", "")
            explanation = f.get("claude_explanation") or f.get("reason") or f.get("explanation") or ""
            section = f.get("section", "")
            confidence = float(f.get("confidence") or 0.85)
            page = f.get("page") or f.get("page_number") or 1

            # Issue 8: Confidence Threshold Check (< 0.70 -> REJECT)
            if confidence < self.min_confidence:
                logger.debug(f"[FILTER] Dropping low-confidence finding ({confidence} < {self.min_confidence}): {title}")
                continue

            # Issues 1, 2, 3, 4, 11: Suppression & Placeholder/Heading Check
            if self.is_suppressed(quote, title, explanation, section):
                logger.debug(f"[FILTER] Suppressing noise/placeholder/heading finding: '{quote}' | {title}")
                continue

            # Category Normalization & Specific Impact / Recommendation
            raw_cat = f.get("category") or f.get("type") or f.get("business_category") or "Business Consistency"
            category = self.normalize_category(raw_cat)
            f["category"] = category
            f["business_impact"] = self.generate_specific_business_impact(category, title, explanation)
            f["recommendation"] = self.generate_specific_recommendation(category, title, explanation)

            # Severity Calculation
            occurrence_count = int(f.get("occurrence_count") or 1)
            f["severity"] = self.calculate_severity(category, confidence, explanation, f["business_impact"], occurrence_count)

            # Store page location
            pages_list = f.get("locations") or ([page] if page else [1])
            f["locations"] = sorted(list(set(pages_list)))

            valid_findings.append(f)

        # Issue 1 & Issue 9: Semantic Deduplication & Root-Cause Consolidation
        consolidated_map = {}
        for f in valid_findings:
            cat = f["category"]
            quote_clean = f.get("quote", "").strip().lower()
            title_clean = f.get("title", "").strip().lower()

            # Group key based on category + main topic stem
            topic_words = re.findall(r"\b[a-z]{4,}\b", title_clean + " " + quote_clean)
            key_words = [w for w in topic_words if w not in {"the", "this", "that", "from", "with", "have", "been", "where"}]
            topic_key = "_".join(sorted(key_words[:3])) if key_words else title_clean[:20]
            group_key = (cat, topic_key)

            if group_key not in consolidated_map:
                consolidated_map[group_key] = f
            else:
                existing = consolidated_map[group_key]
                # Merge page locations across pages (Issue 1: Aggregate supporting locations)
                new_locations = set(existing.get("locations", [])) | set(f.get("locations", []))
                existing["locations"] = sorted(list(new_locations))
                existing["occurrence_count"] = int(existing.get("occurrence_count", 1)) + 1

                # Keep highest confidence & strongest severity
                if f.get("confidence", 0) > existing.get("confidence", 0):
                    existing["confidence"] = f["confidence"]
                    existing["quote"] = f["quote"]

                sev_order = {"Critical": 4, "High": 3, "Medium": 2, "Low": 1, "Informational": 0}
                if sev_order.get(f["severity"], 0) > sev_order.get(existing["severity"], 0):
                    existing["severity"] = f["severity"]

        result = list(consolidated_map.values())

        # Issue 12: Target 15-40 meaningful findings max for large annual reports
        if len(result) > self.max_findings:
            sev_rank = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3, "Informational": 4}
            result.sort(key=lambda item: sev_rank.get(item.get("severity", "Medium"), 2))
            result = result[: self.max_findings]

        return result
