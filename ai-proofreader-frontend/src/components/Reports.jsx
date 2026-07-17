import React, { useState, useEffect, useMemo } from "react";
import { fetchDocuments, fetchDocument } from "../api";

export default function Reports() {
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [dateFilter, setDateFilter] = useState("all"); // all, today, week, month

  // Load documents and their full details for completed ones
  const loadReportsData = async () => {
    setLoading(true);
    setError(null);
    try {
      const docs = await fetchDocuments();
      setDocuments(docs);
      
      // Load details for completed docs so we can aggregate issues
      const completedDocs = docs.filter(d => d.status === "completed");
      const details = await Promise.all(
        completedDocs.map(async (doc) => {
          try {
            return await fetchDocument(doc.id);
          } catch (e) {
            console.error("Failed to load details for", doc.id, e);
            return null;
          }
        })
      );
      
      // Update state with detailed documents
      const docsWithDetails = docs.map(d => {
        const detail = details.find(x => x && x.id === d.id);
        return detail ? { ...d, ...detail } : d;
      });
      setDocuments(docsWithDetails);
    } catch (err) {
      setError("Failed to fetch documents for report generation.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadReportsData();
  }, []);

  // Filter documents by date
  const filteredDocuments = useMemo(() => {
    return documents.filter((doc) => {
      if (dateFilter === "all") return true;
      if (!doc.created_at) return false;

      const createdDate = new Date(doc.created_at);
      const today = new Date();
      
      if (dateFilter === "today") {
        return createdDate.toDateString() === today.toDateString();
      }
      if (dateFilter === "week") {
        const sevenDaysAgo = new Date();
        sevenDaysAgo.setDate(today.getDate() - 7);
        return createdDate >= sevenDaysAgo;
      }
      if (dateFilter === "month") {
        const thirtyDaysAgo = new Date();
        thirtyDaysAgo.setDate(today.getDate() - 30);
        return createdDate >= thirtyDaysAgo;
      }
      return true;
    });
  }, [documents, dateFilter]);

  // Aggregate statistics
  const stats = useMemo(() => {
    const completed = filteredDocuments.filter((d) => d.status === "completed");
    
    let totalIssues = 0;
    let spellingCount = 0;
    let grammarCount = 0;
    let tenseCount = 0;
    let punctuationCount = 0;
    let sumAccuracy = 0;
    
    // Confidence buckets
    let confLow = 0;    // 0.40 - 0.60
    let confMed = 0;    // 0.60 - 0.80
    let confHigh = 0;   // 0.80 - 1.00

    // Frequent corrections list
    const frequentCorrections = {};

    completed.forEach((doc) => {
      const docIssues = doc.issues || [];
      totalIssues += docIssues.length;
      
      const score = Math.max(45, 100 - docIssues.length);
      sumAccuracy += score;

      docIssues.forEach((issue) => {
        // Increment types
        if (issue.issue_type === "spelling") spellingCount++;
        else if (issue.issue_type === "grammar") grammarCount++;
        else if (issue.issue_type === "tense") tenseCount++;
        else if (issue.issue_type === "punctuation") punctuationCount++;
        else grammarCount++; // default

        // Confidence bucket
        const conf = issue.final_confidence || issue.confidence || 0;
        if (conf >= 0.8) confHigh++;
        else if (conf >= 0.6) confMed++;
        else confLow++;

        // Track frequent mistakes
        const key = `${issue.original_text} ➔ ${issue.suggested_text}`;
        frequentCorrections[key] = (frequentCorrections[key] || 0) + 1;
      });
    });

    const averageAccuracy = completed.length > 0 ? Math.round(sumAccuracy / completed.length) : 0;

    // Sort frequent corrections
    const topCorrections = Object.entries(frequentCorrections)
      .map(([text, count]) => ({ text, count }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 5);

    return {
      totalDocs: filteredDocuments.length,
      completedDocs: completed.length,
      totalIssues,
      spellingCount,
      grammarCount,
      tenseCount,
      punctuationCount,
      averageAccuracy,
      confLow,
      confMed,
      confHigh,
      topCorrections,
    };
  }, [filteredDocuments]);

  // Export to CSV
  const handleExportCSV = () => {
    const completed = filteredDocuments.filter((d) => d.status === "completed");
    let csvContent = "data:text/csv;charset=utf-8,";
    csvContent += "Job ID,Filename,Status,FileType,Size,Created At,Issues Count,Accuracy Score\n";
    
    completed.forEach((doc) => {
      const score = Math.max(45, 100 - (doc.issues?.length || 0));
      const row = `"${doc.id}","${doc.filename}","${doc.status}","${doc.fileType}","${doc.size}","${doc.created_at || ""}","${doc.issues?.length || 0}","${score}%"`;
      csvContent += row + "\n";
    });

    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", `Proofreading_Summary_Report_${dateFilter}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  // Export to JSON
  const handleExportJSON = () => {
    const completed = filteredDocuments.filter((d) => d.status === "completed");
    const exportData = {
      generatedAt: new Date().toISOString(),
      dateFilter,
      summary: stats,
      detailedDocuments: completed.map(doc => ({
        id: doc.id,
        filename: doc.filename,
        created_at: doc.created_at,
        statistics: doc.statistics || {},
        issues: doc.issues || [],
        protected_terms: doc.protected_terms || [],
      }))
    };

    const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(exportData, null, 2));
    const link = document.createElement("a");
    link.setAttribute("href", dataStr);
    link.setAttribute("download", `Proofreading_Aggregated_Report_${dateFilter}.json`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div style={styles.container}>
      {/* Header */}
      <div style={styles.header}>
        <div>
          <h1 style={styles.title}>Reports & Analytics</h1>
          <p style={styles.subtitle}>Aggregate performance, grammar accuracy, and pipeline error breakdown</p>
        </div>
        <div style={styles.actions}>
          <select
            style={styles.select}
            value={dateFilter}
            onChange={(e) => setDateFilter(e.target.value)}
          >
            <option value="all">All Time</option>
            <option value="today">Today</option>
            <option value="week">Last 7 Days</option>
            <option value="month">Last 30 Days</option>
          </select>
          <button style={styles.btnSecondary} onClick={handleExportCSV} disabled={stats.completedDocs === 0}>
            Export CSV
          </button>
          <button style={styles.btnPrimary} onClick={handleExportJSON} disabled={stats.completedDocs === 0}>
            Export JSON
          </button>
        </div>
      </div>

      {loading ? (
        <div style={styles.loadingBox}>
          <div style={styles.spinner} />
          <p style={{ marginTop: 12, fontSize: 13, color: "var(--text-secondary)" }}>Aggregating document reports...</p>
        </div>
      ) : error ? (
        <div style={styles.errorBox}>
          <p style={{ color: "var(--red)", fontWeight: 600 }}>{error}</p>
          <button style={styles.retryBtn} onClick={loadReportsData}>Retry</button>
        </div>
      ) : stats.completedDocs === 0 ? (
        <div style={styles.emptyBox}>
          <p style={{ fontSize: 14, color: "var(--text-muted)", margin: "0 0 10px" }}>No completed documents found in this range.</p>
          <p style={{ fontSize: 12, color: "var(--text-muted)", margin: 0 }}>Try changing the date filter or upload a file to run analysis.</p>
        </div>
      ) : (
        <div style={styles.dashboard}>
          
          {/* Summary Stats Grid */}
          <div style={styles.statsGrid}>
            <div style={styles.statCard}>
              <p style={styles.statLabel}>Documents Checked</p>
              <p style={styles.statValue}>{stats.completedDocs}</p>
              <p style={styles.statSub}>Out of {stats.totalDocs} uploaded</p>
            </div>
            <div style={styles.statCard}>
              <p style={styles.statLabel}>Average Accuracy</p>
              <p style={{ ...styles.statValue, color: "var(--brand)" }}>{stats.averageAccuracy}%</p>
              <p style={styles.statSub}>Overall quality score</p>
            </div>
            <div style={styles.statCard}>
              <p style={styles.statLabel}>Total Issues Corrected</p>
              <p style={styles.statValue}>{stats.totalIssues}</p>
              <p style={styles.statSub}>Bypassed protected terms</p>
            </div>
            <div style={styles.statCard}>
              <p style={styles.statLabel}>Issues per Document</p>
              <p style={styles.statValue}>{(stats.totalIssues / stats.completedDocs).toFixed(1)}</p>
              <p style={styles.statSub}>Average density</p>
            </div>
          </div>

          <div style={styles.analyticsLayout}>
            {/* Left Col: Issue Breakdown & Confidence Intervals */}
            <div style={styles.detailsCol}>
              
              {/* Category Breakdown */}
              <div style={styles.card}>
                <h2 style={styles.cardTitle}>Correction Types Breakdown</h2>
                <p style={styles.cardDesc}>Distribution of processed corrections in this date range</p>
                
                <div style={styles.chartGroup}>
                  {/* Spelling */}
                  <div style={styles.chartRow}>
                    <div style={styles.chartMeta}>
                      <span style={styles.chartLabel}>Spelling Mistakes</span>
                      <span style={styles.chartValue}>{stats.spellingCount} ({Math.round(stats.spellingCount / stats.totalIssues * 100) || 0}%)</span>
                    </div>
                    <div style={styles.barOuter}>
                      <div style={{ ...styles.barInner, width: `${(stats.spellingCount / stats.totalIssues * 100) || 0}%`, background: "var(--amber)" }} />
                    </div>
                  </div>

                  {/* Grammar */}
                  <div style={styles.chartRow}>
                    <div style={styles.chartMeta}>
                      <span style={styles.chartLabel}>Grammar Errors</span>
                      <span style={styles.chartValue}>{stats.grammarCount} ({Math.round(stats.grammarCount / stats.totalIssues * 100) || 0}%)</span>
                    </div>
                    <div style={styles.barOuter}>
                      <div style={{ ...styles.barInner, width: `${(stats.grammarCount / stats.totalIssues * 100) || 0}%`, background: "var(--red)" }} />
                    </div>
                  </div>

                  {/* Tense */}
                  <div style={styles.chartRow}>
                    <div style={styles.chartMeta}>
                      <span style={styles.chartLabel}>Tense Mismatches</span>
                      <span style={styles.chartValue}>{stats.tenseCount} ({Math.round(stats.tenseCount / stats.totalIssues * 100) || 0}%)</span>
                    </div>
                    <div style={styles.barOuter}>
                      <div style={{ ...styles.barInner, width: `${(stats.tenseCount / stats.totalIssues * 100) || 0}%`, background: "var(--brand)" }} />
                    </div>
                  </div>

                  {/* Punctuation */}
                  <div style={styles.chartRow}>
                    <div style={styles.chartMeta}>
                      <span style={styles.chartLabel}>Punctuation / Style</span>
                      <span style={styles.chartValue}>{stats.punctuationCount} ({Math.round(stats.punctuationCount / stats.totalIssues * 100) || 0}%)</span>
                    </div>
                    <div style={styles.barOuter}>
                      <div style={{ ...styles.barInner, width: `${(stats.punctuationCount / stats.totalIssues * 100) || 0}%`, background: "var(--blue-icon)" }} />
                    </div>
                  </div>
                </div>
              </div>

              {/* Confidence Summary */}
              <div style={styles.card}>
                <h2 style={styles.cardTitle}>Engine Confidence Intervals</h2>
                <p style={styles.cardDesc}>Distribution of correct predictions based on pipeline agreement metrics</p>
                
                <div style={styles.confGrid}>
                  <div style={styles.confCard}>
                    <p style={styles.confLabel}>High Confidence (80-100%)</p>
                    <p style={{ ...styles.confValue, color: "var(--green)" }}>{stats.confHigh}</p>
                    <p style={styles.confSub}>Strong source agreement</p>
                  </div>
                  <div style={styles.confCard}>
                    <p style={styles.confLabel}>Medium Confidence (60-80%)</p>
                    <p style={{ ...styles.confValue, color: "var(--amber)" }}>{stats.confMed}</p>
                    <p style={styles.confSub}>Single source detection</p>
                  </div>
                  <div style={styles.confCard}>
                    <p style={styles.confLabel}>Low Confidence (40-60%)</p>
                    <p style={{ ...styles.confValue, color: "var(--red)" }}>{stats.confLow}</p>
                    <p style={styles.confSub}>Weak suggestion score</p>
                  </div>
                </div>
              </div>

            </div>

            {/* Right Col: Top Corrections */}
            <div style={styles.topCorrectionsCol}>
              <div style={{ ...styles.card, height: "100%" }}>
                <h2 style={styles.cardTitle}>Frequent Errors & Corrections</h2>
                <p style={styles.cardDesc}>Top 5 most common mistakes across your documents</p>
                
                <div style={styles.correctionsList}>
                  {stats.topCorrections.length === 0 ? (
                    <p style={{ fontSize: 13, color: "var(--text-muted)" }}>No errors logged yet.</p>
                  ) : (
                    stats.topCorrections.map((item, idx) => (
                      <div key={idx} style={styles.correctionRow}>
                        <span style={styles.rankNum}>#{idx + 1}</span>
                        <div style={styles.correctionDetails}>
                          <p style={styles.correctionText}>{item.text}</p>
                          <p style={styles.correctionCount}>Found {item.count} times</p>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>
          </div>

        </div>
      )}
    </div>
  );
}

const styles = {
  container: { display: "flex", flexDirection: "column", gap: 16, textAlign: "left" },
  header: { display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 },
  title: { margin: 0, fontSize: 24, fontWeight: 700 },
  subtitle: { margin: "4px 0 0", fontSize: 13, color: "var(--text-secondary)" },
  actions: { display: "flex", gap: 8 },
  select: {
    background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 8,
    padding: "8px 12px", fontSize: 12.5, color: "var(--text-primary)", cursor: "pointer", outline: "none",
  },
  btnPrimary: {
    background: "var(--brand)", color: "white", border: "none", borderRadius: 8,
    padding: "8px 14px", fontSize: 12.5, fontWeight: 600, cursor: "pointer",
  },
  btnSecondary: {
    background: "transparent", color: "var(--text-secondary)", border: "1px solid var(--border)",
    borderRadius: 8, padding: "8px 14px", fontSize: 12.5, fontWeight: 600, cursor: "pointer",
  },
  loadingBox: { display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", minHeight: 240 },
  spinner: {
    width: 24, height: 24, borderRadius: "50%",
    border: "3px solid var(--border)", borderTopColor: "var(--brand)",
    animation: "spin 0.8s linear infinite",
  },
  errorBox: { display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: 24, background: "var(--bg-card)", borderRadius: 12, border: "1px solid var(--border)" },
  retryBtn: { marginTop: 8, background: "var(--brand)", color: "white", border: "none", borderRadius: 8, padding: "6px 12px", fontSize: 12, cursor: "pointer" },
  emptyBox: { display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", minHeight: 180, background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 12 },
  dashboard: { display: "flex", flexDirection: "column", gap: 16 },
  statsGrid: { display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 },
  statCard: {
    background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: "var(--radius-card)",
    padding: 16, boxShadow: "var(--shadow-card)",
  },
  statLabel: { margin: 0, fontSize: 12.5, fontWeight: 600, color: "var(--text-secondary)" },
  statValue: { margin: "6px 0", fontSize: 24, fontWeight: 800, color: "var(--text-primary)" },
  statSub: { margin: 0, fontSize: 11, color: "var(--text-muted)" },
  analyticsLayout: { display: "grid", gridTemplateColumns: "1.4fr 1fr", gap: 16 },
  detailsCol: { display: "flex", flexDirection: "column", gap: 16 },
  topCorrectionsCol: { minWidth: 0 },
  card: {
    background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: "var(--radius-card)",
    padding: 16, boxShadow: "var(--shadow-card)",
  },
  cardTitle: { margin: 0, fontSize: 15, fontWeight: 700 },
  cardDesc: { margin: "4px 0 16px", fontSize: 12.5, color: "var(--text-muted)" },
  chartGroup: { display: "flex", flexDirection: "column", gap: 12 },
  chartRow: { display: "flex", flexDirection: "column", gap: 4 },
  chartMeta: { display: "flex", justifyContent: "space-between", fontSize: 12.5 },
  chartLabel: { fontWeight: 600, color: "var(--text-secondary)" },
  chartValue: { fontWeight: 700, color: "var(--text-primary)" },
  barOuter: { height: 8, background: "var(--bg-page)", borderRadius: 4, overflow: "hidden" },
  barInner: { height: "100%", borderRadius: 4 },
  confGrid: { display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 10 },
  confCard: {
    background: "var(--bg-page)", border: "1px solid var(--border)", borderRadius: 8,
    padding: 10, textAlign: "center",
  },
  confLabel: { margin: 0, fontSize: 11, fontWeight: 600, color: "var(--text-secondary)" },
  confValue: { margin: "4px 0", fontSize: 18, fontWeight: 800 },
  confSub: { margin: 0, fontSize: 9.5, color: "var(--text-muted)" },
  correctionsList: { display: "flex", flexDirection: "column", gap: 8 },
  correctionRow: { display: "flex", gap: 10, padding: "8px 10px", background: "var(--bg-page)", borderRadius: 8, alignItems: "center" },
  rankNum: { fontSize: 12, fontWeight: 750, color: "var(--brand)" },
  correctionDetails: { minWidth: 0 },
  correctionText: { margin: 0, fontSize: 13, fontWeight: 600, fontFamily: "monospace", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" },
  correctionCount: { margin: "2px 0 0", fontSize: 11, color: "var(--text-muted)" },
};
