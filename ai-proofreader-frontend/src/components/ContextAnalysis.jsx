import React, { useState, useEffect } from "react";
import { 
  fetchDocument, 
  runContextAnalysis, 
  API_BASE_URL 
} from "../api";

export default function ContextAnalysis({ id, onShowInDocument }) {
  const [activeWorkspaceTab, setActiveWorkspaceTab] = useState("overview"); // overview | clusters | claims | chunk | cluster | claude | final
  
  // Loading and error states
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState(null);
  const [docProgress, setDocProgress] = useState(null);
  
  // Loaded reports data
  const [clustersReport, setClustersReport] = useState(null);
  const [claimsReport, setClaimsReport] = useState(null);
  const [chunkReport, setChunkReport] = useState(null);
  const [clusterReport, setClusterReport] = useState(null);
  const [claudeReport, setClaudeReport] = useState(null);
  const [finalReport, setFinalReport] = useState(null);

  // Status checks and auto-run poll loops
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
          // Fetch final report by default
          await fetchAllReports();
        } else if (docData.context_analysis_status === "not_started") {
          setRunning(true);
          await runContextAnalysis(id);
          timerId = setTimeout(checkStatus, 2000);
        } else if (docData.context_analysis_status === "failed") {
          setRunning(false);
          setError("Auditing execution pass failed: " + (docData.error || "Check backend engine log."));
        } else {
          // Fallback check
          await fetchAllReports();
        }
      } catch (err) {
        if (err.message.includes("404")) {
          try {
            setRunning(true);
            await runContextAnalysis(id);
            timerId = setTimeout(checkStatus, 2000);
          } catch (triggerErr) {
            if (active) setError("Failed to initialize audit pipeline: " + triggerErr.message);
          }
        } else {
          if (active) setError("Connection anomaly: " + err.message);
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

  const fetchAllReports = async () => {
    try {
      const fetchJson = async (url) => {
        const res = await fetch(url);
        if (!res.ok) throw new Error(`Report not ready: ${res.status}`);
        return res.json();
      };
      
      const [clusters, claims, chunk, cluster, claude, final] = await Promise.all([
        fetchJson(`${API_BASE_URL}/reports/${id}/semantic-clusters`).catch(() => null),
        fetchJson(`${API_BASE_URL}/reports/${id}/claim-extraction`).catch(() => null),
        fetchJson(`${API_BASE_URL}/reports/${id}/chunk-reasoning`).catch(() => null),
        fetchJson(`${API_BASE_URL}/reports/${id}/cluster-reasoning`).catch(() => null),
        fetchJson(`${API_BASE_URL}/reports/${id}/claude-verification`).catch(() => null),
        fetchJson(`${API_BASE_URL}/reports/${id}/final-report`).catch(() => null)
      ]);

      if (clusters) setClustersReport(clusters);
      if (claims) setClaimsReport(claims);
      if (chunk) setChunkReport(chunk);
      if (cluster) setClusterReport(cluster);
      if (claude) setClaudeReport(claude);
      if (final) setFinalReport(final);
    } catch (e) {
      console.error("Error fetching pipeline sub-reports", e);
    }
  };

  const handleGenerate = async () => {
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

  const handleDownload = (downloadUrl, filename) => {
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
        <p style={{ marginTop: 16, fontSize: 14, color: "var(--text-muted)" }}>Retrieving audit database records...</p>
      </div>
    );
  }

  if (running) {
    const stage = docProgress?.context_analysis_stage || "Analyzing Inconsistencies";
    const pct = docProgress?.context_analysis_progress || 0;
    return (
      <div style={styles.runningContainer}>
        <div style={styles.runningHeader}>
          <div style={styles.spinner} />
          <h3 style={styles.runningTitle}>Context Audit In Progress</h3>
        </div>
        <p style={styles.runningSubtitle}>
          The senior compliance review agent is processing semantic graphs, extracting claims, and reconciling conflicts.
        </p>
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
            <span style={styles.statLabel}>Page Scope</span>
            <span style={styles.statVal}>{docProgress?.current_page || 0} / {docProgress?.total_pages || "N/A"}</span>
          </div>
          <div style={styles.statGridItem}>
            <span style={styles.statLabel}>Processing Time</span>
            <span style={styles.statVal}>{docProgress?.context_analysis_est_time || "Estimating..."}</span>
          </div>
          <div style={styles.statGridItem}>
            <span style={styles.statLabel}>Issues Detected</span>
            <span style={{ ...styles.statVal, color: "var(--red)" }}>{docProgress?.context_analysis_issues_count || 0}</span>
          </div>
        </div>
      </div>
    );
  }

  if (!finalReport) {
    return (
      <div style={styles.emptyContainer}>
        <h3>No Auditing Reports Found</h3>
        <p style={{ maxWidth: 450, color: "var(--text-muted)", fontSize: 13, marginBottom: 20 }}>
          This requirements auditing engine identifies pronoun ambiguities, terminology drift, and contradictory policies.
        </p>
        <button style={styles.actionBtn} onClick={handleGenerate}>Run Audit Pipeline</button>
        {error && <p style={{ color: "var(--red)", fontSize: 12, marginTop: 12 }}>{error}</p>}
      </div>
    );
  }

  const fMeta = finalReport.metadata || {};
  const fData = finalReport.data || {};

  return (
    <div style={styles.workspaceWrapper}>
      
      {/* Tab bar */}
      <div style={styles.tabBar}>
        <button 
          style={{ ...styles.tabBtn, ...(activeWorkspaceTab === "overview" ? styles.tabBtnActive : {}) }}
          onClick={() => setActiveWorkspaceTab("overview")}
        >
          🏠 Overview
        </button>
        <button 
          style={{ ...styles.tabBtn, ...(activeWorkspaceTab === "clusters" ? styles.tabBtnActive : {}) }}
          onClick={() => setActiveWorkspaceTab("clusters")}
        >
          📦 Related Sections
        </button>
        <button 
          style={{ ...styles.tabBtn, ...(activeWorkspaceTab === "claims" ? styles.tabBtnActive : {}) }}
          onClick={() => setActiveWorkspaceTab("claims")}
        >
          📄 Extracted Claims
        </button>
        <button 
          style={{ ...styles.tabBtn, ...(activeWorkspaceTab === "chunk" ? styles.tabBtnActive : {}) }}
          onClick={() => setActiveWorkspaceTab("chunk")}
        >
          📄 Section Analysis
        </button>
        <button 
          style={{ ...styles.tabBtn, ...(activeWorkspaceTab === "cluster" ? styles.tabBtnActive : {}) }}
          onClick={() => setActiveWorkspaceTab("cluster")}
        >
          🌐 Multi-Section Conflict
        </button>
        <button 
          style={{ ...styles.tabBtn, ...(activeWorkspaceTab === "claude" ? styles.tabBtnActive : {}) }}
          onClick={() => setActiveWorkspaceTab("claude")}
        >
          🛡️ Claude Audit Review
        </button>
        <button 
          style={{ ...styles.tabBtn, ...(activeWorkspaceTab === "final" ? styles.tabBtnActive : {}) }}
          onClick={() => setActiveWorkspaceTab("final")}
        >
          💼 Executive report
        </button>
      </div>

      {/* Main Tab Panels */}
      <div style={styles.panelContent}>
        
        {/* 1. Overview */}
        {activeWorkspaceTab === "overview" && (
          <div>
            <div style={styles.headerRow}>
              <div>
                <h3 style={styles.panelTitle}>Compliance Audit Dashboard</h3>
                <p style={styles.panelDesc}>Corporate assurance review verifying narrative coherence, spelling references, and metrics.</p>
              </div>
              <div style={styles.downloadsRow}>
                <button style={styles.downloadBtn} onClick={() => handleDownload(fMeta.download_urls?.json, "final_report.json")}>
                  Developer JSON
                </button>
                <button style={styles.downloadBtn} onClick={() => handleDownload(fMeta.download_urls?.markdown, "final_report.md")}>
                  Markdown report
                </button>
                <button style={styles.downloadActiveBtn} onClick={() => handleDownload(fMeta.download_urls?.html, "final_report.html")}>
                  Open Interactive HTML
                </button>
              </div>
            </div>

            <div style={styles.metricsGrid}>
              <div style={styles.metricCard}>
                <span style={styles.metricLabel}>Document Health</span>
                <span style={{ 
                  ...styles.metricValue, 
                  color: fData.overall_document_health === "Poor" ? "var(--red)" : (fData.overall_document_health === "Fair" ? "var(--amber)" : "var(--green)") 
                }}>
                  {fData.overall_document_health || "Good"}
                </span>
              </div>
              <div style={styles.metricCard}>
                <span style={styles.metricLabel}>Consistency Score</span>
                <span style={styles.metricValue}>{fData.consistency_score || 100}%</span>
              </div>
              <div style={styles.metricCard}>
                <span style={styles.metricLabel}>Quality Index</span>
                <span style={styles.metricValue}>{fData.quality_score || 100}%</span>
              </div>
              <div style={styles.metricCard}>
                <span style={styles.metricLabel}>Readability rating</span>
                <span style={styles.metricValue}>{fData.readability_score || "High"}</span>
              </div>
            </div>

            <div style={styles.detailCard}>
              <h4>Executive Summary</h4>
              <p style={{ lineHeight: 1.6 }}>{fData.executive_summary?.summary_text}</p>
            </div>
          </div>
        )}

        {/* 2. Semantic Clusters */}
        {activeWorkspaceTab === "clusters" && (
          <div>
            <h3 style={styles.panelTitle}>Mapped Related Sections (Semantic Communities)</h3>
            <table style={styles.table}>
              <thead>
                <tr>
                  <th>Community ID</th>
                  <th>Topic Summary Label</th>
                  <th>Section Size</th>
                  <th>Similarity Index</th>
                  <th>Document Sections</th>
                </tr>
              </thead>
              <tbody>
                {(clustersReport?.data || []).map((cl) => (
                  <tr key={cl.cluster_id}>
                    <td style={{ fontFamily: "monospace", fontWeight: "bold" }}>{cl.cluster_id}</td>
                    <td><strong>{cl.topic_summary}</strong></td>
                    <td>{cl.cluster_size}</td>
                    <td>{cl.average_similarity.toFixed(3)}</td>
                    <td style={{ fontFamily: "monospace", fontSize: 11 }}>{cl.chunk_ids.join(", ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* 3. Claims */}
        {activeWorkspaceTab === "claims" && (
          <div>
            <h3 style={styles.panelTitle}>Extracted Factual Claims Index</h3>
            <table style={styles.table}>
              <thead>
                <tr>
                  <th>Finding ID</th>
                  <th>Document Location</th>
                  <th>Section Type</th>
                  <th>Factual Directive Statement</th>
                </tr>
              </thead>
              <tbody>
                {Object.keys(claimsReport?.data || {}).map((cid) => {
                  const ch = claimsReport?.data[cid] || {};
                  return (ch.extraction?.claims || []).map((c, i) => (
                    <tr key={`${cid}_claim_${i}`}>
                      <td style={{ fontFamily: "monospace" }}>{c.claim_id}</td>
                      <td style={{ fontFamily: "monospace", fontSize: 11 }}>{cid}</td>
                      <td><span style={styles.badge}>{c.type}</span></td>
                      <td>{c.text}</td>
                    </tr>
                  ));
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* 4. Chunk Analysis */}
        {activeWorkspaceTab === "chunk" && (
          <div>
            <h3 style={styles.panelTitle}>Section-Level Ambiguities & Rewrites</h3>
            <table style={styles.table}>
              <thead>
                <tr>
                  <th>Finding ID</th>
                  <th>Document Location</th>
                  <th>Ambiguity Wording Type</th>
                  <th>Severity</th>
                  <th>Original Text Quote</th>
                  <th>Consulting Suggestion Rewrite</th>
                </tr>
              </thead>
              <tbody>
                {Object.keys(chunkReport?.data || {}).map((cid) => {
                  const cr = chunkReport?.data[cid] || {};
                  return (cr.ambiguities || []).map((amb, i) => (
                    <tr key={`${cid}_amb_${i}`}>
                      <td style={{ fontFamily: "monospace" }}>{amb.issue_id}</td>
                      <td style={{ fontFamily: "monospace", fontSize: 11 }}>{cid}</td>
                      <td>{amb.type}</td>
                      <td>
                        <span style={{ 
                          ...styles.badge, 
                          backgroundColor: amb.severity === "High" ? "#fee2e2" : "#fef3c7",
                          color: amb.severity === "High" ? "#b91c1c" : "#d97706"
                        }}>
                          {amb.severity}
                        </span>
                      </td>
                      <td style={{ fontStyle: "italic" }}>"{amb.quote}"</td>
                      <td style={{ color: "var(--brand)", fontWeight: 500 }}>{amb.suggested_rewrite}</td>
                    </tr>
                  ));
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* 5. Cluster Analysis */}
        {activeWorkspaceTab === "cluster" && (
          <div>
            <h3 style={styles.panelTitle}>Cross-Section Inconsistencies & Policy Conflicts</h3>
            <table style={styles.table}>
              <thead>
                <tr>
                  <th>Finding ID</th>
                  <th>Topic Community ID</th>
                  <th>Conflict Type</th>
                  <th>Severity</th>
                  <th>Description Explanation</th>
                  <th>Suggested Resolution Action</th>
                </tr>
              </thead>
              <tbody>
                {Object.keys(clusterReport?.data || {}).map((clid) => {
                  const clr = clusterReport?.data[clid] || {};
                  return (clr.cluster_findings || []).map((find, i) => (
                    <tr key={`${clid}_find_${i}`}>
                      <td style={{ fontFamily: "monospace" }}>{find.issue_id}</td>
                      <td style={{ fontFamily: "monospace" }}>{clid}</td>
                      <td><strong>{find.type}</strong></td>
                      <td>
                        <span style={{ 
                          ...styles.badge, 
                          backgroundColor: "#fca5a5",
                          color: "#b91c1c"
                        }}>
                          {find.severity}
                        </span>
                      </td>
                      <td>{find.description}</td>
                      <td style={{ color: "var(--brand)", fontWeight: 500 }}>{find.suggested_resolution}</td>
                    </tr>
                  ));
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* 6. Claude Verification */}
        {activeWorkspaceTab === "claude" && (
          <div>
            <h3 style={styles.panelTitle}>Claude Verified & Filtered Audit Results</h3>
            <table style={styles.table}>
              <thead>
                <tr>
                  <th>Finding ID</th>
                  <th>Verification Status</th>
                  <th>Audit Category</th>
                  <th>Severity Rating</th>
                  <th>Verification Audit Reason</th>
                  <th>Suggested Action</th>
                </tr>
              </thead>
              <tbody>
                {(claudeReport?.data?.verified_findings || []).map((f) => (
                  <tr key={f.issue_id}>
                    <td style={{ fontFamily: "monospace", fontWeight: "bold" }}>{f.issue_id}</td>
                    <td>
                      <span style={{ 
                        ...styles.badge, 
                        backgroundColor: f.status === "confirmed" ? "#d1fae5" : "#fee2e2",
                        color: f.status === "confirmed" ? "#065f46" : "#991b1b"
                      }}>
                        {f.status.toUpperCase()}
                      </span>
                    </td>
                    <td>{f.business_category}</td>
                    <td><span style={styles.badge}>{f.severity}</span></td>
                    <td>{f.reason}</td>
                    <td style={{ color: "var(--brand)", fontWeight: 500 }}>{f.recommendation}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* 7. Final Report */}
        {activeWorkspaceTab === "final" && (
          <div>
            <div style={styles.headerRow}>
              <div>
                <h3 style={styles.panelTitle}>Polished Business Compliance Audit Report</h3>
                <p style={styles.panelDesc}>Formally compiled audit findings utilizing business terminology and consulting impact reviews.</p>
              </div>
            </div>

            {fData.findings?.map((f) => (
              <div key={f.finding_id} style={styles.findingCard}>
                <div style={styles.findingHeader}>
                  <strong>{f.title}</strong>
                  <span style={{ 
                    ...styles.badge, 
                    backgroundColor: f.severity === "High" ? "#fee2e2" : "#fef3c7",
                    color: f.severity === "High" ? "#b91c1c" : "#d97706"
                  }}>{f.severity}</span>
                </div>
                <div style={styles.findingBody}>
                  <p><strong>Category:</strong> {f.category}</p>
                  <p><strong>Explanation:</strong> {f.explanation}</p>
                  <p style={{ color: "#991b1b" }}><strong>Business Impact:</strong> {f.business_impact}</p>
                  <p><strong>Suggested Resolution:</strong> {f.suggested_resolution}</p>
                  <div style={styles.evidenceBox}>
                    <strong>Supporting Evidence Locations:</strong>
                    <ul style={{ margin: "5px 0 0 15px", padding: 0 }}>
                      {(f.evidence || []).map((ev, i) => (
                        <li key={i}>Section Location <code>{ev.chunk_id}</code>: "{ev.quote}"</li>
                      ))}
                    </ul>
                  </div>
                </div>
              </div>
            ))}
          </div>
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
    padding: 60,
    background: "var(--bg-card)",
    borderRadius: 12,
    border: "1px solid var(--border)",
  },
  spinner: {
    width: 24,
    height: 24,
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
    padding: 60,
    background: "var(--bg-card)",
    borderRadius: 12,
    border: "1px solid var(--border)",
    textAlign: "center"
  },
  actionBtn: {
    background: "var(--brand)",
    color: "#fff",
    border: "none",
    borderRadius: 6,
    padding: "8px 16px",
    fontSize: 13,
    fontWeight: "bold",
    cursor: "pointer"
  },
  runningContainer: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    padding: 40,
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
    fontSize: 16,
    fontWeight: 700,
  },
  runningSubtitle: {
    fontSize: 13,
    color: "var(--text-muted)",
    marginBottom: 20,
    maxWidth: 480,
    lineHeight: 1.5
  },
  progressBarBg: {
    width: "100%",
    maxWidth: 350,
    height: 6,
    background: "var(--border)",
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
    fontWeight: "bold",
    color: "var(--brand)",
    marginBottom: 20
  },
  statsCardGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(4, 1fr)",
    gap: 12,
    width: "100%",
    maxWidth: 700,
    background: "var(--bg-hover)",
    padding: 12,
    borderRadius: 8,
    border: "1px solid var(--border)"
  },
  statGridItem: {
    display: "flex",
    flexDirection: "column",
    alignItems: "flex-start",
    textAlign: "left",
    background: "var(--bg-card)",
    border: "1px solid var(--border)",
    padding: 8,
    borderRadius: 4
  },
  statLabel: {
    fontSize: 9,
    fontWeight: 700,
    color: "var(--text-muted)",
    textTransform: "uppercase",
    marginBottom: 2
  },
  statVal: {
    fontSize: 12,
    fontWeight: "bold",
  },
  workspaceWrapper: {
    display: "flex",
    flexDirection: "column",
    gap: 20
  },
  tabBar: {
    display: "flex",
    gap: 8,
    borderBottom: "1px solid var(--border)",
    paddingBottom: 8,
    overflowX: "auto"
  },
  tabBtn: {
    background: "none",
    border: "none",
    padding: "8px 12px",
    fontSize: 13,
    fontWeight: 500,
    color: "var(--text-muted)",
    cursor: "pointer",
    borderRadius: 4,
    whiteSpace: "nowrap"
  },
  tabBtnActive: {
    background: "var(--brand-light)",
    color: "var(--brand)",
    fontWeight: "bold"
  },
  panelContent: {
    padding: "10px 0"
  },
  panelTitle: {
    margin: "0 0 4px 0",
    fontSize: 16,
    fontWeight: 700
  },
  panelDesc: {
    margin: "0 0 20px 0",
    fontSize: 13,
    color: "var(--text-muted)"
  },
  headerRow: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "flex-start",
    gap: 20,
    flexWrap: "wrap",
    marginBottom: 20
  },
  downloadsRow: {
    display: "flex",
    gap: 8
  },
  downloadBtn: {
    background: "none",
    border: "1px solid var(--border)",
    borderRadius: 6,
    padding: "6px 12px",
    fontSize: 12,
    cursor: "pointer",
    color: "var(--text-primary)"
  },
  downloadActiveBtn: {
    background: "var(--brand)",
    color: "#fff",
    border: "none",
    borderRadius: 6,
    padding: "6px 12px",
    fontSize: 12,
    fontWeight: "bold",
    cursor: "pointer"
  },
  metricsGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(4, 1fr)",
    gap: 16,
    marginBottom: 24
  },
  metricCard: {
    background: "var(--bg-card)",
    border: "1px solid var(--border)",
    borderRadius: 8,
    padding: 16,
    display: "flex",
    flexDirection: "column",
    gap: 4
  },
  metricLabel: {
    fontSize: 11,
    fontWeight: 600,
    color: "var(--text-muted)"
  },
  metricValue: {
    fontSize: 20,
    fontWeight: 800,
    color: "var(--primary)"
  },
  detailCard: {
    background: "var(--bg-card)",
    border: "1px solid var(--border)",
    borderRadius: 8,
    padding: 20
  },
  table: {
    width: "100%",
    borderCollapse: "collapse",
    background: "var(--bg-card)"
  },
  badge: {
    background: "var(--brand-light)",
    color: "var(--brand)",
    padding: "2px 6px",
    borderRadius: 4,
    fontSize: 10,
    fontWeight: "bold",
    textTransform: "uppercase"
  },
  findingCard: {
    background: "var(--bg-card)",
    border: "1px solid var(--border)",
    borderRadius: 8,
    marginBottom: 16,
    overflow: "hidden"
  },
  findingHeader: {
    padding: "12px 16px",
    background: "var(--bg-hover)",
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    borderBottom: "1px solid var(--border)"
  },
  findingBody: {
    padding: 16,
    fontSize: 13,
    lineHeight: 1.5
  },
  evidenceBox: {
    background: "var(--bg-hover)",
    padding: 12,
    borderRadius: 6,
    marginTop: 10,
    borderLeft: "3px solid var(--border)"
  }
};
