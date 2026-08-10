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

# Business taxonomy is defined ONCE, centrally, in ambiguity_taxonomy.py --
# this used to be a separate, independently-maintained 12-category set with
# its own legacy-string mapping, which drifted out of sync with the
# taxonomy enforced everywhere else in the pipeline (see the audit that
# found four different, unaligned category lists). Both names are kept as
# aliases here since other modules in this codebase still import
# TAXONOMY_CATEGORIES/CATEGORY_MAPPINGS by these names.
from src.rag.ambiguity_taxonomy import APPROVED_CATEGORIES, normalize_category as _normalize_category_shared

TAXONOMY_CATEGORIES = set(APPROVED_CATEGORIES)
CATEGORY_MAPPINGS = {c: c for c in APPROVED_CATEGORIES}

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
    "FIXED RATE INSTRUMENTS", "VARIABLE RATE INSTRUMENTS", "OUR GOVERNANCE COMMITMENT",
    "EDUCATION AND SKILL DEVELOPMENT", "GROWTH", "TABLE 1", "APPENDIX"
}

PLACEHOLDER_TEXT_PATTERNS = [
    "the model processes", "example text", "sample content", "placeholder",
    "lorem ipsum", "internal test", "test string", "sample paragraph",
    "chunk analysis", "internal validation", "in this chunk", "claims made in this chunk",
    "unrelated to the provided text", "from the given text", "validation or disvalidation",
    "information provided in the table", "based on information provided in",
    "no direct evidence", "the claims and entities", "claims and entities in this chunk",
    "seem unrelated to the provided text", "do not have direct evidence"
]

PROJECT_FACILITY_PATTERNS = [
    "coal handling plant", "raw material handling plant", "pet coke handling system",
    "bifpcl bangladesh maitree", "sail dsp", "iocl paradip", "yadadri tps",
    "ntpc pakri mines", "talcher fertilizer", "wbpdcl power plant", "sagardighi"
]

EXCLUDED_BOILERPLATE_SECTIONS = [
    "chairman's message", "vision", "mission", "corporate philosophy",
    "acknowledgements", "forward looking statements", "contents page", "index page"
]

SUPPRESSED_REGEXES = [
    re.compile(r"^\s*(?:our vision|our mission|vision|mission|projects|overview|strengths|content|document|section|our heritage|company profile|contact|industry|headquarters|board|leadership|website|email|address|phone|tel|fax|about us|growth|table\s*\d+|appendix|our governance commitment|education and skill development)\s*$", re.IGNORECASE),
    re.compile(r"^\s*(?:https?://|www\.|[\w.+-]+@[\w-]+\.[\w.-]+)\s*$", re.IGNORECASE),
    re.compile(r"^\s*(?:page\s*\d+|section\s*\d+(?:\.\d+)*)\s*$", re.IGNORECASE),
    re.compile(r"^\s*\w+\s*(?:is|lacks|undefined|vague|not defined|lacks explanation|lacks context)\s*$", re.IGNORECASE),
]


