import React, { useState, useEffect, useRef } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { fetchNotifications } from "../api";

export default function TopBar({ userInitial = "S" }) {
  const navigate = useNavigate();
  const location = useLocation();
  const [theme, setTheme] = useState(localStorage.getItem("theme") || "light");
  const [notifOpen, setNotifOpen] = useState(false);
  const [avatarOpen, setAvatarOpen] = useState(false);
  const [actionsOpen, setActionsOpen] = useState(false);
  const [metricsOpen, setMetricsOpen] = useState(false);
  const [notifications, setNotifications] = useState([]);
  const [hasNewNotifs, setHasNewNotifs] = useState(true);
  const [activeDoc, setActiveDoc] = useState(null);

  const notifRef = useRef(null);
  const avatarRef = useRef(null);
  const actionsRef = useRef(null);
  const metricsRef = useRef(null);

  useEffect(() => {
    const updateActiveDoc = (evt) => {
      const id = localStorage.getItem("currentlyOpenDocId");
      const name = localStorage.getItem("currentlyOpenDocName");
      const pages = localStorage.getItem("currentlyOpenDocPages");
      const status = localStorage.getItem("currentlyOpenDocStatus") || "pending";
      let flags = {};
      try {
        const rawFlags = localStorage.getItem("currentlyOpenDocFlags");
        if (rawFlags) flags = JSON.parse(rawFlags);
      } catch (e) {}

      if (evt && evt.detail) {
        const detail = evt.detail;
        flags = {
          upload_ready: detail.upload_ready,
          document_viewer_ready: detail.document_viewer_ready || detail.extraction_ready,
          spell_ready: detail.spell_ready,
          grammar_ready: detail.grammar_ready,
          proofreading_ready: detail.proofreading_ready || detail.spell_ready || detail.grammar_ready || detail.status === "completed",
          rag_ready: detail.rag_ready || detail.rag_status === "completed" || detail.status === "completed",
          context_analysis_ready: detail.context_analysis_ready || detail.context_analysis_status === "completed" || detail.status === "completed",
          comparative_analysis_ready: detail.comparative_analysis_ready || detail.comparative_analysis_status === "completed" || detail.status === "completed",
          reports_ready: detail.reports_ready || detail.status === "completed"
        };
      }

      const pathId = location.pathname.startsWith("/documents/") ? location.pathname.split("/")[2] : null;
      const effectiveId = id || pathId;
      const effectiveName = name || (effectiveId ? "Active Document" : null);

      if (effectiveId && effectiveName) {
        setActiveDoc({ id: effectiveId, name: effectiveName, pages: pages || 1, status, flags });
      } else {
        setActiveDoc(null);
      }
    };

    updateActiveDoc();
    window.addEventListener("activeDocChanged", updateActiveDoc);
    return () => window.removeEventListener("activeDocChanged", updateActiveDoc);
  }, [location.pathname]);

  // Apply theme
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("theme", theme);
  }, [theme]);

  // Load notifications
  useEffect(() => {
    async function loadNotifs() {
      try {
        const list = await fetchNotifications();
        setNotifications(list);
      } catch (e) {
        setNotifications([
          { id: 1, text: "Grammar review engine is fully online.", time: "Just now" },
          { id: 2, text: "LanguageTool dictionary loaded successfully.", time: "5m ago" },
          { id: 3, text: "Symspell spelling checks initialized.", time: "10m ago" }
        ]);
      }
    }
    loadNotifs();
  }, []);

  // Handle outside click & escape
  useEffect(() => {
    function handleClickOutside(event) {
      if (notifRef.current && !notifRef.current.contains(event.target)) setNotifOpen(false);
      if (avatarRef.current && !avatarRef.current.contains(event.target)) setAvatarOpen(false);
      if (actionsRef.current && !actionsRef.current.contains(event.target)) setActionsOpen(false);
      if (metricsRef.current && !metricsRef.current.contains(event.target)) setMetricsOpen(false);
    }

    function handleKeyDown(event) {
      if (event.key === "Escape") {
        setNotifOpen(false);
        setAvatarOpen(false);
        setActionsOpen(false);
        setMetricsOpen(false);
      }
    }

    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, []);

  const toggleTheme = () => setTheme(prev => prev === "light" ? "dark" : "light");

  const handleNavTab = (tab) => {
    const docId = activeDoc?.id || localStorage.getItem("currentlyOpenDocId");
    if (docId) {
      navigate(`/documents/${docId}?tab=${tab}`);
      window.dispatchEvent(new Event("activeDocChanged"));
    } else {
      navigate("/");
    }
  };

  const handleTriggerExport = () => {
    window.dispatchEvent(new Event("openDownloadModal"));
  };

  const queryParams = new URLSearchParams(location.search);
  const activeTab = queryParams.get("tab") || "proofreading";
  const isDocWorkspace = location.pathname.includes("/documents") || Boolean(activeDoc);

  const isProofreadActive = (activeTab === "proofreading" || activeTab === "proofread") && isDocWorkspace;
  const isAssistantActive = (activeTab === "assistant" || activeTab === "ask-ai") && isDocWorkspace;
  const isAnalysisActive = (activeTab === "analysis" || activeTab === "context") && isDocWorkspace;
  const isComparativeActive = (activeTab === "comparative" || activeTab === "comparative-analysis" || activeTab === "benchmarking") && isDocWorkspace;
  const isReportsActive = (activeTab === "reports") && isDocWorkspace;
  const isImagesActive = (activeTab === "images" || activeTab === "gallery") && isDocWorkspace;

  let assessmentText = "Processing";
  let badgeColor = "var(--amber)";
  let badgeBg = "var(--amber-light)";
  
  if (activeDoc) {
    if (activeDoc.status === "completed") {
      assessmentText = "✓ Scan Complete";
      badgeColor = "var(--green)";
      badgeBg = "var(--green-light)";
    }
  }

  const flags = activeDoc?.flags || {};
  const isCompleted = activeDoc?.status === "completed";
  const isProcessing = activeDoc?.status === "processing" || activeDoc?.status === "pending";

  const isProofreadReady = flags.proofreading_ready || flags.spell_ready || flags.grammar_ready || isCompleted;
  const isAssistantReady = flags.rag_ready || isCompleted;
  const isAnalysisReady = flags.context_analysis_ready || isCompleted;
  const isComparativeReady = flags.comparative_analysis_ready || isCompleted;
  const isReportsReady = flags.reports_ready || isCompleted;

  return (
    <div style={styles.container}>
      {/* ---------------------------------------------------- */}
      {/* TIER 1: Compact Enterprise Application Header       */}
      {/* ---------------------------------------------------- */}
      <header style={styles.tier1Bar}>
        <div style={styles.brandGroup} onClick={() => navigate("/")} title="Return to Documents Dashboard">
          <div style={styles.logoBox}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
              <polyline points="14 2 14 8 20 8"/>
              <path d="M16 13H8"/>
              <path d="M16 17H8"/>
              <path d="M10 9H8"/>
            </svg>
          </div>
          <span style={styles.platformTitle}>Corporate Document Intelligence</span>
          <span style={styles.platformTag}>ENTERPRISE</span>
        </div>

        <div style={styles.tier1Right}>
          {/* Theme Toggle */}
          <button style={styles.iconBtn} onClick={toggleTheme} aria-label="Toggle theme" title={`Switch to ${theme === 'light' ? 'dark' : 'light'} mode`}>
            {theme === "light" ? (
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <circle cx="12" cy="12" r="4" />
                <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
              </svg>
            ) : (
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
              </svg>
            )}
          </button>

          {/* Notifications */}
          <div ref={notifRef} style={{ position: "relative" }}>
            <button style={styles.iconBtn} onClick={() => { setNotifOpen(!notifOpen); setHasNewNotifs(false); }} aria-label="Notifications" title="System Notifications">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M18 8a6 6 0 10-12 0c0 7-3 9-3 9h18s-3-2-3-9" />
                <path d="M13.7 21a2 2 0 01-3.4 0" />
              </svg>
              {hasNewNotifs && <span style={styles.notifDot} />}
            </button>

            {notifOpen && (
              <div style={styles.dropdown}>
                <div style={styles.dropdownHeader}>System Notifications</div>
                <div style={styles.dropdownContent}>
                  {notifications.length === 0 ? (
                    <p style={styles.emptyText}>No recent alerts</p>
                  ) : (
                    notifications.map((n) => (
                      <div key={n.id} style={styles.dropdownItem}>
                        <p style={styles.itemText}>{n.text}</p>
                        <p style={styles.itemTime}>{n.time}</p>
                      </div>
                    ))
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Avatar Menu */}
          <div ref={avatarRef} style={{ position: "relative" }}>
            <div style={styles.avatar} onClick={() => setAvatarOpen(!avatarOpen)} aria-label="User menu" role="button" tabIndex={0}>
              {userInitial}
              <span style={styles.onlineDot} />
            </div>

            {avatarOpen && (
              <div style={{ ...styles.dropdown, right: 0 }}>
                <div style={styles.dropdownHeader}>Enterprise User</div>
                <div style={styles.dropdownContent}>
                  <button style={styles.menuItem} onClick={() => { setAvatarOpen(false); navigate("/settings"); }}>Account & Settings</button>
                  <button style={styles.menuItem} onClick={() => { setAvatarOpen(false); navigate("/reports"); }}>Reports Library</button>
                  <hr style={styles.hr} />
                  <button style={{ ...styles.menuItem, color: "var(--red)" }} onClick={() => { setAvatarOpen(false); navigate("/"); }}>Sign Out</button>
                </div>
              </div>
            )}
          </div>
        </div>
      </header>

      {/* ---------------------------------------------------- */}
      {/* TIER 2: Document Workspace Header                   */}
      {/* ---------------------------------------------------- */}
      {isDocWorkspace && (
        <div style={styles.tier2Bar}>
          <div style={styles.tier2Left}>
            {/* Back Button */}
            <button
              onClick={() => {
                localStorage.removeItem("currentlyOpenDocId");
                localStorage.removeItem("currentlyOpenDocName");
                window.dispatchEvent(new Event("activeDocChanged"));
                navigate("/");
              }}
              style={styles.backBtn}
              title="Return to Documents Directory"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="19" y1="12" x2="5" y2="12" />
                <polyline points="12 19 5 12 12 5" />
              </svg>
              <span>Back to Documents</span>
            </button>

            <span style={styles.vDivider} />

            {/* Document Info */}
            <div style={styles.docInfoGroup}>
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="var(--brand)" strokeWidth="2" style={{ flexShrink: 0 }}>
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                <polyline points="14 2 14 8 20 8"/>
              </svg>
              <span style={styles.docTitle} title={activeDoc?.name || "Active Document"}>
                {activeDoc?.name || "Active Document"}
              </span>
              <span style={styles.pageCountBadge}>
                {activeDoc?.pages || 1} {activeDoc?.pages === 1 ? "Page" : "Pages"}
              </span>
            </div>

            <span style={styles.vDivider} />

            {/* Status & Metrics Badge */}
            <div ref={metricsRef} style={{ position: "relative" }}>
              <button
                onClick={() => setMetricsOpen(!metricsOpen)}
                style={{
                  ...styles.statusBadgeBtn,
                  backgroundColor: badgeBg,
                  color: badgeColor
                }}
                title="Click to expand detailed scan metrics"
              >
                <span style={styles.statusDot} />
                <span>{assessmentText}</span>
                <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" style={{ transform: metricsOpen ? "rotate(180deg)" : "none", transition: "transform 0.15s" }}>
                  <polyline points="6 9 12 15 18 9"/>
                </svg>
              </button>

              {metricsOpen && (
                <div style={styles.metricsPopover}>
                  <div style={styles.popoverHeading}>Audit Metrics Breakdown</div>
                  <div style={styles.popoverRow}>
                    <span>Processing Status:</span>
                    <strong style={{ color: activeDoc?.status === "completed" ? "var(--green)" : "var(--amber)" }}>
                      {activeDoc?.status === "completed" ? "Completed" : "In Progress"}
                    </strong>
                  </div>
                  <div style={styles.popoverRow}>
                    <span>Document Pages:</span>
                    <strong>{activeDoc?.pages || 1}</strong>
                  </div>
                  <div style={styles.popoverRow}>
                    <span>Ingestion Engine:</span>
                    <strong>Docling Standard PDF</strong>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Right: Actions Dropdown Menu */}
          <div ref={actionsRef} style={{ position: "relative" }}>
            <button
              onClick={() => setActionsOpen(!actionsOpen)}
              style={styles.actionsBtn}
              title="Document Management & Recovery Actions"
            >
              <span>Actions</span>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" style={{ transform: actionsOpen ? "rotate(180deg)" : "none", transition: "transform 0.15s" }}>
                <polyline points="6 9 12 15 18 9"/>
              </svg>
            </button>

            {actionsOpen && (
              <div style={styles.actionsMenu}>
                <button
                  style={styles.actionsMenuItem}
                  onClick={() => { setActionsOpen(false); handleNavTab("assistant"); }}
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ marginRight: 8 }}>
                    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
                  </svg>
                  Open AI Assistant
                </button>

                <button
                  style={styles.actionsMenuItem}
                  onClick={() => { setActionsOpen(false); handleNavTab("reports"); }}
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ marginRight: 8 }}>
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>
                  </svg>
                  Open Executive Report
                </button>

                <button
                  style={styles.actionsMenuItem}
                  onClick={() => { setActionsOpen(false); window.dispatchEvent(new Event("downloadCleanDoc")); }}
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ marginRight: 8 }}>
                    <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/>
                  </svg>
                  Download Clean Document
                </button>

                <button
                  style={styles.actionsMenuItem}
                  onClick={() => { setActionsOpen(false); window.dispatchEvent(new Event("openDownloadModal")); }}
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ marginRight: 8 }}>
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
                  </svg>
                  Download Reports & Exports
                </button>

                <hr style={styles.hr} />

                <button
                  style={styles.actionsMenuItem}
                  onClick={() => { setActionsOpen(false); window.dispatchEvent(new Event("validateOutputs")); }}
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ marginRight: 8 }}>
                    <circle cx="12" cy="12" r="10"/><path d="M12 8v4M12 16h.01"/>
                  </svg>
                  Validate Output Files
                </button>

                <button
                  style={styles.actionsMenuItem}
                  onClick={() => { setActionsOpen(false); window.dispatchEvent(new Event("repairJob")); }}
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ marginRight: 8 }}>
                    <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>
                  </svg>
                  Auto-Repair Pipeline
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ---------------------------------------------------- */}
      {/* TIER 3: Analysis Horizontal Navigation Row           */}
      {/* ---------------------------------------------------- */}
      {isDocWorkspace && (
        <nav style={styles.tier3Bar}>
          <div style={styles.tabList}>
            {/* 1. Proofread */}
            <button
              onClick={() => handleNavTab("proofreading")}
              style={{
                ...styles.navTab,
                ...(isProofreadActive ? styles.navTabActive : {})
              }}
            >
              <span>Proofread</span>
              {!isProofreadReady && isProcessing && <span style={styles.statusChip}>Processing</span>}
            </button>

            {/* 2. Ask AI */}
            <button
              onClick={() => handleNavTab("assistant")}
              style={{
                ...styles.navTab,
                ...(isAssistantActive ? styles.navTabActive : {})
              }}
            >
              <span>Ask AI</span>
              {!isAssistantReady && isProcessing && <span style={styles.statusChip}>Indexing</span>}
            </button>

            {/* 3. Ambiguity Analysis */}
            <button
              onClick={() => handleNavTab("analysis")}
              style={{
                ...styles.navTab,
                ...(isAnalysisActive ? styles.navTabActive : {})
              }}
            >
              <span>Ambiguity Analysis</span>
              {!isAnalysisReady && isProcessing && <span style={styles.statusChip}>Reviewing</span>}
            </button>

            {/* 4. Comparative Analysis */}
            <button
              onClick={() => handleNavTab("comparative")}
              style={{
                ...styles.navTab,
                ...(isComparativeActive ? styles.navTabActive : {})
              }}
            >
              <span>Comparative Analysis</span>
              {!isComparativeReady && isProcessing && <span style={styles.statusChip}>Benchmarking</span>}
            </button>

            {/* 5. Image Gallery */}
            <button
              onClick={() => handleNavTab("images")}
              style={{
                ...styles.navTab,
                ...(isImagesActive ? styles.navTabActive : {})
              }}
            >
              <span>Images</span>
              {!isAssistantReady && isProcessing && <span style={styles.statusChip}>Indexing</span>}
            </button>

            {/* 6. Reports */}
            <button
              onClick={() => handleNavTab("reports")}
              style={{
                ...styles.navTab,
                ...(isReportsActive ? styles.navTabActive : {})
              }}
            >
              <span>Reports</span>
              {!isReportsReady && isProcessing && <span style={styles.statusChip}>Generating</span>}
            </button>
          </div>

          {/* Export Action Button */}
          <button
            onClick={handleTriggerExport}
            style={styles.exportBtn}
            title="Export reports, ZIP package & corrected document"
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
              <polyline points="7 10 12 15 17 10"/>
              <line x1="12" y1="15" x2="12" y2="3"/>
            </svg>
            <span>Export</span>
          </button>
        </nav>
      )}
    </div>
  );
}

