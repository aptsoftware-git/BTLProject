from __future__ import annotations

import logging
from typing import List, Optional
from src.comparative_analysis.models import (
    CompanySummary,
    CompetitorSummaryList,
    ComparativeAnalysisResult,
    InnovationOpportunity,
)
from src.comparative_analysis.prompts.innovation_prompt import INNOVATION_SYSTEM_PROMPT, INNOVATION_USER_PROMPT

logger = logging.getLogger("comparative_analysis.innovation_opportunity_agent")


class InnovationOpportunityAgent:
    """
    Agent responsible for identifying market white spaces, technology gaps,
    and disruptive innovation opportunities based on market comparison data.
    """

    def __init__(self, llm_model_name: Optional[str] = None) -> None:
        """
        Initialize InnovationOpportunityAgent.

        Args:
            llm_model_name: Optional local LLM model override.
        """
        self.llm_model_name = llm_model_name
        self.system_prompt = INNOVATION_SYSTEM_PROMPT
        self.user_prompt_template = INNOVATION_USER_PROMPT

    def identify_opportunities(
        self,
        company_summary: CompanySummary,
        competitor_summary_list: CompetitorSummaryList,
        comparative_analysis: ComparativeAnalysisResult
    ) -> List[InnovationOpportunity]:
        """
        Identifies market innovation opportunities.

        Args:
            company_summary: Target company summary.
            competitor_summary_list: Competitor profiles list.
            comparative_analysis: Comparative analysis result.

        Returns:
            List of InnovationOpportunity items.
        """
        logger.info("Identifying innovation opportunities for company: %s", company_summary.company_name)

        # Interface / Stub placeholder implementation
        opp1 = InnovationOpportunity(
            id="INN-001",
            title="Real-Time Automated Comparative Benchmarking Widget",
            opportunity_type="Product Feature White Space",
            description="No existing market competitor provides automated real-time document benchmarking directly inside proofreading workflows.",
            target_segment="Enterprise Strategy and Product Marketing teams",
            competitive_advantage_potential="High - Creates unique end-to-end document intelligence value proposition.",
            feasibility="High"
        )

        opp2 = InnovationOpportunity(
            id="INN-002",
            title="Multimodal Financial Table & Chart Benchmarking",
            opportunity_type="Technology Gap Innovation",
            description="Leverage Docling multimodal layout analysis to compare visual charts and complex financial tables against competitor SEC filings.",
            target_segment="Financial Analysts and Investment Banking firms",
            competitive_advantage_potential="Very High - Solves complex tabular document benchmark friction.",
            feasibility="Medium"
        )

        return [opp1, opp2]
