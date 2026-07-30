from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from src.comparative_analysis.models import (
    CompanyProfile,
    CompetitorProfile,
    CompetitorSummaryList,
    ComparativeAnalysisResult,
    GapAnalysis,
    SWOTComparison,
    StrategicRecommendation,
    TargetCompanyProfile,
    CompanyProfileChunk,
)
from src.comparative_analysis.agents.company_profile_retriever import CompanyProfileRetriever
from src.comparative_analysis.agents.company_summary_agent import CompanySummaryAgent
from src.comparative_analysis.agents.search_query_builder import SearchQueryBuilder
from src.comparative_analysis.agents.tavily_search_agent import TavilySearchAgent
from src.comparative_analysis.agents.market_intelligence_filter import MarketIntelligenceFilter
from src.comparative_analysis.agents.competitor_summary_agent import CompetitorSummaryAgent
from src.comparative_analysis.agents.comparative_analysis_agent import ComparativeBenchmarkingAgent
from src.comparative_analysis.agents.gap_analysis_agent import GapAnalysisAgent
from src.comparative_analysis.agents.swot_analysis_agent import SWOTAnalysisAgent
from src.comparative_analysis.agents.strategic_recommendation_agent import StrategicRecommendationAgent
from src.comparative_analysis.report_generator import ComparativeReportGenerator


