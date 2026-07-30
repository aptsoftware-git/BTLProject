from __future__ import annotations

import logging
from typing import List, Dict, Optional
from src.comparative_analysis.models import (
    CompanyProfile,
    CompetitorSummaryList,
    CompetitorProfile,
    ComparativeAnalysisResult,
    FeatureComparisonRow,
    SWOTComparison,
)

logger = logging.getLogger("comparative_analysis.comparative_analysis_agent")


class ComparativeBenchmarkingAgent:
    """
    Agent responsible for performing head-to-head benchmarking between the target company
    and every verified competitor across 8 key dimensions.
    """

    def __init__(self) -> None:
        pass

    def benchmark(
        self,
        company_profile: CompanyProfile,
        competitor_summary_list: CompetitorSummaryList
    ) -> ComparativeAnalysisResult:
        """
        Executes head-to-head benchmarking matrix generation.

        Args:
            company_profile: Verified target CompanyProfile object.
            competitor_summary_list: Verified CompetitorSummaryList object containing Top 5 competitors.

        Returns:
            ComparativeAnalysisResult model.
        """
        logger.info(
            "ComparativeBenchmarkingAgent evaluating '%s' against %d competitors...",
            company_profile.company_name,
            len(competitor_summary_list.competitors)
        )

        competitors = competitor_summary_list.competitors
        feature_matrix: List[FeatureComparisonRow] = []

        # Part 9: 7 Clean Core Comparison Dimensions
        # 1. Core Services
        target_services_str = ", ".join(company_profile.core_services) if company_profile.core_services else "Not specified"
        comp_services_map = {c.company_name: ", ".join(c.core_services) if c.core_services else "Not specified" for c in competitors}
        feature_matrix.append(
            FeatureComparisonRow(
                dimension="Core Services",
                target_company_score=target_services_str,
                competitor_scores=comp_services_map,
                insights=f"{company_profile.company_name} specialized services benchmarked against peers."
            )
        )

        # 2. Business Segments
        target_domains_str = ", ".join(company_profile.business_domains) if company_profile.business_domains else company_profile.primary_industry
        comp_domains_map = {c.company_name: c.industry if c.industry else company_profile.primary_industry for c in competitors}
        feature_matrix.append(
            FeatureComparisonRow(
                dimension="Business Segments",
                target_company_score=target_domains_str,
                competitor_scores=comp_domains_map,
                insights=f"Business segment coverage across {company_profile.primary_industry} ecosystem."
            )
        )

        # 3. Technology Capabilities
        target_tech_str = ", ".join(company_profile.technologies) if company_profile.technologies else "Enterprise Stack"
        comp_tech_map = {c.company_name: ", ".join(c.technologies) if c.technologies else "Cloud & Automation Tech" for c in competitors}
        feature_matrix.append(
            FeatureComparisonRow(
                dimension="Technology Capabilities",
                target_company_score=target_tech_str,
                competitor_scores=comp_tech_map,
                insights=f"Technology stack and digital capabilities evaluated against market peers."
            )
        )

        # 4. Market Presence
        target_geo_str = ", ".join(company_profile.geographic_presence) if company_profile.geographic_presence else "Global"
        comp_geo_map = {c.company_name: ", ".join(c.geographic_presence) if c.geographic_presence else "Global" for c in competitors}
        feature_matrix.append(
            FeatureComparisonRow(
                dimension="Market Presence",
                target_company_score=target_geo_str,
                competitor_scores=comp_geo_map,
                insights="Geographic footprint and regional presence benchmarked against peers."
            )
        )

        # 5. Competitive Advantages
        target_adv_str = ", ".join(company_profile.competitive_advantages or company_profile.business_strengths) if (company_profile.competitive_advantages or company_profile.business_strengths) else "Domain Expertise"
        comp_adv_map = {c.company_name: ", ".join(c.business_strengths) if c.business_strengths else "Market presence" for c in competitors}
        feature_matrix.append(
            FeatureComparisonRow(
                dimension="Competitive Advantages",
                target_company_score=target_adv_str,
                competitor_scores=comp_adv_map,
                insights=f"Key competitive moats distinguishing {company_profile.company_name}."
            )
        )

        # 6. Major Projects
        target_projects_str = ", ".join(company_profile.major_projects) if company_profile.major_projects else "Enterprise Deployments"
        comp_projects_map = {c.company_name: ", ".join(c.major_projects) if c.major_projects else "Industry Projects" for c in competitors}
        feature_matrix.append(
            FeatureComparisonRow(
                dimension="Major Projects",
                target_company_score=target_projects_str,
                competitor_scores=comp_projects_map,
                insights="Project track record evaluated across enterprise customer implementations."
            )
        )

        # 7. Strategic Positioning
        target_pos_str = f"Specialized Provider in {company_profile.primary_industry}"
        comp_pos_map = {c.company_name: f"Peer Competitor in {c.industry}" for c in competitors}
        feature_matrix.append(
            FeatureComparisonRow(
                dimension="Strategic Positioning",
                target_company_score=target_pos_str,
                competitor_scores=comp_pos_map,
                insights=f"Strategic market tier positioning within {company_profile.primary_industry}."
            )
        )

        # Dynamic SWOT synthesis
        strengths = company_profile.business_strengths or [f"Established domain focus in {company_profile.primary_industry}"]
        weaknesses = [f"Opportunity to expand global market footprint in {company_profile.primary_industry}", "Potential to accelerate product packaging"]
        opportunities = [f"Expanding automated digital solutions across {company_profile.primary_industry}", "Strategic partner alliances"]
        threats = [f"Competitor market expansion in {company_profile.primary_industry}", "Evolving client technology adoption"]

        swot = SWOTComparison(
            strengths_vs_competitors=strengths[:3],
            weaknesses_vs_competitors=weaknesses,
            opportunities_in_market=opportunities,
            threats_from_competitors=threats
        )

        return ComparativeAnalysisResult(
            target_company_name=company_profile.company_name,
            industry=company_profile.primary_industry,
            feature_matrix=feature_matrix,
            swot_analysis=swot,
            market_positioning_score=0.0,
            key_differentiators=strengths[:2],
            comparative_summary=f"{company_profile.company_name} maintains a competitive standing in {company_profile.primary_industry}."
        )


# Alias for backward compatibility
ComparativeAnalysisAgent = ComparativeBenchmarkingAgent
