import React from "react";
import { NavLink } from "react-router-dom";

const NAV_ITEMS = [
  { key: "dashboard", label: "Dashboard", icon: "grid" },
  { key: "proofreading", label: "Proofreading", icon: "check-square" },
  { key: "assistant", label: "AI Assistant", icon: "message-square" },
  { key: "analysis", label: "Context Analysis", icon: "search" },
  { key: "comparative", label: "Comparative Analysis", icon: "layers" },
  { key: "reports", label: "Reports", icon: "bar-chart" },
  { key: "settings", label: "Settings", icon: "settings" },
];

function Icon({ name }) {
  const common = { width: 15, height: 15, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 2, strokeLinecap: "round", strokeLinejoin: "round" };
  switch (name) {
    case "grid":
      return <svg {...common}><rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" /><rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" /></svg>;
    case "check-square":
      return <svg {...common}><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M8 12l3 3 5-6" /></svg>;
    case "bar-chart":
      return <svg {...common}><path d="M4 20V10" /><path d="M12 20V4" /><path d="M20 20v-7" /></svg>;
    case "search":
      return <svg {...common}><circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" /></svg>;
    case "layers":
      return <svg {...common}><polygon points="12 2 2 7 12 12 22 7 12 2" /><polyline points="2 17 12 22 22 17" /><polyline points="2 12 12 17 22 12" /></svg>;
    case "settings":
      return <svg {...common}><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 00.34 1.87l.06.06a2 2 0 11-2.83 2.83l-.06-.06a1.7 1.7 0 00-1.87-.34 1.7 1.7 0 00-1 1.55V21a2 2 0 11-4 0v-.09a1.7 1.7 0 00-1-1.55 1.7 1.7 0 00-1.87.34l-.06.06a2 2 0 11-2.83-2.83l.06-.06a1.7 1.7 0 00.34-1.87 1.7 1.7 0 00-1.55-1H3a2 2 0 110-4h.09a1.7 1.7 0 001.55-1 1.7 1.7 0 00-.34-1.87l-.06-.06a2 2 0 112.83-2.83l.06.06a1.7 1.7 0 001.87.34H9a1.7 1.7 0 001-1.55V3a2 2 0 114 0v.09a1.7 1.7 0 001 1.55 1.7 1.7 0 001.87-.34l.06-.06a2 2 0 112.83 2.83l-.06.06a1.7 1.7 0 00-.34 1.87V9a1.7 1.7 0 001.55 1H21a2 2 0 110 4h-.09a1.7 1.7 0 00-1.55 1z" /></svg>;
    case "message-square":
      return <svg {...common}><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" /></svg>;
    default:
      return null;
  }
}

const DEFAULT_SYSTEM_STATUS = [
  { name: "Backend", online: true },
  { name: "LLM (Ollama)", online: true },
  { name: "LanguageTool", online: true },
  { name: "SymSpell", online: true },
];

