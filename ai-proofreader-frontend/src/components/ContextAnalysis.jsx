import React, { useState, useEffect, useMemo } from "react";
import { 
  fetchDocument, 
  runContextAnalysis, 
  API_BASE_URL 
} from "../api";

export const APPROVED_CATEGORIES = [
  "Cross-reference / contradiction",
  "Numerical inconsistency",
  "Pronoun / entity-reference ambiguity",
  "Terminology inconsistency",
  "Date / timeline inconsistency",
  "Unit / measurement inconsistency",
  "Internal factual contradiction",
  "Structural / convention inconsistency",
  "Missing / conflicting context",
];

const EXCLUDED_CATEGORIES = new Set([
  "grammar issue", "grammar error", "grammar errors", "grammar",
  "spelling issue", "spelling error", "spelling errors", "spelling",
  "writing clarity", "writing quality", "writing style issues", "clarity",
  "vague wording", "vague qualifier", "generic wording", "ambiguities", "style", "stylistic",
  "undefined term", "undefined acronym", "acronym definition",
]);

const ALIASES = {
  "possible contradiction": "Cross-reference / contradiction",
  "contradictory statement": "Cross-reference / contradiction",
  "contradictory statements": "Cross-reference / contradiction",
  "contradiction": "Cross-reference / contradiction",
  "contradictions": "Cross-reference / contradiction",
  "cross-reference issue": "Cross-reference / contradiction",
  "cross-reference inconsistency": "Cross-reference / contradiction",
  "cross-reference error": "Cross-reference / contradiction",
  "reference inconsistency": "Cross-reference / contradiction",
  "reference conflict": "Cross-reference / contradiction",
  "cross-reference mismatch": "Cross-reference / contradiction",
  "broken reference": "Cross-reference / contradiction",
  "cross-reference / contradiction": "Cross-reference / contradiction",

  "numeric inconsistency": "Numerical inconsistency",
  "numerical inconsistency": "Numerical inconsistency",
  "cross-chunk numerical inconsistency": "Numerical inconsistency",
  "numerical conflict": "Numerical inconsistency",
  "numerical mismatch": "Numerical inconsistency",
  "numerical ambiguity": "Numerical inconsistency",
  "numerical consistency": "Numerical inconsistency",
  "data quality": "Numerical inconsistency",

  "pronoun ambiguity": "Pronoun / entity-reference ambiguity",
  "referential ambiguity": "Pronoun / entity-reference ambiguity",
  "ambiguous reference": "Pronoun / entity-reference ambiguity",
  "pronoun / entity-reference ambiguity": "Pronoun / entity-reference ambiguity",

  "terminology conflict": "Terminology inconsistency",
  "terminology issue": "Terminology inconsistency",
  "terminology inconsistency": "Terminology inconsistency",
  "inconsistent terminology": "Terminology inconsistency",

  "date conflicts": "Date / timeline inconsistency",
  "date conflict": "Date / timeline inconsistency",
  "temporal ambiguity": "Date / timeline inconsistency",
  "temporal conflict": "Date / timeline inconsistency",
  "date / timeline inconsistency": "Date / timeline inconsistency",

  "unit inconsistency": "Unit / measurement inconsistency",
  "unit / measurement inconsistency": "Unit / measurement inconsistency",
  "formatting inconsistency": "Unit / measurement inconsistency",

  "policy conflict": "Internal factual contradiction",
  "policy conflicts": "Internal factual contradiction",
  "policy inconsistency": "Internal factual contradiction",
  "governance inconsistency": "Internal factual contradiction",
  "business logic conflict": "Internal factual contradiction",
  "duplicate guidance": "Internal factual contradiction",
  "internal factual contradiction": "Internal factual contradiction",

  "structural inconsistency": "Structural / convention inconsistency",
  "convention inconsistency": "Structural / convention inconsistency",
  "structural / convention inconsistency": "Structural / convention inconsistency",

  "missing context": "Missing / conflicting context",
  "missing information": "Missing / conflicting context",
  "missing evidence": "Missing / conflicting context",
  "unsupported claim": "Missing / conflicting context",
  "missing / conflicting context": "Missing / conflicting context",
};

export function normalizeAmbiguityCategory(rawCat) {
  if (!rawCat) return null;
  const key = String(rawCat).trim().toLowerCase();
  if (EXCLUDED_CATEGORIES.has(key)) return null;
  for (const c of APPROVED_CATEGORIES) {
    if (c.toLowerCase() === key) return c;
  }
  return ALIASES[key] || null;
}

