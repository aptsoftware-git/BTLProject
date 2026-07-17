import React, { useState, useEffect } from "react";
import { 
  fetchContextAnalysisReport, 
  runContextAnalysis, 
  fetchDocument,
  API_BASE_URL 
} from "../api";

export default function ContextAnalysis({ id, onShowInDocument }) {
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [docProgress, setDocProgress] = useState(null);
  const [error, setError] = useState(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedPriority, setSelectedPriority] = useState("all");
  const [selectedCategory, setSelectedCategory] = useState("all");
  const [expandedIssues, setExpandedIssues] = useState({});

  useEffect(() => {
    let active = true;
    let timerId = null;

    async function checkStatus() {
      try {
        const docData = await fetchDocument(id);
        if (!active) return;
        
        setDocProgress(docData);
        
        if (docData.context_analysis_status === "running" || docData.context_analysis_status === "pending") {
          setRunning(true);
          timerId = setTimeout(checkStatus, 2000);
        } else if (docData.context_analysis_status === "completed") {
          setRunning(false);
          const data = await fetchContextAnalysisReport(id);
          if (active) {
            setReport(data);
          }
        } else if (docData.context_analysis_status === "not_started") {
          setRunning(true);
          await runContextAnalysis(id);
          timerId = setTimeout(checkStatus, 2000);
        } else if (docData.context_analysis_status === "failed") {
          setRunning(false);
          setError("Consistency analysis failed: " + (docData.error || "Unknown error."));
        } else {
          // Fallback check
          const data = await fetchContextAnalysisReport(id).catch(() => null);
          if (data) {
            setReport(data);
          } else {
            setRunning(true);
            await runContextAnalysis(id);
            timerId = setTimeout(checkStatus, 2000);
          }
        }
      } catch (err) {
        if (err.message.includes("404")) {
          try {
            setRunning(true);
            await runContextAnalysis(id);
            timerId = setTimeout(checkStatus, 2000);
          } catch (triggerErr) {
            if (active) setError("Failed to run consistency analysis: " + triggerErr.message);
          }
        } else {
          if (active) {
            setError("Error: " + err.message);
          }
        }
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

  const loadReport = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchContextAnalysisReport(id);
      setReport(data);
    } catch (err) {
      if (err.message.includes("404")) {
        setReport(null);
      } else {
        setError("Unable to retrieve the consistency analysis. Please try running it.");
      }
    } finally {
      setLoading(false);
    }
  };

  const handleGenerate = async () => {
    setRunning(true);
    setError(null);
    try {
      await runContextAnalysis(id);
      // Wait a moment and check status
      const docData = await fetchDocument(id);
      setDocProgress(docData);
    } catch (err) {
      setError(err.message || "Failed to generate consistency analysis.");
      setRunning(false);
    }
  };

  const toggleExpand = (idx) => {
    setExpandedIssues(prev => ({
      ...prev,
      [idx]: !prev[idx]
    }));
  };

  const handleDownload = (filename) => {
    const downloadUrl = `${API_BASE_URL}/download/${id}/${filename}`;
    const link = document.createElement("a");
    link.href = downloadUrl;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  if (loading) {
    return (
      <div style={styles.centerContainer}>
        <div style={styles.spinner} />
        <p style={{ marginTop: 16, fontSize: 15, fontWeight: 600, color: "var(--text-primary)" }}>
          Retrieving audit records...
        </p>
      </div>
    );
  }

  if (running) {
    const stage = docProgress?.context_analysis_stage || "Analyzing Inconsistencies";
    const pageNum = docProgress?.current_page || 0;
    const totalPages = docProgress?.total_pages || 0;
    const batchNum = docProgress?.current_batch || 0;
    const totalBatches = docProgress?.total_batches || 0;
    const estTime = docProgress?.context_analysis_est_time || docProgress?.estimated_remaining_time || "Estimating...";
    const issuesCount = docProgress?.context_analysis_issues_count || 0;
    const memorySafe = docProgress?.memory_safe_mode ? "Active" : "Disabled";
    const memory = docProgress?.memory_usage || "N/A";
    const cpu = docProgress?.cpu_usage || "N/A";
    const pct = docProgress?.context_analysis_progress || 0;

    return (
      <div style={styles.runningContainer}>
        <div style={styles.runningHeader}>
          <div style={styles.spinner} />
          <h3 style={styles.runningTitle}>Context Analysis Running</h3>
        </div>
        <p style={styles.runningSubtitle}>
          The audit engine is performing sequence alignment, numerical checks, and cross-section semantic validation.
        </p>

        {/* Progress bar */}
        <div style={styles.progressBarBg}>
          <div style={{ ...styles.progressBarFill, width: `${pct}%` }} />
        </div>
        <span style={styles.progressPercent}>{Math.round(pct)}% Completed</span>

        <div style={styles.statsCardGrid}>
          <div style={styles.statGridItem}>
            <span style={styles.statLabel}>Current Stage</span>
            <span style={styles.statVal}>{stage}</span>
          </div>
          <div style={styles.statGridItem}>
            <span style={styles.statLabel}>Current Page</span>
            <span style={styles.statVal}>{pageNum} / {totalPages || "N/A"}</span>
          </div>
          <div style={styles.statGridItem}>
            <span style={styles.statLabel}>Current Batch</span>
            <span style={styles.statVal}>{batchNum} / {totalBatches || "N/A"}</span>
          </div>
          <div style={styles.statGridItem}>
            <span style={styles.statLabel}>Est. Remaining Time</span>
            <span style={styles.statVal}>{estTime}</span>
          </div>
          <div style={styles.statGridItem}>
            <span style={styles.statLabel}>Issues Detected</span>
            <span style={{ ...styles.statVal, color: issuesCount > 0 ? "var(--red)" : "var(--green)" }}>{issuesCount}</span>
          </div>
          <div style={styles.statGridItem}>
            <span style={styles.statLabel}>Memory Safe Mode</span>
            <span style={styles.statVal}>{memorySafe}</span>
          </div>
          <div style={styles.statGridItem}>
            <span style={styles.statLabel}>Memory Usage</span>
            <span style={styles.statVal}>{memory}</span>
          </div>
          <div style={styles.statGridItem}>
            <span style={styles.statLabel}>CPU Usage</span>
            <span style={styles.statVal}>{cpu}</span>
          </div>
        </div>
      </div>
    );
  }

  if (!report) {
    return (
      <div style={styles.emptyContainer}>
        <div style={styles.emptyIcon}>
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="var(--text-muted)" strokeWidth="1.5">
            <path d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
          </svg>
        </div>
        <h3 style={{ fontSize: 16, fontWeight: 700, color: "var(--text-primary)", marginBottom: 8 }}>
          No Context Analysis has been generated.
        </h3>
        <p style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 20, maxWidth: 480, textAlign: "center" }}>
          Consistency auditing maps section sequences, cross-references, numerical values, and structural logic across pages to flag potential discrepancies.
        </p>
        <button style={styles.actionBtn} onClick={handleGenerate}>
          Generate Analysis
        </button>
        {error && <p style={{ color: "var(--red)", fontSize: 12, marginTop: 12 }}>{error}</p>}
      </div>
    );
  }

  const { summary, issues = [] } = report;

  // Filter issues
  const filteredIssues = issues.filter(issue => {
    const searchContent = `${issue.description} ${issue.category} ${issue.reason} ${issue.page_numbers.join(", ")}`.toLowerCase();
    const matchesSearch = searchContent.includes(searchQuery.toLowerCase());
    const matchesPriority = selectedPriority === "all" || issue.severity.toLowerCase() === selectedPriority.toLowerCase();
    const matchesCategory = selectedCategory === "all" || issue.category === selectedCategory;
    return matchesSearch && matchesPriority && matchesCategory;
  });

  const healthColors = {
    "Critical": "var(--red)",
    "Needs Review": "var(--amber)",
    "Good": "var(--blue)",
    "Excellent": "var(--green)"
  };
  const currentHealthColor = healthColors[summary.overall_health] || "var(--text-secondary)";

  return (
    <div style={styles.dashboardContainer}>
      
      {/* 1. Header Information & Downloads */}
      <div style={styles.dashboardHeader}>
        <div>
          <h3 style={styles.sectionHeaderTitle}>Integrity & Consistency Audit</h3>
          <p style={styles.sectionHeaderSub}>Corporate assurance review verifying narrative coherence, reference links, and metrics.</p>
        </div>
        
        <div style={styles.downloadsRow}>
          <button style={styles.downloadLinkBtn} onClick={() => handleDownload("context_report.json")}>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" style={{ marginRight: 5 }}><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3"/></svg>
            Developer JSON
          </button>
          <button style={styles.downloadLinkBtn} onClick={() => handleDownload("context_report.html")}>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" style={{ marginRight: 5 }}><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3"/></svg>
            Developer HTML
          </button>
          <button style={styles.downloadActiveBtn} onClick={() => handleDownload("business_report.html")}>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" style={{ marginRight: 5 }}><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3"/></svg>
            Business Report (HTML)
          </button>
        </div>
      </div>

      {/* 2. Executive Summary Cards & Health Panel */}
      <div style={styles.overviewLayout}>
        <div style={styles.auditDetailsGrid}>
          <div style={styles.detailMetricCard}>
            <span style={styles.detailLabel}>Document Name</span>
            <span style={styles.detailValue} title={summary.document_name}>{summary.document_name}</span>
          </div>
          <div style={styles.detailMetricCard}>
            <span style={styles.detailLabel}>Format / Type</span>
            <span style={styles.detailValue}>{summary.document_type}</span>
          </div>
          <div style={styles.detailMetricCard}>
            <span style={styles.detailLabel}>Total Pages</span>
            <span style={styles.detailValue}>{summary.pages_analysed}</span>
          </div>
          <div style={styles.detailMetricCard}>
            <span style={styles.detailLabel}>Audit Time</span>
            <span style={styles.detailValue}>{summary.processing_time}</span>
          </div>
          <div style={{ ...styles.detailMetricCard, gridColumn: "span 2" }}>
            <span style={styles.detailLabel}>Audit Completed On</span>
            <span style={styles.detailValue}>{summary.analysis_completed_on}</span>
          </div>
        </div>

        <div style={{ ...styles.healthPanel, borderLeftColor: currentHealthColor }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
            <h4 style={styles.healthTitle}>{summary.overall_health} Health</h4>
            <span style={{ ...styles.healthBadge, backgroundColor: currentHealthColor }}>
              {summary.overall_health}
            </span>
          </div>
          <p style={styles.healthDesc}>{summary.health_description}</p>
          <span style={styles.completionLabel}>✓ Audit Pipeline Completed Successfully</span>
        </div>
      </div>

      {/* 3. Priority Summary Cards */}
      <div style={styles.priorityStatsGrid}>
        <div style={styles.priorityCard}>
          <span style={styles.priorityNum}>{summary.total_issues}</span>
          <span style={styles.priorityText}>Potential Issues Found</span>
        </div>
        <div style={{ ...styles.priorityCard, borderTopColor: "var(--red)" }}>
          <span style={{ ...styles.priorityNum, color: "var(--red)" }}>{summary.high_severity}</span>
          <span style={styles.priorityText}>High Priority</span>
        </div>
        <div style={{ ...styles.priorityCard, borderTopColor: "var(--amber)" }}>
          <span style={{ ...styles.priorityNum, color: "var(--amber)" }}>{summary.medium_severity}</span>
          <span style={styles.priorityText}>Medium Priority</span>
        </div>
        <div style={{ ...styles.priorityCard, borderTopColor: "var(--text-secondary)" }}>
          <span style={{ ...styles.priorityNum, color: "var(--text-secondary)" }}>{summary.low_severity}</span>
          <span style={styles.priorityText}>Low Priority</span>
        </div>
      </div>

      {/* 4. Category Dashboard */}
      <h4 style={styles.sectionDividerTitle}>Issue Category Counts</h4>
      <div style={styles.categoryGrid}>
        {Object.entries(summary.categories_distribution || {}).map(([catName, count]) => {
          const hasIssues = count > 0;
          const countColor = count > 3 ? "var(--red)" : count > 0 ? "var(--amber)" : "var(--text-muted)";
          return (
            <div 
              key={catName} 
              onClick={() => setSelectedCategory(selectedCategory === catName ? "all" : catName)}
              style={{
                ...styles.categoryCard,
                borderColor: selectedCategory === catName ? "var(--brand)" : "var(--border)",
                backgroundColor: selectedCategory === catName ? "var(--brand-light)" : hasIssues ? "var(--bg-hover)" : "var(--bg-card)",
                cursor: "pointer"
              }}
            >
              <span style={{ ...styles.categoryName, color: selectedCategory === catName ? "var(--brand-text)" : "var(--text-secondary)" }}>
                {catName}
              </span>
              <span style={{ ...styles.categoryCount, backgroundColor: countColor }}>
                {count}
              </span>
            </div>
          );
        })}
      </div>

      {/* 5. Interactive Issue Table / Card Panel */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <h4 style={styles.sectionDividerTitle}>Detailed Audit Findings ({filteredIssues.length} matches)</h4>
        {error && <span style={{ color: "var(--red)", fontSize: 12 }}>{error}</span>}
      </div>

      {/* Toolbar Filters */}
      <div style={styles.filtersBar}>
        <div style={styles.filterRow}>
          <span style={styles.filterLabel}>Search:</span>
          <input 
            type="text" 
            placeholder="Search observation, reasoning or page numbers..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={styles.searchInput}
          />
        </div>
        <div style={styles.filterRow}>
          <span style={styles.filterLabel}>Priority:</span>
          {["all", "High", "Medium", "Low"].map(pri => (
            <button 
              key={pri}
              onClick={() => setSelectedPriority(pri)}
              style={{
                ...styles.filterBtn,
                ...(selectedPriority === pri ? styles.filterBtnActive : {})
              }}
            >
              {pri === "all" ? "All Priorities" : pri}
            </button>
          ))}
        </div>
        <div style={{ ...styles.filterRow, flexWrap: "wrap" }}>
          <span style={styles.filterLabel}>Category:</span>
          <button 
            onClick={() => setSelectedCategory("all")}
            style={{
              ...styles.filterBtn,
              ...(selectedCategory === "all" ? styles.filterBtnActive : {})
            }}
          >
            All Categories
          </button>
          {Object.keys(summary.categories_distribution || {}).map(cat => (
            <button 
              key={cat}
              onClick={() => setSelectedCategory(cat)}
              style={{
                ...styles.filterBtn,
                ...(selectedCategory === cat ? styles.filterBtnActive : {})
              }}
            >
              {cat}
            </button>
          ))}
        </div>
      </div>

      {/* Issues Deck */}
      <div style={styles.issuesContainer}>
        {filteredIssues.length === 0 ? (
          <div style={styles.noIssuesCard}>
            No contextual inconsistency observations match your active filters.
          </div>
        ) : (
          filteredIssues.map((issue) => {
            const isExpanded = expandedIssues[issue.id];
            const severityColor = issue.severity === "High" ? "var(--red)" : issue.severity === "Medium" ? "var(--amber)" : "var(--text-secondary)";
            const badgeBg = issue.severity === "High" ? "rgba(239, 68, 68, 0.1)" : issue.severity === "Medium" ? "rgba(245, 158, 11, 0.1)" : "rgba(100, 116, 139, 0.1)";

            const sideBySide = issue.side_by_side;

            return (
              <div 
                key={issue.id} 
                style={{ ...styles.issueItemCard, borderLeftColor: severityColor }}
              >
                <div style={styles.issueItemHeader} onClick={() => toggleExpand(issue.id)}>
                  <div style={styles.issueHeaderLeft}>
                    <span style={styles.issueIdLabel}>{issue.id}</span>
                    <span style={styles.issueCategoryTag}>{issue.category}</span>
                  </div>
                  
                  <div style={styles.issueHeaderRight}>
                    <span style={{ 
                      ...styles.priorityBadge, 
                      color: severityColor, 
                      backgroundColor: badgeBg,
                      borderColor: `${severityColor}20`
                    }}>
                      {issue.severity} Priority
                    </span>
                    <span style={styles.statusBadge}>Pending Review</span>
                    <svg 
                      width="16" 
                      height="16" 
                      viewBox="0 0 24 24" 
                      fill="none" 
                      stroke="var(--text-secondary)" 
                      strokeWidth="2"
                      style={{ 
                        marginLeft: 10,
                        transform: isExpanded ? "rotate(180deg)" : "rotate(0deg)",
                        transition: "transform 0.2s ease"
                      }}
                    >
                      <path d="M19 9l-7 7-7-7" />
                    </svg>
                  </div>
                </div>

                {(!isExpanded) ? (
                  <div style={styles.collapsedSummary} onClick={() => toggleExpand(issue.id)}>
                    <strong>Observation:</strong> {issue.description.substring(0, 150)}...
                  </div>
                ) : (
                  <div style={styles.issueExpandedContent}>
                    <div style={styles.issueFieldRow}>
                      <span style={styles.issueFieldTitle}>Observation</span>
                      <span style={styles.issueFieldText}>{issue.description}</span>
                    </div>

                    <div style={styles.issueFieldRow}>
                      <span style={styles.issueFieldTitle}>References</span>
                      <span style={styles.issueFieldText}>
                        Page(s): {issue.page_numbers.join(", ")} | Section Path: {issue.section_path}
                      </span>
                    </div>

                    {/* Comparison Block */}
                    <div style={styles.issueFieldRow}>
                      <span style={styles.issueFieldTitle}>Document Evidence</span>
                      <div style={styles.issueFieldText}>
                        {sideBySide && sideBySide.location_b ? (
                          <div style={styles.comparisonContainer}>
                            <div style={styles.comparisonBox}>
                              <div style={styles.compBoxHeader}>LOCATION A</div>
                              <div style={styles.compBoxMeta}>Page {sideBySide.location_a.page} | {sideBySide.location_a.section}</div>
                              <div style={styles.compBoxContent}>"{sideBySide.location_a.text}"</div>
                              <button 
                                style={styles.navigationLinkBtn}
                                onClick={() => onShowInDocument(sideBySide.location_a.page, sideBySide.location_a.text, issue.object_ids[0])}
                              >
                                Show Location A
                              </button>
                            </div>
                            <div style={styles.comparisonArrow}>➔</div>
                            <div style={styles.comparisonBox}>
                              <div style={styles.compBoxHeader}>LOCATION B</div>
                              <div style={styles.compBoxMeta}>Page {sideBySide.location_b.page} | {sideBySide.location_b.section}</div>
                              <div style={styles.compBoxContent}>"{sideBySide.location_b.text}"</div>
                              <button 
                                style={styles.navigationLinkBtn}
                                onClick={() => onShowInDocument(sideBySide.location_b.page, sideBySide.location_b.text, issue.object_ids[1])}
                              >
                                Show Location B
                              </button>
                            </div>
                          </div>
                        ) : sideBySide && sideBySide.location_a ? (
                          <div style={styles.singleLocationContainer}>
                            <div style={styles.comparisonBox}>
                              <div style={styles.compBoxHeader}>LOCATION CITATION</div>
                              <div style={styles.compBoxMeta}>Page {sideBySide.location_a.page} | {sideBySide.location_a.section}</div>
                              <div style={styles.compBoxContent}>"{sideBySide.location_a.text}"</div>
                              <button 
                                style={styles.navigationLinkBtn}
                                onClick={() => onShowInDocument(sideBySide.location_a.page, sideBySide.location_a.text, issue.object_ids[0])}
                              >
                                Show in Document
                              </button>
                            </div>
                          </div>
                        ) : (
                          <div style={styles.rawEvidence}>"{issue.evidence}"</div>
                        )}
                      </div>
                    </div>

                    <div style={styles.issueFieldRow}>
                      <span style={styles.issueFieldTitle}>Reasoning</span>
                      <span style={styles.issueFieldText}>{issue.reason}</span>
                    </div>

                    <div style={styles.issueFieldRow}>
                      <span style={styles.issueFieldTitle}>Manual Action Recommended</span>
                      <span style={{ ...styles.issueFieldText, color: "var(--brand)", fontWeight: 600 }}>
                        {issue.manual_verification}
                      </span>
                    </div>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>

    </div>
  );
}

const styles = {
  centerContainer: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    padding: "80px 20px",
    background: "var(--bg-card)",
    borderRadius: 12,
    border: "1px solid var(--border)",
    minHeight: 300
  },
  spinner: {
    width: 32,
    height: 32,
    border: "3px solid var(--border)",
    borderTopColor: "var(--brand)",
    borderRadius: "50%",
    animation: "spin 1s linear infinite"
  },
  emptyContainer: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    padding: "60px 40px",
    background: "var(--bg-card)",
    borderRadius: 12,
    border: "1px dashed var(--border)",
    textAlign: "center"
  },
  emptyIcon: {
    marginBottom: 16,
    color: "var(--text-muted)"
  },
  actionBtn: {
    background: "var(--brand)",
    color: "#fff",
    border: "none",
    borderRadius: 6,
    padding: "8px 20px",
    fontSize: 13.5,
    fontWeight: 600,
    cursor: "pointer",
    boxShadow: "0 2px 4px rgba(0,0,0,0.1)",
    transition: "background 0.2s"
  },
  dashboardContainer: {
    display: "flex",
    flexDirection: "column",
    gap: 16,
    textAlign: "left"
  },
  dashboardHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    borderBottom: "1px solid var(--border)",
    paddingBottom: 12,
    marginBottom: 8
  },
  sectionHeaderTitle: {
    margin: 0,
    fontSize: 18,
    fontWeight: 700,
    color: "var(--text-primary)"
  },
  sectionHeaderSub: {
    margin: "3px 0 0 0",
    fontSize: 12,
    color: "var(--text-secondary)"
  },
  downloadsRow: {
    display: "flex",
    gap: 8
  },
  downloadLinkBtn: {
    background: "var(--bg-card)",
    color: "var(--text-primary)",
    border: "1px solid var(--border)",
    borderRadius: 6,
    padding: "6px 12px",
    fontSize: 12,
    fontWeight: 600,
    display: "flex",
    alignItems: "center",
    cursor: "pointer"
  },
  downloadActiveBtn: {
    background: "var(--brand)",
    color: "#fff",
    border: "1px solid var(--brand)",
    borderRadius: 6,
    padding: "6px 12px",
    fontSize: 12,
    fontWeight: 600,
    display: "flex",
    alignItems: "center",
    cursor: "pointer"
  },
  overviewLayout: {
    display: "grid",
    gridTemplateColumns: "1.2fr 1fr",
    gap: 16
  },
  auditDetailsGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(2, 1fr)",
    gap: 10,
    background: "var(--bg-card)",
    border: "1px solid var(--border)",
    borderRadius: 10,
    padding: 16
  },
  detailMetricCard: {
    display: "flex",
    flexDirection: "column",
    borderBottom: "1px solid var(--bg-hover)",
    paddingBottom: 6
  },
  detailLabel: {
    fontSize: 10,
    fontWeight: 700,
    color: "var(--text-secondary)",
    textTransform: "uppercase"
  },
  detailValue: {
    fontSize: 13.5,
    fontWeight: 600,
    color: "var(--text-primary)",
    marginTop: 2,
    whiteSpace: "nowrap",
    overflow: "hidden",
    textOverflow: "ellipsis"
  },
  healthPanel: {
    background: "var(--bg-card)",
    border: "1px solid var(--border)",
    borderLeftWidth: 6,
    borderRadius: 10,
    padding: 16,
    display: "flex",
    flexDirection: "column",
    justifyContent: "center"
  },
  healthTitle: {
    margin: 0,
    fontSize: 15,
    fontWeight: 700,
    color: "var(--text-primary)"
  },
  healthBadge: {
    color: "#fff",
    fontWeight: 700,
    fontSize: 10.5,
    padding: "2px 8px",
    borderRadius: 4,
    textTransform: "uppercase"
  },
  healthDesc: {
    margin: "4px 0 10px 0",
    fontSize: 12.5,
    color: "var(--text-secondary)",
    lineHeight: 1.4
  },
  completionLabel: {
    fontSize: 11,
    color: "var(--green)",
    fontWeight: 600
  },
  priorityStatsGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(4, 1fr)",
    gap: 12
  },
  priorityCard: {
    background: "var(--bg-card)",
    border: "1px solid var(--border)",
    borderTopWidth: 4,
    borderRadius: 8,
    padding: 12,
    textAlign: "center",
    boxShadow: "0 1px 2px rgba(0,0,0,0.02)"
  },
  priorityNum: {
    display: "block",
    fontSize: 26,
    fontWeight: 700,
    color: "var(--text-primary)"
  },
  priorityText: {
    fontSize: 10.5,
    fontWeight: 600,
    color: "var(--text-muted)",
    textTransform: "uppercase"
  },
  sectionDividerTitle: {
    margin: "12px 0 6px 0",
    fontSize: 14,
    fontWeight: 700,
    color: "var(--text-primary)",
    borderBottom: "1px solid var(--border)",
    paddingBottom: 4,
    width: "100%"
  },
  categoryGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(5, 1fr)",
    gap: 8,
    marginBottom: 8
  },
  categoryCard: {
    border: "1px solid var(--border)",
    borderRadius: 8,
    padding: 10,
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center"
  },
  categoryName: {
    fontSize: 11.5,
    fontWeight: 600,
    lineHeight: 1.2
  },
  categoryCount: {
    fontSize: 10,
    fontWeight: 700,
    color: "#fff",
    width: 18,
    height: 18,
    borderRadius: "50%",
    display: "flex",
    alignItems: "center",
    justifyContent: "center"
  },
  filtersBar: {
    background: "var(--bg-card)",
    border: "1px solid var(--border)",
    borderRadius: 8,
    padding: 12,
    display: "flex",
    flexDirection: "column",
    gap: 8
  },
  filterRow: {
    display: "flex",
    alignItems: "center",
    gap: 8
  },
  filterLabel: {
    fontSize: 11,
    fontWeight: 700,
    color: "var(--text-muted)",
    textTransform: "uppercase",
    width: 60
  },
  searchInput: {
    flexGrow: 1,
    border: "1px solid var(--border)",
    borderRadius: 6,
    padding: "5px 10px",
    fontSize: 12.5,
    outline: "none"
  },
  filterBtn: {
    background: "var(--bg-card)",
    border: "1px solid var(--border)",
    borderRadius: 5,
    padding: "3px 8px",
    fontSize: 11.5,
    fontWeight: 500,
    cursor: "pointer",
    marginRight: 4,
    marginBottom: 4
  },
  filterBtnActive: {
    background: "var(--brand)",
    color: "#fff",
    borderColor: "var(--brand)"
  },
  issuesContainer: {
    display: "flex",
    flexDirection: "column",
    gap: 12,
    marginTop: 8
  },
  noIssuesCard: {
    background: "var(--bg-card)",
    border: "1px dashed var(--border)",
    borderRadius: 8,
    padding: 24,
    textAlign: "center",
    color: "var(--text-muted)",
    fontSize: 13.5
  },
  issueItemCard: {
    background: "var(--bg-card)",
    border: "1px solid var(--border)",
    borderLeftWidth: 5,
    borderRadius: 8,
    overflow: "hidden"
  },
  issueItemHeader: {
    padding: "12px 16px",
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    cursor: "pointer",
    background: "var(--bg-card)",
    userSelect: "none"
  },
  issueHeaderLeft: {
    display: "flex",
    alignItems: "center",
    gap: 10
  },
  issueIdLabel: {
    fontSize: 13.5,
    fontWeight: 700,
    color: "var(--text-primary)"
  },
  issueCategoryTag: {
    fontSize: 11,
    fontWeight: 600,
    color: "var(--text-secondary)",
    backgroundColor: "var(--bg-hover)",
    padding: "2px 6px",
    borderRadius: 4
  },
  issueHeaderRight: {
    display: "flex",
    alignItems: "center",
    gap: 6
  },
  priorityBadge: {
    fontSize: 10,
    fontWeight: 700,
    padding: "2px 6px",
    borderRadius: 4,
    textTransform: "uppercase",
    border: "1px solid"
  },
  statusBadge: {
    fontSize: 10,
    fontWeight: 600,
    color: "var(--text-muted)",
    backgroundColor: "var(--bg-hover)",
    padding: "2px 6px",
    borderRadius: 4
  },
  collapsedSummary: {
    padding: "0 16px 12px 16px",
    fontSize: 12.5,
    color: "var(--text-secondary)",
    cursor: "pointer"
  },
  issueExpandedContent: {
    padding: "0 16px 16px 16px",
    borderTop: "1px solid var(--bg-hover)",
    display: "flex",
    flexDirection: "column",
    gap: 10,
    paddingTop: 12
  },
  issueFieldRow: {
    display: "grid",
    gridTemplateColumns: "180px 1fr",
    gap: 16,
    fontSize: 13
  },
  issueFieldTitle: {
    fontWeight: 650,
    color: "var(--text-secondary)"
  },
  issueFieldText: {
    color: "var(--text-primary)",
    lineHeight: 1.45
  },
  comparisonContainer: {
    display: "grid",
    gridTemplateColumns: "1fr auto 1fr",
    gap: 12,
    alignItems: "stretch",
    marginTop: 4
  },
  singleLocationContainer: {
    display: "grid",
    gridTemplateColumns: "1fr",
    marginTop: 4
  },
  comparisonBox: {
    background: "var(--bg-hover)",
    border: "1px solid var(--border)",
    borderRadius: 6,
    padding: 10,
    display: "flex",
    flexDirection: "column",
    justifyContent: "space-between",
    gap: 6
  },
  compBoxHeader: {
    fontSize: 9,
    fontWeight: 700,
    color: "var(--text-secondary)",
    letterSpacing: 0.5
  },
  compBoxMeta: {
    fontSize: 11,
    fontWeight: 600,
    color: "var(--brand)"
  },
  compBoxContent: {
    fontSize: 12.5,
    color: "var(--text-primary)",
    fontStyle: "italic",
    background: "#ffffff",
    border: "1px solid var(--border)",
    padding: "6px 8px",
    borderRadius: 4,
    borderLeft: "3px solid var(--brand)",
    lineHeight: 1.35
  },
  comparisonArrow: {
    fontSize: 16,
    color: "var(--text-muted)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center"
  },
  navigationLinkBtn: {
    alignSelf: "flex-start",
    background: "none",
    border: "none",
    color: "var(--brand)",
    fontSize: 11,
    fontWeight: 700,
    cursor: "pointer",
    padding: 0,
    marginTop: 4,
    textDecoration: "underline"
  },
  rawEvidence: {
    fontSize: 12.5,
    fontStyle: "italic",
    background: "var(--bg-hover)",
    padding: "8px 10px",
    borderRadius: 4,
    lineHeight: 1.4
  },
  runningContainer: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    padding: "40px 20px",
    background: "var(--bg-card)",
    borderRadius: 12,
    border: "1px solid var(--border)",
    textAlign: "center"
  },
  runningHeader: {
    display: "flex",
    alignItems: "center",
    gap: 12,
    marginBottom: 8
  },
  runningTitle: {
    margin: 0,
    fontSize: 18,
    fontWeight: 700,
    color: "var(--text-primary)"
  },
  runningSubtitle: {
    fontSize: 13,
    color: "var(--text-muted)",
    marginBottom: 20,
    maxWidth: 500,
    lineHeight: 1.5
  },
  progressBarBg: {
    width: "100%",
    maxWidth: 400,
    height: 8,
    background: "var(--bg-page)",
    borderRadius: 999,
    overflow: "hidden",
    marginBottom: 8
  },
  progressBarFill: {
    height: "100%",
    background: "var(--brand)",
    borderRadius: 999,
    transition: "width 0.3s ease"
  },
  progressPercent: {
    fontSize: 12,
    fontWeight: 700,
    color: "var(--brand)",
    marginBottom: 24
  },
  statsCardGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(4, 1fr)",
    gap: 12,
    width: "100%",
    maxWidth: 800,
    background: "var(--bg-page)",
    padding: 16,
    borderRadius: 10,
    border: "1px solid var(--border)"
  },
  statGridItem: {
    display: "flex",
    flexDirection: "column",
    alignItems: "flex-start",
    textAlign: "left",
    background: "var(--bg-card)",
    border: "1px solid var(--border)",
    padding: 10,
    borderRadius: 6
  },
  statLabel: {
    fontSize: 9.5,
    fontWeight: 700,
    color: "var(--text-secondary)",
    textTransform: "uppercase",
    marginBottom: 4
  },
  statVal: {
    fontSize: 12.5,
    fontWeight: 650,
    color: "var(--text-primary)",
    wordBreak: "break-all"
  }
};
