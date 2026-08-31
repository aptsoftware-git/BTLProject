"""
test_comparative_analysis_local_llm_fallback.py
=================================================
Regression tests for the local-LLM fallback added to the Comparative
Analysis Claude agents (src/comparative_analysis/agents/llm_fallback.py).

Previously, if the Claude API was unreachable (no/invalid key, out of
credits, rate-limited, network failure), every one of these agents fell
straight through to a generic, templated, non-document-specific fallback.
These tests verify: the shared Ollama-fallback helper degrades safely when
the local server is unreachable or errors, and that ExecutiveInsightsAgent
actually uses a successful local-LLM response instead of jumping straight
to its generic template when Claude is unavailable.
"""
from unittest.mock import patch, MagicMock

from src.comparative_analysis.agents.llm_fallback import call_local_llm_fallback


def test_local_llm_fallback_returns_none_when_ollama_unreachable():
    with patch("src.rag.ollama_client.OllamaClient.check_connection", return_value=False):
        result = call_local_llm_fallback("system", "user prompt", "TestAgent")
    assert result is None


def test_local_llm_fallback_returns_none_on_generate_exception():
    with patch("src.rag.ollama_client.OllamaClient.check_connection", return_value=True), \
         patch("src.rag.ollama_client.OllamaClient.generate", side_effect=RuntimeError("boom")):
        result = call_local_llm_fallback("system", "user prompt", "TestAgent")
    assert result is None


def test_local_llm_fallback_returns_text_on_success():
    with patch("src.rag.ollama_client.OllamaClient.check_connection", return_value=True), \
         patch("src.rag.ollama_client.OllamaClient.generate", return_value='{"ok": true}'):
        result = call_local_llm_fallback("system", "user prompt", "TestAgent")
    assert result == '{"ok": true}'


def test_executive_insights_agent_uses_local_llm_fallback_when_claude_unavailable():
    from src.comparative_analysis.agents.executive_insights_agent import ExecutiveInsightsAgent
    from src.comparative_analysis.models import CompanyProfile, MarketPosition, CompetitorSummaryList, GapAnalysis

    agent = ExecutiveInsightsAgent(api_key=None)  # no Claude key -> Claude branch skipped entirely
    company_profile = CompanyProfile(company_name="Acme Corp", primary_industry="Manufacturing")
    market_position = MarketPosition(classification="Strong Competitor", position_title="Regional leader")
    competitor_list = CompetitorSummaryList(competitors=[])
    gap_analysis = GapAnalysis()

    fake_local_response = (
        '{"top_strengths": ["Real synthesized strength from local LLM"], '
        '"top_weaknesses": [], "top_risks": [], "top_growth_opportunities": [], '
        '"key_competitive_threats": [], "most_promising_expansion_areas": [], '
        '"executive_summary_narrative": "Locally-generated narrative, not the generic template."}'
    )

    with patch(
        "src.comparative_analysis.agents.llm_fallback.call_local_llm_fallback",
        return_value=fake_local_response,
    ):
        insights = agent.generate_insights(company_profile, market_position, competitor_list, gap_analysis)

    assert insights.top_strengths == ["Real synthesized strength from local LLM"]
    assert insights.executive_summary_narrative == "Locally-generated narrative, not the generic template."


def test_executive_insights_agent_falls_through_to_generic_template_when_both_unavailable():
    from src.comparative_analysis.agents.executive_insights_agent import ExecutiveInsightsAgent
    from src.comparative_analysis.models import CompanyProfile, MarketPosition, CompetitorSummaryList, GapAnalysis

    agent = ExecutiveInsightsAgent(api_key=None)
    company_profile = CompanyProfile(company_name="Acme Corp", primary_industry="Manufacturing")
    market_position = MarketPosition(classification="Strong Competitor", position_title="Regional leader")
    competitor_list = CompetitorSummaryList(competitors=[])
    gap_analysis = GapAnalysis()

    with patch(
        "src.comparative_analysis.agents.llm_fallback.call_local_llm_fallback",
        return_value=None,
    ):
        insights = agent.generate_insights(company_profile, market_position, competitor_list, gap_analysis)

    # Falls all the way through to the generic template -- still returns a
    # usable result, just not a real synthesis.
    assert "Acme Corp" in insights.executive_summary_narrative