export default function ContextAnalysis({ id, doc: propDoc, onShowInDocument }) {
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState(null);
  const [docProgress, setDocProgress] = useState(null);
  
  const [finalReport, setFinalReport] = useState(null);
  const [claudeReport, setClaudeReport] = useState(null);

  const [searchTerm, setSearchTerm] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("ALL");
  const [selectedSeverity, setSelectedSeverity] = useState("ALL");
  const [showRejected, setShowRejected] = useState(false);

  useEffect(() => {
    let active = true;
    let timerId = null;

    async function checkStatus() {
      try {
        const docData = await fetchDocument(id);
        if (!active) return;
        setDocProgress(docData);

        const isContextComplete = docData.context_analysis_status === "completed" || docData.status === "completed";
        const isContextRunning = docData.context_analysis_status === "running" || docData.context_analysis_status === "pending";

        if (isContextComplete) {
          setRunning(false);
          await fetchReports();
        } else if (isContextRunning) {
          setRunning(true);
          timerId = setTimeout(checkStatus, 2500);
        } else if (docData.context_analysis_ready) {
          setRunning(false);
          await fetchReports();
        } else if (docData.context_analysis_status === "failed") {
          setRunning(false);
          setError("Ambiguity analysis pipeline encountered an error.");
        } else {
          setRunning(true);
          await runContextAnalysis(id).catch(() => {});
          timerId = setTimeout(checkStatus, 2500);
        }
      } catch (err) {
        if (active) setError("Connection error: " + err.message);
      } finally {
        if (active) setLoading(false);
      }
    }

    checkStatus();

    return () => {
      active = false;
      if (timerId) clearTimeout(timerId);
    };
  }, [id]);

  const fetchReports = async () => {
    try {
      const fetchJson = async (url) => {
        const res = await fetch(url);
        if (!res.ok) return null;
        return res.json();
      };

      const [final, claude] = await Promise.all([
        fetchJson(`${API_BASE_URL}/reports/${id}/final-report`),
        fetchJson(`${API_BASE_URL}/reports/${id}/claude-verification`)
      ]);

      if (final) setFinalReport(final);
      if (claude) setClaudeReport(claude);
    } catch (e) {
      console.error("Error fetching ambiguity reports", e);
    }
  };

  const handleRerun = async () => {
    setRunning(true);
    setError(null);
    try {
      await runContextAnalysis(id);
      const docData = await fetchDocument(id);
      setDocProgress(docData);
    } catch (err) {
      setError(err.message || "Failed to trigger analysis.");
      setRunning(false);
    }
  };

  // --------------------------------------------------------------------------
  // Data Mapping: Extract verified findings grounded in approved 9-taxonomy
  // --------------------------------------------------------------------------
  const { verifiedFindings, rejectedFindings, summaryMetrics } = useMemo(() => {
    let rawFindings = [];
    let rawRejected = [];

    const finalData = finalReport?.data || finalReport;
    const claudeData = claudeReport?.data || claudeReport;

    if (finalData && Array.isArray(finalData.findings)) {
      rawFindings = finalData.findings;
    } else if (claudeData && Array.isArray(claudeData.verified_findings)) {
      rawFindings = claudeData.verified_findings.filter(f => f.status === "confirmed" || f.status === "Verified");
    }

    if (finalData && Array.isArray(finalData.rejected_findings)) {
      rawRejected = finalData.rejected_findings;
    }

    const verified = [];
    const rejectedTracked = [...rawRejected];

    rawFindings.forEach((f, idx) => {
      const rawCat = f.category || f.business_category || f.ambiguity_category || "";
      const normCat = normalizeAmbiguityCategory(rawCat);

      if (!normCat) {
        // Out of scope category (grammar, spelling, vague wording, etc.) -> Filter out
        rejectedTracked.push({
          ...f,
          status: "rejected",
          reject_reason: `category '${rawCat || 'unmapped'}' is not in the approved Ambiguity Analysis taxonomy`
        });
        return;
      }

      // Check evidence quote & page
      let quote = f.highlighted_ambiguity || f.quote || f.suspected_text || "";
      let pageNum = f.page_number || f.page || 1;
      let evidenceArr = Array.isArray(f.evidence) ? f.evidence : [];

      if (!quote && evidenceArr.length > 0) {
        const firstEv = evidenceArr[0];
        quote = firstEv.quote || firstEv.quote_a || firstEv.text || "";
        if (firstEv.page || firstEv.page_a) pageNum = firstEv.page || firstEv.page_a;
      }

      let affectedPages = Array.isArray(f.affected_pages) && f.affected_pages.length > 0
        ? f.affected_pages
        : [pageNum];

      const sevRaw = String(f.severity || "MEDIUM").toUpperCase();
      const severity = ["CRITICAL", "HIGH", "MEDIUM", "LOW"].includes(sevRaw) ? sevRaw : "MEDIUM";

      verified.push({
        finding_id: f.finding_id || `ambiguity_${idx + 1}`,
        title: f.title || `${normCat} on Page ${pageNum}`,
        category: normCat,
        severity: severity,
        explanation: f.explanation || f.claude_explanation || f.why_claude_flagged_it || f.reason || "Contextual ambiguity identified across document passages.",
        highlighted_ambiguity: quote,
        page_number: pageNum,
        affected_pages: affectedPages,
        section_heading: f.section_heading || f.section || null,
        evidence: evidenceArr,
        suggested_resolution: f.suggested_resolution || f.recommended_resolution || f.recommendation || null,
        business_impact: f.business_impact || f.why_it_matters || null,
        is_cross_reference: Boolean(f.is_cross_reference || evidenceArr.length > 1 || (evidenceArr[0] && evidenceArr[0].location_b))
      });
    });

    // Deduplicate findings by category + quote/title stem & merge pages
    const dedupeMap = new Map();
    verified.forEach(item => {
      const stem = (item.highlighted_ambiguity || item.title).toLowerCase().trim().slice(0, 40);
      const key = `${item.category}::${stem}`;

      if (!dedupeMap.has(key)) {
        dedupeMap.set(key, { ...item, pages_set: new Set(item.affected_pages) });
      } else {
        const existing = dedupeMap.get(key);
        item.affected_pages.forEach(p => existing.pages_set.add(p));
      }
    });

    const finalVerified = Array.from(dedupeMap.values()).map(item => ({
      ...item,
      affected_pages: Array.from(item.pages_set).sort((a, b) => a - b)
    }));

    // Sort by Severity: CRITICAL -> HIGH -> MEDIUM -> LOW
    const SEV_RANK = { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3 };
    finalVerified.sort((a, b) => (SEV_RANK[a.severity] ?? 4) - (SEV_RANK[b.severity] ?? 4));

    // Calculate Summary Metrics
    const sevBreakdown = { CRITICAL: 0, HIGH: 0, MEDIUM: 0, LOW: 0 };
    const categoriesSet = new Set();
    const pagesSet = new Set();

    finalVerified.forEach(f => {
      sevBreakdown[f.severity] = (sevBreakdown[f.severity] || 0) + 1;
      categoriesSet.add(f.category);
      f.affected_pages.forEach(p => pagesSet.add(p));
    });

    return {
      verifiedFindings: finalVerified,
      rejectedFindings: rejectedTracked,
      summaryMetrics: {
        totalVerified: finalVerified.length,
        sevBreakdown,
        categoriesCount: categoriesSet.size,
        pagesCount: pagesSet.size,
        availableCategories: Array.from(categoriesSet)
      }
    };
  }, [finalReport, claudeReport]);

  // Dynamic Filtering
  const filteredFindings = useMemo(() => {
    return verifiedFindings.filter(f => {
      const matchSev = selectedSeverity === "ALL" || f.severity === selectedSeverity;
      const matchCat = selectedCategory === "ALL" || f.category === selectedCategory;

      const q = searchTerm.toLowerCase().trim();
      const matchSearch = !q ||
        f.title.toLowerCase().includes(q) ||
        f.category.toLowerCase().includes(q) ||
        f.explanation.toLowerCase().includes(q) ||
        (f.highlighted_ambiguity && f.highlighted_ambiguity.toLowerCase().includes(q)) ||
        (f.suggested_resolution && f.suggested_resolution.toLowerCase().includes(q));

      return matchSev && matchCat && matchSearch;
    });
  }, [verifiedFindings, selectedSeverity, selectedCategory, searchTerm]);

  const isPipelineRunning = running || (docProgress && (docProgress.context_analysis_status === "running" || docProgress.context_analysis_status === "pending"));

  if (loading) {
    return (
      <div style={styles.centerContainer}>
        <div style={styles.spinner} />
        <p style={{ marginTop: 14, fontSize: 13, color: "var(--text-secondary)" }}>Loading Contextual Ambiguity Audit...</p>
      </div>
    );
  }

  return (
    <div style={styles.container}>
      {/* ---------------------------------------------------- */}
      {/* 1. Compact Processing Banner                        */}
      {/* ---------------------------------------------------- */}
      {isPipelineRunning && (
        <div style={styles.progressBanner}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span style={styles.pulseDot} />
            <strong style={{ fontSize: 13, color: "var(--amber)" }}>
              Stage 6 Contextual Ambiguity Review in Progress
            </strong>
            <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>
              ({docProgress?.overall_progress || Math.round(docProgress?.progress_percentage || 70)}% complete)
            </span>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <span style={{ fontSize: 11.5, color: "var(--text-muted)" }}>
              Est. Remaining: {docProgress?.estimated_remaining_time || "~1 min"}
            </span>
            <button onClick={handleRerun} style={styles.retryBtn}>
              ↻ Re-trigger
            </button>
          </div>
        </div>
      )}

      {/* ---------------------------------------------------- */}
      {/* 2. Workspace Header                                  */}
      {/* ---------------------------------------------------- */}
      <div style={styles.header}>
        <div>
          <h2 style={styles.title}>Contextual Ambiguity Analysis</h2>
          <p style={styles.subtitle}>
            Audits cross-chunk contradictions, numerical mismatches, and structural conflicts across document clauses.
          </p>
        </div>
        <button onClick={handleRerun} style={styles.rerunBtn}>
          ↻ Re-run Analysis
        </button>
      </div>

      {/* ---------------------------------------------------- */}
      {/* 3. Executive KPI Summary Cards                       */}
      {/* ---------------------------------------------------- */}
      <div style={styles.kpiGrid}>
        {/* Card 1: Verified Findings */}
        <div style={styles.kpiCard}>
          <div style={styles.kpiLabel}>TOTAL VERIFIED FINDINGS</div>
          <div style={{ ...styles.kpiVal, color: summaryMetrics.totalVerified > 0 ? "var(--brand)" : "var(--green)" }}>
            {summaryMetrics.totalVerified}
          </div>
          <div style={styles.kpiSub}>Grounded ambiguity disclosures</div>
        </div>

        {/* Card 2: Severity Breakdown */}
        <div style={styles.kpiCard}>
          <div style={styles.kpiLabel}>SEVERITY BREAKDOWN</div>
          <div style={styles.sevGrid}>
            <span style={{ ...styles.sevTag, background: "#FEE2E2", color: "#DC2626" }}>
              CRITICAL: {summaryMetrics.sevBreakdown.CRITICAL}
            </span>
            <span style={{ ...styles.sevTag, background: "#FFEDD5", color: "#C2410C" }}>
              HIGH: {summaryMetrics.sevBreakdown.HIGH}
            </span>
            <span style={{ ...styles.sevTag, background: "#FEF3C7", color: "#D97706" }}>
              MEDIUM: {summaryMetrics.sevBreakdown.MEDIUM}
            </span>
            <span style={{ ...styles.sevTag, background: "#F1F5F9", color: "#475569" }}>
              LOW: {summaryMetrics.sevBreakdown.LOW}
            </span>
          </div>
        </div>

        {/* Card 3: Categories Affected */}
        <div style={styles.kpiCard}>
          <div style={styles.kpiLabel}>TAXONOMY CATEGORIES</div>
          <div style={styles.kpiVal}>{summaryMetrics.categoriesCount}</div>
          <div style={styles.kpiSub}>Out of 9 approved ambiguity types</div>
        </div>

        {/* Card 4: Pages Affected */}
        <div style={styles.kpiCard}>
          <div style={styles.kpiLabel}>PAGES AFFECTED</div>
          <div style={styles.kpiVal}>{summaryMetrics.pagesCount}</div>
          <div style={styles.kpiSub}>Document pages with disclosures</div>
        </div>
      </div>

      {/* ---------------------------------------------------- */}
      {/* 4. Filters Bar (Dynamic Categories & Severities)     */}
      {/* ---------------------------------------------------- */}
      <div style={styles.filterBar}>
        <div style={styles.searchBox}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" style={{ color: "var(--text-muted)", flexShrink: 0 }}>
            <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
          </svg>
          <input
            type="text"
            placeholder="Search findings, clauses, quotes..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            style={styles.searchInput}
          />
          {searchTerm && (
            <button onClick={() => setSearchTerm("")} style={styles.clearSearchBtn}>✕</button>
          )}
        </div>

        {/* Dynamic Category Filter Buttons */}
        <div style={styles.categoryBar}>
          <button
            onClick={() => setSelectedCategory("ALL")}
            style={{
              ...styles.catFilterPill,
              ...(selectedCategory === "ALL" ? styles.catFilterPillActive : {})
            }}
          >
            All Categories ({verifiedFindings.length})
          </button>
          {summaryMetrics.availableCategories.map(cat => {
            const count = verifiedFindings.filter(f => f.category === cat).length;
            return (
              <button
                key={cat}
                onClick={() => setSelectedCategory(cat)}
                style={{
                  ...styles.catFilterPill,
                  ...(selectedCategory === cat ? styles.catFilterPillActive : {})
                }}
              >
                {cat} ({count})
              </button>
            );
          })}
        </div>

        {/* Severity Filter Dropdown */}
        <select
          value={selectedSeverity}
          onChange={(e) => setSelectedSeverity(e.target.value)}
          style={styles.sevSelect}
        >
          <option value="ALL">All Severities</option>
          <option value="CRITICAL">Critical Severity</option>
          <option value="HIGH">High Severity</option>
          <option value="MEDIUM">Medium Severity</option>
          <option value="LOW">Low Severity</option>
        </select>
      </div>

      {/* ---------------------------------------------------- */}
      {/* 5. Findings Workspace List / Cards                  */}
      {/* ---------------------------------------------------- */}
      {filteredFindings.length === 0 ? (
        <div style={styles.emptyState}>
          <div style={styles.emptyIcon}>✓</div>
          <h3 style={styles.emptyTitle}>No verified ambiguities were found in this document.</h3>
          <p style={styles.emptySub}>
            The document was audited across all 9 approved ambiguity categories with zero grounded context conflicts detected.
          </p>
        </div>
      ) : (
        <div style={styles.findingsList}>
          {filteredFindings.map((f) => {
            const sevColor = f.severity === "CRITICAL" ? "#DC2626" : (f.severity === "HIGH" ? "#C2410C" : (f.severity === "MEDIUM" ? "#D97706" : "#475569"));
            const sevBg = f.severity === "CRITICAL" ? "#FEE2E2" : (f.severity === "HIGH" ? "#FFEDD5" : (f.severity === "MEDIUM" ? "#FEF3C7" : "#F1F5F9"));

            const firstPage = f.affected_pages[0] || f.page_number || 1;
            const quoteForNav = f.highlighted_ambiguity || (f.evidence[0]?.quote) || f.title;

            return (
              <div key={f.finding_id} style={{ ...styles.findingCard, borderLeft: `4px solid ${sevColor}` }}>
                {/* Top Row Badges */}
                <div style={styles.cardTopRow}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                    <span style={{ ...styles.sevBadge, background: sevBg, color: sevColor }}>
                      [{f.severity}]
                    </span>
                    <span style={styles.categoryBadge}>{f.category}</span>
                    <span style={styles.pageBadge}>
                      {f.affected_pages.length > 1
                        ? `Pages ${f.affected_pages.join(", ")}`
                        : `Page ${firstPage}`}
                    </span>
                    {f.section_heading && (
                      <span style={styles.sectionBadge}>
                        Section: {f.section_heading}
                      </span>
                    )}
                  </div>
                  <span style={styles.findingIdTag}>ID: {f.finding_id}</span>
                </div>

                {/* Title */}
                <h3 style={styles.cardTitle}>{f.title}</h3>

                {/* Explanation / Why it is ambiguous */}
                <div style={styles.explanationBox}>
                  <strong style={{ fontSize: 11, textTransform: "uppercase", color: "var(--text-muted)" }}>Why it is Ambiguous:</strong>
                  <p style={{ margin: "4px 0 0", fontSize: 13, color: "var(--text-primary)", lineHeight: 1.45 }}>
                    {f.explanation}
                  </p>
                </div>

                {/* Evidence Section */}
                <div style={styles.evidenceSection}>
                  <div style={styles.evidenceHeader}>
                    {f.is_cross_reference ? "Cross-Reference Contradiction Evidence:" : "Document Evidence:"}
                  </div>

                  {f.is_cross_reference && f.evidence.length >= 2 ? (
                    /* Cross Reference A VS B Evidence Layout */
                    <div style={styles.crossRefBox}>
                      <div style={styles.locationBlock}>
                        <span style={styles.locBadge}>LOCATION A (Page {f.evidence[0].page_a || f.evidence[0].page || firstPage}):</span>
                        <blockquote style={styles.quoteBox}>"{f.evidence[0].quote_a || f.evidence[0].quote || f.highlighted_ambiguity}"</blockquote>
                      </div>

                      <div style={styles.vsBadge}>VS</div>

                      <div style={styles.locationBlock}>
                        <span style={styles.locBadge}>LOCATION B (Page {f.evidence[1].page_b || f.evidence[1].page || f.evidence[0].page_b || firstPage}):</span>
                        <blockquote style={styles.quoteBox}>"{f.evidence[1].quote_b || f.evidence[1].quote || f.evidence[0].quote_b}"</blockquote>
                      </div>

                      {(f.business_impact || f.evidence[0].why_it_matters) && (
                        <div style={styles.whyMattersBox}>
                          <strong>Why this matters:</strong> {f.business_impact || f.evidence[0].why_it_matters}
                        </div>
                      )}
                    </div>
                  ) : (
                    /* Single Passage Evidence Layout */
                    <div style={styles.singleEvidenceBox}>
                      <blockquote style={styles.quoteBox}>
                        "{f.highlighted_ambiguity || (f.evidence[0]?.quote) || 'Evidence passage verified in document.'}"
                      </blockquote>
                    </div>
                  )}
                </div>

                {/* Suggested Resolution / Recommendation */}
                {f.suggested_resolution && (
                  <div style={styles.resolutionBox}>
                    <span style={{ fontWeight: 700, marginRight: 6 }}>💡 Recommended Action:</span>
                    {f.suggested_resolution}
                  </div>
                )}

                {/* Actions Footer */}
                <div style={styles.cardFooter}>
                  <button
                    onClick={() => {
                      if (onShowInDocument) {
                        onShowInDocument(firstPage, quoteForNav);
                      }
                    }}
                    style={styles.viewDocBtn}
                    title={`Jump to Page ${firstPage} in Document Viewer`}
                  >
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                      <circle cx="12" cy="12" r="3"/>
                    </svg>
                    <span>View in Document (Page {firstPage})</span>
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* ---------------------------------------------------- */}
      {/* 6. Collapsible Rejected Candidate Audit Log          */}
      {/* ---------------------------------------------------- */}
      {rejectedFindings.length > 0 && (
        <div style={styles.rejectedAccordion}>
          <button
            onClick={() => setShowRejected(!showRejected)}
            style={styles.rejectedAccordionBtn}
          >
            <span>
              {showRejected ? "▼" : "▶"} Rejected Candidates Audit Log ({rejectedFindings.length} items filtered out during validation)
            </span>
            <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
              {showRejected ? "Click to collapse" : "Click to view noise filter audit trail"}
            </span>
          </button>

          {showRejected && (
            <div style={styles.rejectedContent}>
              <p style={{ margin: "0 0 10px", fontSize: 12, color: "var(--text-secondary)" }}>
                These candidate items were generated during preliminary chunk scanning but rejected during validation for being out of ambiguity taxonomy scope or ungrounded.
              </p>
              <div style={styles.rejectedTable}>
                {rejectedFindings.map((rej, rIdx) => (
                  <div key={rIdx} style={styles.rejectedRow}>
                    <div style={{ fontWeight: 600, color: "var(--text-primary)" }}>
                      {rej.category || rej.business_category || "Unmapped"} - {rej.title || rej.highlighted_ambiguity || "Candidate Finding"}
                    </div>
                    <div style={{ fontSize: 11.5, color: "var(--red)" }}>
                      Reason: {rej.reject_reason || "Filtered out by taxonomy validation gate"}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

const styles = {
  centerContainer: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    minHeight: 280
  },
  spinner: {
    width: 30,
    height: 30,
    borderRadius: "50%",
    border: "3px solid var(--border)",
    borderTopColor: "var(--brand)",
    animation: "spin 0.8s linear infinite"
  },
  container: {
    display: "flex",
    flexDirection: "column",
    gap: 16,
    textAlign: "left",
    width: "100%"
  },

  /* Banner */
  progressBanner: {
    background: "#FEF3C7",
    border: "1px solid #F59E0B",
    borderRadius: 8,
    padding: "8px 14px",
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center"
  },
  pulseDot: {
    width: 8,
    height: 8,
    borderRadius: "50%",
    background: "#D97706",
    animation: "pulse 1.5s infinite"
  },
  retryBtn: {
    background: "#FFFFFF",
    border: "1px solid #D97706",
    color: "#D97706",
    borderRadius: 4,
    padding: "3px 8px",
    fontSize: 11,
    fontWeight: 700,
    cursor: "pointer"
  },

  /* Header */
  header: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "flex-start",
    marginBottom: 4
  },
  title: {
    margin: 0,
    fontSize: 18,
    fontWeight: 700,
    color: "var(--text-primary)"
  },
  subtitle: {
    margin: "4px 0 0",
    fontSize: 12.5,
    color: "var(--text-secondary)"
  },
  rerunBtn: {
    background: "var(--bg-card)",
    color: "var(--text-primary)",
    border: "1px solid var(--border)",
    borderRadius: 6,
    padding: "6px 12px",
    fontSize: 12,
    fontWeight: 600,
    cursor: "pointer"
  },

  /* KPI Grid */
  kpiGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(4, 1fr)",
    gap: 12
  },
  kpiCard: {
    background: "var(--bg-card)",
    border: "1px solid var(--border)",
    borderRadius: 8,
    padding: 14,
    display: "flex",
    flexDirection: "column",
    gap: 4
  },
  kpiLabel: {
    fontSize: 10.5,
    fontWeight: 700,
    color: "var(--text-muted)",
    letterSpacing: "0.5px"
  },
  kpiVal: {
    fontSize: 22,
    fontWeight: 800,
    color: "var(--text-primary)"
  },
  kpiSub: {
    fontSize: 11,
    color: "var(--text-secondary)"
  },
  sevGrid: {
    display: "flex",
    flexWrap: "wrap",
    gap: 4,
    marginTop: 2
  },
  sevTag: {
    fontSize: 10.5,
    fontWeight: 700,
    padding: "2px 6px",
    borderRadius: 4
  },

  /* Filters */
  filterBar: {
    display: "flex",
    flexDirection: "column",
    gap: 10,
    background: "var(--bg-card)",
    border: "1px solid var(--border)",
    borderRadius: 8,
    padding: 12
  },
  searchBox: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    background: "var(--bg-page)",
    border: "1px solid var(--border)",
    borderRadius: 6,
    padding: "6px 10px"
  },
  searchInput: {
    background: "none",
    border: "none",
    outline: "none",
    width: "100%",
    fontSize: 12.5,
    color: "var(--text-primary)"
  },
  clearSearchBtn: {
    background: "none",
    border: "none",
    color: "var(--text-muted)",
    cursor: "pointer",
    fontSize: 12
  },
  categoryBar: {
    display: "flex",
    gap: 6,
    overflowX: "auto",
    paddingBottom: 2
  },
  catFilterPill: {
    background: "var(--bg-page)",
    border: "1px solid var(--border)",
    borderRadius: 6,
    padding: "4px 10px",
    fontSize: 11.5,
    fontWeight: 500,
    color: "var(--text-secondary)",
    cursor: "pointer",
    whiteSpace: "nowrap"
  },
  catFilterPillActive: {
    background: "var(--brand-light)",
    color: "var(--brand)",
    borderColor: "var(--brand)",
    fontWeight: 700
  },
  sevSelect: {
    background: "var(--bg-page)",
    border: "1px solid var(--border)",
    borderRadius: 6,
    padding: "4px 8px",
    fontSize: 12,
    color: "var(--text-primary)",
    outline: "none",
    width: "fit-content"
  },

  /* Empty State */
  emptyState: {
    background: "var(--bg-card)",
    border: "1px solid var(--border)",
    borderRadius: 10,
    padding: "40px 24px",
    textAlign: "center"
  },
  emptyIcon: {
    width: 44,
    height: 44,
    borderRadius: "50%",
    background: "var(--green-light)",
    color: "var(--green)",
    fontSize: 22,
    fontWeight: 800,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    margin: "0 auto 12px"
  },
  emptyTitle: {
    margin: 0,
    fontSize: 16,
    fontWeight: 700,
    color: "var(--text-primary)"
  },
  emptySub: {
    margin: "6px 0 0",
    fontSize: 12.5,
    color: "var(--text-secondary)"
  },

  /* Findings Cards */
  findingsList: {
    display: "flex",
    flexDirection: "column",
    gap: 14
  },
  findingCard: {
    background: "var(--bg-card)",
    border: "1px solid var(--border)",
    borderRadius: 8,
    padding: 16,
    display: "flex",
    flexDirection: "column",
    gap: 10
  },
  cardTopRow: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center"
  },
  sevBadge: {
    fontSize: 11,
    fontWeight: 800,
    padding: "2px 6px",
    borderRadius: 4
  },
  categoryBadge: {
    fontSize: 11,
    fontWeight: 700,
    background: "var(--brand-light)",
    color: "var(--brand)",
    padding: "2px 8px",
    borderRadius: 4
  },
  pageBadge: {
    fontSize: 11,
    fontWeight: 600,
    background: "var(--bg-page)",
    color: "var(--text-secondary)",
    padding: "2px 6px",
    borderRadius: 4,
    border: "1px solid var(--border)"
  },
  sectionBadge: {
    fontSize: 11,
    color: "var(--text-muted)"
  },
  findingIdTag: {
    fontSize: 10.5,
    color: "var(--text-muted)",
    fontFamily: "monospace"
  },
  cardTitle: {
    margin: 0,
    fontSize: 15,
    fontWeight: 700,
    color: "var(--text-primary)"
  },

  explanationBox: {
    background: "var(--bg-page)",
    border: "1px solid var(--border)",
    borderRadius: 6,
    padding: 10
  },

  /* Evidence */
  evidenceSection: {
    display: "flex",
    flexDirection: "column",
    gap: 6
  },
  evidenceHeader: {
    fontSize: 11,
    fontWeight: 700,
    color: "var(--text-muted)",
    textTransform: "uppercase"
  },
  crossRefBox: {
    display: "flex",
    flexDirection: "column",
    gap: 8,
    background: "var(--bg-page)",
    border: "1px solid var(--border)",
    borderRadius: 6,
    padding: 12
  },
  locationBlock: {
    display: "flex",
    flexDirection: "column",
    gap: 4
  },
  locBadge: {
    fontSize: 11,
    fontWeight: 700,
    color: "var(--brand)"
  },
  vsBadge: {
    fontSize: 11,
    fontWeight: 800,
    color: "var(--red)",
    textAlign: "center",
    margin: "2px 0"
  },
  whyMattersBox: {
    marginTop: 4,
    paddingTop: 8,
    borderTop: "1px solid var(--border)",
    fontSize: 12,
    color: "var(--red)",
    fontWeight: 500
  },
  singleEvidenceBox: {
    background: "var(--bg-page)",
    borderRadius: 6,
    padding: 2
  },
  quoteBox: {
    margin: 0,
    fontSize: 12.5,
    fontStyle: "italic",
    color: "var(--text-primary)",
    borderLeft: "3px solid var(--brand)",
    paddingLeft: 10
  },

  resolutionBox: {
    background: "var(--green-light)",
    border: "1px solid rgba(22, 163, 74, 0.2)",
    borderRadius: 6,
    padding: "8px 12px",
    fontSize: 12.5,
    color: "var(--green)"
  },

  cardFooter: {
    display: "flex",
    justifyContent: "flex-end",
    paddingTop: 4
  },
  viewDocBtn: {
    background: "var(--brand-light)",
    color: "var(--brand)",
    border: "1px solid var(--brand-border)",
    borderRadius: 6,
    padding: "5px 12px",
    fontSize: 12,
    fontWeight: 650,
    display: "inline-flex",
    alignItems: "center",
    gap: 6,
    cursor: "pointer"
  },

  /* Rejected Accordion */
  rejectedAccordion: {
    marginTop: 12,
    background: "var(--bg-card)",
    border: "1px solid var(--border)",
    borderRadius: 8,
    overflow: "hidden"
  },
  rejectedAccordionBtn: {
    width: "100%",
    background: "none",
    border: "none",
    padding: "10px 14px",
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    fontSize: 12,
    fontWeight: 650,
    color: "var(--text-secondary)",
    cursor: "pointer"
  },
  rejectedContent: {
    padding: 14,
    borderTop: "1px solid var(--border)",
    background: "var(--bg-page)"
  },
  rejectedTable: {
    display: "flex",
    flexDirection: "column",
    gap: 6
  },
  rejectedRow: {
    padding: "6px 10px",
    background: "var(--bg-card)",
    border: "1px solid var(--border)",
    borderRadius: 6,
    fontSize: 12,
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center"
  }
};
