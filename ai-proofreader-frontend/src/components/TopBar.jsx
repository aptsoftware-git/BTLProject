import React, { useState, useEffect, useRef } from "react";
import { fetchNotifications } from "../api";

export default function TopBar({ userInitial = "S" }) {
  const [theme, setTheme] = useState(localStorage.getItem("theme") || "light");
  const [notifOpen, setNotifOpen] = useState(false);
  const [avatarOpen, setAvatarOpen] = useState(false);
  const [notifications, setNotifications] = useState([]);
  const [hasNewNotifs, setHasNewNotifs] = useState(true);

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

  return (
    <header style={styles.bar}>
      <p style={styles.title}>Document intelligence platform</p>
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

        {/* Avatar */}
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
  );
}

const styles = {
  bar: {
    height: 56, background: "var(--bg-card)", borderBottom: "1px solid var(--border)",
    display: "flex", alignItems: "center", justifyContent: "space-between",
    padding: "0 24px", flexShrink: 0,
  },
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
