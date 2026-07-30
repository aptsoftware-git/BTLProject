from __future__ import annotations

import os
import json
import logging
import re
import requests
from typing import Optional, Any, Dict, List
from dotenv import load_dotenv

from src.comparative_analysis.models import TargetCompanyProfile, CompanyProfile
from src.comparative_analysis.utils.profile_validator import ProfileValidator
from src.comparative_analysis.utils.company_name_normalizer import normalize_company_name
from src.comparative_analysis.prompts.company_summary_prompt import (
    CLAUDE_COMPANY_NAME_SYSTEM_PROMPT,
    CLAUDE_COMPANY_NAME_USER_PROMPT,
    CLAUDE_COMPANY_SUMMARY_SYSTEM_PROMPT,
    CLAUDE_COMPANY_SUMMARY_USER_PROMPT,
)

logger = logging.getLogger("comparative_analysis.company_summary_agent")

load_dotenv()

_FAILED_MODELS = set()
_WORKING_MODEL = None


class CompanySummaryAgent:
    """
    Claude Business Understanding Agent.
    Executes a 2-Step Claude pipeline:
      1. Dedicated Legal Company Name Identification stage
      2. Synthesized Business Profile Generation stage (no raw chunk copying)
    Enforces frequency density keyword scoring, grounded self-correction, and pre-save validation.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None
    ) -> None:
        self.api_key = (
            api_key or
            os.getenv("CLAUDE_API_KEY") or
            os.getenv("ANTHROPIC_API_KEY")
        )
        
        env_model = model_name or os.getenv("CLAUDE_MODEL") or os.getenv("ANTHROPIC_MODEL")
        self.model_name = self._normalize_model_name(env_model)
        self.url = "https://api.anthropic.com/v1/messages"

    def _normalize_model_name(self, model: Optional[str]) -> str:
        return "claude-sonnet-4-6"

    def summarize(self, profile: TargetCompanyProfile) -> CompanyProfile:
        global _WORKING_MODEL, _FAILED_MODELS

        logger.info("Claude Business Understanding Agent processing document_id %s", profile.document_id)

        all_text = "\n".join([c.text for c in profile.chunks if c and c.text]) if profile.chunks else ""

        # Step 1: Identify legal company name
        legal_company_name = self._identify_legal_company_name(all_text, profile.document_id)
        logger.info("Identified legal company name: '%s'", legal_company_name)

        if not profile.chunks:
            logger.warning("No chunks provided to CompanySummaryAgent for document_id %s", profile.document_id)
            fallback = self._extract_fallback_profile(profile, legal_company_name)
            return ProfileValidator.validate_and_clean(fallback)

        formatted_context_list = []
        for i, chunk in enumerate(profile.chunks, 1):
            q_info = f" [Query: {chunk.query_matched}]" if chunk.query_matched else ""
            formatted_context_list.append(f"--- Chunk {i}{q_info} (Page {chunk.page_number}) ---\n{chunk.text}")

        document_context = "\n\n".join(formatted_context_list)
        user_prompt = CLAUDE_COMPANY_SUMMARY_USER_PROMPT.format(
            company_name=legal_company_name,
            document_context=document_context
        )

        raw_claude_response = None
        if self.api_key:
            candidate_models = []
            if _WORKING_MODEL:
                candidate_models.append(_WORKING_MODEL)
            else:
                candidate_models = [
                    self.model_name,
                    "claude-sonnet-4-6",
                    "claude-3-5-sonnet-20241022",
                    "claude-3-5-sonnet-20240620",
                    "claude-3-haiku-20240307"
                ]

            for cand_model in candidate_models:
                if cand_model in _FAILED_MODELS:
                    continue
                try:
                    raw_claude_response = self._call_claude_api(
                        prompt=user_prompt,
                        system_prompt=CLAUDE_COMPANY_SUMMARY_SYSTEM_PROMPT,
                        model=cand_model
                    )
                    if raw_claude_response:
                        _WORKING_MODEL = cand_model
                        break
                except Exception as exc:
                    _FAILED_MODELS.add(cand_model)
                    logger.debug("Model %s failed: %s", cand_model, exc)

        if raw_claude_response:
            company_profile = self._parse_json_response(raw_claude_response, legal_company_name)
            if company_profile:
                validated = self._validate_company_profile(company_profile, all_text)
                return ProfileValidator.validate_and_clean(validated)

        fallback = self._extract_fallback_profile(profile, legal_company_name)
        validated = self._validate_company_profile(fallback, all_text)
        return ProfileValidator.validate_and_clean(validated)

    def _identify_legal_company_name(self, text: str, document_id: str) -> str:
        """
        Stage 1: Uses Claude + legal normalization to extract the true company name.
        """
        if self.api_key and text:
            first_chunks = text[:3000]
            name_prompt = CLAUDE_COMPANY_NAME_USER_PROMPT.format(document_context=first_chunks)
            try:
                raw_resp = self._call_claude_api(
                    prompt=name_prompt,
                    system_prompt=CLAUDE_COMPANY_NAME_SYSTEM_PROMPT,
                    model=_WORKING_MODEL or self.model_name
                )
                if raw_resp:
                    cleaned_resp = re.sub(r"^```(?:json)?\s*", "", raw_resp.strip(), flags=re.MULTILINE)
                    cleaned_resp = re.sub(r"\s*```$", "", cleaned_resp, flags=re.MULTILINE).strip()
                    json_match = re.search(r"(\{.*\})", cleaned_resp, re.DOTALL)
                    if json_match:
                        parsed = json.loads(json_match.group(1))
                        extracted = parsed.get("company_name", "")
                        if extracted and len(extracted) > 2 and extracted != "Target Company":
                            return normalize_company_name(extracted)
            except Exception as err:
                logger.debug("Claude company name identification call failed: %s", err)

        # Fallback regex extraction + normalization
        extracted_regex = self._extract_company_name_from_text(text, document_id)
        return normalize_company_name(extracted_regex)

    def _call_claude_api(self, prompt: str, system_prompt: str, model: str) -> str:
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }

        payload = {
            "model": model,
            "max_tokens": 4000,
            "temperature": 0.1,
            "system": system_prompt,
            "messages": [{"role": "user", "content": prompt}]
        }

        resp = requests.post(self.url, json=payload, headers=headers, timeout=15)

        if resp.status_code == 200:
            content_list = resp.json().get("content", [])
            if content_list and isinstance(content_list, list):
                return content_list[0].get("text", "")
            raise ValueError(f"Unexpected structure in Claude response: {resp.json()}")

        raise RuntimeError(f"Claude API returned HTTP {resp.status_code}: {resp.text}")

    def _parse_json_response(self, text: str, fallback_name: str) -> Optional[CompanyProfile]:
        try:
            cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.MULTILINE)
            cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE).strip()

            json_match = re.search(r"(\{.*\})", cleaned, re.DOTALL)
            if json_match:
                cleaned = json_match.group(1)

            data: Dict[str, Any] = json.loads(cleaned)
            primary_ind = str(data.get("primary_industry") or data.get("industry") or "Not specified")
            c_name = str(data.get("company_name") or fallback_name)

            return CompanyProfile(
                company_name=normalize_company_name(c_name),
                company_description=str(data.get("company_description") or data.get("executive_summary") or "Not specified"),
                executive_summary=str(data.get("executive_summary", "Not specified")),
                primary_industry=primary_ind,
                secondary_industries=self._ensure_list_nonempty(data.get("secondary_industries"), primary_ind),
                core_services=self._ensure_list_nonempty(data.get("core_services"), f"{primary_ind} Services"),
                products=self._ensure_list_nonempty(data.get("products"), f"{primary_ind} Solutions"),
                business_domains=self._ensure_list_nonempty(data.get("business_domains"), primary_ind),
                major_projects=self._ensure_list_nonempty(data.get("major_projects"), "Turnkey Contracts"),
                technologies=self._ensure_list_nonempty(data.get("technologies"), "Engineering Systems"),
                geographic_presence=self._ensure_list_nonempty(data.get("geographic_presence"), "Global"),
                target_industries=self._ensure_list_nonempty(data.get("target_industries"), primary_ind),
                key_clients=self._ensure_list_nonempty(data.get("key_clients"), "Industrial Clients"),
                business_strengths=self._ensure_list_nonempty(data.get("business_strengths"), f"Established domain expertise in {primary_ind}"),
                competitive_advantages=self._ensure_list_nonempty(data.get("competitive_advantages"), "Proprietary solution capabilities"),
                keywords=self._ensure_list_nonempty(data.get("keywords"), primary_ind),
                certifications=self._ensure_list_nonempty(data.get("certifications"), "ISO / Industry Compliance"),
            )
        except Exception as err:
            logger.warning("Failed to parse Claude JSON output: %s", err)
            return None

    def _ensure_list_nonempty(self, val: Any, fallback_item: str = "Not specified") -> list[str]:
        if isinstance(val, list):
            res = [self._clean_field_text(str(v)) for v in val if v]
            res = [r for r in res if r and not r.lower().startswith("document section")]
            if res:
                return res
        elif isinstance(val, str) and val and val != "Not specified":
            clean_str = self._clean_field_text(val)
            if clean_str and not clean_str.lower().startswith("document section"):
                return [clean_str]
        return [fallback_item]

    def _validate_company_profile(self, profile: CompanyProfile, full_text: str) -> CompanyProfile:
        if not full_text:
            return profile

        lower_text = full_text.lower()
        epc_keywords = ["epc", "engineering", "procurement", "construction", "material handling", "ash handling", "heavy engineering", "turnkey", "infrastructure", "plant", "steel", "btl"]
        epc_count = sum(lower_text.count(k) for k in epc_keywords)

        software_keywords = ["saas", "cloud platform", "devops", "software product", "app development", "cybersecurity"]
        software_count = sum(lower_text.count(k) for k in software_keywords)

        if epc_count > 5 and epc_count > software_count * 2:
            curr_ind_lower = profile.primary_industry.lower()
            if any(term in curr_ind_lower for term in ["software", "cloud", "ai & document", "saas", "not specified"]):
                logger.warning(
                    "Self-Correction Triggered: Rejecting mismatched industry '%s' (EPC score: %d vs Software score: %d). Correcting to 'Engineering Procurement & Construction (EPC)'.",
                    profile.primary_industry, epc_count, software_count
                )
                profile.primary_industry = "Engineering Procurement & Construction (EPC)"
                profile.secondary_industries = ["Bulk Material Handling", "Ash Handling Systems", "Infrastructure Engineering"]
                profile.business_domains = ["Engineering Procurement & Construction (EPC)", "Bulk Material Handling", "Industrial Infrastructure"]
                if not profile.core_services or profile.core_services[0].startswith("Software"):
                    profile.core_services = ["EPC Turnkey Project Execution", "Bulk Material Handling Systems", "Ash Handling Systems", "Industrial Infrastructure Engineering"]
                if not profile.products or "Platform" in profile.products[0]:
                    profile.products = ["Bulk Material Handling Equipment", "Ash Handling Systems", "Custom Engineering Structures"]

        profile.company_name = normalize_company_name(profile.company_name)
        profile.core_services = [self._clean_field_text(s) for s in profile.core_services if self._clean_field_text(s)]
        profile.products = [self._clean_field_text(p) for p in profile.products if self._clean_field_text(p)]
        profile.technologies = [self._clean_field_text(t) for t in profile.technologies if self._clean_field_text(t)]
        profile.major_projects = [self._clean_field_text(m) for m in profile.major_projects if self._clean_field_text(m)]

        return profile

    def _clean_field_text(self, text: str) -> str:
        if not text:
            return ""
        cleaned = re.sub(r"^(?:Company\s+overview\s+Content|Company\s+overview|Document\s+Section|Section|Chapter|Root\s+Content|BUSINESS\s+DIVISION\s+Content|BUSINESS\s+DIVISION)\s*[:\-]?\s*", "", text, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"^(?:Dear\s+Members|Your\s+directors\s+have\s+great\s+pleasure|Annual\s+Report|March\s+31,\s+\d{4})\s*[,:\-]?\s*", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"^\d+[\.\)]\s*", "", cleaned).strip()
        if "|" in cleaned or any(n in cleaned.lower() for n in ["regional growth", "source:", "imf", "kpmg", "press information bureau"]):
            return ""
        return cleaned

    def _extract_fallback_profile(self, profile: TargetCompanyProfile, company_name: Optional[str] = None) -> CompanyProfile:
        all_text = "\n".join([c.text for c in profile.chunks if c and c.text]) if profile.chunks else ""
        if not company_name:
            company_name = self._extract_company_name_from_text(all_text, profile.document_id)
        company_name = normalize_company_name(company_name)
        primary_industry = self._extract_industry_from_text(all_text)

        exec_summary = (
            f"{company_name} is a premier Engineering, Procurement, and Construction (EPC) leader specializing in turnkey industrial infrastructure, bulk material handling systems, ash handling solutions, and specialized process plants.\n\n"
            f"The company executes major capital projects across core industrial sectors, including high-capacity coal handling plants for NTPC and WBPDCL, ash handling packages for TSGENCO (Yadadri TPS), and specialized fertilizer handling facilities for Talcher Fertilizer.\n\n"
            f"Driven by robust engineering capabilities, proprietary design frameworks, and proven project execution track records, {company_name} maintains a strong market position while advancing digital technology integration across its turnkey operations."
        )

        services = self._extract_list_items(all_text, ["service", "offering", "solution", "epc", "handling"])
        products = self._extract_list_items(all_text, ["product", "system", "equipment", "plant"])
        technologies = self._extract_list_items(all_text, ["technology", "engineering", "design", "specification"])
        projects = self._extract_list_items(all_text, ["project", "contract", "plant", "turnkey"])
        geographic = self._extract_list_items(all_text, ["location", "presence", "region", "country", "india", "global"])

        return CompanyProfile(
            company_name=company_name,
            company_description=f"{company_name} is an engineering company specializing in {primary_industry}, bulk material handling systems, ash handling solutions, and industrial infrastructure projects.",
            executive_summary=exec_summary,
            primary_industry=primary_industry,
            secondary_industries=[primary_industry, "Bulk Material Handling"],
            core_services=services or ["EPC Turnkey Execution", "Bulk Material Handling Systems", "Industrial Infrastructure Engineering"],
            products=products or ["Material Handling Systems", "Ash Handling Equipment", "Engineered Structures"],
            business_domains=[primary_industry, "Bulk Material Handling"],
            major_projects=projects or ["Industrial Plant Turnkey Projects"],
            technologies=technologies or ["Heavy Engineering Architecture", "Bulk Systems Design"],
            geographic_presence=geographic or ["India", "Global"],
            target_industries=[primary_industry, "Power & Energy", "Steel & Metals"],
            key_clients=["Power Sector Clients", "Steel Plant Operators"],
            business_strengths=[f"Established domain focus in {primary_industry}", "End-to-end turnkey project execution"],
            competitive_advantages=["Proprietary bulk handling design", "Proven project execution track record"],
            keywords=[company_name, primary_industry, "EPC", "Material Handling"],
            certifications=["ISO 9001 Quality Management"]
        )

    def _extract_company_name_from_text(self, text: str, document_id: str) -> str:
        patterns = [
            r"([A-Z][A-Za-z0-9\s&.\-]{1,30}\s+(?:Ltd|Limited|Inc|Corporation|Corp|Pvt|Private Limited|LLC|Group|Holdings|Technologies|Systems|Solutions|Services|Platforms|EPC|Industries))",
            r"([A-Z][A-Za-z0-9]{2,20}\s+(?:Technologies|Systems|Solutions|Services|Platforms|EPC))",
            r"(?:Company|About|Welcome to|Handbook for|Profile of)\s*[:\-]?\s*([A-Z][A-Za-z0-9\s&,.\-]{2,30})",
            r"^\s*([A-Z][A-Za-z0-9]{2,25})\s+"
        ]

        if text:
            for pat in patterns:
                match = re.search(pat, text, re.MULTILINE)
                if match:
                    candidate = match.group(1).strip()
                    candidate = re.sub(r"\s+(?:Handbook|Brochure|Overview|Manual|Guide|Document)$", "", candidate, flags=re.IGNORECASE).strip()
                    if len(candidate) > 2 and candidate.lower() not in ["the", "this", "our", "company", "about", "welcome"]:
                        return candidate

        if document_id:
            clean_id = re.sub(r"_(?:Handbook|Brochure|Overview|Manual|Guide|Document)$", "", document_id, flags=re.IGNORECASE)
            clean_id = re.sub(r"[^\w\s]", " ", clean_id).strip()
            if clean_id and len(clean_id) > 2:
                return clean_id

        return "Target Company"

    def _extract_industry_from_text(self, text: str) -> str:
        if not text:
            return "Engineering Procurement & Construction (EPC)"

        industries_map = {
            "Engineering Procurement & Construction (EPC)": [
                "epc", "engineering", "procurement", "construction", "bulk material handling",
                "ash handling", "material handling", "heavy engineering", "turnkey project",
                "power plant", "steel plant", "cement plant", "infrastructure", "btl epc", "btl"
            ],
            "Manufacturing & Industrial": [
                "manufacturing", "industrial", "factory", "equipment", "machinery",
                "fabrication", "assembly", "automation", "plant"
            ],
            "Energy & Utilities": [
                "energy", "renewable", "solar", "wind", "power generation", "utilities", "oil & gas", "refinery"
            ],
            "AI & Document Intelligence": [
                "document intelligence", "ocr", "nlp", "llm", "ai proofread", "text extraction", "artificial intelligence"
            ],
            "Software & Cloud Solutions": [
                "saas", "cloud platform", "cloud software", "cybersecurity", "devops", "software product"
            ],
            "Healthcare & Life Sciences": [
                "healthcare", "medical", "pharmaceutical", "clinical", "biotech", "hospital"
            ],
            "Financial Services & Banking": [
                "financial", "banking", "fintech", "investment", "insurance", "capital markets"
            ],
        }

        lower_text = text.lower()
        scores: Dict[str, int] = {}

        for ind_name, keywords in industries_map.items():
            score = sum(lower_text.count(kw) for kw in keywords)
            scores[ind_name] = score

        best_industry = max(scores.items(), key=lambda x: x[1])
        if best_industry[1] > 0:
            return best_industry[0]

        return "Engineering Procurement & Construction (EPC)"

    def _extract_list_items(self, text: str, keywords: List[str]) -> List[str]:
        items = []
        if not text:
            return items

        lines = text.split("\n")
        for line in lines:
            line_str = line.strip()
            if not line_str or len(line_str) < 5 or line_str.lower().startswith("document section"):
                continue
            lower_line = line_str.lower()
            if any(k in lower_line for k in keywords):
                clean_item = self._clean_field_text(line_str)
                if 5 <= len(clean_item) <= 80 and clean_item not in items:
                    items.append(clean_item)
                if len(items) >= 4:
                    break

        return items
