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

        # 1. Core Services Comparison
        target_services_str = ", ".join(company_profile.core_services) if company_profile.core_services else "Not specified"
        comp_services_map: Dict[str, str] = {}
        for c in competitors:
            comp_services_map[c.company_name] = ", ".join(c.core_services) if c.core_services else "Not specified"
        
        feature_matrix.append(
            FeatureComparisonRow(
                dimension="Core Services",
                target_company_score=target_services_str,
                competitor_scores=comp_services_map,
                insights=f"{company_profile.company_name} provides specialized services; competitors offer benchmarked industry solutions."
            )
        )

        # 2. Products Comparison
        target_prods_str = ", ".join(company_profile.products) if company_profile.products else "Enterprise Platforms"
        comp_prods_map: Dict[str, str] = {}
        for c in competitors:
            comp_prods_map[c.company_name] = ", ".join(c.products) if c.products else "Peer Platforms"

        feature_matrix.append(
            FeatureComparisonRow(
                dimension="Products & Software",
                target_company_score=target_prods_str,
                competitor_scores=comp_prods_map,
                insights=f"{company_profile.company_name} maintains dedicated offerings alongside industry peer products."
            )
        )

        # 3. Technologies Comparison
        target_tech_str = ", ".join(company_profile.technologies) if company_profile.technologies else "Enterprise Stack"
        comp_tech_map: Dict[str, str] = {}
        for c in competitors:
            comp_tech_map[c.company_name] = ", ".join(c.technologies) if c.technologies else "Cloud & Automation Tech"

        feature_matrix.append(
            FeatureComparisonRow(
                dimension="Technologies & Architecture",
                target_company_score=target_tech_str,
                competitor_scores=comp_tech_map,
                insights=f"Technology capabilities evaluated across {company_profile.primary_industry} competitors."
            )
        )

        # 4. Business Domains Comparison
        target_domains_str = ", ".join(company_profile.business_domains) if company_profile.business_domains else company_profile.primary_industry
        comp_domains_map: Dict[str, str] = {}
        for c in competitors:
            comp_domains_map[c.company_name] = c.industry if c.industry else company_profile.primary_industry

        feature_matrix.append(
            FeatureComparisonRow(
                dimension="Business Domains",
                target_company_score=target_domains_str,
                competitor_scores=comp_domains_map,
                insights=f"Competitors operate within overlapping {company_profile.primary_industry} verticals."
            )
        )

        # 5. Major Projects Comparison
        target_projects_str = ", ".join(company_profile.major_projects) if company_profile.major_projects else "Enterprise Projects"
        comp_projects_map: Dict[str, str] = {}
        for c in competitors:
            comp_projects_map[c.company_name] = ", ".join(c.major_projects) if c.major_projects else "Industry Deployments"

        feature_matrix.append(
            FeatureComparisonRow(
                dimension="Major Projects Track Record",
                target_company_score=target_projects_str,
                competitor_scores=comp_projects_map,
                insights="Track record evaluated across enterprise customer implementations."
            )
        )

        # 6. Target Industries Comparison
        target_ind_str = ", ".join(company_profile.target_industries) if company_profile.target_industries else company_profile.primary_industry
        comp_ind_map: Dict[str, str] = {}
        for c in competitors:
            comp_ind_map[c.company_name] = c.industry if c.industry else company_profile.primary_industry

        feature_matrix.append(
            FeatureComparisonRow(
                dimension="Target Customer Industries",
                target_company_score=target_ind_str,
                competitor_scores=comp_ind_map,
                insights=f"Target client sectors aligned with {company_profile.primary_industry} ecosystem."
            )
        )

        # 7. Geographic Presence Comparison
        target_geo_str = ", ".join(company_profile.geographic_presence) if company_profile.geographic_presence else "Global"
        comp_geo_map: Dict[str, str] = {}
        for c in competitors:
            comp_geo_map[c.company_name] = ", ".join(c.geographic_presence) if c.geographic_presence else "Global"

        feature_matrix.append(
            FeatureComparisonRow(
                dimension="Geographic Presence",
                target_company_score=target_geo_str,
                competitor_scores=comp_geo_map,
                insights="Geographic footprint benchmarked against international competitors."
            )
        )

        # 8. Business Strengths Comparison
        target_str_str = ", ".join(company_profile.business_strengths) if company_profile.business_strengths else "Proven Track Record"
        comp_str_map: Dict[str, str] = {}
        for c in competitors:
            comp_str_map[c.company_name] = ", ".join(c.business_strengths) if c.business_strengths else "Market presence"

        feature_matrix.append(
            FeatureComparisonRow(
                dimension="Business Strengths",
                target_company_score=target_str_str,
                competitor_scores=comp_str_map,
                insights=f"Core competencies forming key market differentiation for {company_profile.company_name}."
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