const styles = {
  container: {
    display: "flex",
    flexDirection: "column",
    width: "100%",
    position: "sticky",
    top: 0,
    zIndex: 100,
    boxShadow: "0 1px 3px rgba(15, 23, 42, 0.06)",
    backgroundColor: "var(--bg-card)"
  },

  /* Tier 1 Bar */
  tier1Bar: {
    height: 48,
    background: "var(--bg-card)",
    borderBottom: "1px solid var(--border)",
    display: "flex",
    alignItems: "center",
    justify: "space-between",
    padding: "0 24px",
    flexShrink: 0
  },
  brandGroup: {
    display: "flex",
    alignItems: "center",
    gap: 10,
    cursor: "pointer",
    userSelect: "none"
  },
  logoBox: {
    width: 30,
    height: 30,
    borderRadius: 6,
    background: "var(--brand)",
    color: "#FFFFFF",
    display: "flex",
    alignItems: "center",
    justifyContent: "center"
  },
  platformTitle: {
    fontSize: 14,
    fontWeight: 700,
    color: "var(--text-primary)",
    letterSpacing: "-0.2px"
  },
  platformTag: {
    fontSize: 9.5,
    fontWeight: 800,
    letterSpacing: "0.6px",
    color: "var(--brand)",
    background: "var(--brand-light)",
    padding: "2px 6px",
    borderRadius: 4
  },
  tier1Right: {
    display: "flex",
    alignItems: "center",
    gap: 12,
    marginLeft: "auto"
  },
  iconBtn: {
    position: "relative",
    width: 32,
    height: 32,
    borderRadius: "50%",
    border: "1px solid var(--border)",
    background: "var(--bg-card)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    color: "var(--text-secondary)",
    cursor: "pointer",
    transition: "all 0.15s ease"
  },
  notifDot: {
    position: "absolute",
    top: 6,
    right: 7,
    width: 6,
    height: 6,
    borderRadius: "50%",
    background: "var(--brand)"
  },
  avatar: {
    position: "relative",
    width: 30,
    height: 30,
    borderRadius: "50%",
    background: "var(--brand)",
    color: "#FFFFFF",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontSize: 12.5,
    fontWeight: 700,
    cursor: "pointer"
  },
  onlineDot: {
    position: "absolute",
    bottom: -1,
    right: -1,
    width: 8,
    height: 8,
    borderRadius: "50%",
    background: "var(--green)",
    border: "2px solid var(--bg-card)"
  },

  /* Tier 2 Bar */
  tier2Bar: {
    height: 42,
    background: "var(--bg-card)",
    borderBottom: "1px solid var(--border)",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "0 24px",
    flexShrink: 0
  },
  tier2Left: {
    display: "flex",
    alignItems: "center",
    gap: 10,
    minWidth: 0
  },
  backBtn: {
    background: "none",
    border: "none",
    padding: "4px 8px",
    borderRadius: 6,
    color: "var(--text-secondary)",
    fontSize: 12.5,
    fontWeight: 500,
    display: "flex",
    alignItems: "center",
    gap: 6,
    cursor: "pointer",
    whiteSpace: "nowrap"
  },
  vDivider: {
    width: 1,
    height: 16,
    background: "var(--border)",
    flexShrink: 0
  },
  docInfoGroup: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    minWidth: 0
  },
  docTitle: {
    fontSize: 13,
    fontWeight: 650,
    color: "var(--text-primary)",
    maxWidth: 240,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap"
  },
  pageCountBadge: {
    fontSize: 11,
    color: "var(--text-muted)",
    whiteSpace: "nowrap"
  },
  statusBadgeBtn: {
    background: "none",
    border: "none",
    padding: "3px 8px",
    borderRadius: 6,
    fontSize: 11,
    fontWeight: 700,
    display: "inline-flex",
    alignItems: "center",
    gap: 6,
    cursor: "pointer",
    whiteSpace: "nowrap"
  },
  statusDot: {
    width: 6,
    height: 6,
    borderRadius: "50%",
    background: "currentColor"
  },
  actionsBtn: {
    background: "var(--bg-page)",
    border: "1px solid var(--border)",
    borderRadius: 6,
    padding: "5px 12px",
    fontSize: 12,
    fontWeight: 600,
    color: "var(--text-primary)",
    display: "inline-flex",
    alignItems: "center",
    gap: 6,
    cursor: "pointer"
  },

  /* Tier 3 Navigation Bar */
  tier3Bar: {
    height: 42,
    background: "var(--bg-card)",
    borderBottom: "1px solid var(--border)",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "0 24px",
    flexShrink: 0,
    overflowX: "auto"
  },
  tabList: {
    display: "flex",
    alignItems: "center",
    gap: 2,
    height: "100%"
  },
  navTab: {
    height: "100%",
    background: "transparent",
    border: "none",
    borderBottom: "2px solid transparent",
    padding: "0 14px",
    fontSize: 13,
    fontWeight: 500,
    color: "var(--text-secondary)",
    whiteSpace: "nowrap",
    display: "inline-flex",
    alignItems: "center",
    cursor: "pointer",
    transition: "all 0.15s ease",
    outline: "none"
  },
  navTabActive: {
    color: "var(--brand)",
    fontWeight: 650,
    borderBottomColor: "var(--brand)"
  },
  statusChip: {
    fontSize: 9.5,
    fontWeight: 700,
    color: "var(--amber)",
    background: "var(--amber-light)",
    padding: "1px 6px",
    borderRadius: 4,
    marginLeft: 6
  },
  exportBtn: {
    background: "var(--brand)",
    color: "#FFFFFF",
    border: "none",
    borderRadius: 6,
    padding: "5px 14px",
    fontSize: 12,
    fontWeight: 600,
    display: "inline-flex",
    alignItems: "center",
    gap: 6,
    cursor: "pointer",
    whiteSpace: "nowrap",
    marginLeft: 16
  },

  /* Dropdowns & Popovers */
  dropdown: {
    position: "absolute",
    top: 40,
    right: 0,
    width: 240,
    background: "var(--bg-card)",
    border: "1px solid var(--border)",
    borderRadius: 8,
    boxShadow: "0 10px 15px -3px rgba(0,0,0,0.1), 0 4px 6px -2px rgba(0,0,0,0.05)",
    zIndex: 200,
    padding: "8px 0"
  },
  dropdownHeader: {
    padding: "6px 12px",
    fontSize: 11,
    fontWeight: 700,
    color: "var(--text-muted)",
    textTransform: "uppercase",
    letterSpacing: "0.5px"
  },
  dropdownContent: {
    display: "flex",
    flexDirection: "column"
  },
  dropdownItem: {
    padding: "8px 12px",
    borderBottom: "1px solid var(--border)",
    textAlign: "left"
  },
  itemText: { margin: 0, fontSize: 12.5, color: "var(--text-primary)" },
  itemTime: { margin: "2px 0 0", fontSize: 10, color: "var(--text-muted)" },
  emptyText: { margin: 0, padding: 12, fontSize: 12, color: "var(--text-muted)", textAlign: "center" },
  menuItem: {
    background: "none",
    border: "none",
    textAlign: "left",
    padding: "8px 12px",
    fontSize: 12.5,
    color: "var(--text-primary)",
    cursor: "pointer",
    width: "100%"
  },
  actionsMenu: {
    position: "absolute",
    top: 36,
    right: 0,
    width: 230,
    background: "var(--bg-card)",
    border: "1px solid var(--border)",
    borderRadius: 8,
    boxShadow: "0 10px 15px -3px rgba(0,0,0,0.1)",
    zIndex: 200,
    padding: "6px 0",
    display: "flex",
    flexDirection: "column"
  },
  actionsMenuItem: {
    background: "none",
    border: "none",
    textAlign: "left",
    padding: "8px 14px",
    fontSize: 12.5,
    fontWeight: 500,
    color: "var(--text-primary)",
    cursor: "pointer",
    display: "flex",
    alignItems: "center",
    width: "100%"
  },
  metricsPopover: {
    position: "absolute",
    top: 32,
    left: 0,
    width: 220,
    background: "var(--bg-card)",
    border: "1px solid var(--border)",
    borderRadius: 8,
    padding: 12,
    boxShadow: "0 10px 15px -3px rgba(0,0,0,0.1)",
    zIndex: 200,
    display: "flex",
    flexDirection: "column",
    gap: 6
  },
  popoverHeading: {
    fontSize: 11,
    fontWeight: 700,
    textTransform: "uppercase",
    color: "var(--text-muted)",
    borderBottom: "1px solid var(--border)",
    paddingBottom: 4,
    marginBottom: 4
  },
  popoverRow: {
    display: "flex",
    justifyContent: "space-between",
    fontSize: 12,
    color: "var(--text-primary)"
  },
  hr: {
    margin: "4px 0",
    border: "none",
    borderTop: "1px solid var(--border)"
  }
};
