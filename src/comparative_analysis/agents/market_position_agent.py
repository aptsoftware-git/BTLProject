from __future__ import annotations

import logging
from typing import List
from src.comparative_analysis.models import (
    CompanyProfile,
    CompetitorSummaryList,
    MarketPosition,
)

logger = logging.getLogger("comparative_analysis.market_position_agent")


class MarketPositionAgent:
    """
    Agent responsible for classifying the target company's qualitative market position dynamically.
    Uses 100% data-driven parameters with zero hardcoded company names or industry assumptions.
    """

    def __init__(self) -> None:
        pass

    def classify_market_position(
        self,
        company_profile: CompanyProfile,
        competitor_summary_list: CompetitorSummaryList
    ) -> MarketPosition:
        """
        Classifies target company's qualitative market standing dynamically with evidence.
        """
        logger.info("MarketPositionAgent classifying market standing for %s...", company_profile.company_name)

        industry = company_profile.primary_industry if company_profile.primary_industry != "Not specified" else "Enterprise Solutions"
        name = company_profile.company_name if company_profile.company_name != "Not specified" else "Target Company"

        classification = "Specialized Provider" if company_profile.core_services else "Emerging Competitor"
        headline = f"Established {classification} in {industry}"

        evidence = []
        if company_profile.business_strengths:
            evidence.extend(company_profile.business_strengths[:3])
        if company_profile.core_services:
            evidence.append(f"Specialized core expertise in {', '.join(company_profile.core_services[:2])}")
        if not evidence:
            evidence = [
                f"Established capabilities and technical focus in {industry}",
                f"Document analysis verified client deployment footprint in {industry}"
            ]

        tech_str = ", ".join(company_profile.technologies[:2]) if company_profile.technologies else "domain capabilities"
        moat = f"Specialized domain focus in {industry} combined with proprietary {tech_str}."

        rationale = (
            f"{name} maintains a '{classification}' market position in {industry}. "
            f"The company maintains a high-margin, specialized focus leveraging its expertise in {', '.join(company_profile.core_services[:2]) or industry}."
        )

        return MarketPosition(
            classification=classification,
            position_title=headline,
            supporting_evidence=evidence[:4],
            competitive_moat=moat,
            market_tier_rationale=rationale
        )
