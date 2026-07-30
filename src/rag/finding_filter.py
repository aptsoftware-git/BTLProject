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

# PART 5: Business-Focused Finding Taxonomy (15 Standard Categories)
TAXONOMY_CATEGORIES = {
    "Business Consistency",
    "Numerical Consistency",
    "Acronym Definition",
    "Missing Evidence",
    "Regulatory Risk",
    "Compliance Risk",
    "Contradictory Statements",
    "Duplicate Information",
    "Incomplete Information",
    "Cross-Reference Mismatch",
    "Market Positioning Conflict",
    "Operational Ambiguity",
    "Strategic Risk",
    "Data Quality",
    "Document Structure",
}

# Mapping legacy / raw LLM category strings to the 15 standard business categories
CATEGORY_MAPPINGS = {
    "vague wording": "Operational Ambiguity",
    "Writing Clarity": "Operational Ambiguity",
    "undefined terminology": "Acronym Definition",
    "Undefined Term": "Acronym Definition",
    "policy conflict": "Contradictory Statements",
    "Policy Conflict": "Contradictory Statements",
    "contradiction": "Contradictory Statements",
    "numerical ambiguity": "Numerical Consistency",
    "Numerical Mismatch": "Numerical Consistency",
    "temporal ambiguity": "Business Consistency",
    "Reference Conflict": "Cross-Reference Mismatch",
    "weak instructions": "Operational Ambiguity",
    "pronoun ambiguity": "Operational Ambiguity",
    "Compliance Risk": "Compliance Risk",
    "Regulatory Risk": "Regulatory Risk",
    "Data Quality": "Data Quality",
    "Missing Evidence": "Missing Evidence",
    "Market Overlap": "Market Positioning Conflict",
    "Duplicate Info": "Duplicate Information",
    "Incomplete Info": "Incomplete Information",
}

# PART 1: Suppressed Terms, Section Headers, Contact Details, and Standalone Entities
SUPPRESSED_EXACT_PATTERNS = {
    "COMPANY PROFILE",
    "CONTACT",
    "CONTACT US",
    "INDUSTRY",
    "HEADQUARTERS",
    "BOARD & KEY LEADERSHIP",
    "BOARD AND KEY LEADERSHIP",
    "KEY LEADERSHIP",
    "LARSEN & TOUBRO",
    "LARSEN AND TOUBRO",
    "L&T",
    "WEBSITE",
    "EMAIL",
    "ADDRESS",
    "OVERVIEW",
    "ABOUT US",
    "TABLE OF CONTENTS",
    "EXECUTIVE SUMMARY",
    "INTRODUCTION",
    "FINANCIAL PERFORMANCE",
    "SERVICES",
    "PRODUCTS",
    "LEADERSHIP",
    "MANAGEMENT",
    "CORPORATE INFORMATION",
    "REGISTERED OFFICE",
}

SUPPRESSED_REGEXES = [
    re.compile(r"^\s*(?:company profile|contact|industry|headquarters|board|leadership|larsen\s*&\s*toubro|l&t|website|email|address|phone|tel|fax|overview|about us)\s*$", re.IGNORECASE),
    re.compile(r"^\s*(?:https?://|www\.|[\w.+-]+@[\w-]+\.[\w.-]+)\s*$", re.IGNORECASE),
    re.compile(r"^\s*(?:page\s*\d+|section\s*\d+(?:\.\d+)*)\s*$", re.IGNORECASE),
    re.compile(r"^\s*\w+\s*(?:is|lacks|undefined|vague|not defined|lacks explanation|lacks context)\s*$", re.IGNORECASE),
]


