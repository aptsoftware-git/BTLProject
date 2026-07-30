import React, { useState } from 'react';

/**
 * 10 Specialized Icons for Executive Business Scanning (Requirement 15)
 */
const IconBuilding = ({ size = 16, color = "var(--brand)" }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
    <path d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5m0 0h4m-4 0V11m0 0h4m-4 0H9m4 0V7m0 0h4m-4 0H9" />
  </svg>
);

const IconGlobe = ({ size = 16, color = "#0284c7" }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
    <path d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9" />
  </svg>
);

const IconCpu = ({ size = 16, color = "#4f46e5" }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
    <path d="M9 3v2m6-2v2M9 19v2m6-2v2M3 9h2m-2 6h2m14-6h2m-2 6h2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z" />
  </svg>
);

const IconFolder = ({ size = 16, color = "#0284c7" }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
    <path d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
  </svg>
);

const IconRocket = ({ size = 16, color = "var(--brand)" }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
    <path d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" />
  </svg>
);

const IconTrophy = ({ size = 16, color = "#d97706" }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
    <path d="M8 21h8m-4-4v4m-5-8h10a2 2 0 002-2V5a2 2 0 00-2-2H7a2 2 0 00-2 2v6a2 2 0 002 2z" />
  </svg>
);

const IconTrendingUp = ({ size = 16, color = "var(--green)" }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
    <path d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
  </svg>
);

const IconAlertTriangle = ({ size = 16, color = "#ef4444" }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
    <path d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
  </svg>
);

const IconLightbulb = ({ size = 16, color = "var(--brand)" }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
    <path d="M9.663 17h4.674M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 01-2 2h0a2 2 0 01-2-2v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
  </svg>
);

const IconFileText = ({ size = 16, color = "var(--text-secondary)" }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
    <path d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
  </svg>
);

const IconCheckCircle = ({ size = 16, color = "var(--green)" }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
    <path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
  </svg>
);

const IconClock = ({ size = 14, color = "var(--text-secondary)" }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
    <path d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
  </svg>
);

const IconExternalLink = ({ size = 12, color = "currentColor" }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
    <path d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
  </svg>
);

const IconRefreshCw = ({ size = 14, color = "currentColor", className = "" }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className} style={{ flexShrink: 0 }}>
    <path d="M23 4v6h-6M1 20v-6h6M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15" />
  </svg>
);

const LOADING_STAGES = [
  { step: 1, label: "Understanding Target Company Profile" },
  { step: 2, label: "Classifying Primary Industry & Business Domain" },
  { step: 3, label: "Searching Industry Peers & Competitors" },
  { step: 4, label: "Verifying Official Corporate Websites" },
  { step: 5, label: "Building Head-to-Head Comparison Matrix" },
  { step: 6, label: "Generating Strategic SWOT Analysis" },
  { step: 7, label: "Preparing Top 5 Recommendations" },
  { step: 8, label: "Building Executive Comparative Report" }
];

const NAV_ITEMS = [
  { id: "sec-overview", label: "Overview", icon: IconFileText },
  { id: "sec-company", label: "Company", icon: IconBuilding },
  { id: "sec-competitors", label: "Competitors", icon: IconTrophy },
  { id: "sec-comparison", label: "Comparison", icon: IconBuilding },
  { id: "sec-swot", label: "SWOT", icon: IconTrendingUp },
  { id: "sec-gaps", label: "Improvement Areas", icon: IconAlertTriangle },
  { id: "sec-recommendations", label: "Recommendations", icon: IconLightbulb },
  { id: "sec-references", label: "References", icon: IconGlobe }
];

