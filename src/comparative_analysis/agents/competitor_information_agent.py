from __future__ import annotations

import logging
from typing import List, Optional
from src.comparative_analysis.models import CompetitorRawData, TavilySearchResult
from src.comparative_analysis.agents.tavily_search_agent import TavilySearchAgent

logger = logging.getLogger("comparative_analysis.competitor_information_agent")


class CompetitorInformationAgent:
    """
    Agent responsible for performing targeted company expansion searches via Tavily for verified top competitors.

    CRITICAL REQUIREMENTS:
    - Does NOT scrape external websites directly.
    - Does NOT download brochures.
    - Uses Tavily API expansion searches to retrieve:
      Company Overview, Industry, Products, Services, Technologies, Major Projects, Markets, Headquarters, Official Website.
    """

    def __init__(self, tavily_search_agent: Optional[TavilySearchAgent] = None) -> None:
        """
        Initialize CompetitorInformationAgent.
        """
        self.tavily_agent = tavily_search_agent or TavilySearchAgent()

    def expand_competitor_information(
        self,
        competitors_raw: List[CompetitorRawData],
        primary_industry: str
    ) -> List[CompetitorRawData]:
        """
        Executes targeted Tavily company expansion search for each verified competitor.

        Args:
            competitors_raw: List of verified Top 5 CompetitorRawData objects.
            primary_industry: Primary industry sector name.

        Returns:
            List of CompetitorRawData populated with expanded Tavily search snippets.
        """
        logger.info("Expanding company information via Tavily for %d verified competitors...", len(competitors_raw))

        expanded_list: List[CompetitorRawData] = []

        for comp in competitors_raw:
            logger.info("Expanding Tavily search data for competitor: '%s'", comp.competitor_name)

            # Perform targeted Tavily search expansion
            expansion_snippets: List[TavilySearchResult] = self.tavily_agent.search_company_details(
                company_name=comp.competitor_name,
                primary_industry=primary_industry
            )

            # Combine initial discovery snippets with targeted expansion snippets
            combined_snippets = list(comp.search_results)
            existing_urls = set(comp.source_urls)

            for snip in expansion_snippets:
                if snip.url not in existing_urls:
                    existing_urls.add(snip.url)
                    combined_snippets.append(snip)

            expanded_list.append(
                CompetitorRawData(
                    competitor_name=comp.competitor_name,
                    official_website=comp.official_website or (expansion_snippets[0].website if expansion_snippets else ""),
                    search_results=combined_snippets,
                    source_urls=list(existing_urls)
                )
            )

        return expanded_list
