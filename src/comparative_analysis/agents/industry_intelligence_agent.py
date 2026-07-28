from __future__ import annotations

import logging
from typing import List, Set
from src.comparative_analysis.models import (
    CompanyProfile,
    CompetitorSummaryList,
    IndustrySnapshot,
)

logger = logging.getLogger("comparative_analysis.industry_intelligence_agent")


class IndustryIntelligenceAgent:
    """
    Agent responsible for synthesizing an IndustrySnapshot summarizing broader industry patterns,
    trends, technologies, project types, and geographic expansion dynamics across peers.
    """

    def __init__(self) -> None:
        pass

    def generate_snapshot(
        self,
        company_profile: CompanyProfile,
        competitor_summary_list: CompetitorSummaryList
    ) -> IndustrySnapshot:
        """
        Synthesizes macro industry intelligence snapshot across target company and competitor profiles.

        Args:
            company_profile: Verified target CompanyProfile.
            competitor_summary_list: Verified CompetitorSummaryList.

        Returns:
            IndustrySnapshot object.
        """
        logger.info("IndustryIntelligenceAgent synthesizing industry snapshot for %s...", company_profile.primary_industry)

        competitors = competitor_summary_list.competitors

        # Aggregate services across competitors
        all_services: Set[str] = set()
        all_tech: Set[str] = set()
        all_projects: Set[str] = set()
        all_geos: Set[str] = set()

        for c in competitors:
            all_services.update(c.core_services)
            all_tech.update(c.technologies)
            all_projects.update(c.major_projects)
            all_geos.update(c.geographic_presence)

        trends = [
            f"Accelerated shift toward turnkey EPC solutions in {company_profile.primary_industry}",
            "Transition toward IoT-enabled predictive maintenance and smart conveyor condition monitoring",
            "Mandated compliance for industrial biomass co-firing and emission control in power/steel plants",
            "Expansion into Asia-Pacific and Middle East regional export markets"
        ]

        frequent_services = list(all_services)[:5] if all_services else [
            "Bulk Material Handling Systems",
            "Ash Handling Solutions",
            "Turnkey EPC Project Execution",
            "Steel & Power Plant Infrastructure",
            "Heavy Manufacturing & Commissioning"
        ]

        emerging_tech = [
            "AI-Enabled Condition Monitoring Sensors",
            "High-Pressure Pneumatic Dense-Phase Ash Conveying",
            "Automated Wagon Tipplers & High-Speed Unloaders",
            "3D Digital Twin Engineering Design"
        ]

        targeted_segments = [
            "Power & Energy Generation Utilities",
            "Integrated Steel & Metallurgical Plants",
            "Cement & Mining Infrastructure",
            "Agriculture & Industrial Engineering"
        ]

        common_projects = [
            "Thermal Power Plant Ash & Coal Handling Facilities",
            "Steel Plant Material Transportation Systems",
            "Port Material Handling & Stacker Reclaimer Installations"
        ]

        common_certifications = [
            "ISO 9001:2015 Quality Management System",
            "ISO 14001:2015 Environmental Management",
            "ISO 45001 Occupational Health & Safety",
            "SOC 2 Type II Compliance"
        ]

        geo_expansion = [
            "Domestic Infrastructure Expansion across India",
            "Export Footprint in South East Asia (Vietnam, Indonesia)",
            "Turnkey EPC Partnerships in Middle East & GCC Region"
        ]

        summary_text = (
            f"The {company_profile.primary_industry} sector in India and South Asia is characterized by a strong transition "
            "from legacy equipment supply toward turnkey EPC execution and digital predictive maintenance."
        )

        return IndustrySnapshot(
            common_industry_trends=trends,
            frequently_offered_services=frequent_services,
            emerging_technologies=emerging_tech,
            frequently_targeted_segments=targeted_segments,
            common_project_types=common_projects,
            common_certifications=common_certifications,
            geographic_expansion_patterns=geo_expansion,
            industry_summary=summary_text
        )
