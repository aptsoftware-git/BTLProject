import React, { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import {
  fetchDocuments,
  fetchDocument,
  fetchFinalReport
} from "../api";

// Plain-language labels for the internal ambiguity-analysis taxonomy, so a
// non-technical reader never sees the underlying category names.
const CATEGORY_LABELS = {
  "Cross-reference / contradiction": "Information does not match",
  "Numerical inconsistency": "Numbers don't match",
  "Pronoun / entity-reference ambiguity": "Unclear who or what is being referred to",
  "Terminology inconsistency": "Inconsistent wording",
  "Date / timeline inconsistency": "Dates don't match",
  "Unit / measurement inconsistency": "Inconsistent units of measurement",
  "Internal factual contradiction": "Conflicting information",
  "Structural / convention inconsistency": "Inconsistent formatting",
  "Missing / conflicting context": "Missing information or context"
};

function plainCategory(category) {
  return CATEGORY_LABELS[category] || category || "Issue";
}

function priorityInfo(severity) {
  const s = String(severity || "").toUpperCase();
  if (s === "CRITICAL" || s === "HIGH") return { label: "High priority", bg: "#fef2f2", color: "#dc2626" };
  if (s === "MEDIUM") return { label: "Medium priority", bg: "#fffbeb", color: "#b45309" };
  return { label: "Low priority", bg: "#f0fdf4", color: "#166534" };
}

function statusColors(label) {
  const l = String(label || "").toLowerCase();
  if (l.includes("ready")) return { bg: "#f0fdf4", color: "#166534", border: "#bbf7d0" };
  if (l.includes("major")) return { bg: "#fef2f2", color: "#dc2626", border: "#fecaca" };
  if (l.includes("minor")) return { bg: "#eff6ff", color: "#1d4ed8", border: "#bfdbfe" };
  return { bg: "#fffbeb", color: "#b45309", border: "#fde68a" };
}

export default function Reports({ activeDocId }) {
  const navigate = useNavigate();
  const [documents, setDocuments] = useState([]);
  const [selectedDocId, setSelectedDocId] = useState("");
  const [activeDoc, setActiveDoc] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [reportsState, setReportsState] = useState({});
  const [exportDropdownOpen, setExportDropdownOpen] = useState(false);

  // Full-list viewer for the Compliance Report (opened via "View all")
  const [showAllIssues, setShowAllIssues] = useState(false);

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

  // Only the two user-facing reports are polled/shown here. Claude
  // Verification / Chunk Reasoning / Cluster Reasoning are internal
  // debugging reports -- their backend generation is untouched, this view
  // simply no longer surfaces them.
  const checkStatusAndReports = useCallback(async () => {
    if (!selectedDocId) return;

    try {
      const doc = await fetchDocument(selectedDocId).catch(() => null);
      if (doc) setActiveDoc(doc);

      const isDocProcessing = doc && (
        doc.context_analysis_status === "running" ||
        doc.context_analysis_status === "pending"
      );

      const reportKeys = ["final-report", "comparative-analysis"];
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
                  state: "generating", isReady: false, isGenerating: true,
                  isWaiting: false, isFailed: false,
                  timestamp: "Preparing your report...", meta, data: null
                };
              } else if (resJson.data) {
                const rawDate = meta.created_at || meta.timestamp;
                let formattedTime = "Generated recently";
                if (rawDate) {
                  try {
                    const parsed = new Date(rawDate);
                    if (!isNaN(parsed.getTime())) {
                      formattedTime = parsed.toLocaleString("en-US", {
                        month: "short", day: "numeric", hour: "2-digit", minute: "2-digit"
                      });
                    }
                  } catch (e) {
                    formattedTime = rawDate;
                  }
                }
                newReportsState[key] = {
                  state: "ready", isReady: true, isGenerating: false,
                  isWaiting: false, isFailed: false,
                  timestamp: formattedTime, meta, data: resJson.data
                };
              } else {
                newReportsState[key] = {
                  state: "waiting", isReady: false, isGenerating: false,
                  isWaiting: true, isFailed: false,
                  timestamp: "Not generated yet", meta, data: null
                };
              }
            } else {
              newReportsState[key] = {
                state: "waiting", isReady: false, isGenerating: false,
                isWaiting: true, isFailed: false,
                timestamp: "Not generated yet", meta: {}, data: null
              };
            }
          } catch (e) {
            newReportsState[key] = {
              state: "waiting", isReady: false, isGenerating: false,
              isWaiting: true, isFailed: false,
              timestamp: "Not generated yet", meta: {}, data: null
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

  const handleViewReportCard = async (key) => {
    if (key === "comparative-analysis") {
      navigate(`/documents/${selectedDocId}?tab=comparative`);
      return;
    }
    setShowAllIssues(true);
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
  const findingsList = fData.findings || [];

  const sevBreak = fData.executive_summary?.severity_breakdown || {};
  const highCount = (sevBreak.CRITICAL || 0) + (sevBreak.HIGH || 0);
  const medCount = sevBreak.MEDIUM || 0;
  const lowCount = sevBreak.LOW || 0;
  const totalIssues = findingsList.length;

  const overallStatusLabel = fData.publication_status?.label || "Review Pending";
  const overallStatusAction = fData.publication_status?.action || "The document review has not finished yet.";
  const statusStyle = statusColors(overallStatusLabel);

  const docLabel = activeDoc?.filename || documents.find(d => d.id === selectedDocId)?.filename || selectedDocId;

  const reviewSummarySentence = totalIssues === 0
    ? "No issues were found in this document."
    : `${totalIssues} issue${totalIssues === 1 ? "" : "s"} ${totalIssues === 1 ? "was" : "were"} identified that may require your attention.`;

  function renderFindingCard(f, idx) {
    const priority = priorityInfo(f.severity);
    const whatWasFound = f.highlighted_ambiguity || f.original_chunk || f.claude_explanation || "An issue was found in this section of the document.";
    const location = f.section_heading && f.section_heading !== "General Section"
      ? `Page ${f.page_number || 1} — ${f.section_heading}`
      : `Page ${f.page_number || 1}`;
    const whyItMatters = f.business_impact || "This may affect how the document is understood or used.";
    const suggestedAction = f.recommended_resolution || "Review this section and confirm the correct information.";

    return (
      <div key={f.finding_id || idx} style={styles.findingCard}>
        <div style={styles.findingCardTop}>
          <span style={styles.findingTitle}>{plainCategory(f.category)}</span>
          <span style={{ ...styles.priorityBadge, background: priority.bg, color: priority.color }}>{priority.label}</span>
        </div>
        <div style={styles.findingLocation}>📍 {location}</div>

        <div style={styles.findingRow}>
          <span style={styles.findingLabel}>What was found</span>
          <p style={styles.findingText}>{whatWasFound}</p>
        </div>
        <div style={styles.findingRow}>
          <span style={styles.findingLabel}>Why it matters</span>
          <p style={styles.findingText}>{whyItMatters}</p>
        </div>
        <div style={styles.actionRow}>
          <span style={styles.findingLabel}>Suggested action</span>
          <p style={styles.actionText}>{suggestedAction}</p>
        </div>
      </div>
    );
  }

  return (
    <div style={styles.container}>
      {/* Page Header */}
      <div style={styles.header}>
        <div>
          <h1 style={styles.title}>Reports</h1>
          <p style={styles.subtitle}>Document: <strong>{docLabel}</strong></p>
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
            <button onClick={() => setExportDropdownOpen(!exportDropdownOpen)} style={styles.exportBtn}>
              📥 Download ▼
            </button>
            {exportDropdownOpen && (
              <div style={styles.dropdownMenu}>
                <button style={styles.dropdownItem} onClick={() => { setExportDropdownOpen(false); handleDownloadPdf("final-report", "Compliance Report"); }}>
                  📄 Compliance Report (PDF)
                </button>
                <button style={styles.dropdownItem} onClick={() => { setExportDropdownOpen(false); navigate(`/documents/${selectedDocId}?tab=comparative`); }}>
                  📊 Comparative Analysis Report
                </button>
                <button style={styles.dropdownItem} onClick={() => { setExportDropdownOpen(false); window.open(`/api/documents/${selectedDocId}/export`, "_blank"); }}>
                  📦 Download All Files (ZIP)
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Report Cards */}
      <div style={styles.reportCardsGrid}>
        {[
          { key: "final-report", title: "Executive Compliance Report", desc: "A plain-language summary of issues found in this document." },
          { key: "comparative-analysis", title: "Executive Comparative Analysis Report", desc: "Compares this document against a reference version." }
        ].map(item => {
          const st = reportsState[item.key] || {};
          const isCompRep = item.key === "comparative-analysis";
          return (
            <div key={item.key} style={styles.reportStatusCard}>
              <div style={styles.reportStatusTitle}>{item.title}</div>
              <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4 }}>{item.desc}</div>

              {st.isReady ? (
                <div>
                  <div style={styles.stateBadgeReady}>✓ Ready</div>
                  <div style={styles.reportTimeText}>{st.timestamp}</div>
                  <div style={{ ...styles.btnRow, flexWrap: "wrap" }}>
                    <button style={styles.viewBtn} onClick={() => handleViewReportCard(item.key)}>View</button>
                    {isCompRep ? (
                      <>
                        <a href={`/api/download/${selectedDocId}/comparative_report.html`} download style={{ textDecoration: "none" }}>
                          <button style={{ ...styles.dlBtn, background: "var(--brand-light)", color: "var(--brand)" }}>HTML</button>
                        </a>
                        <button style={styles.dlBtn} onClick={() => handleDownloadPdf("comparative-analysis", item.title)}>PDF</button>
                      </>
                    ) : (
                      <button style={styles.dlBtn} onClick={() => handleDownloadPdf(item.key, item.title)}>PDF</button>
                    )}
                  </div>
                </div>
              ) : st.isGenerating ? (
                <div>
                  <div style={styles.stateBadgeGenerating}>⏳ Preparing your report...</div>
                  <div style={{ fontSize: 12, color: "#64748b", marginTop: 6 }}>This usually takes a minute. Check back shortly.</div>
                </div>
              ) : (
                <div>
                  <div style={styles.stateBadgeWaiting}>Not available yet</div>
                  <div style={{ fontSize: 12, color: "#64748b", marginTop: 6 }}>This report will appear once the document review finishes.</div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Document Review Summary */}
      <div style={styles.layout}>
        <div style={styles.sectionBlock}>
          <h2 style={styles.sectionTitleText}>Document Review Summary</h2>
          <p style={styles.reviewSentence}>{reviewSummarySentence}</p>

          <div style={styles.summaryStatsRow}>
            <div style={styles.statTile}>
              <span style={{ ...styles.statDot, background: "#dc2626" }} />
              <div>
                <div style={styles.statNumber}>{highCount}</div>
                <div style={styles.statLabel}>High priority</div>
              </div>
            </div>
            <div style={styles.statTile}>
              <span style={{ ...styles.statDot, background: "#b45309" }} />
              <div>
                <div style={styles.statNumber}>{medCount}</div>
                <div style={styles.statLabel}>Medium priority</div>
              </div>
            </div>
            <div style={styles.statTile}>
              <span style={{ ...styles.statDot, background: "#166534" }} />
              <div>
                <div style={styles.statNumber}>{lowCount}</div>
                <div style={styles.statLabel}>Low priority</div>
              </div>
            </div>
          </div>

          <div style={{ ...styles.statusBanner, background: statusStyle.bg, borderColor: statusStyle.border }}>
            <span style={{ ...styles.statusBadge, color: statusStyle.color }}>{overallStatusLabel}</span>
            <span style={{ fontSize: 13, color: "#334155" }}>{overallStatusAction}</span>
          </div>
        </div>

        {totalIssues > 0 && (
          <div style={styles.sectionBlock}>
            <div style={styles.sectionHeaderRow}>
              <h2 style={styles.sectionTitleText}>Issues Found ({totalIssues})</h2>
              {totalIssues > 5 && (
                <button style={styles.viewAllBtn} onClick={() => setShowAllIssues(true)}>View all</button>
              )}
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {findingsList.slice(0, 5).map((f, idx) => renderFindingCard(f, idx))}
            </div>
            {totalIssues > 5 && (
              <p style={styles.moreText}>Showing 5 of {totalIssues} issues. <button style={styles.inlineLink} onClick={() => setShowAllIssues(true)}>View all issues</button></p>
            )}
          </div>
        )}
      </div>

      {/* Full issues list viewer */}
      {showAllIssues && (
        <div style={modalStyles.overlay} onClick={() => setShowAllIssues(false)}>
          <div style={modalStyles.dialog} onClick={(e) => e.stopPropagation()}>
            <div style={modalStyles.header}>
              <div>
                <h2 style={modalStyles.title}>All Issues Found</h2>
                <p style={modalStyles.subTitle}>{docLabel}</p>
              </div>
              <button style={modalStyles.closeBtn} onClick={() => setShowAllIssues(false)}>✕ Close</button>
            </div>
            <div style={modalStyles.body}>
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                {findingsList.map((f, idx) => renderFindingCard(f, idx))}
              </div>
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
    display: "flex", alignItems: "center", justifyContent: "center",
    zIndex: 9999, padding: 24
  },
  dialog: {
    background: "#ffffff", border: "1px solid #cbd5e1", borderRadius: 16,
    maxWidth: 780, width: "100%", maxHeight: "85vh", display: "flex",
    flexDirection: "column", boxShadow: "0 20px 25px -5px rgba(0, 0, 0, 0.2)",
    overflow: "hidden"
  },
  header: {
    padding: "20px 24px", borderBottom: "1px solid #e2e8f0",
    display: "flex", justifyContent: "space-between", alignItems: "flex-start",
    background: "#f8fafc"
  },
  title: { margin: 0, fontSize: 18, fontWeight: 800, color: "#0f172a" },
  subTitle: { margin: "2px 0 0", fontSize: 12, color: "#64748b" },
  closeBtn: { background: "#f1f5f9", border: "1px solid #cbd5e1", borderRadius: 6, padding: "6px 12px", fontSize: 12, fontWeight: 700, cursor: "pointer", color: "#0f172a" },
  body: { padding: 24, overflowY: "auto", flex: 1 }
};

const styles = {
  container: { maxWidth: 900, margin: "0 auto", padding: "10px 0" },
  header: { display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 },
  title: { margin: 0, fontSize: 22, fontWeight: 800, color: "#0f172a" },
  subtitle: { margin: "4px 0 0", fontSize: 13, color: "#64748b" },
  docSelect: { padding: "8px 12px", borderRadius: 8, border: "1px solid #cbd5e1", fontSize: 13 },
  exportBtn: { background: "#0f172a", color: "#fff", border: "none", borderRadius: 8, padding: "8px 16px", fontSize: 13, fontWeight: 700, cursor: "pointer" },
  dropdownMenu: { position: "absolute", right: 0, top: 42, background: "#fff", border: "1px solid #cbd5e1", borderRadius: 8, boxShadow: "0 10px 15px -3px rgba(0,0,0,0.1)", zIndex: 100, width: 240, overflow: "hidden" },
  dropdownItem: { width: "100%", padding: "10px 14px", textAlign: "left", background: "none", border: "none", fontSize: 12.5, fontWeight: 600, color: "#0f172a", cursor: "pointer" },
  reportCardsGrid: { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 12, marginBottom: 24 },
  reportStatusCard: { background: "#ffffff", border: "1px solid #cbd5e1", borderRadius: 10, padding: 16, textAlign: "left" },
  reportStatusTitle: { fontSize: 14, fontWeight: 800, color: "#0f172a" },
  stateBadgeReady: { display: "inline-block", background: "#f0fdf4", color: "#166534", fontSize: 11, fontWeight: 800, padding: "2px 8px", borderRadius: 4, marginTop: 8 },
  stateBadgeGenerating: { display: "inline-block", background: "#eff6ff", color: "#1d4ed8", fontSize: 11, fontWeight: 800, padding: "2px 8px", borderRadius: 4, marginTop: 8 },
  stateBadgeWaiting: { display: "inline-block", background: "#f1f5f9", color: "#64748b", fontSize: 11, fontWeight: 800, padding: "2px 8px", borderRadius: 4, marginTop: 8 },
  reportTimeText: { fontSize: 11, color: "#64748b", marginTop: 4 },
  btnRow: { display: "flex", gap: 6, marginTop: 10 },
  viewBtn: { background: "#0f172a", color: "#fff", border: "none", borderRadius: 4, padding: "5px 12px", fontSize: 11.5, fontWeight: 700, cursor: "pointer" },
  dlBtn: { background: "#f1f5f9", color: "#0f172a", border: "1px solid #cbd5e1", borderRadius: 4, padding: "5px 12px", fontSize: 11.5, fontWeight: 700, cursor: "pointer" },
  layout: { display: "flex", flexDirection: "column", gap: 20 },
  sectionBlock: { background: "#ffffff", border: "1px solid #e2e8f0", borderRadius: 12, padding: 24 },
  sectionHeaderRow: { display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 },
  sectionTitleText: { margin: "0 0 4px", fontSize: 16, fontWeight: 800, color: "#0f172a" },
  reviewSentence: { margin: "0 0 18px", fontSize: 14.5, color: "#334155" },
  summaryStatsRow: { display: "flex", gap: 20, marginBottom: 18, flexWrap: "wrap" },
  statTile: { display: "flex", alignItems: "center", gap: 10 },
  statDot: { width: 10, height: 10, borderRadius: "50%", display: "inline-block", flexShrink: 0 },
  statNumber: { fontSize: 20, fontWeight: 800, color: "#0f172a", lineHeight: 1.1 },
  statLabel: { fontSize: 12, color: "#64748b" },
  statusBanner: { display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap", padding: "12px 16px", borderRadius: 8, border: "1px solid" },
  statusBadge: { fontSize: 13, fontWeight: 800 },
  viewAllBtn: { background: "none", border: "none", color: "var(--brand, #4f46e5)", fontSize: 12.5, fontWeight: 700, cursor: "pointer" },
  moreText: { fontSize: 12.5, color: "#64748b", margin: "10px 0 0", textAlign: "center" },
  inlineLink: { background: "none", border: "none", color: "var(--brand, #4f46e5)", fontWeight: 700, cursor: "pointer", fontSize: 12.5, padding: 0 },
  findingCard: { background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 10, padding: 14 },
  findingCardTop: { display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 },
  findingTitle: { fontSize: 14, fontWeight: 800, color: "#0f172a" },
  priorityBadge: { fontSize: 11, fontWeight: 800, padding: "3px 8px", borderRadius: 4 },
  findingLocation: { fontSize: 12, color: "#64748b", marginTop: 4, marginBottom: 10 },
  findingRow: { marginTop: 8 },
  findingLabel: { fontSize: 11, fontWeight: 800, color: "#64748b", textTransform: "uppercase", letterSpacing: 0.3 },
  findingText: { margin: "3px 0 0", fontSize: 13, lineHeight: 1.5, color: "#1e293b" },
  actionRow: { marginTop: 10, paddingTop: 10, borderTop: "1px dashed #cbd5e1" },
  actionText: { margin: "3px 0 0", fontSize: 13, lineHeight: 1.5, color: "#166534", fontWeight: 600 }
};
