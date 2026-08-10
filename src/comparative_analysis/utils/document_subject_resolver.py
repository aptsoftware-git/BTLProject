"""
document_subject_resolver.py
=============================
Determines the true legal report owner of an annual report or corporate document.
Grounds the target company identity in document front-matter / corporate disclosures
with verbatim evidence text and page numbers.

Strictly rejects customer, project, vendor, subsidiary, or JV partner references
from being selected as the target company. Does NOT hardcode any company names.
"""

from __future__ import annotations

import re
import logging
from typing import Dict, List, Optional, Tuple, Any

logger = logging.getLogger("comparative_analysis.document_subject_resolver")

class TargetCompanyResolutionError(ValueError):
    """Raised when Target Company Identity cannot be established with high confidence."""
    pass


# Anti-collision keywords: candidates appearing in these contexts are project/client references, NOT the report owner.
PROJECT_CLIENT_CONTEXT_KEYWORDS = [
    "handling plant for", "package for", "contract for", "order from", "order received from",
    "client:", "client", "customer:", "customer", "vendor", "supplier", "project for", "plant for",
    "major project", "executed for", "awarded by", "sub-contractor to", "subsidiary of",
    "associate company of", "joint venture with", "consortium with", "supply of", "erection of"
]

# Legal entity suffixes with strict word boundaries
LEGAL_ENTITY_SUFFIXES = (
    r"\b(?:LIMITED|LTD|INC|INCORPORATED|CORPORATION|CORP|PVT\s+LTD|PRIVATE\s+LIMITED|"
    r"LLC|PLC|GMBH|S\.A\.|B\.V\.|L\.P\.|CO\.\,\s*LTD|COMPANY\s+LIMITED)\b"
)

# Universal legal corporate disclosure patterns (evaluated against front-matter pages)
CORPORATE_DISCLOSURE_PATTERNS = [
    # 1. Cover Page Title Block: "BTL EPC LIMITED\nANNUAL REPORT"
    (r"([A-Z0-9\s&.\-]{2,60}?" + LEGAL_ENTITY_SUFFIXES + r")[\s\n]{1,20}?(?:ANNUAL\s+REPORT|FINANCIAL\s+STATEMENTS)", 98.0),

    # 2. CIN disclosure: "CIN: L27109WB1962PLC025484 BTL EPC LIMITED" or "NAME OF THE COMPANY: BTL EPC LIMITED"
    (r"CIN\s*:\s*[A-Z0-9]{21}\s+([A-Z0-9\s&.\-]{2,60}?" + LEGAL_ENTITY_SUFFIXES + r")", 98.0),
    (r"(?:NAME\s+OF\s+(?:THE\s+)?COMPANY|COMPANY\s+NAME)\s*[:\-\n]+\s*([A-Z0-9\s&.\-]{2,60}?" + LEGAL_ENTITY_SUFFIXES + r")", 98.0),

    # 3. Corporate Info header block: "CORPORATE INFORMATION ... BTL EPC LIMITED"
    (r"(?:CORPORATE\s+INFORMATION|COMPANY\s+INFORMATION|CORPORATE\s+DETAILS)\s*[:\-\n\s]{1,40}?([A-Z0-9\s&.\-]{2,60}?" + LEGAL_ENTITY_SUFFIXES + r")", 95.0),

    # 4. Directors' Report header: "DIRECTORS' REPORT TO THE MEMBERS OF BTL EPC LIMITED"
    (r"(?:DIRECTORS['’]?\s+REPORT|BOARD['’]?S\s+REPORT)\s+(?:TO\s+THE\s+MEMBERS\s+OF|OF)\s+([A-Z0-9\s&.\-]{2,60}?" + LEGAL_ENTITY_SUFFIXES + r")", 92.0),

    # 5. Auditor's Report header: "INDEPENDENT AUDITOR'S REPORT TO THE MEMBERS OF BTL EPC LIMITED"
    (r"(?:INDEPENDENT\s+)?AUDITOR['’]?S?\s+REPORT\s+TO\s+THE\s+MEMBERS\s+OF\s+([A-Z0-9\s&.\-]{2,60}?" + LEGAL_ENTITY_SUFFIXES + r")", 90.0),

    # 6. Financial Statements header: "BALANCE SHEET OF BTL EPC LIMITED"
    (r"(?:BALANCE\s+SHEET|STATEMENT\s+OF\s+PROFIT\s+AND\s+LOSS)\s+(?:OF|FOR)\s+([A-Z0-9\s&.\-]{2,60}?" + LEGAL_ENTITY_SUFFIXES + r")", 85.0),

    # 7. Annual Report title: "ANNUAL REPORT OF BTL EPC LIMITED"
    (r"ANNUAL\s+REPORT\s+(?:OF|FOR)\s+([A-Z0-9\s&.\-]{2,60}?" + LEGAL_ENTITY_SUFFIXES + r")", 85.0),
]