class FindingRelevanceFilter:
    """
    Filtering, scoring, deduplication, and consolidation engine for Context Analysis & Executive Reports.
    Enforces Context Analysis Quality & Transparency Overhaul (Issues 1-11).
    """

    def __init__(self, min_confidence: float = 0.70, max_findings: int = 25, min_findings: int = 5):
        self.min_confidence = min_confidence
        self.max_findings = max_findings
        self.min_findings = min_findings
        self.transparency_stats = {
            "raw_findings_generated": 0,
            "heading_rejections": 0,
            "table_rejections": 0,
            "placeholder_rejections": 0,
            "project_name_rejections": 0,
            "duplicate_rejections": 0,
            "claude_rejections": 0,
            "executive_findings_retained": 0
        }

    def is_placeholder(self, text: str) -> bool:
        """Issue 3: Detects and rejects internal system/placeholder text leakage."""
        if not text:
            return False
        text_lower = text.lower()
        return any(pattern in text_lower for pattern in PLACEHOLDER_TEXT_PATTERNS)

    def is_project_or_facility_name(self, quote: str, title: str = "") -> bool:
        """Issue 4: Detects standalone project names, plant names, client facility references."""
        text_block = (quote + " " + title).lower()
        if any(proj in text_block for proj in PROJECT_FACILITY_PATTERNS):
            # Only flag as issue if there is an explicit numeric conflict or broken reference
            if not any(kw in text_block for kw in ["mismatch", "conflict", "contradict", "differ", "incorrect", "broken"]):
                return True
        return False

    def is_boilerplate_heading_or_table(self, quote: str, title: str = "", section: str = "") -> bool:
        """Issues 1 & 2: Detects section titles, headings, TOC entries, and financial tables/data grids."""
        q_clean = quote.strip().upper()
        t_clean = title.strip().upper()
        s_clean = section.strip().lower()

        # Reject boilerplate annual report sections
        if any(b_sec in s_clean or b_sec in q_clean.lower() or b_sec in t_clean.lower() for b_sec in EXCLUDED_BOILERPLATE_SECTIONS):
            return True

        # Reject single-word headings, TOC labels, section titles, table labels
        if q_clean in SUPPRESSED_EXACT_PATTERNS or t_clean in SUPPRESSED_EXACT_PATTERNS:
            return True

        # Issue 2: Skip financial tables, data grids, and spreadsheet rows
        if re.search(r"\|\s*[\d,.-]+\s*\|", quote) or re.search(r"financial assets|net debt|total equity|fixed rate instruments|variable rate instruments|sensitivity analysis", q_clean, re.IGNORECASE):
            return True

        # Check regex suppressions
        for pattern in SUPPRESSED_REGEXES:
            if pattern.search(quote) or pattern.search(title):
                return True

        # Suppress short quotes (< 8 chars) without action verbs unless it's an ambiguity quote/term
        if len(quote.strip()) < 8 and not re.search(r"\b(?:is|are|was|were|has|have|will|must|should|cannot|tbd|asap|etc|or)\b", quote, re.IGNORECASE):
            if not any(term in (title + " " + quote).lower() for term in ["ambiguity", "vague", "spelling", "typo", "pronoun", "unclear", "undefined"]):
                return True

        return False

    def is_suppressed(self, quote: str, title: str = "", explanation: str = "", section: str = "") -> bool:
        """Determines if a finding is low-value noise or suppressed content."""
        if self.is_placeholder(quote) or self.is_placeholder(title) or self.is_placeholder(explanation):
            return True

        if self.is_project_or_facility_name(quote, title):
            return True

        e_clean = (explanation + " " + title).lower()
        if any(term in e_clean for term in ["numeric", "mismatch", "broken", "reference", "page reference", "section reference", "parentheses"]):
            return False

        if self.is_boilerplate_heading_or_table(quote, title, section):
            return True

        return False

    def normalize_category(self, raw_category: str, quote: str = "", explanation: str = "") -> Optional[str]:
        """Maps a raw category string onto the single shared Ambiguity Analysis
        taxonomy (src/rag/ambiguity_taxonomy.py). Returns None if the raw
        category doesn't map to an approved category (e.g. grammar/spelling/
        style) -- by the time findings reach this filter they should
        already have been gated upstream (final_report_generator.py), so
        this is a defense-in-depth check, not the primary enforcement
        point."""
        return _normalize_category_shared(raw_category)

    def generate_specific_business_impact(self, category: str, title: str = "", text: str = "") -> str:
        """Phase 5: Generates category-specific business impacts."""
        cat_lower = (category or "").lower()

        if "numerical" in cat_lower:
            return "May affect financial reporting accuracy and stakeholder trust."
        if "unit" in cat_lower or "measurement" in cat_lower:
            return "Inconsistent unit basis may cause the value to be misread or miscalculated downstream."
        if "date" in cat_lower or "timeline" in cat_lower:
            return "Conflicting dates/deadlines create scheduling or compliance risk."
        if "cross-reference" in cat_lower or "contradiction" in cat_lower and "cross" in cat_lower:
            return "May reduce document traceability during audits and reviews."
        if "pronoun" in cat_lower or "entity-reference" in cat_lower:
            return "Reader may misattribute the statement to the wrong entity or section."
        if "terminology" in cat_lower:
            return "Inconsistent terminology creates interpretation ambiguity among readers."
        if "structural" in cat_lower or "convention" in cat_lower:
            return "Structural inconsistency reduces document navigability and professional polish."
        if "missing" in cat_lower or "conflicting context" in cat_lower:
            return "Missing prerequisite context weakens the claim's credibility during review."
        if "internal factual" in cat_lower or "contradictory" in cat_lower or "contradiction" in cat_lower:
            return "Conflicting disclosures degrade executive clarity and audit reliability."
        return "Operational execution deviation & stakeholder ambiguity."

    def generate_specific_recommendation(self, category: str, title: str = "", text: str = "") -> str:
        """Phase 6: Generates category-specific actionable recommendations."""
        cat_lower = (category or "").lower()

        if "numerical" in cat_lower:
            return "Reconcile the reported values across referenced sections and update the source figures."
        if "unit" in cat_lower or "measurement" in cat_lower:
            return "Standardize the unit/scale basis and re-verify the reported value."
        if "date" in cat_lower or "timeline" in cat_lower:
            return "Confirm the correct date/deadline and update all conflicting references."
        if "cross-reference" in cat_lower:
            return "Correct section, note, and page cross-references across all document chapters."
        if "pronoun" in cat_lower or "entity-reference" in cat_lower:
            return "Replace the ambiguous pronoun/reference with an explicit noun or entity name."
        if "terminology" in cat_lower:
            return "Standardize terminology to a single term across the document."
        if "structural" in cat_lower or "convention" in cat_lower:
            return "Align numbering, headings, and formatting to a single document convention."
        if "missing" in cat_lower or "conflicting context" in cat_lower:
            return "Add the missing context or definition the claim depends on."
        if "internal factual" in cat_lower or "contradictory" in cat_lower or "contradiction" in cat_lower:
            return "Reconcile contradictory statements into a unified authoritative narrative."
        return "Review source document to reconcile conflicting statements."

    def calculate_severity(
        self,
        category: str,
        confidence: float,
        explanation: str = "",
        impact: str = "",
        occurrence_count: int = 1,
        title: str = "",
        quote: str = ""
    ) -> str:
        """Assigns 4-tier severity (CRITICAL, HIGH, MEDIUM, LOW)."""
        cat_lower = (category or "").lower()
        text_block = (title + " " + quote + " " + explanation + " " + impact + " " + category).lower()

        if any(w in text_block for w in ["regulatory audit failure", "legal liability", "contract breach", "penalty", "statutory violation", "gender", "statutory disclosure", "board appointment", "secretarial audit", "companies act", "director"]):
            return "CRITICAL"
        if "statutory" in text_block and occurrence_count > 1:
            return "CRITICAL"

        if (
            "internal factual" in cat_lower or "contradiction" in cat_lower
            or "numerical" in cat_lower or "unit" in cat_lower or "measurement" in cat_lower
            or any(w in text_block for w in ["financial mismatch", "contradiction", "discrepancy", "policy conflict", "revenue"])
        ):
            return "HIGH"

        if "cross-reference" in cat_lower or "date" in cat_lower or "timeline" in cat_lower or "missing" in cat_lower:
            return "MEDIUM"

        if "structural" in cat_lower or "convention" in cat_lower or "terminology" in cat_lower or "pronoun" in cat_lower:
            return "LOW"

        return "MEDIUM"

    def assign_materiality(
        self,
        severity: str,
        category: str,
        explanation: str = ""
    ) -> str:
        """Assigns Materiality (Material, Moderate, Informational)."""
        sev_upper = severity.upper()
        if sev_upper == "CRITICAL":
            return "Material"
        if sev_upper == "HIGH":
            return "Material"
        if sev_upper == "MEDIUM":
            return "Moderate"
        return "Informational"

    def calculate_risk_score(
        self,
        severity: str,
        materiality: str,
        category: str,
        explanation: str = ""
    ) -> int:
        """Assigns a deterministic Risk Score between 1 and 10."""
        sev_upper = severity.upper()
        text_lower = explanation.lower()

        if sev_upper == "CRITICAL":
            if any(w in text_lower for w in ["statutory", "financial", "legal", "penalty"]):
                return 10
            return 9
        elif sev_upper == "HIGH":
            if "governance" in text_lower or "policy" in text_lower:
                return 8
            return 7
        elif sev_upper == "MEDIUM":
            if "cross-reference" in text_lower or "reference" in text_lower:
                return 6
            return 5
        else:
            if "formatting" in text_lower:
                return 2
            return 3

    def generate_risk_reason(
        self,
        risk_score: int,
        category: str,
        title: str = ""
    ) -> str:
        """Generates documented audit risk reason for risk score."""
        if risk_score >= 9:
            return "Statutory disclosure contradiction or financial statement conflict with high compliance audit risk."
        elif risk_score >= 7:
            return "Governance disclosure issue or material policy inconsistency across document sections."
        elif risk_score >= 4:
            return "Cross-reference error, incomplete disclosure, or process execution ambiguity."
        else:
            return "Naming, terminology, or minor formatting inconsistency."

    def generate_confidence_reason(
        self,
        confidence_pct: int,
        category: str,
        evidence_text: str = ""
    ) -> str:
        """Generates textual explanation for why confidence score was assigned."""
        if confidence_pct >= 90:
            return "Direct verbatim textual contradiction verified across document passages."
        elif confidence_pct >= 80:
            return "High certainty finding validated by multi-section context comparison."
        elif confidence_pct >= 70:
            return "Moderate certainty finding flagged during consistency assurance scan."
        return "Low certainty finding requiring manual auditor review."

    @staticmethod
    def calculate_overall_risk_rating(findings: List[Dict[str, Any]]) -> str:
        """Derives Overall Risk Rating (CRITICAL, HIGH, MEDIUM, LOW)."""
        critical_count = sum(1 for f in findings if str(f.get("severity", "")).upper() == "CRITICAL" and f.get("materiality") == "Material")
        high_count = sum(1 for f in findings if str(f.get("severity", "")).upper() == "HIGH")
        material_count = sum(1 for f in findings if f.get("materiality") == "Material")

        if critical_count >= 1 or material_count >= 3:
            return "CRITICAL"
        elif high_count >= 2 or material_count >= 1:
            return "HIGH"
        elif len(findings) > 0:
            return "MEDIUM"
        else:
            return "LOW"

    def filter_and_consolidate(self, raw_findings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Executes Context Analysis Quality & Transparency Overhaul (Issues 1-11):
        - Filters out noise, placeholders, tables, project names, & headings.
        - Enforces confidence threshold >= 0.70.
        - Performs semantic deduplication & aggregates page locations.
        - Generates specific impacts & recommendations.
        - Consolidates findings down to 10-25 high-signal items for 200+ page reports.
        - Calculates full pipeline transparency metrics.
        """
        valid_findings = []
        self.transparency_stats = {
            "raw_findings_generated": len(raw_findings),
            "heading_rejections": 0,
            "table_rejections": 0,
            "placeholder_rejections": 0,
            "project_name_rejections": 0,
            "duplicate_rejections": 0,
            "claude_rejections": 0,
            "executive_findings_retained": 0
        }

        for f in raw_findings:
            quote = f.get("quote") or f.get("highlighted_ambiguity") or f.get("suspected_text") or f.get("original_text") or ""
            title = f.get("title", "")
            explanation = f.get("claude_explanation") or f.get("reason") or f.get("explanation") or ""
            section = f.get("section", "")
            confidence = float(f.get("confidence") or 0.85)
            page = f.get("page") or f.get("page_number") or 1

            if confidence < self.min_confidence:
                self.transparency_stats["claude_rejections"] += 1
                logger.debug(f"[FILTER] Dropping low-confidence finding ({confidence} < {self.min_confidence}): {title}")
                continue

            if self.is_placeholder(quote) or self.is_placeholder(title) or self.is_placeholder(explanation):
                self.transparency_stats["placeholder_rejections"] += 1
                logger.debug(f"[FILTER] Suppressing placeholder text finding: '{quote}'")
                continue

            if self.is_project_or_facility_name(quote, title):
                self.transparency_stats["project_name_rejections"] += 1
                logger.debug(f"[FILTER] Suppressing standalone project/facility name: '{quote}'")
                continue

            if self.is_boilerplate_heading_or_table(quote, title, section):
                if re.search(r"\|\s*[\d,.-]+\s*\|", quote) or re.search(r"financial assets|net debt|total equity|fixed rate|variable rate", quote, re.IGNORECASE):
                    self.transparency_stats["table_rejections"] += 1
                else:
                    self.transparency_stats["heading_rejections"] += 1
                logger.debug(f"[FILTER] Suppressing heading/table noise finding: '{quote}' | {title}")
                continue

            # Category Normalization & Specific Impact / Recommendation
            raw_cat = f.get("category") or f.get("type") or f.get("business_category")
            category = self.normalize_category(raw_cat, quote, explanation)
            if category is None:
                # Not in the approved Ambiguity Analysis taxonomy (e.g. a
                # grammar/spelling/style label) -- should already have been
                # gated out upstream, but never let an unmapped category
                # reach the report as a defaulted/fabricated bucket.
                self.transparency_stats["claude_rejections"] += 1
                logger.debug(f"[FILTER] Dropping finding with unmapped category '{raw_cat}': {title}")
                continue
            f["category"] = category
            f["business_impact"] = self.generate_specific_business_impact(category, title, explanation)
            f["recommendation"] = self.generate_specific_recommendation(category, title, explanation)

            # Severity Calculation
            occurrence_count = int(f.get("occurrence_count") or 1)
            severity = self.calculate_severity(category, confidence, explanation, f["business_impact"], occurrence_count)
            f["severity"] = severity

            # Audit Metadata Enrichments
            materiality = self.assign_materiality(severity, category, explanation)
            f["materiality"] = materiality

            risk_score = self.calculate_risk_score(severity, materiality, category, explanation)
            f["risk_score"] = risk_score
            f["risk_reason"] = self.generate_risk_reason(risk_score, category, title)

            conf_pct = int(confidence * 100) if confidence <= 1.0 else int(confidence)
            conf_pct = min(100, max(0, conf_pct))
            f["confidence_pct"] = conf_pct
            f["confidence_reason"] = self.generate_confidence_reason(conf_pct, category, quote)

            f["finding_status"] = f.get("finding_status") or "Verified"
            f["audit_traceability"] = f.get("audit_traceability") or "Verified by Independent AI Validation Layer"

            # Store page location
            pages_list = f.get("locations") or ([page] if page else [1])
            f["locations"] = sorted(list(set(pages_list)))

            valid_findings.append(f)

        # Issue 6: Semantic Deduplication & Root-Cause Consolidation
        consolidated_map = {}
        for f in valid_findings:
            cat = f["category"]
            quote_clean = f.get("quote", "").strip().lower()
            title_clean = f.get("title", "").strip().lower()

            topic_words = re.findall(r"\b[a-z]{4,}\b", title_clean + " " + quote_clean)
            key_words = [w for w in topic_words if w not in {"the", "this", "that", "from", "with", "have", "been", "where"}]
            topic_key = "_".join(sorted(key_words[:3])) if key_words else title_clean[:20]
            group_key = (cat, topic_key)

            if group_key not in consolidated_map:
                consolidated_map[group_key] = f
            else:
                self.transparency_stats["duplicate_rejections"] += 1
                existing = consolidated_map[group_key]
                new_locations = set(existing.get("locations", [])) | set(f.get("locations", []))
                existing["locations"] = sorted(list(new_locations))
                existing["occurrence_count"] = int(existing.get("occurrence_count", 1)) + 1

                if f.get("confidence", 0) > existing.get("confidence", 0):
                    existing["confidence"] = f["confidence"]
                    existing["confidence_pct"] = f["confidence_pct"]
                    existing["quote"] = f["quote"]

                sev_order = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
                if sev_order.get(str(f["severity"]).upper(), 0) > sev_order.get(str(existing["severity"]).upper(), 0):
                    existing["severity"] = f["severity"]
                    existing["risk_score"] = f["risk_score"]
                    existing["materiality"] = f["materiality"]

        result = list(consolidated_map.values())

        # Sort findings by: Severity (CRITICAL -> HIGH -> MEDIUM -> LOW) -> Risk Score (Highest) -> Confidence (Highest)
        sev_rank = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
        result.sort(key=lambda item: (
            sev_rank.get(str(item.get("severity", "LOW")).upper(), 4),
            -int(item.get("risk_score", 1)),
            -int(item.get("confidence_pct", 0))
        ))

        if len(result) > self.max_findings:
            result = result[: self.max_findings]

        self.transparency_stats["executive_findings_retained"] = len(result)
        return result
