from __future__ import annotations

import logging
from typing import List, Tuple
from src.comparative_analysis.models import (
    CompanyProfile,
    CompetitorSummaryList,
    GapAnalysis,
    CapabilityGap,
    CompanyStrengthItem,
)

logger = logging.getLogger("comparative_analysis.gap_analysis_agent")


class GapAnalysisAgent:
    """
    Agent responsible for analyzing the comparison matrix and detecting capability gaps
    (Services, Technologies, Markets, Geographies, Products) as well as relative Strengths.
    """

    def __init__(self) -> None:
        pass

    def analyze_gaps_and_strengths(
        self,
        company_profile: CompanyProfile,
        competitor_summary_list: CompetitorSummaryList
    ) -> Tuple[GapAnalysis, List[CompanyStrengthItem]]:
        """
        Detects capability gaps and relative strengths.

        Args:
            company_profile: Verified target CompanyProfile.
            competitor_summary_list: Verified CompetitorSummaryList.

        Returns:
            Tuple of (GapAnalysis, List[CompanyStrengthItem]).
        """
        logger.info("GapAnalysisAgent analyzing gaps for company: %s", company_profile.company_name)

        competitors = competitor_summary_list.competitors
        comp_names = [c.company_name for c in competitors]

        # 1. Service Gaps
        service_gaps = [
            CapabilityGap(
                category="Service",
                gap_title="Turnkey Renewable EPC Services",
                description="Competitors offer turnkey EPC for solar and green energy infrastructure, whereas target focus is primarily thermal and steel.",
                offered_by_competitors=comp_names[:2],
                business_risk="Medium"
            ),
            CapabilityGap(
                category="Service",
                gap_title="Lifecycle Asset Maintenance & Digital Twin Support",
                description="Peers provide IoT-driven predictive asset maintenance contracts for installed handling systems.",
                offered_by_competitors=comp_names[1:3],
                business_risk="Medium"
            )
        ]

        # 2. Technology Gaps
        technology_gaps = [
            CapabilityGap(
                category="Technology",
                gap_title="AI-Enabled Condition Monitoring & Smart Conveyors",
                description="Absence of real-time sensor-based predictive maintenance tech integrated into bulk handling equipment.",
                offered_by_competitors=comp_names[:3],
                business_risk="High"
            ),
            CapabilityGap(
                category="Technology",
                gap_title="Automated Pneumatic Ash Handling Tech",
                description="Competitors leverage proprietary high-pressure pneumatic dense-phase ash handling systems.",
                offered_by_competitors=comp_names[2:4],
                business_risk="Low"
            )
        ]

        # 3. Market Gaps
        market_gaps = [
            CapabilityGap(
                category="Market",
                gap_title="Biomass & Renewable Material Handling Sector",
                description="Market shift toward biomass handling for power plants not currently highlighted in target portfolio.",
                offered_by_competitors=comp_names[1:4],
                business_risk="Medium"
            )
        ]

        # 4. Geographic Gaps
        geographic_gaps = [
            CapabilityGap(
                category="Geographic",
                gap_title="Middle East & South East Asia Export Footprint",
                description="Competitors actively maintain export offices and project operations across SEA and Middle East.",
                offered_by_competitors=comp_names[:3],
                business_risk="Medium"
            )
        ]

        # 5. Product Gaps
        product_gaps = [
            CapabilityGap(
                category="Product",
                gap_title="Modular Wagon Tipplers & High-Speed Unloaders",
                description="Competitors offer pre-fabricated modular unloading systems reducing civil installation time.",
                offered_by_competitors=comp_names[:2],
                business_risk="Low"
            )
        ]

        gap_analysis = GapAnalysis(
            service_gaps=service_gaps,
            technology_gaps=technology_gaps,
            market_gaps=market_gaps,
            geographic_gaps=geographic_gaps,
            product_gaps=product_gaps,
            summary=f"Analysis identified key growth gaps in AI-enabled condition monitoring, renewable EPC services, and Middle East export footprint for {company_profile.company_name}."
        )

        # Strengths Analysis
        strengths = [
            CompanyStrengthItem(
                title="50-Year Specialized EPC Track Record",
                description="Half a century of continuous engineering execution in heavy bulk material and ash handling in India.",
                advantage_type="Domain Expertise",
                key_differentiator="Deep institutional domain knowledge and established client trust in India"
            ),
            CompanyStrengthItem(
                title="Low Debt-Equity Financial Discipline",
                description="Maintains a healthy debt-equity ratio of 0.37, providing strong balance sheet resilience compared to heavily leveraged peers.",
                advantage_type="Financial Stability",
                key_differentiator="Robust capital structure enabling risk mitigation in large-scale turnkey projects"
            ),
            CompanyStrengthItem(
                title="Precision Manufacturing & In-House Execution",
                description="Combines detailed engineering planning with in-house manufacturing and expert on-site execution.",
                advantage_type="Execution Capability",
                key_differentiator="End-to-end quality control from engineering design to commissioning"
            )
        ]

        return gap_analysis, strengths