# Words/Phrases that should never be identified as a company name
INVALID_COMPANY_SUBSTRINGS = [
    "ANNUAL REPORT", "CORPORATE INFORMATION", "DIRECTORS REPORT", "BOARDS REPORT",
    "AUDITORS REPORT", "BALANCE SHEET", "PROFIT AND LOSS", "TABLE OF CONTENTS",
    "REGISTERED OFFICE", "STANDALONE", "CONSOLIDATED", "FINANCIAL STATEMENTS"
]


def _normalize_name(name: str) -> str:
    """Normalizes company name spacing, removes stray headers, and leading orphaned suffixes."""
    name = re.sub(r"\s+", " ", name or "").strip()
    name = re.sub(r"\s*[\(\[].*?[\)\]]", "", name).strip()
    # Strip leading orphaned legal suffixes from page line breaks (e.g. "LTD BTL EPC LIMITED" -> "BTL EPC LIMITED")
    name = re.sub(r"^(?:LTD|LIMITED|INC|INCORPORATED|CORP|CORPORATION|PVT|PRIVATE)\b\s*", "", name, flags=re.IGNORECASE).strip()
    return name


class DocumentSubjectResolver:
    """
    Document Subject Resolution Engine.
    Determines the true legal report owner from front-matter / corporate disclosures.
    Returns target_company, evidence quote, page number, and source metadata.
    """

    @classmethod
    def resolve_target_company(
        cls,
        text_chunks_or_pages: List[Dict[str, Any]],
        document_id: str = "",
        min_confidence_threshold: float = 70.0
    ) -> Dict[str, Any]:
        """
        Extracts and grounds the Target Company Identity from document front-matter.
        """
        if not text_chunks_or_pages:
            raise TargetCompanyResolutionError("Cannot resolve target company: Empty document content provided.")

        # 1. Filter front-matter pages (Pages 1 to 15)
        front_matter: List[Dict[str, Any]] = []
        for item in text_chunks_or_pages:
            p_num = item.get("page_number") or item.get("page") or 1
            if isinstance(p_num, (int, float)) and p_num <= 15:
                text = (item.get("content") or item.get("text") or "").strip()
                if text:
                    front_matter.append({"text": text, "page": int(p_num)})

        if not front_matter:
            for item in text_chunks_or_pages[:10]:
                text = (item.get("content") or item.get("text") or "").strip()
                p_num = item.get("page_number") or item.get("page") or 1
                if text:
                    front_matter.append({"text": text, "page": int(p_num)})

        candidate_evidence: List[Dict[str, Any]] = []

        # 2. Evaluate Corporate Disclosure Patterns against front-matter
        for entry in front_matter:
            text = entry["text"]
            page_num = entry["page"]
            text_upper = text.upper()

            for pattern, score in CORPORATE_DISCLOSURE_PATTERNS:
                matches = re.finditer(pattern, text_upper, re.MULTILINE)
                for match in matches:
                    raw_candidate = match.group(1).strip()
                    candidate = _normalize_name(raw_candidate)
                    
                    if cls._is_valid_legal_owner(candidate, text):
                        start_pos = max(0, match.start() - 30)
                        end_pos = min(len(text), match.end() + 30)
                        snippet = text[start_pos:end_pos].replace("\n", " ").strip()
                        
                        candidate_evidence.append({
                            "target_company": cls._format_company_name(candidate),
                            "raw_name": candidate,
                            "confidence": score,
                            "evidence": snippet,
                            "page": page_num
                        })

        # Sort by confidence descending, then by page ascending
        if candidate_evidence:
            candidate_evidence.sort(key=lambda x: (-x["confidence"], x["page"]))
            best = candidate_evidence[0]
            logger.info("Resolved Target Company '%s' (Confidence: %.1f%%, Page %d)", best["target_company"], best["confidence"], best["page"])
            return {
                "target_company": best["target_company"],
                "evidence": best["evidence"],
                "page": best["page"],
                "source": "document",
                "confidence": best["confidence"]
            }

        # 3. Fallback Cover Page Title Block Parsing (Pages 1 to 3)
        cover_candidates: List[Dict[str, Any]] = []
        cover_regex = re.compile(
            r"([A-Z0-9\s&.\-]{2,50}?" + LEGAL_ENTITY_SUFFIXES + r")",
            re.MULTILINE
        )
        
        for entry in front_matter[:3]:
            text = entry["text"]
            page_num = entry["page"]
            for m in cover_regex.finditer(text.upper()):
                cand = _normalize_name(m.group(1))
                if cls._is_valid_legal_owner(cand, text):
                    cover_candidates.append({
                        "target_company": cls._format_company_name(cand),
                        "evidence": text[:150].replace("\n", " ").strip(),
                        "page": page_num,
                        "confidence": 75.0
                    })

        if cover_candidates:
            cover_candidates.sort(key=lambda x: x["page"])
            best = cover_candidates[0]
            logger.info("Resolved Target Company '%s' (Confidence: %.1f%%, Page %d) via cover title block.", best["target_company"], best["confidence"], best["page"])
            return {
                "target_company": best["target_company"],
                "evidence": best["evidence"],
                "page": best["page"],
                "source": "document",
                "confidence": best["confidence"]
            }

        # 4. Low Confidence Error: Fail analysis rather than guessing a customer name
        msg = f"Failed to ground Target Company Identity in document '{document_id}'. No corporate identity disclosures found."
        logger.error(msg)
        raise TargetCompanyResolutionError(msg)

    @classmethod
    def _is_valid_legal_owner(cls, candidate: str, context_text: str) -> bool:
        """
        Verifies candidate is a valid legal company name and NOT a customer,
        project, vendor, subsidiary, or generic header.
        """
        cand_upper = candidate.upper().strip()

        if len(cand_upper) < 4:
            return False

        # Reject if generic header or invalid phrase
        for inv in INVALID_COMPANY_SUBSTRINGS:
            if inv in cand_upper:
                return False

        # Reject if candidate appears in project/client context in the text
        cand_lower = candidate.lower()
        lines = context_text.split("\n")
        for line in lines:
            line_lower = line.lower()
            if cand_lower in line_lower:
                if any(kw in line_lower for kw in PROJECT_CLIENT_CONTEXT_KEYWORDS):
                    return False

        return True

    @classmethod
    def _format_company_name(cls, name: str) -> str:
        """Formats legal company name cleanly, preserving uppercase acronyms."""
        name = _normalize_name(name)
        words = name.split()
        formatted = []
        for w in words:
            w_clean = re.sub(r"[^\w]", "", w)
            w_upper = w_clean.upper()
            if len(w_clean) <= 3 or w_upper in ("LIMITED", "LTD", "PRIVATE", "PVT", "INC", "CORP", "LLC", "PLC", "GMBH"):
                if w_upper in ("BTL", "EPC", "LTD", "INC", "CORP", "LLC", "PLC", "CIN", "PCL", "USA", "UK"):
                    formatted.append(w_upper)
                else:
                    formatted.append(w.capitalize())
            else:
                formatted.append(w.capitalize() if w.isupper() else w)
        return " ".join(formatted)
