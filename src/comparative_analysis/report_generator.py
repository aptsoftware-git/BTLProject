from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, Optional, List
from src.comparative_analysis.models import (
    CompanyProfile,
    CompetitorSummaryList,
    ComparativeAnalysisResult,
    GapAnalysis,
    CompanyStrengthItem,
    CategorizedOpportunity,
    StrategicRecommendation,
    IndustrySnapshot,
    MarketPosition,
    CompetitiveDifferentiator,
    ExecutiveInsights,
)
from src.config import ROOT_DIR

logger = logging.getLogger("comparative_analysis.report_generator")


class ComparativeReportGenerator:
    """
    Report generator rendering Phase 6 Executive Demonstration HTML Reports, Dashboard Views, and JSON artifacts.
    """

    def __init__(self, output_dir: Optional[Path] = None) -> None:
        self.output_dir = output_dir or (ROOT_DIR / "data" / "output" / "reports")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_reports(
        self,
        analysis_id: str,
        document_id: str,
        company_profile: CompanyProfile,
        competitor_summary_list: Optional[CompetitorSummaryList] = None,
        comparative_result: Optional[ComparativeAnalysisResult] = None,
        gap_analysis: Optional[GapAnalysis] = None,
        strengths: Optional[List[CompanyStrengthItem]] = None,
        opportunities: Optional[List[CategorizedOpportunity]] = None,
        recommendations: Optional[List[StrategicRecommendation]] = None,
        industry_snapshot: Optional[IndustrySnapshot] = None,
        market_position: Optional[MarketPosition] = None,
        differentiators: Optional[List[CompetitiveDifferentiator]] = None,
        executive_insights: Optional[ExecutiveInsights] = None
    ) -> Dict[str, str]:
        """
        Renders Phase 6 Executive Dashboard HTML Report and JSON artifacts.
        """
        logger.info("Generating Phase 6 Executive Demonstration Report for analysis_id: %s", analysis_id)

        doc_output_dir = ROOT_DIR / "data" / "output" / document_id / "comparative_analysis"
        doc_output_dir.mkdir(parents=True, exist_ok=True)

        doc_dashboard_html = doc_output_dir / "executive_dashboard.html"
        doc_exec_report = doc_output_dir / "comparative_report.html"
        doc_similar_html = doc_output_dir / "similar_companies.html"
        doc_profile_html = doc_output_dir / "company_profile.html"

        global_dashboard_html = self.output_dir / f"executive_dashboard_{analysis_id}.html"
        global_json = self.output_dir / f"comparative_analysis_{analysis_id}.json"

        # Render Executive Dashboard HTML (No numerical scores, business indicators, expandable evidence)
        dashboard_html = self._render_executive_dashboard_html(
            analysis_id=analysis_id,
            document_id=document_id,
            company_profile=company_profile,
            competitor_summary_list=competitor_summary_list,
            industry_snapshot=industry_snapshot,
            market_position=market_position,
            differentiators=differentiators or [],
            opportunities=opportunities or [],
            executive_insights=executive_insights,
            recommendations=recommendations or [],
            comparative_result=comparative_result,
            gap_analysis=gap_analysis,
            strengths=strengths or []
        )

        with open(doc_dashboard_html, "w", encoding="utf-8") as f:
            f.write(dashboard_html)
        with open(global_dashboard_html, "w", encoding="utf-8") as f:
            f.write(dashboard_html)
        with open(doc_exec_report, "w", encoding="utf-8") as f:
            f.write(dashboard_html)

        # Save comprehensive JSON payload
        json_payload = {
            "analysis_id": analysis_id,
            "document_id": document_id,
            "company_profile": company_profile.model_dump(),
            "competitors": competitor_summary_list.model_dump() if competitor_summary_list else None,
            "industry_snapshot": industry_snapshot.model_dump() if industry_snapshot else None,
            "market_position": market_position.model_dump() if market_position else None,
            "differentiators": [d.model_dump() for d in (differentiators or [])],
            "comparative_matrix": comparative_result.model_dump() if comparative_result else None,
            "gap_analysis": gap_analysis.model_dump() if gap_analysis else None,
            "strengths": [s.model_dump() for s in (strengths or [])],
            "opportunities": [o.model_dump() for o in (opportunities or [])],
            "executive_insights": executive_insights.model_dump() if executive_insights else None,
            "recommendations": [r.model_dump() for r in (recommendations or [])]
        }
        with open(global_json, "w", encoding="utf-8") as f:
            json.dump(json_payload, f, indent=2, ensure_ascii=False)
        with open(doc_output_dir / "comparative_report.json", "w", encoding="utf-8") as f:
            json.dump(json_payload, f, indent=2, ensure_ascii=False)

        # Save individual domain JSON artifacts (Requirement 2)
        with open(doc_output_dir / "company_profile.json", "w", encoding="utf-8") as f:
            json.dump(company_profile.model_dump(), f, indent=2, ensure_ascii=False)

        if competitor_summary_list:
            with open(doc_output_dir / "competitor_profiles.json", "w", encoding="utf-8") as f:
                json.dump(competitor_summary_list.model_dump(), f, indent=2, ensure_ascii=False)

        if comparative_result:
            with open(doc_output_dir / "comparison_matrix.json", "w", encoding="utf-8") as f:
                json.dump(comparative_result.model_dump(), f, indent=2, ensure_ascii=False)
            if comparative_result.swot_analysis:
                with open(doc_output_dir / "swot_analysis.json", "w", encoding="utf-8") as f:
                    json.dump(comparative_result.swot_analysis.model_dump(), f, indent=2, ensure_ascii=False)

        if gap_analysis:
            with open(doc_output_dir / "gap_analysis.json", "w", encoding="utf-8") as f:
                json.dump(gap_analysis.model_dump(), f, indent=2, ensure_ascii=False)

        if recommendations:
            with open(doc_output_dir / "recommendations.json", "w", encoding="utf-8") as f:
                json.dump([r.model_dump() for r in recommendations], f, indent=2, ensure_ascii=False)

        return {
            "executive_dashboard_html": str(doc_dashboard_html),
            "comparative_report_html": str(doc_exec_report),
            "similar_companies_html": str(doc_similar_html),
            "company_profile_html": str(doc_profile_html),
            "json": str(doc_output_dir / "comparative_report.json")
        }

    def _render_executive_dashboard_html(
        self,
        analysis_id: str,
        document_id: str,
        company_profile: CompanyProfile,
        competitor_summary_list: Optional[CompetitorSummaryList],
        industry_snapshot: Optional[IndustrySnapshot],
        market_position: Optional[MarketPosition],
        differentiators: List[CompetitiveDifferentiator],
        opportunities: List[CategorizedOpportunity],
        executive_insights: Optional[ExecutiveInsights],
        recommendations: List[StrategicRecommendation],
        comparative_result: Optional[ComparativeAnalysisResult] = None,
        gap_analysis: Optional[GapAnalysis] = None,
        strengths: Optional[List[CompanyStrengthItem]] = None
    ) -> str:
        competitors = competitor_summary_list.competitors if competitor_summary_list else []
        swot = comparative_result.swot_analysis if comparative_result and comparative_result.swot_analysis else SWOTComparison()

        # Competitor Cards HTML (Section 3)
        comp_cards_html = []
        for idx, comp in enumerate(competitors, 1):
            domain = comp.official_website.replace("https://", "").replace("http://", "").split("/")[0] if comp.official_website else ""
            favicon_url = f"https://www.google.com/s2/favicons?domain={domain}&sz=64" if domain else ""
            logo_html = f'<img src="{favicon_url}" class="comp-logo" alt="logo" />' if favicon_url else f'<div class="comp-rank">#{idx}</div>'
            web_link = f'<a href="{comp.official_website}" target="_blank" class="comp-link">{comp.official_website}</a>' if comp.official_website and comp.official_website != "Not specified" else '<span class="not-spec">Not specified</span>'

            prods_html = ", ".join(comp.products) if comp.products else "Custom Solutions"
            strengths_html = ", ".join(comp.business_strengths) if comp.business_strengths else "Market presence"

            comp_cards_html.append(f"""
            <div class="comp-card">
                <div class="comp-header">
                    {logo_html}
                    <div>
                        <h3 class="comp-title">{comp.company_name}</h3>
                        <span class="comp-ind">{comp.industry}</span>
                    </div>
                </div>
                <p class="comp-exec">{comp.executive_summary}</p>
                <div class="comp-block"><strong>Core Services:</strong> {", ".join(comp.core_services) if comp.core_services else 'Not specified'}</div>
                <div class="comp-block"><strong>Products:</strong> {prods_html}</div>
                <div class="comp-block"><strong>Business Strengths:</strong> {strengths_html}</div>
                <div class="comp-block"><strong>Website:</strong> {web_link}</div>
            </div>
            """)

        # Matrix HTML (Section 4)
        comp_headers = "".join(f"<th>{c.company_name}</th>" for c in competitors)
        matrix_rows_html = []
        if comparative_result and comparative_result.feature_matrix:
            for row in comparative_result.feature_matrix:
                comp_cells = "".join(f"<td>{row.competitor_scores.get(c.company_name, 'N/A')}</td>" for c in competitors)
                matrix_rows_html.append(f"""
                <tr>
                    <td class="dim-label"><strong>{row.dimension}</strong></td>
                    <td class="target-cell">{row.target_company_score}</td>
                    {comp_cells}
                </tr>
                """)

        # Key Areas of Improvement (Section 6 - Gap Analysis)
        gap_items_html = []
        if gap_analysis:
            all_gaps = (
                gap_analysis.service_gaps +
                gap_analysis.technology_gaps +
                gap_analysis.product_gaps +
                gap_analysis.market_gaps +
                gap_analysis.geographic_gaps
            )
            for g in all_gaps:
                risk_badge = f'<span class="badge badge-{g.business_risk.lower()}">{g.business_risk} Risk</span>'
                peers_str = ", ".join(g.offered_by_competitors) if g.offered_by_competitors else "Competitors"
                gap_items_html.append(f"""
                <div class="gap-card">
                    <div class="gap-top">
                        <span class="gap-cat">{g.category} Gap</span>
                        {risk_badge}
                    </div>
                    <h4>{g.gap_title}</h4>
                    <p>{g.description}</p>
                    <div class="gap-peers"><strong>Offered by Competitors:</strong> {peers_str}</div>
                </div>
                """)

        # Strategic Recommendations HTML (Section 7 - Top 5)
        rec_cards_html = []
        for r in recommendations[:5]:
            obs_text = getattr(r, 'observation', None) or r.rationale or r.title
            evid_text = getattr(r, 'supporting_evidence', None) or "Observed across peer market benchmark"
            impact_text = getattr(r, 'business_impact', None) or r.expected_impact or "High positive business impact"
            action_text = getattr(r, 'suggested_action', None) or r.title

            rec_cards_html.append(f"""
            <div class="rec-card prio-{r.priority.lower()}">
                <div class="rec-top">
                    <span class="rec-id">{r.id}</span>
                    <span class="prio-tag prio-{r.priority.lower()}">Priority: {r.priority}</span>
                </div>
                <h4>{r.title if r.title else action_text}</h4>
                <div class="rec-block"><strong>Observation:</strong> {obs_text}</div>
                <div class="rec-block"><strong>Supporting Evidence:</strong> {evid_text}</div>
                <div class="rec-block"><strong>Business Impact:</strong> {impact_text}</div>
                <div class="rec-block"><strong>Suggested Action:</strong> {action_text}</div>
                <details class="evidence-panel">
                    <summary>View Execution Action Items</summary>
                    <div class="evidence-content">
                        <ul>{"".join(f"<li>{a}</li>" for a in r.action_items)}</ul>
                    </div>
                </details>
            </div>
            """)

        # Supporting Evidence & References HTML (Section 8)
        ref_urls_html = []
        for c in competitors:
            if c.source_urls:
                for u in c.source_urls:
                    ref_urls_html.append(f'<li><a href="{u}" target="_blank">{u}</a> ({c.company_name})</li>')
            elif c.official_website and c.official_website != "Not specified":
                ref_urls_html.append(f'<li><a href="{c.official_website}" target="_blank">{c.official_website}</a> ({c.company_name})</li>')

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Executive Comparative Analysis Report - {company_profile.company_name}</title>
    <style>
        :root {{
            --bg: #f4f6fb;
            --card-bg: #ffffff;
            --border: #e2e8f0;
            --border-soft: #cbd5e1;
            --text: #1e293b;
            --muted: #64748b;
            
            /* Pastel Accents */
            --blue-pastel-bg: #e0f2fe;
            --blue-pastel-text: #0369a1;
            --indigo-pastel-bg: #e0e7ff;
            --indigo-pastel-text: #4338ca;
            --mint-pastel-bg: #d1fae5;
            --mint-pastel-text: #047857;
            --amber-pastel-bg: #fef3c7;
            --amber-pastel-text: #b45309;
            --rose-pastel-bg: #ffe4e6;
            --rose-pastel-text: #be123c;
            --purple-pastel-bg: #f3e8ff;
            --purple-pastel-text: #6b21a8;
        }}
        body {{
            font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
            background-color: var(--bg);
            color: var(--text);
            margin: 0;
            padding: 40px 24px;
            line-height: 1.6;
        }}
        .container {{ max-width: 1280px; margin: 0 auto; }}
        .header {{
            background: linear-gradient(135deg, #ffffff, #f1f5f9);
            border: 1px solid var(--border);
            border-left: 6px solid var(--blue-pastel-text);
            padding: 32px;
            border-radius: 16px;
            margin-bottom: 24px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 4px 15px -3px rgba(0, 0, 0, 0.05);
        }}
        .header h1 {{ margin: 0 0 8px 0; color: #0f172a; font-size: 2.2rem; }}
        .header p {{ margin: 0; color: var(--muted); font-size: 0.95rem; }}
        .pos-badge {{
            background: var(--indigo-pastel-bg);
            color: var(--indigo-pastel-text);
            font-weight: 700;
            padding: 10px 20px;
            border-radius: 12px;
            border: 1px solid #c7d2fe;
        }}
        .section-card {{
            background-color: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 30px;
            margin-bottom: 32px;
            box-shadow: 0 4px 20px -2px rgba(0,0,0,0.04);
        }}
        .section-card h2 {{ margin-top: 0; color: #0f172a; border-bottom: 2px solid #f1f5f9; padding-bottom: 12px; font-size: 1.4rem; }}
        .grid-2 {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(360px, 1fr)); gap: 24px; }}
        .comp-card, .gap-card, .rec-card {{ background: #fafafa; border: 1px solid var(--border); border-radius: 14px; padding: 22px; margin-bottom: 16px; }}
        .comp-header {{ display: flex; align-items: center; gap: 14px; border-bottom: 1px solid var(--border); padding-bottom: 12px; margin-bottom: 12px; }}
        .comp-logo {{ width: 36px; height: 36px; border-radius: 8px; background: #ffffff; padding: 4px; border: 1px solid var(--border); }}
        .comp-rank {{ width: 36px; height: 36px; border-radius: 8px; background: var(--blue-pastel-bg); color: var(--blue-pastel-text); font-weight: 700; display: flex; align-items: center; justify-content: center; }}
        .comp-title {{ margin: 0; color: #0f172a; font-size: 1.1rem; }}
        .comp-ind {{ color: var(--blue-pastel-text); font-size: 0.8rem; font-weight: 600; }}
        .comp-exec {{ font-size: 0.88rem; color: #334155; margin-bottom: 12px; }}
        a.comp-link {{ color: var(--blue-pastel-text); text-decoration: none; font-size: 0.85rem; font-weight: 600; }}
        .matrix-table {{ width: 100%; border-collapse: collapse; margin-top: 14px; font-size: 0.88rem; min-width: 800px; }}
        .matrix-table th {{ background: #f1f5f9; color: #0f172a; padding: 12px; border: 1px solid var(--border); text-align: left; font-weight: 700; }}
        .matrix-table td {{ padding: 12px; border: 1px solid var(--border); vertical-align: top; background: #ffffff; color: #334155; }}
        .target-cell {{ background: var(--blue-pastel-bg) !important; color: var(--blue-pastel-text) !important; font-weight: 600; }}
        .swot-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
        .swot-box {{ border-radius: 12px; padding: 20px; border: 1px solid var(--border); }}
        .swot-box h3 {{ margin-top: 0; font-size: 1.1rem; border-bottom: 1px dashed var(--border-soft); padding-bottom: 8px; }}
        .swot-s {{ background-color: var(--mint-pastel-bg); border-color: #a7f3d0; }}
        .swot-s h3 {{ color: var(--mint-pastel-text); }}
        .swot-w {{ background-color: var(--rose-pastel-bg); border-color: #fecdd3; }}
        .swot-w h3 {{ color: var(--rose-pastel-text); }}
        .swot-o {{ background-color: var(--blue-pastel-bg); border-color: #bae6fd; }}
        .swot-o h3 {{ color: var(--blue-pastel-text); }}
        .swot-t {{ background-color: var(--amber-pastel-bg); border-color: #fde68a; }}
        .swot-t h3 {{ color: var(--amber-pastel-text); }}
        .rec-card.prio-high {{ border-left: 5px solid #f43f5e; background: #fff5f5; }}
        .rec-card.prio-medium {{ border-left: 5px solid #f59e0b; background: #fffbeb; }}
        .prio-tag.prio-high {{ background: var(--rose-pastel-bg); color: var(--rose-pastel-text); padding: 3px 10px; border-radius: 12px; font-weight: 700; font-size: 0.75rem; border: 1px solid #fecdd3; }}
        .prio-tag.prio-medium {{ background: var(--amber-pastel-bg); color: var(--amber-pastel-text); padding: 3px 10px; border-radius: 12px; font-weight: 700; font-size: 0.75rem; border: 1px solid #fde68a; }}
        .badge {{ padding: 2px 8px; border-radius: 6px; font-size: 0.75rem; font-weight: 600; }}
        .badge-high {{ background: var(--rose-pastel-bg); color: var(--rose-pastel-text); border: 1px solid #fecdd3; }}
        .badge-medium {{ background: var(--amber-pastel-bg); color: var(--amber-pastel-text); border: 1px solid #fde68a; }}
        details.evidence-panel {{ margin-top: 12px; border: 1px solid var(--border); border-radius: 8px; background: #ffffff; padding: 8px 12px; }}
        details.evidence-panel summary {{ color: var(--indigo-pastel-text); font-size: 0.8rem; font-weight: 600; cursor: pointer; }}
        .evidence-content {{ margin-top: 8px; font-size: 0.8rem; color: #475569; border-top: 1px dashed var(--border); padding-top: 8px; }}
    </style>
</head>
<body>
    <div class="container">
        <!-- HEADER -->
        <div class="header">
            <div>
                <h1>Executive Comparative Analysis Report</h1>
                <p>Target Company: <strong>{company_profile.company_name}</strong> &bull; Industry: <strong>{company_profile.primary_industry}</strong></p>
            </div>
            <div class="pos-badge">
                {market_position.classification if market_position else "Specialized Provider"}
            </div>
        </div>

        <!-- 1. EXECUTIVE SUMMARY -->
        <div class="section-card">
            <h2>1. Executive Summary</h2>
            <p>{executive_insights.executive_summary_narrative if executive_insights and executive_insights.executive_summary_narrative else company_profile.executive_summary}</p>
        </div>

        <!-- 2. TARGET COMPANY OVERVIEW -->
        <div class="section-card">
            <h2>2. Target Company Overview</h2>
            <div class="grid-2">
                <div>
                    <p><strong>Company Description:</strong> {company_profile.company_description}</p>
                    <p><strong>Primary Industry:</strong> {company_profile.primary_industry}</p>
                    <p><strong>Secondary Industries:</strong> {", ".join(company_profile.secondary_industries) if company_profile.secondary_industries else "Not specified"}</p>
                    <p><strong>Geographic Presence:</strong> {", ".join(company_profile.geographic_presence) if company_profile.geographic_presence else "Not specified"}</p>
                </div>
                <div>
                    <p><strong>Core Services:</strong> {", ".join(company_profile.core_services) if company_profile.core_services else "Not specified"}</p>
                    <p><strong>Products & Systems:</strong> {", ".join(company_profile.products) if company_profile.products else "Not specified"}</p>
                    <p><strong>Technologies:</strong> {", ".join(company_profile.technologies) if company_profile.technologies else "Not specified"}</p>
                    <p><strong>Major Projects:</strong> {", ".join(company_profile.major_projects) if company_profile.major_projects else "Not specified"}</p>
                </div>
            </div>
        </div>

        <!-- 3. INDUSTRY & SIMILAR COMPANIES -->
        <div class="section-card">
            <h2>3. Industry & Similar Companies</h2>
            <p>Identified verified competitors operating in the <strong>{company_profile.primary_industry}</strong> sector via Tavily market discovery and web scraping:</p>
            <div class="grid-2">
                {"".join(comp_cards_html)}
            </div>
        </div>

        <!-- 4. COMPARATIVE ANALYSIS MATRIX -->
        <div class="section-card">
            <h2>4. Comparative Analysis Matrix</h2>
            <div style="overflow-x: auto;">
                <table class="matrix-table">
                    <thead>
                        <tr>
                            <th>Dimension</th>
                            <th>{company_profile.company_name} (Target)</th>
                            {comp_headers}
                        </tr>
                    </thead>
                    <tbody>
                        {"".join(matrix_rows_html)}
                    </tbody>
                </table>
            </div>
        </div>

        <!-- 5. SWOT ANALYSIS -->
        <div class="section-card">
            <h2>5. SWOT Analysis</h2>
            <div class="swot-grid">
                <div class="swot-box swot-s">
                    <h3>Strengths (vs Peers)</h3>
                    <ul>{"".join(f"<li>{s}</li>" for s in swot.strengths_vs_competitors)}</ul>
                </div>
                <div class="swot-box swot-w">
                    <h3>Weaknesses (vs Peers)</h3>
                    <ul>{"".join(f"<li>{w}</li>" for w in swot.weaknesses_vs_competitors)}</ul>
                </div>
                <div class="swot-box swot-o">
                    <h3>Market Opportunities</h3>
                    <ul>{"".join(f"<li>{o}</li>" for o in swot.opportunities_in_market)}</ul>
                </div>
                <div class="swot-box swot-t">
                    <h3>Competitor Threats</h3>
                    <ul>{"".join(f"<li>{t}</li>" for t in swot.threats_from_competitors)}</ul>
                </div>
            </div>
        </div>

        <!-- 6. KEY AREAS OF IMPROVEMENT -->
        <div class="section-card">
            <h2>6. Key Areas of Improvement (Gap Analysis)</h2>
            <div class="grid-2">
                {"".join(gap_items_html)}
            </div>
        </div>

        <!-- 7. STRATEGIC RECOMMENDATIONS -->
        <div class="section-card">
            <h2>7. Strategic Recommendations</h2>
            <p>Top 5 prioritized, evidence-backed strategic recommendations derived from competitor benchmarking:</p>
            {"".join(rec_cards_html)}
        </div>

        <!-- 8. SUPPORTING EVIDENCE & REFERENCES -->
        <div class="section-card">
            <h2>8. Supporting Evidence & References</h2>
            <p>Grounding source URLs and verified business references retrieved during live web search and ChromaDB indexing:</p>
            <ul>
                {"".join(ref_urls_html) if ref_urls_html else "<li>ChromaDB Document Index: " + document_id + "</li>"}
            </ul>
        </div>
    </div>
</body>
</html>
"""

