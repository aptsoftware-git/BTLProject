from __future__ import annotations

import re
from typing import List, Any
from src.comparative_analysis.models import CompanyProfile
from src.comparative_analysis.utils.company_name_normalizer import normalize_company_name

RAW_NOISE_PATTERNS = [
    r"^(?:Document\s+Section|Section|Chapter|Root\s+Content)\s*[:\-]?\s*",
    r"^(?:Table\s+of\s+Contents|Contents|Annual\s+Report|Corporate\s+Overview)\s*[:\-]?\s*",
    r"^\d+[\.\)]\s*",
    r"```(?:json)?",
    r"```"
]


def clean_text_string(text: str) -> str:
    """
    Sanitizes raw text strings by stripping section headers, OCR artifacts,
    markdown symbols, broken unicode, and collapsing redundant whitespace.
    """
    if not text or not isinstance(text, str):
        return ""

    cleaned = text
    for pat in RAW_NOISE_PATTERNS:
        cleaned = re.sub(pat, "", cleaned, flags=re.IGNORECASE).strip()

    # Remove markdown bold/italics markers
    cleaned = re.sub(r"[\*\_~`#]", "", cleaned)

    # Collapse multiple spaces and newlines
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    return cleaned


def clean_text_list(items: Any, fallback_item: str = "Not specified") -> List[str]:
    """
    Cleans a list of text strings, filtering out section headers, noise strings,
    and duplicate entries.
    """
    if not items or not isinstance(items, list):
        if isinstance(items, str) and items and items != "Not specified":
            c = clean_text_string(items)
            if c and not c.lower().startswith("document section"):
                return [c]
        return [fallback_item] if fallback_item else []

    cleaned_items: List[str] = []
    seen = set()

    for item in items:
        if not item:
            continue
        c = clean_text_string(str(item))
        if not c or len(c) < 3:
            continue
        c_lower = c.lower()
        if c_lower.startswith("document section") or c_lower in {"contents", "annual report", "corporate overview"}:
            continue
        if c_lower not in seen:
            seen.add(c_lower)
            cleaned_items.append(c)

    return cleaned_items if cleaned_items else ([fallback_item] if fallback_item else [])


def clean_company_profile(profile: CompanyProfile) -> CompanyProfile:
    """
    Centralized cleaning layer for CompanyProfile.
    Sanitizes all 17 fields, normalizes the legal company name, and ensures
    clean executive business language.
    """
    if not profile:
        return profile

    profile.company_name = normalize_company_name(profile.company_name)
    profile.company_description = clean_text_string(profile.company_description)
    profile.executive_summary = clean_text_string(profile.executive_summary)
    profile.primary_industry = clean_text_string(profile.primary_industry)

    profile.secondary_industries = clean_text_list(profile.secondary_industries, profile.primary_industry)
    profile.core_services = clean_text_list(profile.core_services, f"{profile.primary_industry} Services")
    profile.products = clean_text_list(profile.products, f"{profile.primary_industry} Solutions")
    profile.business_domains = clean_text_list(profile.business_domains, profile.primary_industry)
    profile.major_projects = clean_text_list(profile.major_projects, "Turnkey Contracts")
    profile.technologies = clean_text_list(profile.technologies, "Engineering Systems")
    profile.geographic_presence = clean_text_list(profile.geographic_presence, "Global")
    profile.target_industries = clean_text_list(profile.target_industries, profile.primary_industry)
    profile.key_clients = clean_text_list(profile.key_clients, "Industrial Clients")
    profile.business_strengths = clean_text_list(profile.business_strengths, f"Established domain expertise in {profile.primary_industry}")
    profile.competitive_advantages = clean_text_list(profile.competitive_advantages, "Proprietary solution capabilities")
    profile.keywords = clean_text_list(profile.keywords, profile.primary_industry)
    profile.certifications = clean_text_list(profile.certifications, "ISO / Industry Compliance")

    return profile
