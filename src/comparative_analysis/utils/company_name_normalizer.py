from __future__ import annotations

import re

# Words that should never be used as company names
FORBIDDEN_NAME_PATTERNS = {
    "annual report", "brochure", "contents", "corporate overview", "table of contents",
    "document title", "executive summary", "overview", "handbook", "guide", "manual",
    "profile", "financial report", "statement", "index"
}

def normalize_company_name(raw_name: str) -> str:
    """
    Normalizes corporate names to clean, legal formatting.
    Fixes reversed orders like 'LTD BTL EPC' -> 'BTL EPC Limited',
    and standardizes suffixes ('Private Limited' -> 'Pvt. Ltd.', 'LIMITED' -> 'Limited').
    """
    if not raw_name or not isinstance(raw_name, str):
        return "Target Company"

    # Remove section header noise
    cleaned = re.sub(r"^(?:Document\s+Section|Section|Chapter|Root\s+Content)\s*[:\-]?\s*", "", raw_name, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"^\d+[\.\)]\s*", "", cleaned).strip()
    cleaned = re.sub(r"[^\w\s&.\-]", "", cleaned).strip()

    if not cleaned or cleaned.lower() in FORBIDDEN_NAME_PATTERNS:
        return "Target Company"

    # Fix reversed prefix/suffix order like "LTD BTL EPC" or "LIMITED BTL EPC"
    reversed_match = re.match(r"^(LTD|LIMITED|PVT|PRIVATE|INC|CORP)\s+(.+)$", cleaned, re.IGNORECASE)
    if reversed_match:
        suffix_part = reversed_match.group(1).upper()
        main_part = reversed_match.group(2).strip()

        if suffix_part in ["LTD", "LIMITED"]:
            cleaned = f"{main_part} Limited"
        elif suffix_part in ["PVT", "PRIVATE"]:
            cleaned = f"{main_part} Pvt. Ltd."
        else:
            cleaned = f"{main_part} {suffix_part.capitalize()}"

    # Normalize standard suffixes
    cleaned = re.sub(r"\bPRIVATE\s+LIMITED\b", "Pvt. Ltd.", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bPVT\s+LTD\b\.?", "Pvt. Ltd.", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bLIMITED\b", "Limited", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bLTD\b\.?", "Limited", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bINCORPORATED\b", "Inc.", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bCORPORATION\b", "Corp.", cleaned, flags=re.IGNORECASE)

    # Format title casing for corporate names (e.g. BTL EPC Limited)
    words = cleaned.split()
    formatted_words = []

    for w in words:
        w_upper = w.upper()
        # Preserve acronyms like BTL, EPC, AI, IT, LLM, OCR, BHEL, ISGEC, L&T
        if w_upper in {"BTL", "EPC", "AI", "IT", "LLM", "OCR", "BHEL", "ISGEC", "PWC", "EY", "KPMG", "BCG", "L&T", "USA", "UK", "UAE"}:
            formatted_words.append(w_upper)
        elif w in {"Pvt.", "Ltd.", "Inc.", "Corp."}:
            formatted_words.append(w)
        else:
            formatted_words.append(w.capitalize())

    final_name = " ".join(formatted_words)

    # Final sanity check against forbidden phrases
    if final_name.lower() in FORBIDDEN_NAME_PATTERNS or len(final_name) < 2:
        return "Target Company"

    return final_name
