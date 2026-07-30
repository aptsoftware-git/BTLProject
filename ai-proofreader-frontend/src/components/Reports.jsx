import React, { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import {
  fetchDocuments,
  fetchDocument,
  fetchFinalReport,
  fetchClaudeVerificationReport,
  fetchChunkReasoningReport,
  fetchClusterReasoningReport,
  fetchComparativeAnalysis
} from "../api";

export default function Reports({ activeDocId }) {
  const navigate = useNavigate();
  const [documents, setDocuments] = useState([]);
  const [selectedDocId, setSelectedDocId] = useState("");
  const [activeDoc, setActiveDoc] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [reportsState, setReportsState] = useState({});
  const [exportDropdownOpen, setExportDropdownOpen] = useState(false);

  // Modal / Dedicated View state
  const [activeModalReportKey, setActiveModalReportKey] = useState(null);
  const [modalReportData, setModalReportData] = useState(null);
  const [modalLoading, setModalLoading] = useState(false);
  const [modalFilter, setModalFilter] = useState("ALL");

  const [searchTerm, setSearchTerm] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("ALL");
  const [selectedSeverity, setSelectedSeverity] = useState("ALL");
  const [verifiedOnly, setVerifiedOnly] = useState(false);
  const [highPriorityOnly, setHighPriorityOnly] = useState(false);
  const [showRejectedOnly, setShowRejectedOnly] = useState(false);

  useEffect(() => {
    async function loadDocs() {
      setLoading(true);
      setError(null);
      try {
        const docs = await fetchDocuments();
        setDocuments(docs);

        const storedId = activeDocId || localStorage.getItem("currentlyOpenDocId");
        if (storedId && docs.some(d => d.id === storedId)) {
          setSelectedDocId(storedId);
        } else if (docs.length > 0) {
          setSelectedDocId(docs[0].id);
        }
      } catch (err) {
        setError("Failed to fetch documents list.");
      } finally {
        setLoading(false);
      }
    }
    loadDocs();
  }, [activeDocId]);

  const checkStatusAndReports = useCallback(async () => {
    if (!selectedDocId) return;

    try {
      const doc = await fetchDocument(selectedDocId).catch(() => null);
      if (doc) setActiveDoc(doc);

      const isDocProcessing = doc && (
        doc.context_analysis_status === "running" || 
        doc.context_analysis_status === "pending"
      );

      const reportKeys = [
        "final-report",
        "claude-verification",
        "chunk-reasoning",
        "cluster-reasoning",
        "comparative-analysis"
      ];

      const newReportsState = {};

      await Promise.all(
        reportKeys.map(async (key) => {
          try {
            const res = await fetch(`/api/reports/${selectedDocId}/${key}`);
            if (res.ok) {
              const resJson = await res.json();
              const meta = resJson.metadata || {};
              const isGen = meta.status === "generating";

              if (isGen || (!resJson.data && isDocProcessing)) {
                newReportsState[key] = {
                  state: "generating",
                  isReady: false,
                  isGenerating: true,
                  isWaiting: false,
                  isFailed: false,
                  timestamp: doc?.current_stage || "Generating report...",
                  meta: meta,
                  data: null
                };
              } else if (resJson.data) {
                const rawDate = meta.created_at || meta.timestamp;
                let formattedTime = "Generated recently";

                if (rawDate) {
                  try {
                    const parsed = new Date(rawDate);
                    if (!isNaN(parsed.getTime())) {
                      formattedTime = parsed.toLocaleString("en-US", {
                        month: "short",
                        day: "numeric",
                        hour: "2-digit",
                        minute: "2-digit"
                      });
                    }
                  } catch (e) {
                    formattedTime = rawDate;
                  }
                }

                newReportsState[key] = {
                  state: "ready",
                  isReady: true,
                  isGenerating: false,
                  isWaiting: false,
                  isFailed: false,
                  timestamp: formattedTime,
                  meta: meta,
                  data: resJson.data
                };
              } else {
                newReportsState[key] = {
                  state: "waiting",
                  isReady: false,
                  isGenerating: false,
                  isWaiting: true,
                  isFailed: false,
                  timestamp: "Pending",
                  meta: meta,
                  data: null
                };
              }
            } else {
              newReportsState[key] = {
                state: "waiting",
                isReady: false,
                isGenerating: false,
                isWaiting: true,
                isFailed: false,
                timestamp: "Pending",
                meta: {},
                data: null
              };
            }
          } catch (e) {
            newReportsState[key] = {
              state: "waiting",
              isReady: false,
              isGenerating: false,
              isWaiting: true,
              isFailed: false,
              timestamp: "Pending",
              meta: {},
              data: null
            };
          }
        })
      );

      setReportsState(newReportsState);
    } catch (err) {
      console.error("Error in checkStatusAndReports:", err);
    }
  }, [selectedDocId]);

  useEffect(() => {
    if (!selectedDocId) return;

    checkStatusAndReports();

    const interval = setInterval(() => {
      if (
        activeDoc?.status === "processing" ||
        activeDoc?.context_analysis_status === "running" ||
        Object.values(reportsState).some(r => r.isGenerating)
      ) {
        checkStatusAndReports();
      }
    }, 4000);

    return () => clearInterval(interval);
  }, [selectedDocId, activeDoc?.status, activeDoc?.context_analysis_status, reportsState, checkStatusAndReports]);

  // Open dedicated viewer for each specific report card
  const handleViewReportCard = async (key) => {
    if (key === "comparative-analysis") {
      navigate(`/documents/${selectedDocId}?tab=comparative`);
      return;
    }

    setActiveModalReportKey(key);
    setModalLoading(true);
    setModalReportData(null);
    setModalFilter("ALL");

    try {
      let result = null;
      if (key === "final-report") {
        result = await fetchFinalReport(selectedDocId);
      } else if (key === "claude-verification") {
        result = await fetchClaudeVerificationReport(selectedDocId);
      } else if (key === "chunk-reasoning") {
        result = await fetchChunkReasoningReport(selectedDocId);
      } else if (key === "cluster-reasoning") {
        result = await fetchClusterReasoningReport(selectedDocId);
      }
      setModalReportData(result?.data || result);
    } catch (err) {
      console.error(`Error loading ${key}:`, err);
    } finally {
      setModalLoading(false);
    }
  };

  const handleDownloadPdf = (reportKey, title = "Report") => {
    const link = document.createElement("a");
    link.href = `/api/reports/${selectedDocId}/${reportKey}/pdf`;
    link.download = `${reportKey}_${selectedDocId}.pdf`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const finalRep = reportsState["final-report"] || {};
  const fData = finalRep.data || {};

  const kpis = {
    total_findings: fData.total_issues || activeDoc?.issues?.length || 0,
    confirmed_findings: fData.confirmed_issues_count || (fData.findings || []).length,
    rejected_false_positives: fData.rejected_issues_count || (fData.rejected_findings || []).length,
    publication_readiness: fData.executive_summary?.readiness || "Conditional Approval",
    publication_guidance: fData.executive_summary?.guidance || "Review flagged critical clauses prior to release."
  };

  const findingsList = fData.findings || [];

  return (
    <div style={styles.container}>
      {/* Page Header */}
      <div style={styles.header}>
        <div>
          <h1 style={styles.title}>Executive Audit & Intelligence Reports</h1>
          <p style={styles.subtitle}>
            Enterprise Document Reference: <code style={styles.codeRef}>{selectedDocId}</code>
          </p>
        </div>
        
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          {documents.length > 1 && (
            <select
              value={selectedDocId}
              onChange={(e) => {
                setSelectedDocId(e.target.value);
                localStorage.setItem("currentlyOpenDocId", e.target.value);
              }}
              style={styles.docSelect}
            >
              {documents.map(d => (
                <option key={d.id} value={d.id}>{d.filename}</option>
              ))}
            </select>
          )}

          <div style={{ position: "relative" }}>
            <button
              disabled={!finalRep?.isReady}
              onClick={() => setExportDropdownOpen(!exportDropdownOpen)}
              style={{
                ...styles.exportBtn,
                opacity: finalRep?.isReady ? 1 : 0.6
              }}
            >
              📥 Export Package ▼
            </button>
            {exportDropdownOpen && (
              <div style={styles.dropdownMenu}>
                <button style={styles.dropdownItem} onClick={() => { setExportDropdownOpen(false); handleDownloadPdf("final-report", "Executive Audit Report"); }}>
                  📄 Export Executive Report (PDF)
                </button>
                <button style={styles.dropdownItem} onClick={() => { setExportDropdownOpen(false); navigate(`/documents/${selectedDocId}?tab=comparative`); }}>
                  📊 View Executive Comparative Report
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Cache Info Banner */}
      {activeDoc?.cache_info?.cached && (
        <div style={styles.cacheBanner}>
          <div style={styles.cacheHeader}>
            <span style={styles.cacheBadge}>⚡ Cache Status</span>
            <strong>SHA-256 Hash Matched — Reused Verified Pipeline Artifacts</strong>
          </div>
        </div>
      )}

      {/* 5 Report Cards Grid */}
      <div style={styles.reportCardsGrid}>
        {[
          { key: "final-report", title: "Executive Compliance Report", desc: "Opens Executive Compliance Report viewer" },
          { key: "comparative-analysis", title: "Executive Comparative Analysis Report", desc: "Opens Comparative Analysis View" },
          { key: "claude-verification", title: "Claude Verification Report", desc: "Opens Claude Verification Report" },
          { key: "chunk-reasoning", title: "Chunk Reasoning Report", desc: "Opens Chunk Reasoning Report" },
          { key: "cluster-reasoning", title: "Cluster Reasoning Report", desc: "Opens Cluster Reasoning Report" }
        ].map(item => {
          const st = reportsState[item.key] || {};
          const isCompRep = item.key === "comparative-analysis";
          return (
            <div key={item.key} style={styles.reportStatusCard}>
              <div style={styles.reportStatusTitle}>{item.title}</div>
              <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2 }}>{item.desc}</div>
              
              {st.isReady ? (
                <div>
                  <div style={styles.stateBadgeReady}>✓ Ready</div>
                  <div style={styles.reportTimeText}>{st.timestamp}</div>
                  <div style={{ ...styles.btnRow, flexWrap: "wrap", gap: 6, marginTop: 8 }}>
                    <button style={styles.viewBtn} onClick={() => handleViewReportCard(item.key)}>View</button>
                    
                    {isCompRep ? (
                      <>
                        <a href={`/api/download/${selectedDocId}/comparative_report.html`} download style={{ textDecoration: "none" }}>
                          <button style={{ ...styles.dlBtn, background: "var(--brand-light)", color: "var(--brand)" }}>HTML</button>
                        </a>
                        <a href={`/api/download/${selectedDocId}/comparative_report.json`} download style={{ textDecoration: "none" }}>
                          <button style={{ ...styles.dlBtn, background: "var(--brand-light)", color: "var(--brand)" }}>JSON</button>
                        </a>
                        <button style={styles.dlBtn} onClick={() => handleDownloadPdf("comparative-analysis", item.title)}>PDF</button>
                      </>
                    ) : (
                      <>
                        <a href={`/api/reports/${selectedDocId}/${item.key}`} target="_blank" rel="noreferrer" style={{ textDecoration: "none" }}>
                          <button style={{ ...styles.dlBtn, background: "#f8fafc" }}>JSON</button>
                        </a>
                        <button style={styles.dlBtn} onClick={() => handleDownloadPdf(item.key, item.title)}>PDF</button>
                      </>
                    )}
                  </div>
                </div>
              ) : st.isGenerating ? (
                <div>
                  <div style={styles.stateBadgeGenerating}>⏳ Generating</div>
                  <div style={styles.reportSubText}>Processing stage...</div>
                </div>
              ) : (
                <div>
                  <div style={styles.stateBadgeWaiting}>Waiting...</div>
                  <div style={styles.reportSubText}>Analysis pending</div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Default Inline View: Executive Compliance Summary */}
      <div style={styles.layout}>
        <div style={styles.sectionBlock}>
          <div style={styles.sectionHeader}>
            <span style={styles.sectionNumber}>OVERVIEW</span>
            <h2 style={styles.sectionTitleText}>Executive Audit Overview</h2>
          </div>
          <div style={styles.summaryCard}>
            <p style={styles.summaryParagraph}>
              {fData.executive_summary?.summary_text || `Executive Audit Report for document ${selectedDocId}. Evaluated by automated proofreading and Anthropic Claude verification.`}
            </p>
            <div style={styles.summaryMetaRow}>
              <span style={styles.badgeReadiness}>
                Status: <strong>{kpis.publication_readiness}</strong>
              </span>
              <span style={{ fontSize: 12.5, color: "#64748b" }}>
                {kpis.publication_guidance}
              </span>
            </div>
          </div>
        </div>

        <div style={styles.sectionBlock}>
          <div style={styles.sectionHeader}>
            <span style={styles.sectionNumber}>AUDIT LOG</span>
            <h2 style={styles.sectionTitleText}>Audited Detections ({findingsList.length})</h2>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {findingsList.slice(0, 5).map((f, idx) => (
              <div key={idx} style={{ padding: 12, background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 8 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ fontSize: 12, fontWeight: 700, color: "#0f172a" }}>Page {f.page_number || f.page || 1} &bull; {f.category || f.ambiguity_category || "Issue"}</span>
                  <span style={{ fontSize: 11, fontWeight: 700, padding: "2px 6px", borderRadius: 4, background: f.severity === "Critical" ? "#fef2f2" : "#fef3c7", color: f.severity === "Critical" ? "#dc2626" : "#d97706" }}>
                    {f.severity || "Medium"}
                  </span>
                </div>
                <p style={{ margin: "6px 0 0", fontSize: 12.5, color: "#334155" }}>{f.original_chunk || f.text || f.recommendation}</p>
              </div>
            ))}
            {findingsList.length > 5 && (
              <p style={{ fontSize: 12, color: "#64748b", margin: 0, textAlign: "center" }}>Showing 5 of {findingsList.length} findings. Use View on Executive Compliance Report card for full details.</p>
            )}
          </div>
        </div>
      </div>

      {/* ============================================================ */}
      {/* DEDICATED REPORT VIEWER MODALS                                */}
      {/* ============================================================ */}
      {activeModalReportKey && (
        <div style={modalStyles.overlay}>
          <div style={modalStyles.dialog}>
            <div style={modalStyles.header}>
              <div>
                <span style={modalStyles.keyBadge}>{activeModalReportKey.toUpperCase()}</span>
                <h2 style={modalStyles.title}>
                  {activeModalReportKey === "final-report" && "Executive Compliance Report"}
                  {activeModalReportKey === "claude-verification" && "Claude Verification Report"}
                  {activeModalReportKey === "chunk-reasoning" && "Chunk-Level Reasoning Report"}
                  {activeModalReportKey === "cluster-reasoning" && "Cluster-Level Reasoning Report"}
                </h2>
                <p style={modalStyles.subTitle}>Document: <code>{selectedDocId}</code></p>
              </div>
              <button style={modalStyles.closeBtn} onClick={() => setActiveModalReportKey(null)}>✕ Close</button>
            </div>

            <div style={modalStyles.body}>
              {modalLoading ? (
                <div style={{ padding: 40, textAlign: "center", color: "#64748b" }}>
                  <div style={styles.spinner} />
                  <p style={{ marginTop: 12 }}>Fetching dedicated report data from backend...</p>
                </div>
              ) : (
                <>
                  {/* VIEWER 1: EXECUTIVE COMPLIANCE REPORT */}
                  {activeModalReportKey === "final-report" && (
                    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                      <div style={styles.summaryCard}>
                        <h3 style={{ margin: "0 0 8px", fontSize: 14, fontWeight: 700 }}>Executive Narrative</h3>
                        <p style={styles.summaryParagraph}>{modalReportData?.executive_summary?.summary_text || execSummaryText}</p>
                      </div>

                      <div>
                        <h3 style={{ fontSize: 14, fontWeight: 700, margin: "0 0 8px" }}>Audited Detections</h3>
                        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                          {((modalReportData?.findings || findingsList) || []).map((f, i) => (
                            <div key={i} style={modalStyles.itemCard}>
                              <div style={{ display: "flex", justifyBetween: "space-between", alignItems: "center" }}>
                                <span style={{ fontWeight: 700, fontSize: 12.5 }}>Page {f.page_number || 1} &bull; {f.category || "General"}</span>
                                <span style={{ fontSize: 11, fontWeight: 700, color: "#166534", background: "#f0fdf4", padding: "2px 8px", borderRadius: 4 }}>
                                  {f.verification_status || "Verified"}
                                </span>
                              </div>
                              <p style={{ margin: "4px 0", fontSize: 12.5, color: "#334155" }}>{f.original_chunk || f.text}</p>
                              {f.recommended_resolution && (
                                <div style={{ fontSize: 12, color: "#166534", background: "#f0fdf4", padding: 6, borderRadius: 4, marginTop: 4 }}>
                                  <strong>Resolution:</strong> {f.recommended_resolution}
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    </div>
                  )}

                  {/* VIEWER 2: CLAUDE VERIFICATION REPORT */}
                  {activeModalReportKey === "claude-verification" && (
                    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                      <div style={{ display: "flex", gap: 12 }}>
                        <button
                          onClick={() => setModalFilter("ALL")}
                          style={{ ...modalStyles.filterTab, background: modalFilter === "ALL" ? "#0f172a" : "#f1f5f9", color: modalFilter === "ALL" ? "#fff" : "#475569" }}
                        >All Detections</button>
                        <button
                          onClick={() => setModalFilter("CONFIRMED")}
                          style={{ ...modalStyles.filterTab, background: modalFilter === "CONFIRMED" ? "#166534" : "#f1f5f9", color: modalFilter === "CONFIRMED" ? "#fff" : "#475569" }}
                        >Confirmed Detections</button>
                        <button
                          onClick={() => setModalFilter("REJECTED")}
                          style={{ ...modalStyles.filterTab, background: modalFilter === "REJECTED" ? "#dc2626" : "#f1f5f9", color: modalFilter === "REJECTED" ? "#fff" : "#475569" }}
                        >Rejected False Positives</button>
                      </div>

                      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                        {((modalReportData?.audited_findings || modalReportData?.findings || [])
                          .filter(f => {
                            if (modalFilter === "CONFIRMED") return (f.status || f.verification_status || "").toLowerCase().includes("confirm");
                            if (modalFilter === "REJECTED") return (f.status || f.verification_status || "").toLowerCase().includes("reject");
                            return true;
                          })
                        ).map((item, i) => (
                          <div key={i} style={modalStyles.itemCard}>
                            <div style={{ display: "flex", justifyBetween: "space-between", alignItems: "center", width: "100%" }}>
                              <span style={{ fontWeight: 700, fontSize: 12.5 }}>Finding #{i + 1}</span>
                              <span style={{
                                fontSize: 11, fontWeight: 800, padding: "2px 8px", borderRadius: 4,
                                background: (item.status || "").toLowerCase().includes("reject") ? "#fef2f2" : "#f0fdf4",
                                color: (item.status || "").toLowerCase().includes("reject") ? "#dc2626" : "#166534"
                              }}>
                                {item.status || item.verification_status || "Confirmed"}
                              </span>
                            </div>
                            <p style={{ margin: "6px 0", fontSize: 12.5, color: "#1e293b" }}>{item.original_chunk || item.text || item.claim_text}</p>
                            <div style={{ fontSize: 12, color: "#475569", background: "#f8fafc", padding: 8, borderRadius: 6 }}>
                              <strong>Claude Explanation:</strong> {item.claude_explanation || item.reason || item.why_claude_flagged_it || "Audited and verified by Anthropic Claude model."}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* VIEWER 3: CHUNK REASONING REPORT */}
                  {activeModalReportKey === "chunk-reasoning" && (
                    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                      <div style={{ fontSize: 12.5, color: "#64748b" }}>
                        Local LLM semantic chunk-level ambiguity detection findings:
                      </div>

                      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                        {((modalReportData?.chunks || modalReportData?.findings || [])).map((c, i) => (
                          <div key={i} style={modalStyles.itemCard}>
                            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, fontWeight: 700, color: "#1e40af" }}>
                              <span>Chunk ID: {c.chunk_id || `chunk_${i+1}`} &bull; Page {c.page_number || 1}</span>
                              <span>Category: {c.category || c.ambiguity_category || "Ambiguity"}</span>
                            </div>
                            <p style={{ margin: "6px 0", fontSize: 12.5, color: "#334155" }}>{c.text || c.original_chunk}</p>
                            <div style={{ fontSize: 12, color: "#1e40af", background: "#eff6ff", padding: 6, borderRadius: 4 }}>
                              <strong>Local LLM Reasoning:</strong> {c.reasoning || c.explanation || "Flagged potential ambiguity during chunk processing."}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* VIEWER 4: CLUSTER REASONING REPORT */}
                  {activeModalReportKey === "cluster-reasoning" && (
                    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                      <div style={{ fontSize: 12.5, color: "#64748b" }}>
                        Consolidated semantic issue clusters and root cause analysis:
                      </div>

                      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                        {((modalReportData?.clusters || modalReportData?.semantic_clusters || [])).map((cl, i) => (
                          <div key={i} style={modalStyles.itemCard}>
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                              <span style={{ fontWeight: 800, fontSize: 13, color: "#0f172a" }}>{cl.cluster_name || cl.title || `Cluster #${i+1}`}</span>
                              <span style={{ fontSize: 11, fontWeight: 800, padding: "2px 8px", borderRadius: 4, background: "#fef3c7", color: "#d97706" }}>
                                Severity: {cl.severity || "Medium"}
                              </span>
                            </div>
                            <p style={{ margin: "6px 0", fontSize: 12.5, color: "#334155" }}>{cl.description || cl.summary}</p>
                            <div style={{ fontSize: 12, color: "#0f172a", background: "#f8fafc", padding: 8, borderRadius: 6, border: "1px solid #e2e8f0" }}>
                              <strong>Root Cause & Cross-Chunk Tracing:</strong> {cl.root_cause || cl.actionable_resolution || "Cross-referencing verified multiple related instances."}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

const modalStyles = {
  overlay: {
    position: "fixed", top: 0, left: 0, right: 0, bottom: 0,
    background: "rgba(15, 23, 42, 0.75)", backdropFilter: "blur(4px)",
    display: "flex", alignItems: "center", justifyCenter: "center",
    zIndex: 9999, padding: 24
  },
  dialog: {
    background: "#ffffff", border: "1px solid #cbd5e1", borderRadius: 16,
    maxWidth: 840, width: "100%", maxHeight: "85vh", display: "flex",
    flexDirection: "column", boxShadow: "0 20px 25px -5px rgba(0, 0, 0, 0.2)",
    overflow: "hidden"
  },
  header: {
    padding: "20px 24px", borderBottom: "1px solid #e2e8f0",
    display: "flex", justifyContent: "space-between", alignItems: "flex-start",
    background: "#f8fafc"
  },
  keyBadge: { fontSize: 10, fontWeight: 900, color: "#1e40af", background: "#eff6ff", padding: "2px 6px", borderRadius: 4, textTransform: "uppercase" },
  title: { margin: "4px 0 0", fontSize: 18, fontWeight: 800, color: "#0f172a" },
  subTitle: { margin: "2px 0 0", fontSize: 12, color: "#64748b" },
  closeBtn: { background: "#f1f5f9", border: "1px solid #cbd5e1", borderRadius: 6, padding: "6px 12px", fontSize: 12, fontWeight: 700, cursor: "pointer", color: "#0f172a" },
  body: { padding: 24, overflowY: "auto", flex: 1 },
  itemCard: { background: "#ffffff", border: "1px solid #cbd5e1", borderRadius: 8, padding: 14, textAlign: "left" },
  filterTab: { border: "none", borderRadius: 6, padding: "6px 14px", fontSize: 12, fontWeight: 700, cursor: "pointer" }
};

const styles = {
  container: { maxWidth: 1000, margin: "0 auto", padding: "10px 0" },
  header: { display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 },
  title: { margin: 0, fontSize: 22, fontWeight: 800, color: "#0f172a" },
  subtitle: { margin: "4px 0 0", fontSize: 13, color: "#64748b" },
  codeRef: { background: "#f1f5f9", padding: "2px 6px", borderRadius: 4, fontFamily: "monospace", fontSize: 12 },
  docSelect: { padding: "8px 12px", borderRadius: 8, border: "1px solid #cbd5e1", fontSize: 13 },
  exportBtn: { background: "#0f172a", color: "#fff", border: "none", borderRadius: 8, padding: "8px 16px", fontSize: 13, fontWeight: 700, cursor: "pointer" },
  dropdownMenu: { position: "absolute", right: 0, top: 42, background: "#fff", border: "1px solid #cbd5e1", borderRadius: 8, boxShadow: "0 10px 15px -3px rgba(0,0,0,0.1)", zIndex: 100, width: 220, overflow: "hidden" },
  dropdownItem: { width: "100%", padding: "10px 14px", textAlign: "left", background: "none", border: "none", fontSize: 12.5, fontWeight: 600, color: "#0f172a", cursor: "pointer" },
  cacheBanner: { background: "#f0fdf4", border: "1px solid #bbf7d0", padding: "12px 16px", borderRadius: 8, marginBottom: 20, color: "#166534", fontSize: 13 },
  cacheHeader: { display: "flex", alignItems: "center", gap: 10 },
  cacheBadge: { background: "#dcfce7", color: "#15803d", fontSize: 11, fontWeight: 800, padding: "2px 6px", borderRadius: 4 },
  reportCardsGrid: { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 12, marginBottom: 24 },
  reportStatusCard: { background: "#ffffff", border: "1px solid #cbd5e1", borderRadius: 10, padding: 14, textAlign: "left" },
  reportStatusTitle: { fontSize: 12.5, fontWeight: 800, color: "#0f172a" },
  stateBadgeReady: { display: "inline-block", background: "#f0fdf4", color: "#166534", fontSize: 11, fontWeight: 800, padding: "2px 8px", borderRadius: 4, marginTop: 4 },
  stateBadgeGenerating: { display: "inline-block", background: "#eff6ff", color: "#1d4ed8", fontSize: 11, fontWeight: 800, padding: "2px 8px", borderRadius: 4, marginTop: 4 },
  stateBadgeWaiting: { display: "inline-block", background: "#f1f5f9", color: "#64748b", fontSize: 11, fontWeight: 800, padding: "2px 8px", borderRadius: 4, marginTop: 4 },
  reportTimeText: { fontSize: 11, color: "#64748b", marginTop: 4 },
  reportSubText: { fontSize: 11, color: "#94a3b8", marginTop: 4 },
  btnRow: { display: "flex", gap: 6, marginTop: 10 },
  viewBtn: { background: "#0f172a", color: "#fff", border: "none", borderRadius: 4, padding: "4px 10px", fontSize: 11, fontWeight: 700, cursor: "pointer" },
  dlBtn: { background: "#f1f5f9", color: "#0f172a", border: "1px solid #cbd5e1", borderRadius: 4, padding: "4px 10px", fontSize: 11, fontWeight: 700, cursor: "pointer" },
  layout: { display: "flex", flexDirection: "column", gap: 24 },
  sectionBlock: { background: "#ffffff", border: "1px solid #e2e8f0", borderRadius: 12, padding: 24 },
  sectionHeader: { display: "flex", alignItems: "center", gap: 10, marginBottom: 16, borderBottom: "1px solid #f1f5f9", paddingBottom: 10 },
  sectionNumber: { background: "#eff6ff", color: "#1e40af", fontSize: 11, fontWeight: 800, padding: "3px 8px", borderRadius: 4 },
  sectionTitleText: { margin: 0, fontSize: 16, fontWeight: 800, color: "#0f172a" },
  summaryCard: { background: "#f8fafc", borderRadius: 8, padding: 16, border: "1px solid #e2e8f0" },
  summaryParagraph: { margin: 0, fontSize: 13, lineHeight: 1.5, color: "#334155" },
  summaryMetaRow: { display: "flex", alignItems: "center", gap: 12, marginTop: 12 },
  badgeReadiness: { fontSize: 12, color: "#0f172a" }
};
