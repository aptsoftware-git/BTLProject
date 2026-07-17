import React from "react";
import { BrowserRouter as Router, Routes, Route } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Sidebar from "./components/Sidebar";
import TopBar from "./components/TopBar";
import StatCard from "./components/StatCard";
import UploadZone from "./components/UploadZone";
import RecentDocuments from "./components/RecentDocuments";
import Workspace from "./components/Workspace";
import History from "./components/History";
import Reports from "./components/Reports";
import Settings from "./components/Settings";
import ProofreadingEmptyState from "./components/ProofreadingEmptyState";
import Assistant from "./components/Assistant";
import { fetchDocuments, fetchStats, fetchSystemStatus } from "./api";

const FALLBACK_STATS = { totalDocuments: 0, grammarAccuracy: 0, issuesResolvedToday: 0, documentsToday: 0 };

export default function App() {
  const queryClient = useQueryClient();

  // Queries using TanStack React Query
  const { data: documents = [], error: docsError } = useQuery({
    queryKey: ["documents"],
    queryFn: fetchDocuments,
  });

  const { data: stats = FALLBACK_STATS, error: statsError } = useQuery({
    queryKey: ["stats"],
    queryFn: fetchStats,
  });

  const { data: systemStatus } = useQuery({
    queryKey: ["systemStatus"],
    queryFn: fetchSystemStatus,
    refetchInterval: 15000, // Poll system status every 15s to make it live
  });

  const handleRefreshAll = () => {
    queryClient.invalidateQueries({ queryKey: ["documents"] });
    queryClient.invalidateQueries({ queryKey: ["stats"] });
  };

  const loadError = docsError?.message || statsError?.message;

  return (
    <Router>
      <div className="app-shell">
        <Sidebar systemStatus={systemStatus} />

        <div className="main-column">
          <TopBar />

          <main style={styles.content}>
            {loadError && (
              <div style={styles.errorBanner}>
                <span>Couldn't reach the backend ({loadError}). Showing cached or fallback data.</span>
                <button style={styles.retryBtn} onClick={handleRefreshAll}>Retry Connection</button>
              </div>
            )}

            <Routes>
              {/* Route 1: Dashboard Home */}
              <Route
                path="/"
                element={
                  <div style={styles.dashboardGrid}>
                    <div style={styles.pageHeader}>
                      <div>
                        <h1 style={styles.pageTitle}>Documents Dashboard</h1>
                        <p style={styles.pageSub}>Manage and proofread your documents with layout-aware analysis</p>
                      </div>
                      <button style={styles.refreshBtn} onClick={handleRefreshAll} aria-label="Refresh Dashboard">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" style={{ marginRight: 6 }}>
                          <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 11-.57-8.38l5.67-5.67" />
                        </svg>
                        Refresh
                      </button>
                    </div>

                    <div style={styles.statGrid}>
                      <StatCard
                        theme="purple"
                        icon={<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M14 3H6a2 2 0 00-2 2v14a2 2 0 002 2h12a2 2 0 002-2V9z" /><path d="M14 3v6h6" /></svg>}
                        value={stats.totalDocuments}
                        label="Total documents"
                        sublabel="All time"
                      />
                      <StatCard
                        theme="amber"
                        icon={<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M20 6L9 17l-5-5" /></svg>}
                        value={`${stats.grammarAccuracy}%`}
                        label="Grammar accuracy"
                        sublabel="Average score"
                      />
                      <StatCard
                        theme="green"
                        icon={<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M20 6L9 17l-5-5" /></svg>}
                        value={stats.issuesResolvedToday}
                        label="Issues resolved"
                        sublabel="Today"
                      />
                      <StatCard
                        theme="blue"
                        icon={<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M14 3H6a2 2 0 00-2 2v14a2 2 0 002 2h12a2 2 0 002-2V9z" /><path d="M14 3v6h6" /></svg>}
                        value={stats.documentsToday}
                        label="Documents today"
                        sublabel="Checked"
                      />
                    </div>

                    <div style={{ margin: "16px 0" }}>
                      <UploadZone onUploaded={handleRefreshAll} />
                    </div>

                    <RecentDocuments documents={documents} onRefresh={handleRefreshAll} />
                  </div>
                }
              />

              {/* Route 2: Upload Page */}
              <Route
                path="/upload"
                element={
                  <div style={styles.innerPage}>
                    <h1 style={styles.pageTitle}>Upload Document</h1>
                    <p style={{ ...styles.pageSub, marginBottom: 24 }}>Select a document to begin layout-aware proofreading analysis.</p>
                    <UploadZone onUploaded={handleRefreshAll} />
                  </div>
                }
              />

              {/* Route 3: All Documents Page */}
              <Route
                path="/documents"
                element={
                  <div style={styles.innerPage}>
                    <RecentDocuments documents={documents} onRefresh={handleRefreshAll} isFullList={true} />
                  </div>
                }
              />

              {/* Route 4: Document Workspace Page */}
              <Route path="/documents/:id" element={<Workspace />} />

              {/* Route 5: Actual Pages instead of placeholders */}
              <Route path="/proofreading" element={<ProofreadingEmptyState />} />
              <Route path="/reports" element={<Reports />} />
              <Route path="/history" element={<History />} />
              <Route path="/settings" element={<Settings />} />
              <Route path="/assistant" element={<Assistant />} />
              <Route path="/assistant/:id" element={<Assistant />} />
            </Routes>
          </main>
        </div>
      </div>
    </Router>
  );
}

const styles = {
  content: { padding: "24px 28px", maxWidth: 1040, width: "100%", margin: "0 auto" },
  pageHeader: { display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 },
  pageTitle: { margin: 0, fontSize: 24, fontWeight: 700, textAlign: "left" },
  pageSub: { margin: "4px 0 0", fontSize: 13, color: "var(--text-secondary)", textAlign: "left" },
  statGrid: { display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 4 },
  errorBanner: {
    fontSize: 12.5, color: "var(--red)", background: "var(--red-light)", border: "1px solid rgba(225,85,85,0.15)",
    padding: "10px 16px", borderRadius: 8, marginBottom: 16, textAlign: "left", display: "flex", justifyContent: "space-between", alignItems: "center"
  },
  retryBtn: {
    background: "var(--red)", color: "white", border: "none", borderRadius: 6, padding: "4px 10px", fontSize: 11, cursor: "pointer", fontWeight: 600
  },
  refreshBtn: {
    background: "var(--bg-card)", color: "var(--text-primary)", border: "1px solid var(--border)",
    borderRadius: 8, padding: "8px 12px", fontSize: 12.5, fontWeight: 600, display: "flex", alignItems: "center",
    cursor: "pointer", boxShadow: "var(--shadow-card)",
  },
  innerPage: {
    display: "flex", flexDirection: "column", gap: 12, textAlign: "left"
  },
  dashboardGrid: {
    display: "flex", flexDirection: "column", gap: 12
  }
};
