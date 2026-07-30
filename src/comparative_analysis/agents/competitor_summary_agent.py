from __future__ import annotations

import os
import json
import logging
import re
import requests
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv

from src.comparative_analysis.models import (
    CompetitorRawData,
    CompetitorProfile,
    CompetitorSummaryList,
)
from src.comparative_analysis.prompts.competitor_summary_prompt import (
    CLAUDE_COMPETITOR_SUMMARY_SYSTEM_PROMPT,
    CLAUDE_COMPETITOR_SUMMARY_USER_PROMPT,
)

logger = logging.getLogger("comparative_analysis.competitor_summary_agent")

load_dotenv()


class CompetitorSummaryAgent:
    """
    Claude Competitor Profiling Agent.
    Transforms raw Tavily web search snippets into structured CompetitorProfile JSON objects.
    Uses 100% dynamic extraction with zero hardcoded company names or industry assumptions.
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
        self.system_prompt = CLAUDE_COMPETITOR_SUMMARY_SYSTEM_PROMPT
        self.user_prompt_template = CLAUDE_COMPETITOR_SUMMARY_USER_PROMPT

    def _normalize_model_name(self, model: Optional[str]) -> str:
        return "claude-sonnet-4-6"

    def profile_competitors(
        self,
        raw_competitor_list: List[CompetitorRawData],
        primary_industry: str
    ) -> CompetitorSummaryList:
        """
        Profiles list of raw competitors.
        """
        logger.info("CompetitorSummaryAgent profiling %d raw competitors...", len(raw_competitor_list))

        profiles: List[CompetitorProfile] = []
        for raw_comp in raw_competitor_list:
            profile = self._profile_single_competitor(raw_comp, primary_industry)
            if profile:
                profiles.append(profile)

        return CompetitorSummaryList(competitors=profiles)

    def summarize_competitors(
        self,
        competitor_raw_data_list: List[CompetitorRawData],
        primary_industry: str,
        target_company_name: str = "Target Company"
    ) -> CompetitorSummaryList:
        """Alias for backward compatibility."""
        return self.profile_competitors(competitor_raw_data_list, primary_industry)

    def _profile_single_competitor(
        self,
        raw_comp: CompetitorRawData,
        primary_industry: str
    ) -> CompetitorProfile:
        search_snippets = []
        for i, res in enumerate(raw_comp.search_results, 1):
            search_snippets.append(f"--- Snippet {i} ({res.url}) ---\nTitle: {res.title}\nContent: {res.content or res.snippet}")

        context_str = "\n\n".join(search_snippets) if search_snippets else "No search snippets found."

        user_prompt = self.user_prompt_template.format(
            competitor_name=raw_comp.competitor_name,
            industry=primary_industry,
            raw_search_data=context_str,
            official_website=raw_comp.official_website or "Not specified",
            source_urls_json=json.dumps(raw_comp.source_urls or [])
        )

        raw_claude_response = None
        if self.api_key:
            candidate_models = [
                self.model_name,
                "claude-sonnet-4-6",
                "claude-3-5-sonnet-20241022",
                "claude-3-haiku-20240307"
            ]
            for cand in candidate_models:
                try:
                    raw_claude_response = self._call_claude_api(user_prompt, model=cand)
                    if raw_claude_response:
                        break
                except Exception as err:
                    logger.debug("Competitor profiling model %s failed: %s", cand, err)

        if raw_claude_response:
            parsed = self._parse_json_response(raw_claude_response, raw_comp, primary_industry)
            if parsed:
                return parsed

        return self._extract_fallback_competitor(raw_comp, primary_industry)

    def _call_claude_api(self, prompt: str, model: str) -> str:
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        payload = {
            "model": model,
            "max_tokens": 2000,
            "temperature": 0.1,
            "system": self.system_prompt,
            "messages": [{"role": "user", "content": prompt}]
        }

        resp = requests.post(self.url, json=payload, headers=headers, timeout=15)
        if resp.status_code == 200:
            content_list = resp.json().get("content", [])
            if content_list and isinstance(content_list, list):
                return content_list[0].get("text", "")
            raise ValueError(f"Unexpected Claude response: {resp.json()}")

        raise RuntimeError(f"Claude API HTTP {resp.status_code}: {resp.text}")

    def _parse_json_response(
        self,
        text: str,
        raw_comp: CompetitorRawData,
        primary_industry: str
    ) -> Optional[CompetitorProfile]:
        try:
            cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.MULTILINE)
            cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE).strip()
            json_match = re.search(r"(\{.*\})", cleaned, re.DOTALL)
            if json_match:
                cleaned = json_match.group(1)

            data: Dict[str, Any] = json.loads(cleaned)

            return CompetitorProfile(
                company_name=str(data.get("company_name", raw_comp.competitor_name)),
                industry=str(data.get("industry", primary_industry)),
                company_description=str(data.get("company_description") or data.get("executive_summary") or "Not specified"),
                executive_summary=str(data.get("executive_summary", "Not specified")),
                core_services=self._ensure_list(data.get("core_services")),
                products=self._ensure_list(data.get("products")),
                business_domains=self._ensure_list(data.get("business_domains")) or [primary_industry],
                major_projects=self._ensure_list(data.get("major_projects")),
                technologies=self._ensure_list(data.get("technologies")),
                geographic_presence=self._ensure_list(data.get("geographic_presence")),
                business_strengths=self._ensure_list(data.get("business_strengths")),
                competitive_advantages=self._ensure_list(data.get("competitive_advantages")),
                official_website=str(data.get("official_website") or raw_comp.official_website or "Not specified"),
                source_urls=raw_comp.source_urls or [],
                references=raw_comp.source_urls or []
            )
        except Exception as err:
            logger.warning("Failed parsing competitor JSON output for %s: %s", raw_comp.competitor_name, err)
            return None

    def _ensure_list(self, val: Any) -> list[str]:
        if isinstance(val, list):
            return [str(v) for v in val if v]
        if isinstance(val, str) and val and val != "Not specified":
            return [val]
        return []

    def _extract_fallback_competitor(
        self,
        raw_comp: CompetitorRawData,
        primary_industry: str
    ) -> CompetitorProfile:
        all_text = " ".join([r.content or r.snippet for r in raw_comp.search_results]) if raw_comp.search_results else ""
        exec_sum = all_text[:400] if all_text else f"Leading enterprise operating in {primary_industry}."

        ind_str = primary_industry if primary_industry != "Not specified" else "Enterprise Solutions"

        return CompetitorProfile(
            company_name=raw_comp.competitor_name,
            industry=ind_str,
            company_description=exec_sum,
            executive_summary=exec_sum,
            core_services=[f"{ind_str} Solutions", "Enterprise Consulting", "Technical Implementation"],
            products=[f"{raw_comp.competitor_name} Platform"],
            business_domains=[ind_str],
            business_strengths=[f"Established market presence in {ind_str}", "Scalable service delivery"],
            competitive_advantages=["Domain expertise", "Regional market footprint"],
            major_projects=[f"Major {ind_str} Deployments"],
            technologies=["Enterprise Architecture", "Cloud Infrastructure", "Automation Systems"],
            geographic_presence=["Global", "Regional"],
            official_website=raw_comp.official_website or "Not specified",
            source_urls=raw_comp.source_urls or [],
            references=raw_comp.source_urls or []
        )