class FindingRelevanceFilter:
    """
    Filtering, scoring, and consolidation engine for Context Analysis & Executive Reports.
    """

    def __init__(self, min_confidence: float = 0.70, max_findings: int = 10, min_findings: int = 4):
        self.min_confidence = min_confidence
        self.max_findings = max_findings
        self.min_findings = min_findings

    def is_suppressed(self, quote: str, title: str = "", explanation: str = "") -> bool:
        """
        Determines if a finding is low-value noise (e.g. section header, contact info, standalone company name).
        """
        q_clean = quote.strip().upper()
        t_clean = title.strip().upper()
        e_clean = explanation.strip().lower()

        # Check exact pattern suppression list
        if q_clean in SUPPRESSED_EXACT_PATTERNS or t_clean in SUPPRESSED_EXACT_PATTERNS:
            return True

        # Do not suppress evidence quotes for explicit deterministic mismatches, broken references, or numeric conflicts
        if any(term in e_clean or term in t_clean for term in ["numeric", "mismatch", "broken", "reference", "page reference", "section reference", "parentheses"]):
            return False

        # Suppress single/double-word quotes without context (< 20 chars)
        if len(quote.strip()) <= 20 and not re.search(r"\b(?:is|are|was|were|has|have|will|must|should|cannot)\b", quote, re.IGNORECASE):
            return True

        # Suppress specific low-value "X is vague / undefined" noise on short terms
        if re.search(r"\b(?:is ambiguous|is vague|lacks context|is undefined|lacks explanation)\b", e_clean):
            for term in ["company profile", "headquarters", "contact", "industry", "larsen & toubro", "l&t", "website", "email", "address"]:
                if term in q_clean.lower() or term in t_clean.lower():
                    return True

        # Check regex suppressions
        for pattern in SUPPRESSED_REGEXES:
            if pattern.search(quote) or pattern.search(title):
                return True

        return False

    def normalize_category(self, raw_category: str) -> str:
        """Maps any legacy or raw category into one of the 15 standard business taxonomy categories."""
        if raw_category in TAXONOMY_CATEGORIES:
            return raw_category
        return CATEGORY_MAPPINGS.get(raw_category, "Business Consistency")

    def calculate_severity(
        self,
        category: str,
        confidence: float,
        explanation: str = "",
        impact: str = "",
        occurrence_count: int = 1
    ) -> str:
        """
        Calculates business severity (Critical, High, Medium, Low, Informational) based on business risk.
        """
        text_block = (explanation + " " + impact).lower()

        # Critical: Severe compliance violation, legal liability, or major financial contradiction
        if any(w in text_block for w in ["regulatory audit failure", "legal liability", "contract breach", "certification halt", "penalty"]):
            return "Critical"
        if category in ("Regulatory Risk", "Compliance Risk") and occurrence_count > 1:
            return "Critical"

        # High: Numerical mismatches, contradictory policy/strategy statements, strategic risk
        if category in ("Contradictory Statements", "Numerical Consistency", "Strategic Risk") or any(w in text_block for w in ["financial mismatch", "contradiction", "discrepancy", "unauthorized"]):
            return "High"

        # Medium: Operational ambiguity, cross-reference gaps, missing evidence
        if category in ("Operational Ambiguity", "Cross-Reference Mismatch", "Missing Evidence", "Market Positioning Conflict", "Incomplete Information"):
            return "Medium"

        # Low: Acronym definition, data quality, duplicate information
        if category in ("Acronym Definition", "Data Quality", "Duplicate Information", "Document Structure"):
            return "Low"

        if confidence < 0.75:
            return "Informational"

        return "Medium"

    def filter_and_consolidate(self, raw_findings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Executes Parts 1-5 to filter out noise, enforce confidence thresholds,
        score severity, and consolidate findings into a high-signal list of 4-10 items.
        """
        valid_findings = []

        for f in raw_findings:
            quote = f.get("quote") or f.get("highlighted_ambiguity") or f.get("suspected_text") or f.get("original_text") or ""
            title = f.get("title", "")
            explanation = f.get("claude_explanation") or f.get("reason") or f.get("explanation") or ""
            confidence = float(f.get("confidence") or 0.85)

            # Part 2: Confidence Threshold Check
            if confidence < self.min_confidence:
                logger.debug(f"[FILTER] Dropping low-confidence finding ({confidence} < {self.min_confidence}): {title}")
                continue

            # Part 1: Suppression Filter
            if self.is_suppressed(quote, title, explanation):
                logger.debug(f"[FILTER] Suppressing low-value finding: '{quote}' | {title}")
                continue

            # Part 5: Taxonomy Normalization
            raw_cat = f.get("category") or f.get("type") or f.get("business_category") or "Business Consistency"
            category = self.normalize_category(raw_cat)
            f["category"] = category

            # Part 3: Severity Calculation
            occurrence_count = int(f.get("occurrence_count") or 1)
            impact = f.get("business_impact") or ""
            f["severity"] = self.calculate_severity(category, confidence, explanation, impact, occurrence_count)

            valid_findings.append(f)

        # Part 4: Consolidate Similar / Repetitive Findings
        consolidated_map = {}
        for f in valid_findings:
            cat = f["category"]
            title = f.get("title", "").strip()
            # Topic key based on category + main subject
            topic_match = re.search(r"\b([A-Za-z0-9\-]{4,})\b", title)
            topic_stem = topic_match.group(1).lower() if topic_match else title[:20].lower()
            group_key = (cat, topic_stem)

            if group_key not in consolidated_map:
                consolidated_map[group_key] = f
            else:
                existing = consolidated_map[group_key]
                # Merge evidence & update count
                existing["occurrence_count"] = int(existing.get("occurrence_count", 1)) + 1
                sev_order = {"Critical": 4, "High": 3, "Medium": 2, "Low": 1, "Informational": 0}
                if sev_order.get(f["severity"], 0) > sev_order.get(existing["severity"], 0):
                    existing["severity"] = f["severity"]

        result = list(consolidated_map.values())

        # Part 13: Cap finding count to target (4-10 meaningful findings)
        if len(result) > self.max_findings:
            # Sort by severity priority: Critical -> High -> Medium -> Low -> Informational
            sev_rank = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3, "Informational": 4}
            result.sort(key=lambda item: sev_rank.get(item.get("severity", "Medium"), 2))
            result = result[: self.max_findings]

        return result