class TestComparativeAnalysisWorkflow(unittest.TestCase):

    def test_10_agent_workflow(self):
        retriever = CompanyProfileRetriever()
        dummy_target_profile = TargetCompanyProfile(
            document_id="test_doc_123",
            total_chunks=1,
            chunks=[
                CompanyProfileChunk(
                    chunk_id="chk_1",
                    text="BTL EPC Ltd. provides turnkey bulk material handling systems, ash handling solutions, and heavy steel plant infrastructure in India.",
                    page_number=1,
                    query_matched="Company Overview"
                )
            ]
        )

        company_summary_agent = CompanySummaryAgent()
        company_profile = company_summary_agent._extract_fallback_profile(dummy_target_profile)
        self.assertIn("BTL EPC", company_profile.company_name)
        self.assertEqual(company_profile.primary_industry, "Engineering Procurement & Construction (EPC)")

        query_builder = SearchQueryBuilder()
        query_batch = query_builder.build_queries(company_profile)
        self.assertTrue(len(query_batch.queries) > 0)

        tavily_agent = TavilySearchAgent()
        raw_search_results = tavily_agent._generate_fallback_results(query_batch)
        self.assertTrue(len(raw_search_results) > 0)

        verifier = MarketIntelligenceFilter(top_k_companies=5)
        verified_comps = verifier.filter_and_group(raw_search_results, target_company_name=company_profile.company_name)
        self.assertTrue(len(verified_comps) > 0)

        competitor_summary_agent = CompetitorSummaryAgent()
        comp_summary_list = competitor_summary_agent.summarize_competitors(
            competitor_raw_data_list=verified_comps,
            primary_industry=company_profile.primary_industry,
            target_company_name=company_profile.company_name
        )
        self.assertTrue(len(comp_summary_list.competitors) > 0)

        benchmarking_agent = ComparativeBenchmarkingAgent()
        comp_matrix = benchmarking_agent.benchmark(company_profile, comp_summary_list)
        self.assertEqual(len(comp_matrix.feature_matrix), 7)

        gap_agent = GapAnalysisAgent()
        gaps, strengths = gap_agent.analyze_gaps_and_strengths(company_profile, comp_summary_list)

        swot_agent = SWOTAnalysisAgent()
        swot = swot_agent.generate_swot(company_profile, comp_summary_list, comp_matrix, gaps)
        self.assertTrue(len(swot.strengths_vs_competitors) > 0)

        rec_agent = StrategicRecommendationAgent()
        recs = rec_agent._extract_fallback_recommendations(company_profile, comp_summary_list)
        self.assertEqual(len(recs), 5)

        report_gen = ComparativeReportGenerator()
        report_html = report_gen._render_executive_dashboard_html(
            analysis_id="test_run",
            document_id="test_doc_123",
            company_profile=company_profile,
            competitor_summary_list=comp_summary_list,
            industry_snapshot=None,
            market_position=None,
            differentiators=[],
            opportunities=[],
            executive_insights=None,
            recommendations=recs,
            comparative_result=comp_matrix,
            gap_analysis=gaps,
            strengths=strengths
        )
        self.assertIn("1. Executive Summary", report_html)
        self.assertIn("2. Target Company Overview", report_html)
        self.assertIn("3. Industry & Similar Companies", report_html)
        self.assertIn("4. Comparative Analysis Matrix", report_html)
        self.assertIn("5. SWOT Analysis", report_html)
        self.assertIn("6. Key Areas of Improvement (Gap Analysis)", report_html)
        self.assertIn("7. Strategic Recommendations", report_html)
        self.assertIn("8. Supporting Evidence & References", report_html)

    def test_vertexa_vs_btl_epc_dynamic_differentiation(self):
        """Requirement 7: Verify two completely different documents produce completely different results."""
        summary_agent = CompanySummaryAgent()
        tavily_agent = TavilySearchAgent()
        query_builder = SearchQueryBuilder()
        rec_agent = StrategicRecommendationAgent()

        # Document 1: Vertexa Handbook
        vertexa_target = TargetCompanyProfile(
            document_id="Vertexa_Handbook",
            chunks=[
                CompanyProfileChunk(
                    chunk_id="v1",
                    text="Vertexa Technologies is a software platform specializing in AI document intelligence, OCR, and automated text extraction.",
                    page_number=1
                )
            ]
        )
        profile_vertexa = summary_agent._extract_fallback_profile(vertexa_target)
        batch_vertexa = query_builder.build_queries(profile_vertexa)
        search_vertexa = tavily_agent._generate_fallback_results(batch_vertexa)

        # Document 2: BTL EPC Brochure
        btl_target = TargetCompanyProfile(
            document_id="BTL_EPC_Brochure",
            chunks=[
                CompanyProfileChunk(
                    chunk_id="b1",
                    text="BTL EPC Ltd. provides turnkey bulk material handling systems, ash handling solutions, and heavy steel plant infrastructure.",
                    page_number=1
                )
            ]
        )
        profile_btl = summary_agent._extract_fallback_profile(btl_target)
        batch_btl = query_builder.build_queries(profile_btl)
        search_btl = tavily_agent._generate_fallback_results(batch_btl)

        # 1. Company Name changes
        self.assertNotEqual(profile_vertexa.company_name, profile_btl.company_name)
        self.assertIn("Vertexa", profile_vertexa.company_name)
        self.assertIn("BTL", profile_btl.company_name)

        # 2. Industry changes
        self.assertNotEqual(profile_vertexa.primary_industry, profile_btl.primary_industry)
        self.assertEqual(profile_vertexa.primary_industry, "AI & Document Intelligence")
        self.assertEqual(profile_btl.primary_industry, "Engineering Procurement & Construction (EPC)")

        # 3. Competitors change
        vertexa_comp_names = [s.company_name for s in search_vertexa]
        btl_comp_names = [s.company_name for s in search_btl]
        self.assertNotEqual(vertexa_comp_names, btl_comp_names)
        self.assertIn("Abbyy Software", vertexa_comp_names)
        self.assertIn("Elecon Engineering Co.", btl_comp_names)

        # 4. Recommendations change
        recs_vertexa = rec_agent._extract_fallback_recommendations(profile_vertexa, CompetitorSummaryList(competitors=[]))
        recs_btl = rec_agent._extract_fallback_recommendations(profile_btl, CompetitorSummaryList(competitors=[]))
        self.assertNotEqual(recs_vertexa[0].title, recs_btl[0].title)
        self.assertIn("AI & Document Intelligence", recs_vertexa[0].observation)
        self.assertIn("Engineering Procurement & Construction (EPC)", recs_btl[0].observation)


if __name__ == "__main__":
    unittest.main()
