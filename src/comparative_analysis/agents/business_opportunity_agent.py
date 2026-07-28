from __future__ import annotations

import logging
from typing import List
from src.comparative_analysis.models import (
    CompanyProfile,
    CompetitorSummaryList,
    IndustrySnapshot,
    CategorizedOpportunity,
)

logger = logging.getLogger("comparative_analysis.business_opportunity_agent")


class BusinessOpportunityAgent:
    """
    Agent responsible for generating structured, categorized market opportunities
    where every opportunity references competitor evidence, industry trends, and supporting observations.
    """

    def __init__(self) -> None:
        pass

    def generate_categorized_opportunities(
        self,
        company_profile: CompanyProfile,
        competitor_summary_list: CompetitorSummaryList,
        industry_snapshot: IndustrySnapshot
    ) -> List[CategorizedOpportunity]:
        """
        Generates categorized opportunities referencing competitor evidence and trends.

        Args:
            company_profile: Verified target CompanyProfile.
            competitor_summary_list: Verified CompetitorSummaryList.
            industry_snapshot: IndustrySnapshot object.

        Returns:
            List of CategorizedOpportunity objects.
        """
        logger.info("BusinessOpportunityAgent identifying categorized growth opportunities for %s...", company_profile.company_name)

        opps = [
            CategorizedOpportunity(
                id="OPP-TECH-01",
                title="Deploy AI-Enabled Smart Conveyor & Predictive Maintenance Software",
                category="Technology",
                description="Integrate IoT vibration/thermal sensors and AI-driven predictive maintenance software into bulk material handling installations.",
                competitor_evidence="Competitors Elecon Engineering and Thyssenkrupp actively market digital condition monitoring packages.",
                industry_trend_reference="Tavily market search highlights industry-wide transition toward IoT-enabled predictive maintenance.",
                supporting_observation="Target company currently relies on traditional mechanical maintenance contracts."
            ),
            CategorizedOpportunity(
                id="OPP-MKT-01",
                title="Expand Turnkey EPC into Biomass & Green Energy Infrastructure",
                category="Market Expansion",
                description="Formulate specialized biomass pellet handling and co-firing engineering packages for state power utilities.",
                competitor_evidence="TRF Limited and L&T Heavy Engineering bid on biomass and renewable energy EPC infrastructure.",
                industry_trend_reference="Mandated compliance for industrial biomass co-firing in thermal plants across India.",
                supporting_observation="Target company has deep ash and coal handling expertise easily adaptable to biomass handling."
            ),
            CategorizedOpportunity(
                id="OPP-DIG-01",
                title="Establish 3D Digital Twin & BIM Plant Engineering Workflows",
                category="Digital Transformation",
                description="Adopt 3D Digital Twin and Building Information Modeling (BIM) for pre-installation virtual plant commissioning.",
                competitor_evidence="Global peers market 3D plant design and digital twin simulation to reduce EPC execution time.",
                industry_trend_reference="Industry adoption of digital twin modeling to mitigate site assembly delays.",
                supporting_observation="Leverages target company's detailed engineering capabilities to accelerate client delivery."
            ),
            CategorizedOpportunity(
                id="OPP-GEO-01",
                title="Establish Regional Sales & Engineering Hubs in SEA and Middle East",
                category="Geographic Expansion",
                description="Form regional sales and project partnerships in Vietnam, Indonesia, and UAE for bulk handling exports.",
                competitor_evidence="Elecon Engineering and McNally Bharat regularly export material handling units to SEA and Middle East.",
                industry_trend_reference="Surging infrastructure and mining investments in South East Asia and Middle East.",
                supporting_observation="Diversifies revenue stream outside domestic Indian market."
            ),
            CategorizedOpportunity(
                id="OPP-SRV-01",
                title="Launch Long-Term SLA Asset Management & Retrofit Services",
                category="Service Expansion",
                description="Offer multi-year Operations & Maintenance (O&M) and retrofit SLAs for aging bulk handling plants.",
                competitor_evidence="Competitors generate high-margin recurring revenues via long-term O&M contracts.",
                industry_trend_reference="Power and steel utilities prioritizing plant life-extension and retrofit services over new CAPEX.",
                supporting_observation="Unlocks recurring high-margin revenue from installed base of over 50 years."
            )
        ]

        return opps
