import React, { useState } from 'react';

/**
 * ExecutiveDashboardView Component (Phase 6 Demonstration Ready)
 * Executive-facing, production-ready interactive dashboard with section navigation,
 * processing timeline, competitor favicon cards, side-by-side matrix, collapsible evidence,
 * grouped recommendations, and export controls.
 */
export default function ExecutiveDashboardView({ data, isRunning, currentStage }) {
  const [activeTab, setActiveTab] = useState('executive-summary');
  const [openEvidence, setOpenEvidence] = useState({});

  const toggleEvidence = (id) => {
    setOpenEvidence((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  // Handle Export Actions
  const handleExportJSON = () => {
    if (!data) return;
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `comparative_analysis_${data.analysis_id || 'export'}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handlePrintPDF = () => {
    window.print();
  };

  if (isRunning) {
    return (
      <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col justify-center items-center p-8 font-sans">
        <div className="max-w-md w-full bg-slate-900 border border-slate-800 rounded-2xl p-8 text-center shadow-2xl space-y-6">
          <div className="relative w-16 h-16 mx-auto">
            <div className="absolute inset-0 rounded-full border-4 border-sky-500/20 animate-ping"></div>
            <div className="absolute inset-0 rounded-full border-4 border-t-sky-400 border-r-transparent border-b-transparent border-l-transparent animate-spin"></div>
          </div>
          <div>
            <h2 className="text-xl font-bold text-sky-400">Executing Comparative Analysis</h2>
            <p className="text-sm text-slate-400 mt-2 font-medium">
              {currentStage || 'Building Market Intelligence & Benchmarks...'}
            </p>
          </div>
          <div className="w-full bg-slate-950 rounded-full h-2 overflow-hidden border border-slate-800">
            <div className="bg-gradient-to-r from-sky-500 to-emerald-400 h-full w-3/4 animate-pulse"></div>
          </div>
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="p-12 text-center text-slate-400">
        <p className="text-lg">No comparative analysis data available.</p>
      </div>
    );
  }

  const {
    analysis_id = '',
    company_profile: company = {},
    competitor_profiles: competitorsData = {},
    industry_snapshot: snapshot = {},
    market_position: position = {},
    competitive_differentiators: differentiators = [],
    comparative_analysis: matrixData = {},
    gap_analysis: gapData = {},
    company_strengths: strengths = [],
    categorized_opportunities: opportunities = [],
    executive_insights: insights = {},
    strategic_recommendations: recommendations = [],
    execution_time_seconds = null,
  } = data;

  const competitors = competitorsData.competitors || [];

  // Group Recommendations by Priority
  const immediatePriorities = recommendations.filter((r) => r.priority === 'High');
  const mediumTermInitiatives = recommendations.filter((r) => r.priority === 'Medium');
  const longTermOpportunities = recommendations.filter((r) => r.priority === 'Low' || (r.priority !== 'High' && r.priority !== 'Medium'));

  // Processing Timeline Stages
  const timelineStages = [
    { label: 'Company Understanding', status: 'completed' },
    { label: 'Industry Classification', status: 'completed' },
    { label: 'Competitor Discovery', status: 'completed' },
    { label: 'Competitor Profiling', status: 'completed' },
    { label: 'Comparative Benchmarking', status: 'completed' },
    { label: 'Gap Analysis', status: 'completed' },
    { label: 'Industry Intelligence', status: 'completed' },
    { label: 'Strategic Recommendations', status: 'completed' },
    { label: 'Executive Report Ready', status: 'completed' },
  ];

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 p-4 sm:p-6 md:p-10 font-sans print:bg-white print:text-black">
      {/* 1. Executive Dashboard Header & Landing */}
      <div className="max-w-7xl mx-auto bg-gradient-to-r from-slate-900 via-slate-900 to-slate-950 border border-slate-800 border-l-4 border-l-sky-500 rounded-2xl p-6 md:p-8 mb-6 shadow-2xl print:border-none print:shadow-none print:p-0">
        <div className="flex flex-col lg:flex-row justify-between items-start lg:items-center gap-6">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-3xl font-extrabold text-sky-400 tracking-tight print:text-black">
                {company.company_name || 'Target Company'}
              </h1>
              <span className="px-3 py-1 bg-sky-500/10 border border-sky-500/30 text-sky-300 rounded-full text-xs font-bold uppercase tracking-wider print:hidden">
                Executive Analysis
              </span>
            </div>
            <div className="flex flex-wrap items-center gap-4 text-xs md:text-sm text-slate-400 mt-2">
              <span>Primary Industry: <strong className="text-slate-200">{company.primary_industry || 'Not Available'}</strong></span>
              <span>&bull;</span>
              <span>Competitors Analysed: <strong className="text-slate-200">{competitors.length} Companies</strong></span>
              <span>&bull;</span>
              <span>Status: <strong className="text-emerald-400 font-semibold">{execution_time_seconds ? `Completed (${execution_time_seconds}s)` : 'Completed'}</strong></span>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3 print:hidden">
            {/* Qualitative Market Position Badge */}
            <div className="bg-gradient-to-r from-sky-600 to-blue-700 text-white px-5 py-2.5 rounded-xl shadow-lg shadow-sky-500/20 text-center">
              <span className="block text-[10px] uppercase tracking-widest text-sky-200 font-semibold">Market Position</span>
              <span className="text-sm font-bold">{position.classification || 'Specialized Provider'}</span>
            </div>

            {/* Export Buttons */}
            <button
              onClick={handleExportJSON}
              className="px-4 py-2.5 bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 rounded-xl text-xs font-bold transition-all shadow-md"
            >
              Export JSON
            </button>
            <button
              onClick={handlePrintPDF}
              className="px-4 py-2.5 bg-sky-500 hover:bg-sky-400 text-slate-950 font-extrabold rounded-xl text-xs transition-all shadow-lg shadow-sky-500/20"
            >
              Export Report / PDF
            </button>
          </div>
        </div>

        {/* 2. Processing Timeline */}
        <div className="mt-8 pt-6 border-t border-slate-800/80 print:hidden">
          <span className="text-xs font-bold uppercase tracking-wider text-slate-400 block mb-3">
            Analysis Processing Pipeline Workflow
          </span>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 lg:grid-cols-9 gap-2">
            {timelineStages.map((stage, idx) => (
              <div
                key={idx}
                className="p-2 bg-slate-950/80 border border-slate-800 rounded-lg text-center flex flex-col items-center justify-center gap-1"
              >
                <span className="w-4 h-4 rounded-full bg-emerald-500/20 text-emerald-400 text-[10px] font-bold flex items-center justify-center border border-emerald-500/40">
                  ✓
                </span>
                <span className="text-[10px] text-slate-300 font-medium leading-tight">
                  {stage.label}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* 3. Section Navigation Tabs */}
      <div className="max-w-7xl mx-auto flex flex-wrap gap-2 mb-8 border-b border-slate-800 pb-3 print:hidden">
        {[
          { id: 'executive-summary', label: 'Executive Summary' },
          { id: 'company-profile', label: 'Company Profile' },
          { id: 'industry-snapshot', label: 'Industry Snapshot' },
          { id: 'competitor-profiles', label: 'Competitor Cards' },
          { id: 'comparison-matrix', label: 'Comparison Matrix' },
          { id: 'capability-gaps', label: 'Gaps & Strengths' },
          { id: 'growth-opportunities', label: 'Growth Opportunities' },
          { id: 'strategic-recommendations', label: 'Strategic Recommendations' },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-4 py-2.5 rounded-xl text-xs font-bold transition-all duration-200 ${
              activeTab === tab.id
                ? 'bg-sky-500 text-slate-950 font-extrabold shadow-lg shadow-sky-500/20'
                : 'bg-slate-900/80 hover:bg-slate-800 text-slate-300 border border-slate-800'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="max-w-7xl mx-auto space-y-8">
        {/* SECTION 1: EXECUTIVE SUMMARY */}
        {(activeTab === 'executive-summary' || activeTab === 'all') && (
          <div className="space-y-6">
            <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 md:p-8 shadow-xl">
              <h2 className="text-xl font-bold text-sky-400 mb-4 border-b border-slate-800 pb-3">
                Executive Decision-Support Narrative
              </h2>
              <p className="text-slate-300 leading-relaxed text-sm md:text-base">
                {insights.executive_summary_narrative || company.executive_summary}
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-xl">
                <h3 className="text-base font-bold text-sky-400 border-b border-slate-800 pb-2 mb-3">
                  Qualitative Market Position & Moat
                </h3>
                <p className="text-sm font-bold text-slate-100 mb-1">{position.position_title || position.classification}</p>
                <p className="text-xs text-slate-300 leading-relaxed">{position.competitive_moat}</p>
              </div>

              <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-xl">
                <h3 className="text-base font-bold text-emerald-400 border-b border-slate-800 pb-2 mb-3">
                  Key Strategic Expansion Areas
                </h3>
                <ul className="space-y-1.5 text-xs text-slate-300">
                  {(insights.most_promising_expansion_areas || []).map((area, idx) => (
                    <li key={idx} className="flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-emerald-400"></span>
                      <span>{area}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        )}

        {/* SECTION 2: COMPANY PROFILE */}
        {(activeTab === 'company-profile' || activeTab === 'all') && (
          <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 md:p-8 shadow-xl space-y-6">
            <h2 className="text-xl font-bold text-sky-400 border-b border-slate-800 pb-3">
              Verified Company Profile (Single Source of Truth)
            </h2>
            <p className="text-xs text-slate-300">{company.company_description}</p>
            
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              <div className="p-4 bg-slate-950 border border-slate-800 rounded-xl space-y-2">
                <span className="text-xs font-bold text-sky-400 uppercase">Core Services</span>
                <div className="flex flex-wrap gap-1.5">
                  {(company.core_services || []).map((s, idx) => (
                    <span key={idx} className="px-2.5 py-1 bg-sky-950/60 border border-sky-500/30 text-sky-300 rounded-md text-xs">
                      {s}
                    </span>
                  ))}
                </div>
              </div>

              <div className="p-4 bg-slate-950 border border-slate-800 rounded-xl space-y-2">
                <span className="text-xs font-bold text-purple-400 uppercase">Technologies</span>
                <div className="flex flex-wrap gap-1.5">
                  {(company.technologies || []).map((t, idx) => (
                    <span key={idx} className="px-2.5 py-1 bg-purple-950/60 border border-purple-500/30 text-purple-300 rounded-md text-xs">
                      {t}
                    </span>
                  ))}
                </div>
              </div>

              <div className="p-4 bg-slate-950 border border-slate-800 rounded-xl space-y-2">
                <span className="text-xs font-bold text-emerald-400 uppercase">Major Projects</span>
                <div className="flex flex-wrap gap-1.5">
                  {(company.major_projects || []).map((p, idx) => (
                    <span key={idx} className="px-2.5 py-1 bg-emerald-950/60 border border-emerald-500/30 text-emerald-300 rounded-md text-xs">
                      {p}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* SECTION 3: INDUSTRY SNAPSHOT */}
        {(activeTab === 'industry-snapshot' || activeTab === 'all') && (
          <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 md:p-8 shadow-xl space-y-6">
            <h2 className="text-xl font-bold text-sky-400 border-b border-slate-800 pb-3">
              Industry Intelligence Snapshot
            </h2>
            <p className="text-xs text-slate-300 leading-relaxed">{snapshot.industry_summary}</p>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="p-5 bg-slate-950 border border-slate-800 rounded-xl">
                <h3 className="text-xs font-bold text-sky-400 uppercase mb-3">Dominant Macro Trends</h3>
                <ul className="list-disc list-inside space-y-1 text-xs text-slate-300">
                  {(snapshot.common_industry_trends || []).map((t, i) => (
                    <li key={i}>{t}</li>
                  ))}
                </ul>
              </div>

              <div className="p-5 bg-slate-950 border border-slate-800 rounded-xl">
                <h3 className="text-xs font-bold text-purple-400 uppercase mb-3">Emerging Tech & Innovations</h3>
                <ul className="list-disc list-inside space-y-1 text-xs text-slate-300">
                  {(snapshot.emerging_technologies || []).map((t, i) => (
                    <li key={i}>{t}</li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        )}

        {/* SECTION 4: COMPETITOR CARDS WITH FAVICONS */}
        {(activeTab === 'competitor-profiles' || activeTab === 'all') && (
          <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 md:p-8 shadow-xl space-y-6">
            <h2 className="text-xl font-bold text-sky-400 border-b border-slate-800 pb-3">
              Verified Competitor Business Cards ({competitors.length})
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {competitors.map((comp, idx) => {
                const domain = comp.official_website ? comp.official_website.replace(/^https?:\/\//, '').split('/')[0] : '';
                const faviconUrl = domain ? `https://www.google.com/s2/favicons?domain=${domain}&sz=64` : '';

                return (
                  <div key={idx} className="bg-slate-950 border border-slate-800 rounded-2xl p-6 space-y-4 hover:border-sky-500/50 transition-all">
                    <div className="flex items-center gap-4 border-b border-slate-800 pb-3">
                      {faviconUrl ? (
                        <img src={faviconUrl} alt="Logo" className="w-10 h-10 rounded-lg bg-slate-900 p-1 border border-slate-800" />
                      ) : (
                        <div className="w-10 h-10 rounded-lg bg-sky-500/10 text-sky-400 font-bold flex items-center justify-center border border-sky-500/30 text-sm">
                          #{idx + 1}
                        </div>
                      )}
                      <div>
                        <h3 className="text-base font-bold text-slate-100">{comp.company_name}</h3>
                        <span className="text-xs text-sky-400 font-semibold">{comp.industry}</span>
                      </div>
                    </div>

                    <p className="text-xs text-slate-300 leading-relaxed">{comp.executive_summary}</p>

                    <div className="space-y-2 text-xs">
                      <div>
                        <strong className="text-slate-400 block text-[10px] uppercase font-semibold">Core Services</strong>
                        <div className="flex flex-wrap gap-1 mt-1">
                          {(comp.core_services || []).map((s, i) => (
                            <span key={i} className="px-2 py-0.5 bg-sky-950/60 border border-sky-500/30 text-sky-300 rounded text-[11px]">
                              {s}
                            </span>
                          ))}
                        </div>
                      </div>

                      {comp.official_website && comp.official_website !== 'Not specified' && (
                        <div className="pt-2">
                          <a
                            href={comp.official_website}
                            target="_blank"
                            rel="noreferrer"
                            className="inline-flex items-center gap-1.5 text-xs text-sky-400 font-semibold hover:underline"
                          >
                            Official Website &rarr;
                          </a>
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* SECTION 5: INTERACTIVE SIDE-BY-SIDE COMPARISON MATRIX */}
        {(activeTab === 'comparison-matrix' || activeTab === 'all') && (
          <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 md:p-8 shadow-xl space-y-6">
            <h2 className="text-xl font-bold text-sky-400 border-b border-slate-800 pb-3">
              Interactive Side-by-Side Comparison Matrix
            </h2>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs text-slate-300 border-collapse min-w-[900px]">
                <thead>
                  <tr className="bg-slate-950 text-sky-400 border-b border-slate-800">
                    <th className="p-3.5 font-bold sticky left-0 bg-slate-950 z-10 w-44">Dimension</th>
                    <th className="p-3.5 font-bold bg-sky-950/40 text-sky-300 w-64">{company.company_name} (Uploaded)</th>
                    {competitors.map((c, i) => (
                      <th key={i} className="p-3.5 font-bold w-56">{c.company_name}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {(matrixData.feature_matrix || []).map((row, idx) => (
                    <tr key={idx} className="hover:bg-slate-800/40">
                      <td className="p-3.5 font-bold text-slate-200 sticky left-0 bg-slate-900 z-10 border-r border-slate-800">
                        {row.dimension}
                      </td>
                      <td className="p-3.5 bg-sky-950/20 text-sky-200 font-medium border-r border-slate-800">
                        {row.target_company_score}
                      </td>
                      {competitors.map((c, i) => (
                        <td key={i} className="p-3.5 text-slate-300 border-r border-slate-800/60">
                          {row.competitor_scores?.[c.company_name] || 'N/A'}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* SECTION 6: CAPABILITY GAPS & STRENGTHS */}
        {(activeTab === 'capability-gaps' || activeTab === 'all') && (
          <div className="space-y-6">
            <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 md:p-8 shadow-xl">
              <h2 className="text-xl font-bold text-emerald-400 border-b border-slate-800 pb-3 mb-4">
                Competitive Strengths & Core Advantages
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                {strengths.map((st, idx) => (
                  <div key={idx} className="p-5 bg-slate-950 border border-emerald-500/20 rounded-xl space-y-2">
                    <span className="px-2.5 py-0.5 bg-emerald-500/10 text-emerald-400 text-[10px] font-bold rounded">
                      {st.advantage_type}
                    </span>
                    <h3 className="font-bold text-slate-100 text-sm">{st.title}</h3>
                    <p className="text-xs text-slate-300 leading-relaxed">{st.description}</p>
                  </div>
                ))}
              </div>
            </div>

            <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 md:p-8 shadow-xl space-y-4">
              <h2 className="text-xl font-bold text-amber-400 border-b border-slate-800 pb-3">
                Capability & Market Gaps
              </h2>
              {[
                ...(gapData.service_gaps || []),
                ...(gapData.technology_gaps || []),
                ...(gapData.market_gaps || []),
              ].map((gap, idx) => (
                <div key={idx} className="p-4 bg-slate-950 border-l-4 border-l-amber-500 border border-slate-800 rounded-xl space-y-2">
                  <div className="flex justify-between items-center">
                    <span className="text-xs font-bold text-amber-400 uppercase">{gap.category} Gap</span>
                    <span className="px-2 py-0.5 bg-amber-500/20 text-amber-300 text-[10px] font-bold rounded">
                      Risk: {gap.business_risk}
                    </span>
                  </div>
                  <h4 className="font-bold text-slate-100 text-sm">{gap.gap_title}</h4>
                  <p className="text-xs text-slate-300">{gap.description}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* SECTION 7: GROWTH OPPORTUNITY CARDS */}
        {(activeTab === 'growth-opportunities' || activeTab === 'all') && (
          <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 md:p-8 shadow-xl space-y-6">
            <h2 className="text-xl font-bold text-emerald-400 border-b border-slate-800 pb-3">
              Growth Opportunity Cards
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {opportunities.map((opp, idx) => {
                const oppId = `opp_${idx}`;
                return (
                  <div key={idx} className="p-6 bg-slate-950 border border-emerald-500/20 rounded-2xl space-y-4 flex flex-col justify-between">
                    <div className="space-y-3">
                      <span className="px-3 py-1 bg-emerald-500/10 text-emerald-400 text-xs font-bold rounded-lg">
                        {opp.category}
                      </span>
                      <h3 className="font-bold text-slate-100 text-base">{opp.title}</h3>
                      <p className="text-xs text-slate-300 leading-relaxed">{opp.description}</p>
                    </div>

                    <div className="pt-3 border-t border-slate-900 space-y-2 text-xs">
                      <div>
                        <strong className="text-slate-400 block text-[10px] uppercase font-semibold">Supporting Competitor(s)</strong>
                        <p className="text-slate-200 mt-0.5">{opp.competitor_evidence}</p>
                      </div>

                      {/* Expandable Supporting Evidence Panel */}
                      <button
                        onClick={() => toggleEvidence(oppId)}
                        className="text-xs text-sky-400 font-semibold hover:underline flex items-center gap-1"
                      >
                        {openEvidence[oppId] ? '▲ Hide Supporting Evidence' : '▼ View Supporting Evidence'}
                      </button>

                      {openEvidence[oppId] && (
                        <div className="p-3 bg-slate-900 border border-slate-800 rounded-xl text-xs space-y-2 text-slate-300">
                          <div><strong>Industry Trend:</strong> {opp.industry_trend_reference}</div>
                          <div><strong>Observation:</strong> {opp.supporting_observation}</div>
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* SECTION 8: GROUPED EXECUTIVE RECOMMENDATIONS WITH EVIDENCE */}
        {(activeTab === 'strategic-recommendations' || activeTab === 'all') && (
          <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 md:p-8 shadow-xl space-y-8">
            <h2 className="text-xl font-bold text-emerald-400 border-b border-slate-800 pb-3">
              Grouped Executive Recommendations
            </h2>

            {/* Category 1: Immediate Priorities */}
            {immediatePriorities.length > 0 && (
              <div className="space-y-4">
                <h3 className="text-sm font-bold uppercase tracking-wider text-rose-400 flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-rose-500"></span>
                  Immediate Priorities (High Risk / High Return)
                </h3>
                {immediatePriorities.map((rec, idx) => {
                  const recId = `rec_imm_${idx}`;
                  return (
                    <div key={idx} className="p-6 bg-slate-950 border-l-4 border-l-rose-500 border border-slate-800 rounded-2xl space-y-3">
                      <div className="flex justify-between items-center">
                        <span className="text-xs font-bold text-rose-400">{rec.id}</span>
                        <span className="px-3 py-0.5 bg-rose-500 text-slate-950 rounded-full text-xs font-extrabold">
                          Priority: High
                        </span>
                      </div>
                      <h4 className="text-base font-bold text-slate-100">{rec.title}</h4>
                      <p className="text-xs text-slate-300"><strong className="text-slate-200">Business Rationale:</strong> {rec.rationale}</p>
                      <p className="text-xs text-slate-400"><strong className="text-slate-300">Expected Outcome:</strong> {rec.expected_impact}</p>

                      {/* Expandable Supporting Evidence Panel */}
                      <button
                        onClick={() => toggleEvidence(recId)}
                        className="text-xs text-sky-400 font-semibold hover:underline flex items-center gap-1 pt-1"
                      >
                        {openEvidence[recId] ? '▲ Hide Supporting Evidence' : '▼ View Supporting Evidence'}
                      </button>

                      {openEvidence[recId] && (
                        <div className="p-4 bg-slate-900 border border-slate-800 rounded-xl text-xs space-y-2 text-slate-300">
                          <div><strong>Supporting Evidence:</strong> {rec.supporting_evidence}</div>
                          {rec.action_items && (
                            <div>
                              <strong>Action Items:</strong>
                              <ul className="list-disc list-inside mt-1 text-slate-400">
                                {rec.action_items.map((a, i) => (
                                  <li key={i}>{a}</li>
                                ))}
                              </ul>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}

            {/* Category 2: Medium-Term Initiatives */}
            {mediumTermInitiatives.length > 0 && (
              <div className="space-y-4">
                <h3 className="text-sm font-bold uppercase tracking-wider text-amber-400 flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-amber-400"></span>
                  Medium-Term Strategic Initiatives
                </h3>
                {mediumTermInitiatives.map((rec, idx) => {
                  const recId = `rec_med_${idx}`;
                  return (
                    <div key={idx} className="p-6 bg-slate-950 border-l-4 border-l-amber-400 border border-slate-800 rounded-2xl space-y-3">
                      <div className="flex justify-between items-center">
                        <span className="text-xs font-bold text-amber-400">{rec.id}</span>
                        <span className="px-3 py-0.5 bg-amber-400 text-slate-950 rounded-full text-xs font-extrabold">
                          Priority: Medium
                        </span>
                      </div>
                      <h4 className="text-base font-bold text-slate-100">{rec.title}</h4>
                      <p className="text-xs text-slate-300"><strong className="text-slate-200">Business Rationale:</strong> {rec.rationale}</p>
                      <p className="text-xs text-slate-400"><strong className="text-slate-300">Expected Outcome:</strong> {rec.expected_impact}</p>

                      <button
                        onClick={() => toggleEvidence(recId)}
                        className="text-xs text-sky-400 font-semibold hover:underline flex items-center gap-1 pt-1"
                      >
                        {openEvidence[recId] ? '▲ Hide Supporting Evidence' : '▼ View Supporting Evidence'}
                      </button>

                      {openEvidence[recId] && (
                        <div className="p-4 bg-slate-900 border border-slate-800 rounded-xl text-xs space-y-2 text-slate-300">
                          <div><strong>Supporting Evidence:</strong> {rec.supporting_evidence}</div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
