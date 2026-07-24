import { Routes, Route, useNavigate, useLocation } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Sidebar from "./components/Sidebar";
import TopBar from "./components/TopBar";
import StatCard from "./components/StatCard";
import UploadZone from "./components/UploadZone";
import RecentDocuments from "./components/RecentDocuments";
import Workspace from "./components/Workspace";
import Reports from "./components/Reports";
import Settings from "./components/Settings";
import ProofreadingEmptyState from "./components/ProofreadingEmptyState";
import Assistant from "./components/Assistant";
import { fetchDocuments, fetchStats, fetchSystemStatus } from "./api";

const FALLBACK_STATS = { totalDocuments: 0, grammarAccuracy: 0, issuesResolvedToday: 0, documentsToday: 0 };

export default function App() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const location = useLocation();

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
                      <p style={styles.pageSub}>Upload files and manage your proofreading analysis history</p>
                    </div>
                    <button style={styles.refreshBtn} onClick={handleRefreshAll} aria-label="Refresh Dashboard">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" style={{ marginRight: 6 }}>
                        <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 11-.57-8.38l5.67-5.67" />
                      </svg>
                      Refresh
                    </button>
                  </div>

                  <div style={{ margin: "16px 0" }}>
                    <UploadZone onUploaded={(result) => {
                      handleRefreshAll();
                      if (result && result.id) {
                        localStorage.setItem("currentlyOpenDocId", result.id);
                        localStorage.setItem("currentlyOpenDocName", result.filename || "");
                        localStorage.setItem("currentlyOpenDocPages", result.total_pages || result.pages || 1);
                        window.dispatchEvent(new Event("activeDocChanged"));
                        navigate(`/documents/${result.id}`);
                      }
                    }} />
                  </div>

                  <RecentDocuments documents={documents} onRefresh={handleRefreshAll} />
                </div>
              }
            />

            {/* Route 2: Document Workspace Page */}
            <Route path="/documents/:id" element={<Workspace />} />

            {/* Route 3: Pages */}
            <Route path="/proofreading" element={<ProofreadingEmptyState />} />
            <Route path="/reports" element={<Reports />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="/assistant" element={<Assistant />} />
            <Route path="/assistant/:id" element={<Assistant />} />
          </Routes>
        </main>
      </div>
    </div>
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