export default function Sidebar({ systemStatus }) {
  const statusList = Array.isArray(systemStatus)
    ? systemStatus
    : Array.isArray(systemStatus?.status_list)
    ? systemStatus.status_list
    : [
        { name: "Backend", online: true },
        { name: "LLM (Ollama)", online: systemStatus?.ollama_status === "Online" || systemStatus?.ollama_status === true },
        { name: "LanguageTool", online: true },
        { name: "SymSpell", online: true }
      ];

  return (
    <aside style={styles.sidebar}>
      <div>
        <div style={styles.brandRow}>
          <div style={styles.logoMark}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 2l9 5-9 5-9-5 9-5z" />
              <path d="M3 12l9 5 9-5" />
              <path d="M3 17l9 5 9-5" />
            </svg>
          </div>
          <div>
            <p style={styles.brandName}>AI Proofreader</p>
            <p style={styles.brandSub}>Document intelligence</p>
          </div>
        </div>

        <nav style={styles.nav}>
          {NAV_ITEMS.map((item) => {
            const storedDocId = localStorage.getItem("currentlyOpenDocId");
            let dest = item.key === "dashboard" ? "/" : item.key === "settings" ? "/settings" : `/${item.key}`;
            
            if (storedDocId && ["proofreading", "assistant", "analysis", "comparative", "reports"].includes(item.key)) {
              dest = `/documents/${storedDocId}?tab=${item.key}`;
            }
            return (
              <NavLink
                key={item.key}
                to={dest}
                style={({ isActive }) => ({
                  ...styles.navItem,
                  ...(isActive ? styles.navItemActive : {}),
                })}
              >
                {({ isActive }) => (
                  <>
                    <span style={{ color: isActive ? "var(--brand)" : "var(--text-secondary)", display: "flex", alignItems: "center" }}>
                      <Icon name={item.icon} />
                    </span>
                    {item.label}
                  </>
                )}
              </NavLink>
            );
          })}
        </nav>
      </div>

      <div style={styles.statusCard}>
        <div style={styles.statusHeader}>
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <rect x="2" y="4" width="20" height="14" rx="2" />
            <path d="M8 21h8M12 18v3" />
          </svg>
          <span>System status</span>
        </div>
        {statusList.map((s) => (
          <div key={s.name} style={styles.statusRow}>
            <span style={styles.statusName}>
              <span style={{ ...styles.dot, background: s.online ? "var(--green)" : "var(--red)" }} />
              {s.name}
            </span>
            <span style={{ ...styles.pill, ...(s.online ? styles.pillOnline : styles.pillOffline) }}>
              {s.online ? "Online" : "Offline"}
            </span>
          </div>
        ))}
      </div>
    </aside>
  );
}

const styles = {
  sidebar: {
    width: 220,
    background: "var(--bg-card)",
    borderRight: "1px solid var(--border)",
    padding: "20px 16px",
    display: "flex",
    flexDirection: "column",
    justifyContent: "space-between",
    flexShrink: 0,
  },
  brandRow: { display: "flex", alignItems: "center", gap: 10, padding: "0 4px 24px" },
  logoMark: {
    width: 34, height: 34, borderRadius: 10,
    background: "linear-gradient(135deg, var(--brand), var(--brand-dark))",
    display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
  },
  brandName: { margin: 0, fontSize: 14, fontWeight: 700, color: "var(--text-primary)" },
  brandSub: { margin: 0, fontSize: 11, color: "var(--text-muted)" },
  nav: { display: "flex", flexDirection: "column", gap: 2 },
  navItem: {
    display: "flex", alignItems: "center", gap: 10,
    background: "transparent", border: "none",
    padding: "9px 10px", borderRadius: 8,
    fontSize: 13.5, color: "var(--text-secondary)",
    textAlign: "left", width: "100%",
    cursor: "pointer",
  },
  navItemActive: {
    background: "var(--brand-light)",
    color: "var(--brand)",
    fontWeight: 600,
  },
  statusCard: {
    borderTop: "1px solid var(--border)", paddingTop: 16, marginTop: 16,
  },
  statusHeader: {
    display: "flex", alignItems: "center", gap: 6,
    fontSize: 12, fontWeight: 600, color: "var(--text-secondary)",
    marginBottom: 10,
  },
  statusRow: {
    display: "flex", alignItems: "center",
    justifyContent: "space-between",
    padding: "5px 0", fontSize: 12.5,
  },
  statusName: { display: "flex", alignItems: "center", gap: 6, color: "var(--text-primary)" },
  dot: { width: 6, height: 6, borderRadius: "50%", display: "inline-block" },
  pill: { fontSize: 10.5, fontWeight: 600, padding: "2px 8px", borderRadius: 999 },
  pillOnline: { background: "var(--green-light)", color: "var(--green)" },
  pillOffline: { background: "var(--red-light)", color: "var(--red)" },
};