function ComparativeAnalysisInnerView({ data, isRunning = false, currentStage = '', id, onRerun }) {
  const [activeGapCategory, setActiveGapCategory] = useState('ALL');
  const [evidenceOpen, setEvidenceOpen] = useState(false);
  const [activeNav, setActiveNav] = useState("sec-overview");
  const [reRunning, setReRunning] = useState(false);

  const payload = data?.data || data || {};
  const company = payload.company_profile || {};
  const competitorsData = payload.competitors || payload.competitor_profiles || {};
  const competitors = Array.isArray(competitorsData) ? competitorsData : (competitorsData.competitors || []);
  const matrixData = payload.comparative_matrix || payload.comparative_analysis || {};
  const featureMatrix = matrixData.feature_matrix || (Array.isArray(matrixData) ? matrixData : []);
  const swot = matrixData.swot_analysis || payload.swot_analysis || {};
  const gapData = payload.gap_analysis || {};
  const recommendations = Array.isArray(payload.recommendations) ? payload.recommendations : (payload.strategic_recommendations || []);

  const isGenerating = data?.metadata?.status === "generating" || payload?.metadata?.status === "generating";
  const hasData = !!(company.company_name || company.primary_industry || competitors.length > 0);

  if (isRunning || (isGenerating && !hasData)) {
    return (
      <div style={styles.loadingContainer}>
        <div style={styles.spinner} />
        <div style={{ textAlign: "center" }}>
          <h3 style={{ margin: 0, fontSize: 18, fontWeight: 700, color: "var(--brand)" }}>Synthesizing Executive Comparative Report...</h3>
          <p style={{ margin: "4px 0 0", fontSize: 13, color: styles.theme.bodyText }}>{currentStage || 'Executing multi-agent corporate intelligence workflow'}</p>
        </div>

        <div style={styles.loadingBox}>
          {LOADING_STAGES.map((s) => (
            <div key={s.step} style={styles.loadingStepRow}>
              <span style={styles.stepNum}>{s.step}</span>
              <span>{s.label}</span>
            </div>
          ))}
        </div>
      </div>
    );
  }

  // Requirement 1: Header MUST ALWAYS start with the detected Company Name as the largest element
  const companyName = company.company_name && company.company_name !== "Not specified"
    ? company.company_name
    : "Target Company";

  const primaryIndustry = company.primary_industry && company.primary_industry !== "Not specified"
    ? company.primary_industry
    : "Not specified";

  const secondaryIndustries = (company.secondary_industries || []).filter(i => i && i !== "Not specified");
  const documentName = payload.source_filename || data?.metadata?.filename || "Uploaded Document";
  const dateFormatted = data?.completed_at || new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });

  const scrollToSection = (id) => {
    setActiveNav(id);
    const el = document.getElementById(id);
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  };

  const renderEmptyState = (msg = "Information not available in the uploaded document.") => (
    <div style={styles.emptyState}>
      <span style={styles.dotMuted} />
      {msg}
    </div>
  );

  const renderPillList = (items) => {
    if (!items || !Array.isArray(items) || items.length === 0) {
      return renderEmptyState();
    }
    const filtered = items.filter(i => i && i !== "Not specified");
    if (filtered.length === 0) {
      return renderEmptyState();
    }

    return (
      <div style={styles.pillWrap}>
        {filtered.map((item, idx) => (
          <span key={idx} style={styles.pillItem}>
            {item}
          </span>
        ))}
      </div>
    );
  };

  const renderMatrixBadge = (val) => {
    if (!val || val === '—' || val === 'Not specified' || val === 'N/A') {
      return <span style={{ color: "#94A3B8", fontWeight: 700 }}>✕</span>;
    }
    const valLower = String(val).toLowerCase();
    if (valLower.includes("partial") || valLower.includes("moderate") || valLower.includes("limited")) {
      return <span style={{ padding: "2px 8px", background: "#FEF3C7", color: "#D97706", borderRadius: 4, fontSize: 11, fontWeight: 700 }}>Partial</span>;
    }
    if (valLower.includes("✓") || valLower.includes("available") || valLower.includes("yes") || valLower.includes("high") || valLower.includes("full") || valLower.includes("strong")) {
      return <span style={{ padding: "2px 8px", background: "#E4F9EC", color: "#22C55E", borderRadius: 4, fontSize: 11, fontWeight: 700 }}>✓ Available</span>;
    }
    return <span style={{ fontSize: 12, fontWeight: 600, color: "#1E293B" }}>{val}</span>;
  };

  const allGaps = [
    ...(gapData.service_gaps || []),
    ...(gapData.technology_gaps || []),
    ...(gapData.product_gaps || []),
    ...(gapData.market_gaps || []),
    ...(gapData.geographic_gaps || []),
  ];

  const gapCategories = ['ALL', 'Technology', 'Products', 'Markets', 'Services', 'Capabilities'];
  const filteredGaps = activeGapCategory === 'ALL'
    ? allGaps
    : allGaps.filter(g => (g.category || '').toLowerCase().includes(activeGapCategory.toLowerCase()));

  // Capped at max 5 bullet points per quadrant with safe array type checking
  const rawStrengths = swot.strengths_vs_competitors || company.business_strengths || [];
  const strengthsList = Array.isArray(rawStrengths) ? rawStrengths.slice(0, 5) : (typeof rawStrengths === 'string' ? [rawStrengths] : []);

  const rawWeaknesses = swot.weaknesses_vs_competitors || [];
  const weaknessesList = Array.isArray(rawWeaknesses) ? rawWeaknesses.slice(0, 5) : (typeof rawWeaknesses === 'string' ? [rawWeaknesses] : []);

  const rawOpportunities = swot.opportunities_in_market || [];
  const opportunitiesList = Array.isArray(rawOpportunities) ? rawOpportunities.slice(0, 5) : (typeof rawOpportunities === 'string' ? [rawOpportunities] : []);

  const rawThreats = swot.threats_from_competitors || [];
  const threatsList = Array.isArray(rawThreats) ? rawThreats.slice(0, 5) : (typeof rawThreats === 'string' ? [rawThreats] : []);

  const handleReRun = async () => {
    const docId = id || payload?.document_job_id || payload?.id;
    if (!docId) return;
    setReRunning(true);
    try {
      await fetch(`/api/comparative-analysis/run/${docId}`, { method: 'POST' });
      if (onRerun) onRerun();
      setTimeout(() => window.location.reload(), 4000);
    } catch (err) {
      console.error(err);
      setReRunning(false);
    }
  };

  return (
    <div style={styles.pageWrap}>

      {/* Requirement 16: Sticky Section Navigator at Top */}
      <div style={styles.navBar}>
        {NAV_ITEMS.map((item) => {
          const IconComponent = item.icon;
          const isActive = activeNav === item.id;
          return (
            <button
              key={item.id}
              onClick={() => scrollToSection(item.id)}
              style={{
                ...styles.navBtn,
                ...(isActive ? styles.navBtnActive : {})
              }}
            >
              <IconComponent size={14} color={isActive ? "#FFFFFF" : "var(--brand)"} />
              <span>{item.label}</span>
            </button>
          );
        })}
      </div>

      <div style={styles.container}>

        {/* 1. REPORT HEADER: Detected Company Name is LARGEST element */}
        <div style={styles.headerCard}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16 }}>
            <div>
              <span style={styles.headerTag}>EXECUTIVE COMPARATIVE ANALYSIS REPORT</span>
              <h1 style={styles.companyTitle}>{companyName}</h1>
            </div>
            <button
              onClick={handleReRun}
              disabled={reRunning}
              style={{
                background: "var(--brand)",
                color: "#FFFFFF",
                border: "none",
                borderRadius: 6,
                padding: "8px 16px",
                fontSize: 12,
                fontWeight: 700,
                cursor: reRunning ? "wait" : "pointer",
                display: "flex",
                alignItems: "center",
                gap: 6,
                boxShadow: "0 2px 4px rgba(0,0,0,0.1)"
              }}
            >
              <IconRefreshCw size={14} color="#FFFFFF" className={reRunning ? "spin" : ""} />
              <span>{reRunning ? "Re-generating..." : "↻ Re-run Comparative Report"}</span>
            </button>
          </div>

          <div style={styles.badgeRow}>
            <div style={styles.badgePill}>
              <IconGlobe size={14} color="var(--brand)" />
              <span>{primaryIndustry}</span>
            </div>

            {secondaryIndustries.map((sec, i) => (
              <div key={i} style={styles.badgePillMuted}>
                <span>{sec}</span>
              </div>
            ))}

            <div style={styles.badgePillMuted}>
              <IconFileText size={14} color={styles.theme.bodyText} />
              <span>{documentName}</span>
            </div>

            <div style={styles.badgePillMuted}>
              <IconClock size={14} color={styles.theme.bodyText} />
              <span>{dateFormatted}</span>
            </div>

            <div style={{ ...styles.badgePill, background: "#E4F9EC", color: "#22C55E", border: "1px solid rgba(34,197,94,0.2)" }}>
              <IconCheckCircle size={14} color="#22C55E" />
              <span>Analysis Complete</span>
            </div>

            <div style={{ ...styles.badgePill, background: "#E0F2FE", color: "#0369A1", border: "1px solid rgba(3,105,161,0.2)" }}>
              <IconTrophy size={14} color="#0369A1" />
              <span>{competitors.length} Competitors Benchmarked</span>
            </div>
          </div>
        </div>

        {/* 2. HERO DASHBOARD (Clean KPI Cards) */}
        <div style={styles.kpiGrid}>
          <div style={styles.kpiCard}>
            <span style={styles.kpiLabel}>Company Profile</span>
            <div style={styles.kpiValueRow}>
              <IconCheckCircle size={16} color="#22C55E" />
              <span style={styles.kpiValue}>Generated</span>
            </div>
          </div>
          <div style={styles.kpiCard}>
            <span style={styles.kpiLabel}>Industry Sector</span>
            <div style={styles.kpiValueRow}>
              <IconGlobe size={16} color="var(--brand)" />
              <span style={styles.kpiValueText}>{primaryIndustry}</span>
            </div>
          </div>
          <div style={styles.kpiCard}>
            <span style={styles.kpiLabel}>Competitors</span>
            <div style={styles.kpiValueRow}>
              <IconTrophy size={16} color="#D97706" />
              <span style={styles.kpiValue}>{competitors.length} Analysed</span>
            </div>
          </div>
          <div style={styles.kpiCard}>
            <span style={styles.kpiLabel}>SWOT Matrix</span>
            <div style={styles.kpiValueRow}>
              <IconTrendingUp size={16} color="#22C55E" />
              <span style={styles.kpiValue}>Completed</span>
            </div>
          </div>
          <div style={styles.kpiCard}>
            <span style={styles.kpiLabel}>Recommendations</span>
            <div style={styles.kpiValueRow}>
              <IconLightbulb size={16} color="var(--brand)" />
              <span style={styles.kpiValue}>{recommendations.length} Actions</span>
            </div>
          </div>
          <div style={styles.kpiCard}>
            <span style={styles.kpiLabel}>Pipeline Status</span>
            <div style={styles.kpiValueRow}>
              <IconCheckCircle size={16} color="#22C55E" />
              <span style={styles.kpiValueStatus}>Complete</span>
            </div>
          </div>
        </div>

        {/* FINAL REPORT SECTION STRUCTURE (Requirement 19) */}
        <div style={styles.sectionsList}>

          {/* SECTION 1: EXECUTIVE SUMMARY */}
          <section id="sec-overview" style={styles.cardSection}>
            <div style={styles.sectionTitleRow}>
              <div style={styles.iconBox}>
                <IconFileText size={16} color="var(--brand)" />
              </div>
              <div>
                <h2 style={styles.sectionTitle}>1. Executive Summary</h2>
                <p style={styles.sectionSub}>Concise executive business overview</p>
              </div>
            </div>

            <p style={styles.summaryText}>
              {company.executive_summary && company.executive_summary !== "Not specified"
                ? company.executive_summary
                : "Information not available in the uploaded document."}
            </p>

            <div style={styles.chipGrid}>
              <div style={styles.chipBox}>
                <span style={styles.chipHeading}>
                  <IconFolder size={12} color="var(--brand)" /> Business Domains
                </span>
                {renderPillList(company.business_domains)}
              </div>

              <div style={styles.chipBox}>
                <span style={styles.chipHeading}>
                  <IconBuilding size={12} color="var(--brand)" /> Core Services
                </span>
                {renderPillList(company.core_services)}
              </div>

              <div style={styles.chipBox}>
                <span style={styles.chipHeading}>
                  <IconCpu size={12} color="#4F46E5" /> Key Technologies
                </span>
                {renderPillList(company.technologies)}
              </div>

              <div style={styles.chipBox}>
                <span style={styles.chipHeading}>
                  <IconGlobe size={12} color="#0284C7" /> Primary Markets
                </span>
                {renderPillList(company.geographic_presence)}
              </div>
            </div>
          </section>

          {/* SECTION 2: TARGET COMPANY OVERVIEW */}
          <section id="sec-company" style={styles.cardSection}>
            <div style={styles.sectionTitleRow}>
              <div style={styles.iconBox}>
                <IconBuilding size={16} color="var(--brand)" />
              </div>
              <div>
                <h2 style={styles.sectionTitle}>2. Target Company Overview</h2>
                <p style={styles.sectionSub}>Structured capability cards and operational profile</p>
              </div>
            </div>

            <div style={styles.grid3Col}>
              <div style={styles.infoBox}>
                <div style={styles.infoHeading}>
                  <IconFileText size={14} color="var(--brand)" />
                  <span>Company Description</span>
                </div>
                <p style={styles.infoValueText}>{company.company_description || "Information not available in the uploaded document."}</p>
              </div>

              <div style={styles.infoBox}>
                <div style={styles.infoHeading}>
                  <IconGlobe size={14} color="var(--brand)" />
                  <span>Primary Industry</span>
                </div>
                <p style={styles.infoValue}>{primaryIndustry}</p>
              </div>

              <div style={styles.infoBox}>
                <div style={styles.infoHeading}>
                  <IconFolder size={14} color="#0284C7" />
                  <span>Business Domains</span>
                </div>
                {renderPillList(company.business_domains)}
              </div>

              <div style={styles.infoBox}>
                <div style={styles.infoHeading}>
                  <IconBuilding size={14} color="var(--brand)" />
                  <span>Core Services</span>
                </div>
                {renderPillList(company.core_services)}
              </div>

              <div style={styles.infoBox}>
                <div style={styles.infoHeading}>
                  <IconCpu size={14} color="#4F46E5" />
                  <span>Products & Platforms</span>
                </div>
                {renderPillList(company.products)}
              </div>

              <div style={styles.infoBox}>
                <div style={styles.infoHeading}>
                  <IconCpu size={14} color="#0284C7" />
                  <span>Technologies & Stack</span>
                </div>
                {renderPillList(company.technologies)}
              </div>

              <div style={styles.infoBox}>
                <div style={styles.infoHeading}>
                  <IconRocket size={14} color="#22C55E" />
                  <span>Major Projects</span>
                </div>
                {renderPillList(company.major_projects)}
              </div>

              <div style={styles.infoBox}>
                <div style={styles.infoHeading}>
                  <IconGlobe size={14} color="#D97706" />
                  <span>Geographic Presence</span>
                </div>
                {renderPillList(company.geographic_presence)}
              </div>

              <div style={styles.infoBox}>
                <div style={styles.infoHeading}>
                  <IconCheckCircle size={14} color="#22C55E" />
                  <span>Business Strengths</span>
                </div>
                {renderPillList(company.business_strengths)}
              </div>

              <div style={styles.infoBox}>
                <div style={styles.infoHeading}>
                  <IconTrophy size={14} color="#D97706" />
                  <span>Competitive Advantages</span>
                </div>
                {renderPillList(company.competitive_advantages)}
              </div>
            </div>
          </section>

          {/* SECTION 3: INDUSTRY & SIMILAR COMPANIES */}
          <section id="sec-competitors" style={styles.cardSection}>
            <div style={styles.sectionTitleRow}>
              <div style={styles.iconBox}>
                <IconTrophy size={16} color="#D97706" />
              </div>
              <div>
                <h2 style={styles.sectionTitle}>3. Industry & Similar Companies</h2>
                <p style={styles.sectionSub}>Verified corporate competitor benchmarks (Max 5)</p>
              </div>
            </div>

            {competitors.length > 0 ? (
              <div style={styles.grid2Col}>
                {competitors.slice(0, 5).map((comp, idx) => {
                  const domain = comp.official_website && comp.official_website !== "Not specified"
                    ? comp.official_website.replace(/^https?:\/\//, '').split('/')[0]
                    : "";
                  const faviconUrl = domain ? `https://www.google.com/s2/favicons?domain=${domain}&sz=64` : null;

                  return (
                    <div key={idx} style={styles.compCard}>
                      <div style={styles.compHeader}>
                        <div style={styles.compLeft}>
                          {faviconUrl ? (
                            <img src={faviconUrl} alt="logo" style={styles.logoImg} />
                          ) : (
                            <div style={styles.rankBadge}>#{idx + 1}</div>
                          )}
                          <div>
                            <h3 style={styles.compName}>{comp.company_name}</h3>
                            <span style={styles.compSub}>{comp.industry || primaryIndustry}</span>
                          </div>
                        </div>

                        {comp.official_website && comp.official_website !== "Not specified" && (
                          <a href={comp.official_website} target="_blank" rel="noreferrer" style={styles.siteBtn}>
                            <span>Website</span>
                            <IconExternalLink size={11} />
                          </a>
                        )}
                      </div>

                      <p style={styles.compDesc}>
                        {comp.executive_summary || comp.company_description || "Information not available in the uploaded document."}
                      </p>

                      <div style={styles.compMetaRow}>
                        <span style={styles.compMetaLabel}>Geography:</span>
                        <span style={styles.compMetaVal}>
                          {Array.isArray(comp.geographic_presence) 
                            ? comp.geographic_presence.join(", ") 
                            : (typeof comp.geographic_presence === "string" ? comp.geographic_presence : "Global")}
                        </span>
                      </div>

                      {comp.core_services && (Array.isArray(comp.core_services) ? comp.core_services.length > 0 : typeof comp.core_services === "string") && (
                        <div style={{ paddingTop: 6, borderTop: "1px solid #E2E8F0" }}>
                          <span style={styles.compHeading}>Key Services</span>
                          {renderPillList(Array.isArray(comp.core_services) ? comp.core_services : [comp.core_services])}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            ) : (
              renderEmptyState()
            )}
          </section>

          {/* SECTION 4: COMPARATIVE ANALYSIS MATRIX */}
          <section id="sec-comparison" style={styles.cardSection}>
            <div style={styles.sectionTitleRow}>
              <div style={styles.iconBox}>
                <IconBuilding size={16} color="var(--brand)" />
              </div>
              <div>
                <h2 style={styles.sectionTitle}>4. Comparative Analysis Matrix</h2>
                <p style={styles.sectionSub}>Centerpiece head-to-head capability comparison</p>
              </div>
            </div>

            {featureMatrix.length > 0 ? (
              <div style={styles.tableWrap}>
                <table style={styles.table}>
                  <thead>
                    <tr style={styles.thRow}>
                      <th style={styles.thSticky}>Dimension</th>
                      <th style={styles.thTarget}>{companyName} (Target)</th>
                      {competitors.slice(0, 4).map((c, i) => (
                        <th key={i} style={styles.th}>{c.company_name}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {featureMatrix.map((row, idx) => (
                      <tr key={idx} style={styles.tr}>
                        <td style={styles.tdSticky}>{row.dimension}</td>
                        <td style={styles.tdTarget}>
                          {renderMatrixBadge(row.target_company_val || row.target_company_score || '✓ Available')}
                        </td>
                        {competitors.slice(0, 4).map((c, i) => (
                          <td key={i} style={styles.td}>
                            {renderMatrixBadge(row.competitor_scores?.[c.company_name])}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              renderEmptyState()
            )}
          </section>

          {/* SECTION 5: SWOT ANALYSIS (4 equal quadrant cards, max 5 bullets per quadrant) */}
          <section id="sec-swot" style={styles.cardSection}>
            <div style={styles.sectionTitleRow}>
              <div style={styles.iconBox}>
                <IconTrendingUp size={16} color="#22C55E" />
              </div>
              <h2 style={styles.sectionTitle}>5. SWOT Analysis</h2>
            </div>

            <div style={styles.grid2Col}>
              <div style={{ ...styles.swotBox, borderColor: "rgba(34,197,94,0.3)" }}>
                <div style={{ ...styles.swotHeader, color: "#22C55E" }}>
                  <IconTrendingUp size={16} color="#22C55E" />
                  <span>Strengths</span>
                </div>
                {strengthsList.length > 0 ? (
                  <ul style={styles.swotList}>
                    {strengthsList.map((s, idx) => (
                      <li key={idx} style={styles.swotItem}>
                        <span style={{ ...styles.swotDot, background: "#22C55E" }} />
                        <span>{s}</span>
                      </li>
                    ))}
                  </ul>
                ) : renderEmptyState()}
              </div>

              <div style={{ ...styles.swotBox, borderColor: "rgba(239,68,68,0.3)" }}>
                <div style={{ ...styles.swotHeader, color: "#EF4444" }}>
                  <IconAlertTriangle size={16} color="#EF4444" />
                  <span>Weaknesses</span>
                </div>
                {weaknessesList.length > 0 ? (
                  <ul style={styles.swotList}>
                    {weaknessesList.map((w, idx) => (
                      <li key={idx} style={styles.swotItem}>
                        <span style={{ ...styles.swotDot, background: "#EF4444" }} />
                        <span>{w}</span>
                      </li>
                    ))}
                  </ul>
                ) : renderEmptyState()}
              </div>

              <div style={{ ...styles.swotBox, borderColor: "rgba(2,132,199,0.3)" }}>
                <div style={{ ...styles.swotHeader, color: "#0284C7" }}>
                  <IconRocket size={16} color="#0284C7" />
                  <span>Opportunities</span>
                </div>
                {opportunitiesList.length > 0 ? (
                  <ul style={styles.swotList}>
                    {opportunitiesList.map((o, idx) => (
                      <li key={idx} style={styles.swotItem}>
                        <span style={{ ...styles.swotDot, background: "#0284C7" }} />
                        <span>{o}</span>
                      </li>
                    ))}
                  </ul>
                ) : renderEmptyState()}
              </div>

              <div style={{ ...styles.swotBox, borderColor: "rgba(217,119,6,0.3)" }}>
                <div style={{ ...styles.swotHeader, color: "#D97706" }}>
                  <IconAlertTriangle size={16} color="#D97706" />
                  <span>Threats</span>
                </div>
                {threatsList.length > 0 ? (
                  <ul style={styles.swotList}>
                    {threatsList.map((t, idx) => (
                      <li key={idx} style={styles.swotItem}>
                        <span style={{ ...styles.swotDot, background: "#D97706" }} />
                        <span>{t}</span>
                      </li>
                    ))}
                  </ul>
                ) : renderEmptyState()}
              </div>
            </div>
          </section>

          {/* SECTION 6: KEY AREAS OF IMPROVEMENT */}
          <section id="sec-gaps" style={styles.cardSection}>
            <div style={styles.gapHeaderRow}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <div style={styles.iconBox}>
                  <IconAlertTriangle size={16} color="#D97706" />
                </div>
                <h2 style={styles.sectionTitle}>6. Key Areas of Improvement</h2>
              </div>

              <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                {gapCategories.map((cat) => (
                  <button
                    key={cat}
                    onClick={() => setActiveGapCategory(cat)}
                    style={{
                      ...styles.catTab,
                      ...(activeGapCategory === cat ? styles.catTabActive : {})
                    }}
                  >
                    {cat}
                  </button>
                ))}
              </div>
            </div>

            {filteredGaps.length > 0 ? (
              <div style={styles.grid2Col}>
                {filteredGaps.map((gap, idx) => (
                  <div key={idx} style={styles.gapCard}>
                    <div style={styles.gapTop}>
                      <span style={styles.gapCat}>{gap.category || "Capability"}</span>
                      {gap.business_risk && (
                        <span style={(gap.business_risk || '').toLowerCase() === 'high' ? styles.riskHigh : styles.riskMed}>
                          Priority: {gap.business_risk}
                        </span>
                      )}
                    </div>
                    <h4 style={styles.gapTitle}>{gap.gap_title}</h4>
                    <p style={styles.gapDesc}><strong>Observation:</strong> {gap.description}</p>
                    {gap.suggested_improvement && (
                      <p style={{ ...styles.gapDesc, color: "var(--brand)", fontWeight: 600 }}>
                        <strong>Suggested Improvement:</strong> {gap.suggested_improvement}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              renderEmptyState()
            )}
          </section>

          {/* SECTION 7: STRATEGIC RECOMMENDATIONS (Top 5 Cards) */}
          <section id="sec-recommendations" style={styles.cardSection}>
            <div style={styles.sectionTitleRow}>
              <div style={styles.iconBox}>
                <IconLightbulb size={16} color="var(--brand)" />
              </div>
              <div>
                <h2 style={styles.sectionTitle}>7. Strategic Recommendations</h2>
                <p style={styles.sectionSub}>Top 5 evidence-backed recommendations for executive decision support</p>
              </div>
            </div>

            {recommendations.length > 0 ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                {recommendations.slice(0, 5).map((rec, idx) => (
                  <div key={idx} style={styles.recCard}>
                    <div style={styles.recTop}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <span style={styles.recNum}>0{idx + 1}</span>
                        <span style={styles.recId}>REC-00{idx + 1}</span>
                      </div>
                      <span style={(rec.priority || '').toLowerCase() === 'high' ? styles.riskHigh : styles.riskMed}>
                        Priority: {rec.priority || 'Medium'}
                      </span>
                    </div>

                    <h3 style={styles.recTitle}>{rec.title || rec.suggested_action}</h3>

                    <div style={styles.grid2Col}>
                      <div style={styles.recSubBox}>
                        <span style={styles.recHeading}>Observation</span>
                        <p style={styles.recText}>{rec.observation || rec.rationale || "Identified during competitive benchmarking"}</p>
                      </div>

                      <div style={{ ...styles.recSubBox, background: "#E4F9EC", borderColor: "rgba(34,197,94,0.2)" }}>
                        <span style={{ ...styles.recHeading, color: "#22C55E" }}>Supporting Evidence</span>
                        <p style={{ ...styles.recText, color: "#22C55E" }}>{rec.supporting_evidence || "Verified benchmark evidence"}</p>
                      </div>
                    </div>

                    <div style={styles.grid2Col}>
                      <div style={styles.recSubBox}>
                        <span style={styles.recHeading}>Business Impact</span>
                        <p style={styles.recText}>{rec.business_impact || rec.expected_impact || "Accelerates market differentiation"}</p>
                      </div>

                      <div style={styles.recSubBox}>
                        <span style={styles.recHeading}>Suggested Action</span>
                        <p style={styles.recText}>{rec.suggested_action || rec.title}</p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              renderEmptyState()
            )}
          </section>

          {/* SECTION 8: REFERENCES & SUPPORTING EVIDENCE */}
          <section id="sec-references" style={styles.cardSection}>
            <button onClick={() => setEvidenceOpen(!evidenceOpen)} style={styles.accordionBtn}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <div style={styles.iconBox}>
                  <IconGlobe size={16} color="var(--brand)" />
                </div>
                <div>
                  <h2 style={{ ...styles.sectionTitle, margin: 0 }}>8. References & Supporting Evidence</h2>
                  <p style={{ ...styles.sectionSub, margin: "2px 0 0" }}>Source document and verified corporate domain references</p>
                </div>
              </div>
              <span style={styles.toggleBadge}>
                {evidenceOpen ? 'Hide References ▲' : 'Show References ▼'}
              </span>
            </button>

            {evidenceOpen && (
              <div style={{ marginTop: 16, paddingTop: 16, borderTop: "1px solid #E2E8F0", display: "flex", flexDirection: "column", gap: 12 }}>
                
                <div style={styles.refGroup}>
                  <span style={styles.refHeading}>Uploaded Document</span>
                  <div style={styles.urlRow}>
                    <span>{documentName}</span>
                    <span style={styles.urlComp}>(Target Document)</span>
                  </div>
                </div>

                <div style={styles.refGroup}>
                  <span style={styles.refHeading}>Verified Company Websites</span>
                  {competitors.filter(c => c.official_website && c.official_website !== "Not specified").map((c, idx) => (
                    <div key={idx} style={styles.urlRow}>
                      <a href={c.official_website} target="_blank" rel="noreferrer" style={styles.urlLink}>
                        {c.official_website}
                      </a>
                      <span style={styles.urlComp}>({c.company_name})</span>
                    </div>
                  ))}
                </div>

              </div>
            )}
          </section>

        </div>
      </div>
    </div>
  );
}

class ComparativeAnalysisErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error("ComparativeAnalysisView caught rendering error:", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          padding: 32,
          background: "var(--bg-card, #ffffff)",
          border: "1px solid var(--border, #e2e8f0)",
          borderRadius: 12,
          textAlign: "center",
          margin: "20px 0"
        }}>
          <h3 style={{ color: "var(--brand, #4f46e5)", fontSize: 18, fontWeight: 700, marginBottom: 8 }}>
            Executive Comparative Analysis Summary
          </h3>
          <p style={{ color: "#475569", fontSize: 14, marginBottom: 16 }}>
            {this.state.error?.message || "Render caught an exception while processing comparative data structure."}
          </p>
          <button
            onClick={() => {
              this.setState({ hasError: false, error: null });
              if (this.props.onRerun) this.props.onRerun();
            }}
            style={{
              background: "var(--brand, #4f46e5)",
              color: "#ffffff",
              border: "none",
              padding: "10px 20px",
              borderRadius: 8,
              fontWeight: 600,
              cursor: "pointer"
            }}
          >
            Reload View
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

export default function ComparativeAnalysisView(props) {
  return (
    <ComparativeAnalysisErrorBoundary onRerun={props.onRerun}>
      <ComparativeAnalysisInnerView {...props} />
    </ComparativeAnalysisErrorBoundary>
  );
}

const styles = {
  theme: {
    bg: "#F8FAFC",
    card: "#FFFFFF",
    headerText: "#1E293B",
    bodyText: "#475569",
    border: "#E2E8F0"
  },

  pageWrap: { background: "#F8FAFC", minHeight: "100vh", paddingBottom: 40 },

  navBar: {
    position: "sticky",
    top: 0,
    zIndex: 20,
    background: "#FFFFFF",
    borderBottom: "1px solid #E2E8F0",
    padding: "8px 16px",
    display: "flex",
    gap: 8,
    overflowX: "auto",
    boxShadow: "0 1px 3px rgba(0,0,0,0.05)"
  },
  navBtn: {
    display: "inline-flex",
    alignItems: "center",
    gap: 6,
    padding: "6px 12px",
    background: "#F8FAFC",
    border: "1px solid #E2E8F0",
    borderRadius: 8,
    fontSize: 12,
    fontWeight: 600,
    color: "#475569",
    cursor: "pointer",
    whiteSpace: "nowrap",
    transition: "all 0.15s ease"
  },
  navBtnActive: {
    background: "var(--brand)",
    color: "#FFFFFF",
    borderColor: "var(--brand)"
  },

  container: { display: "flex", flexDirection: "column", gap: 20, width: "100%", maxWidth: 1200, margin: "20px auto 0", padding: "0 16px" },
  
  loadingContainer: { display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", minHeight: 400, gap: 16 },
  spinner: { width: 36, height: 36, borderRadius: "50%", border: "3px solid #E2E8F0", borderTopColor: "var(--brand)", animation: "spin 0.8s linear infinite" },
  loadingBox: { width: "100%", maxWidth: 440, background: "#FFFFFF", border: "1px solid #E2E8F0", borderRadius: 12, padding: 16, display: "flex", flexDirection: "column", gap: 8 },
  loadingStepRow: { display: "flex", alignItems: "center", gap: 10, fontSize: 12, color: "#475569" },
  stepNum: { width: 20, height: 20, borderRadius: "50%", background: "var(--brand-light)", color: "var(--brand)", fontWeight: 700, fontSize: 10, display: "flex", alignItems: "center", justifyContent: "center" },

  headerCard: { background: "#FFFFFF", border: "1px solid #E2E8F0", borderLeft: "5px solid var(--brand)", borderRadius: 12, padding: "20px 24px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" },
  headerTag: { fontSize: 10, fontWeight: 800, color: "var(--brand)", background: "var(--brand-light)", padding: "2px 8px", borderRadius: 4, letterSpacing: "0.5px" },
  companyTitle: { margin: "6px 0 10px", fontSize: 28, fontWeight: 800, color: "#1E293B", letterSpacing: "-0.5px" },
  badgeRow: { display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" },
  badgePill: { display: "inline-flex", alignItems: "center", gap: 6, padding: "4px 10px", background: "var(--brand-light)", color: "var(--brand)", borderRadius: 8, fontSize: 12, fontWeight: 600, border: "1px solid rgba(108,92,231,0.2)" },
  badgePillMuted: { display: "inline-flex", alignItems: "center", gap: 6, padding: "4px 10px", background: "#F8FAFC", color: "#475569", borderRadius: 8, fontSize: 12, fontWeight: 500, border: "1px solid #E2E8F0" },

  kpiGrid: { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 12 },
  kpiCard: { background: "#FFFFFF", border: "1px solid #E2E8F0", borderRadius: 10, padding: "12px 16px", display: "flex", flexDirection: "column", gap: 4, boxShadow: "0 1px 2px rgba(0,0,0,0.03)" },
  kpiLabel: { fontSize: 10.5, fontWeight: 700, color: "#94A3B8", textTransform: "uppercase" },
  kpiValueRow: { display: "flex", alignItems: "center", gap: 6 },
  kpiValue: { fontSize: 13.5, fontWeight: 800, color: "#1E293B" },
  kpiValueText: { fontSize: 12.5, fontWeight: 700, color: "#1E293B", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" },
  kpiValueStatus: { fontSize: 13, fontWeight: 800, color: "#22C55E" },

  sectionsList: { display: "flex", flexDirection: "column", gap: 20 },
  cardSection: { background: "#FFFFFF", border: "1px solid #E2E8F0", borderRadius: 12, padding: 20, boxShadow: "0 1px 3px rgba(0,0,0,0.04)" },
  sectionTitleRow: { display: "flex", alignItems: "center", gap: 10, marginBottom: 16, borderBottom: "1px solid #E2E8F0", paddingBottom: 10 },
  iconBox: { width: 30, height: 30, borderRadius: 8, background: "var(--brand-light)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 },
  sectionTitle: { margin: 0, fontSize: 16, fontWeight: 800, color: "#1E293B" },
  sectionSub: { margin: "2px 0 0", fontSize: 12, color: "#475569" },

  summaryText: { margin: 0, fontSize: 13.5, lineHeight: 1.6, color: "#475569", marginBottom: 14 },
  chipGrid: { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 10, paddingTop: 10, borderTop: "1px solid #E2E8F0" },
  chipBox: { background: "#F8FAFC", border: "1px solid #E2E8F0", borderRadius: 8, padding: 10 },
  chipHeading: { fontSize: 10.5, fontWeight: 700, color: "#475569", textTransform: "uppercase", display: "flex", alignItems: "center", gap: 4, marginBottom: 4 },

  grid3Col: { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 12 },
  grid2Col: { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: 12 },
  
  infoBox: { background: "#F8FAFC", border: "1px solid #E2E8F0", borderRadius: 8, padding: 12 },
  infoHeading: { display: "flex", alignItems: "center", gap: 6, fontSize: 11, fontWeight: 700, color: "#475569", textTransform: "uppercase", marginBottom: 6 },
  infoValue: { margin: 0, fontSize: 13, fontWeight: 600, color: "#1E293B" },
  infoValueText: { margin: 0, fontSize: 12.5, lineHeight: 1.5, color: "#475569" },

  emptyState: { padding: 10, background: "#F8FAFC", border: "1px solid #E2E8F0", borderRadius: 6, fontSize: 12, color: "#94A3B8", fontStyle: "italic", display: "flex", alignItems: "center", gap: 6 },
  dotMuted: { width: 6, height: 6, borderRadius: "50%", background: "#94A3B8", display: "inline-block" },

  pillWrap: { display: "flex", flexWrap: "wrap", gap: 6, marginTop: 4 },
  pillItem: { padding: "2px 8px", background: "var(--brand-light)", color: "var(--brand)", borderRadius: 6, fontSize: 11.5, fontWeight: 600, border: "1px solid rgba(108,92,231,0.15)" },

  compCard: { background: "#F8FAFC", border: "1px solid #E2E8F0", borderRadius: 10, padding: 16, display: "flex", flexDirection: "column", gap: 10 },
  compHeader: { display: "flex", justifyContent: "space-between", alignItems: "center" },
  compLeft: { display: "flex", alignItems: "center", gap: 10 },
  logoImg: { width: 24, height: 24, maxWidth: 24, maxHeight: 24, borderRadius: 4, objectFit: "contain", border: "1px solid #E2E8F0", background: "#fff", padding: 2 },
  rankBadge: { width: 24, height: 24, borderRadius: 6, background: "var(--brand-light)", color: "var(--brand)", fontWeight: 800, fontSize: 11, display: "flex", alignItems: "center", justifyContent: "center" },
  compName: { margin: 0, fontSize: 14, fontWeight: 700, color: "#1E293B" },
  compSub: { fontSize: 11, color: "var(--brand)", fontWeight: 600 },
  siteBtn: { display: "inline-flex", alignItems: "center", gap: 4, padding: "4px 8px", background: "var(--brand-light)", color: "var(--brand)", border: "1px solid rgba(108,92,231,0.2)", borderRadius: 6, fontSize: 11, fontWeight: 600 },
  compDesc: { margin: 0, fontSize: 12, lineHeight: 1.5, color: "#475569" },
  compMetaRow: { display: "flex", gap: 6, fontSize: 11.5 },
  compMetaLabel: { fontWeight: 700, color: "#475569" },
  compMetaVal: { color: "#1E293B" },
  compHeading: { fontSize: 10.5, fontWeight: 700, color: "#94A3B8", textTransform: "uppercase", display: "block", marginBottom: 4 },

  tableWrap: { overflowX: "auto", borderRadius: 8, border: "1px solid #E2E8F0" },
  table: { width: "100%", borderCollapse: "collapse", textAlign: "left", fontSize: 12.5 },
  thRow: { background: "#F8FAFC", borderBottom: "1px solid #E2E8F0" },
  thSticky: { position: "sticky", left: 0, background: "#F8FAFC", zIndex: 3, padding: "10px 12px", fontWeight: 700, fontSize: 11, color: "#475569", textTransform: "uppercase" },
  th: { padding: "10px 12px", fontWeight: 700, fontSize: 11, color: "#475569", textTransform: "uppercase" },
  thTarget: { padding: "10px 12px", fontWeight: 800, fontSize: 11, color: "var(--brand)", background: "var(--brand-light)", textTransform: "uppercase" },
  tr: { borderBottom: "1px solid #E2E8F0" },
  tdSticky: { position: "sticky", left: 0, background: "#FFFFFF", zIndex: 2, padding: "10px 12px", fontWeight: 700, color: "#1E293B" },
  tdTarget: { padding: "10px 12px", background: "var(--brand-light)", color: "var(--brand)", fontWeight: 600 },
  td: { padding: "10px 12px", color: "#475569" },

  swotBox: { background: "#F8FAFC", border: "1px solid #E2E8F0", borderRadius: 8, padding: 14, display: "flex", flexDirection: "column", gap: 8 },
  swotHeader: { display: "flex", alignItems: "center", gap: 6, fontSize: 13, fontWeight: 700, borderBottom: "1px solid #E2E8F0", paddingBottom: 6 },
  swotList: { margin: 0, padding: 0, listStyle: "none", display: "flex", flexDirection: "column", gap: 6 },
  swotItem: { display: "flex", alignItems: "flex-start", gap: 8, fontSize: 12, color: "#1E293B", lineHeight: 1.4 },
  swotDot: { width: 6, height: 6, borderRadius: "50%", marginTop: 5, flexShrink: 0 },

  gapHeaderRow: { display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, marginBottom: 16, borderBottom: "1px solid #E2E8F0", paddingBottom: 10, flexWrap: "wrap" },
  catTab: { background: "#F8FAFC", border: "1px solid #E2E8F0", borderRadius: 6, padding: "4px 10px", fontSize: 11.5, fontWeight: 600, color: "#475569", cursor: "pointer" },
  catTabActive: { background: "var(--brand)", color: "#fff", borderColor: "var(--brand)" },
  gapCard: { background: "#F8FAFC", borderLeft: "3px solid #D97706", border: "1px solid #E2E8F0", borderRadius: 8, padding: 12, display: "flex", flexDirection: "column", gap: 6 },
  gapTop: { display: "flex", justifyContent: "space-between", alignItems: "center" },
  gapCat: { fontSize: 10.5, fontWeight: 800, color: "#D97706", textTransform: "uppercase" },
  gapTitle: { margin: 0, fontSize: 13, fontWeight: 700, color: "#1E293B" },
  gapDesc: { margin: 0, fontSize: 12, color: "#475569", lineHeight: 1.4 },
  riskHigh: { padding: "2px 6px", borderRadius: 4, background: "#FEE2E2", color: "#EF4444", fontSize: 10.5, fontWeight: 700 },
  riskMed: { padding: "2px 6px", borderRadius: 4, background: "#FEF3C7", color: "#D97706", fontSize: 10.5, fontWeight: 700 },

  recCard: { background: "#F8FAFC", borderLeft: "3px solid #22C55E", border: "1px solid #E2E8F0", borderRadius: 10, padding: 16, display: "flex", flexDirection: "column", gap: 10 },
  recTop: { display: "flex", justifyContent: "space-between", alignItems: "center" },
  recNum: { width: 22, height: 22, borderRadius: 6, background: "#E4F9EC", color: "#22C55E", fontWeight: 800, fontSize: 11, display: "flex", alignItems: "center", justifyContent: "center" },
  recId: { fontSize: 11, fontWeight: 700, color: "#22C55E" },
  recTitle: { margin: 0, fontSize: 14, fontWeight: 700, color: "#1E293B" },
  recSubBox: { background: "#FFFFFF", border: "1px solid #E2E8F0", borderRadius: 6, padding: 10 },
  recHeading: { fontSize: 10.5, fontWeight: 700, color: "#475569", textTransform: "uppercase", display: "block", marginBottom: 2 },
  recText: { margin: 0, fontSize: 12, color: "#1E293B", lineHeight: 1.4 },

  accordionBtn: { width: "100%", background: "none", border: "none", padding: 0, display: "flex", justifyContent: "space-between", alignItems: "center", cursor: "pointer", textAlign: "left" },
  toggleBadge: { fontSize: 11.5, fontWeight: 700, color: "var(--brand)", background: "var(--brand-light)", padding: "4px 10px", borderRadius: 6 },
  refGroup: { display: "flex", flexDirection: "column", gap: 6 },
  refHeading: { fontSize: 11, fontWeight: 700, color: "#475569", textTransform: "uppercase" },
  urlRow: { padding: 8, background: "#F8FAFC", border: "1px solid #E2E8F0", borderRadius: 6, display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 12 },
  urlLink: { color: "var(--brand)", fontWeight: 600, textOverflow: "ellipsis", overflow: "hidden", whiteSpace: "nowrap" },
  urlComp: { color: "#475569", fontWeight: 500, flexShrink: 0 }
};
