import React, { useState, useEffect, useRef } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { fetchNotifications } from "../api";

export default function TopBar({ userInitial = "S" }) {
  const navigate = useNavigate();
  const location = useLocation();
  const [theme, setTheme] = useState(localStorage.getItem("theme") || "light");
  const [notifOpen, setNotifOpen] = useState(false);
  const [avatarOpen, setAvatarOpen] = useState(false);
  const [notifications, setNotifications] = useState([]);
  const [hasNewNotifs, setHasNewNotifs] = useState(true);
  const [activeDoc, setActiveDoc] = useState(null);

  useEffect(() => {
    const updateActiveDoc = () => {
      const id = localStorage.getItem("currentlyOpenDocId");
      const name = localStorage.getItem("currentlyOpenDocName");
      const pages = localStorage.getItem("currentlyOpenDocPages");
      if (id && name) {
        setActiveDoc({ id, name, pages });
      } else {
        setActiveDoc(null);
      }
    };
    updateActiveDoc();
    window.addEventListener("activeDocChanged", updateActiveDoc);
    return () => window.removeEventListener("activeDocChanged", updateActiveDoc);
  }, []);

  const notifRef = useRef(null);
  const avatarRef = useRef(null);

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
      if (notifRef.current && !notifRef.current.contains(event.target)) {
        setNotifOpen(false);
      }
      if (avatarRef.current && !avatarRef.current.contains(event.target)) {
        setAvatarOpen(false);
      }
    }

    function handleKeyDown(event) {
      if (event.key === "Escape") {
        setNotifOpen(false);
        setAvatarOpen(false);
      }
    }

    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, []);

  const toggleTheme = () => {
    setTheme(prev => prev === "light" ? "dark" : "light");
  };

  const handleNotifClick = () => {
    setNotifOpen(!notifOpen);
    setHasNewNotifs(false);
  };

  const handleAvatarClick = () => {
    setAvatarOpen(!avatarOpen);
  };

  const queryParams = new URLSearchParams(location.search);
  const activeTab = queryParams.get("tab") || "overview";

  const isProofreadActive = activeTab === "proofreading" && location.pathname.includes("/documents");
  const isAssistantActive = activeTab === "assistant" && location.pathname.includes("/documents");
  const isAnalysisActive = (activeTab === "analysis" || activeTab === "context") && location.pathname.includes("/documents");
  const isComparativeActive = (activeTab === "comparative" || activeTab === "comparative-analysis") && location.pathname.includes("/documents");
  const isReportsActive = activeTab === "reports" && location.pathname.includes("/documents");

  let assessmentText = "Under Review";
  let badgeColor = "var(--amber)";
  let badgeBg = "var(--amber-light)";
  
  if (activeDoc) {
    if (activeDoc.status === "completed") {
      if (activeDoc.issuesCount === 0 && activeDoc.consistencyIssues === 0) {
        assessmentText = "Excellent";
        badgeColor = "var(--green)";
        badgeBg = "var(--green-light)";
      } else if (activeDoc.issuesCount <= 5 && activeDoc.consistencyIssues === 0) {
        assessmentText = "Good";
        badgeColor = "var(--green)";
        badgeBg = "var(--green-light)";
      } else if (activeDoc.issuesCount <= 15) {
        assessmentText = "Needs Attention";
        badgeColor = "var(--amber)";
        badgeBg = "var(--amber-light)";
      } else {
        assessmentText = "Requires Revision";
        badgeColor = "var(--red)";
        badgeBg = "var(--red-light)";
      }
    }
  }

  const handleNavTab = (tab) => {
    if (activeDoc) {
      navigate(`/documents/${activeDoc.id}?tab=${tab}`);
      window.dispatchEvent(new Event("activeDocChanged"));
    }
  };

  const handleTriggerExport = () => {
    window.dispatchEvent(new Event("openDownloadModal"));
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", width: "100%", position: "sticky", top: 0, zIndex: 100 }}>
      {/* Tier 1: Brand Navigation Header */}
      <header style={styles.bar}>
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <p onClick={() => navigate("/")} style={{ ...styles.title, cursor: "pointer" }}>
            AI Document Intelligence Platform
          </p>
        </div>
        <div style={styles.actions}>
          
          {/* Theme Toggle */}
          <button style={styles.iconBtn} onClick={toggleTheme} aria-label="Toggle theme">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <circle cx="12" cy="12" r="4" />
              <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
            </svg>
          </button>

          {/* Notifications */}
          <div ref={notifRef} style={{ position: "relative" }}>
            <button style={styles.iconBtn} onClick={handleNotifClick} aria-label="Notifications">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M18 8a6 6 0 10-12 0c0 7-3 9-3 9h18s-3-2-3-9" />
                <path d="M13.7 21a2 2 0 01-3.4 0" />
              </svg>
              {hasNewNotifs && <span style={styles.notifDot} />}
            </button>

            {notifOpen && (
              <div style={styles.dropdown}>
                <p style={styles.dropdownHeader}>Notifications</p>
                <div style={styles.dropdownContent}>
                  {notifications.length === 0 ? (
                    <p style={styles.emptyText}>No notifications</p>
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
            <div style={styles.avatar} onClick={handleAvatarClick} aria-label="User menu" role="button" tabIndex={0}>
              {userInitial}
              <span style={styles.onlineDot} />
            </div>

            {avatarOpen && (
              <div style={{ ...styles.dropdown, right: 0 }}>
                <p style={styles.dropdownHeader}>User Account</p>
                <div style={styles.dropdownContent}>
                  <button style={styles.menuItem} onClick={() => alert("Profile Coming soon")}>Profile</button>
                  <button style={styles.menuItem} onClick={() => alert("Settings page")}>Settings</button>
                  <hr style={styles.hr} />
                  <button style={{ ...styles.menuItem, color: "var(--red)" }} onClick={() => console.log("Sign out triggered")}>Sign out</button>
                </div>
              </div>
            )}
          </div>

        </div>
      </header>

      {/* Tier 2: Sticky Document Session Header */}
      {activeDoc && (
        <div style={styles.subBar}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, overflow: "hidden" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6, color: "var(--text-secondary)", flexShrink: 0 }}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
              <strong style={{ fontSize: 12.5, color: "var(--text-primary)", maxWidth: 160, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={activeDoc.name}>
                {activeDoc.name}
              </strong>
              <span style={{ fontSize: 11, color: "var(--text-muted)" }}>({activeDoc.pages} Pages)</span>
            </div>

            <span style={{ color: "var(--border)", fontSize: 14 }}>•</span>

            <div style={{ display: "flex", alignItems: "center", gap: 6, flexShrink: 0 }}>
              <span style={{ fontSize: 11.5, color: "var(--text-secondary)" }}>Assessment:</span>
              <span style={{
                fontSize: 10.5, fontWeight: 700, padding: "2px 6px", borderRadius: 4,
                backgroundColor: badgeBg, color: badgeColor
              }}>
                {assessmentText}
              </span>
            </div>

            <span style={{ color: "var(--border)", fontSize: 14 }}>•</span>

            <div style={{ display: "flex", alignItems: "center", gap: 4, flexShrink: 0 }}>
              <span style={{ fontSize: 11.5, color: "var(--text-secondary)" }}>Status:</span>
              <span style={{
                fontSize: 10.5, fontWeight: 750, color: activeDoc.status === "completed" ? "var(--green)" : "var(--amber)",
                textTransform: "uppercase"
              }}>
                {activeDoc.status === "completed" ? "Completed" : "Processing"}
              </span>
            </div>
          </div>

          {/* Quick Actions Navigation Row */}
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontSize: 10, fontWeight: 750, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: 0.5, marginRight: 4 }}>
              Workspace Tab:
            </span>

            <button
              onClick={() => handleNavTab("proofreading")}
              style={{
                ...styles.navLink,
                backgroundColor: isProofreadActive ? "var(--brand-light)" : "transparent",
                color: isProofreadActive ? "var(--brand)" : "var(--text-secondary)",
                fontWeight: isProofreadActive ? 700 : 500
              }}
            >
              Proofread
            </button>

            <button
              onClick={() => handleNavTab("assistant")}
              style={{
                ...styles.navLink,
                backgroundColor: isAssistantActive ? "var(--brand-light)" : "transparent",
                color: isAssistantActive ? "var(--brand)" : "var(--text-secondary)",
                fontWeight: isAssistantActive ? 700 : 500
              }}
            >
              Ask AI
            </button>

            <button
              onClick={() => handleNavTab("analysis")}
              style={{
                ...styles.navLink,
                backgroundColor: isAnalysisActive ? "var(--brand-light)" : "transparent",
                color: isAnalysisActive ? "var(--brand)" : "var(--text-secondary)",
                fontWeight: isAnalysisActive ? 700 : 500
              }}
            >
              Context Analysis
            </button>

            <button
              onClick={() => handleNavTab("comparative")}
              style={{
                ...styles.navLink,
                backgroundColor: isComparativeActive ? "var(--brand-light)" : "transparent",
                color: isComparativeActive ? "var(--brand)" : "var(--text-secondary)",
                fontWeight: isComparativeActive ? 700 : 500
              }}
            >
              Comparative Analysis
            </button>

            <button
              onClick={() => handleNavTab("reports")}
              style={{
                ...styles.navLink,
                backgroundColor: isReportsActive ? "var(--brand-light)" : "transparent",
                color: isReportsActive ? "var(--brand)" : "var(--text-secondary)",
                fontWeight: isReportsActive ? 700 : 500
              }}
            >
              Reports
            </button>

            <button
              onClick={handleTriggerExport}
              style={{
                ...styles.navLink,
                backgroundColor: "var(--brand)",
                color: "white",
                fontWeight: 650
              }}
            >
              Export
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

const styles = {
  bar: {
    height: 56, background: "var(--bg-card)", borderBottom: "1px solid var(--border)",
    display: "flex", alignItems: "center", justifyContent: "space-between",
    padding: "0 24px", flexShrink: 0,
  },
  subBar: {
    height: 48, background: "var(--bg-card)", borderBottom: "1px solid var(--border)",
    display: "flex", alignItems: "center", justifyContent: "space-between",
    padding: "0 24px", flexShrink: 0,
  },
  navLink: {
    background: "none", border: "none", padding: "4px 10px", borderRadius: 6,
    fontSize: 12, cursor: "pointer", transition: "all 0.15s ease",
    display: "flex", alignItems: "center", outline: "none"
  },
  activeDocIndicator: {
    display: "flex", alignItems: "center", gap: 6,
    background: "var(--brand-light)", padding: "4px 10px", borderRadius: 999,
    fontSize: 11.5, border: "1px solid rgba(138, 92, 246, 0.15)",
  },
  indicatorDot: {
    width: 6, height: 6, borderRadius: "50%", background: "var(--brand)",
    animation: "pulse 2s infinite",
  },
  indicatorLabel: { color: "var(--text-secondary)", fontWeight: 500 },
  indicatorName: { color: "var(--brand)", fontWeight: 700, maxWidth: 180, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" },
  indicatorPages: { color: "var(--text-muted)", fontSize: 10.5 },
  title: { margin: 0, fontSize: 14, fontWeight: 600, color: "var(--text-primary)" },
  actions: { display: "flex", alignItems: "center", gap: 12 },
  iconBtn: {
    position: "relative",
    width: 34, height: 34, borderRadius: "50%",
    border: "1px solid var(--border)", background: "var(--bg-card)",
    display: "flex", alignItems: "center", justifyContent: "center",
    color: "var(--text-secondary)",
    cursor: "pointer",
  },
  notifDot: {
    position: "absolute", top: 6, right: 7,
    width: 6, height: 6, borderRadius: "50%", background: "var(--brand)",
  },
  avatar: {
    position: "relative",
    width: 32, height: 32, borderRadius: "50%",
    background: "var(--brand)", color: "white",
    display: "flex", alignItems: "center", justifyContent: "center",
    fontSize: 13, fontWeight: 600,
    cursor: "pointer",
  },
  onlineDot: {
    position: "absolute", bottom: -1, right: -1,
    width: 9, height: 9, borderRadius: "50%",
    background: "var(--green)", border: "2px solid var(--bg-card)",
  },
  dropdown: {
    position: "absolute", top: 40, right: 0,
    width: 240, background: "var(--bg-card)", border: "1px solid var(--border)",
    borderRadius: 8, boxShadow: "0 4px 12px rgba(0, 0, 0, 0.1)", zIndex: 100,
    padding: "8px 0",
  },
  dropdownHeader: {
    margin: 0, padding: "8px 12px 4px", fontSize: 12, fontWeight: 700,
    color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: 0.5,
  },
  dropdownContent: {
    display: "flex", flexDirection: "column",
  },
  dropdownItem: {
    padding: "8px 12px", borderBottom: "1px solid var(--border)",
    textAlign: "left",
  },
  itemText: { margin: 0, fontSize: 12.5, color: "var(--text-primary)" },
  itemTime: { margin: "2px 0 0", fontSize: 10, color: "var(--text-muted)" },
  emptyText: { margin: 0, padding: "16px", fontSize: 12.5, color: "var(--text-muted)", textAlign: "center" },
  menuItem: {
    background: "none", border: "none", textAlign: "left",
    padding: "10px 12px", fontSize: 13, color: "var(--text-primary)",
    cursor: "pointer", width: "100%",
  },
  hr: { margin: "4px 0", border: "none", borderTop: "1px solid var(--border)" },
};
