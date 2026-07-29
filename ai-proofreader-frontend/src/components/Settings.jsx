import React, { useState, useEffect } from "react";
import {
  fetchProtectedTerms,
  saveProtectedTerms,
  fetchPreferences,
  savePreferences,
  fetchSystemInfo
} from "../api";

export default function Settings() {
  // Theme state
  const [theme, setTheme] = useState(localStorage.getItem("theme") || "light");

  // Protected Terms states
  const [protectedTerms, setProtectedTerms] = useState([]);
  const [newTerm, setNewTerm] = useState("");

  // Preferences states
  const [preferences, setPreferences] = useState({
    ollama_host: "",
    ollama_model: "",
    languagetool_language: "",
    confidence_threshold: 40,
  });

  // Account settings state (stored in localStorage)
  const [account, setAccount] = useState({
    username: localStorage.getItem("settings_username") || "sanju_intern",
    email: localStorage.getItem("settings_email") || "sanju@internship.org",
    apiKey: localStorage.getItem("settings_apiKey") || "pk_live_51Pproofreader...",
  });

  // System info state
  const [systemInfo, setSystemInfo] = useState(null);
  const [loadingSys, setLoadingSys] = useState(true);

  // Status/Messages
  const [saving, setSaving] = useState(false);
  const [saveStatus, setSaveStatus] = useState(null); // { type: 'success' | 'error', message: string }
  const [activeSubTab, setActiveSubTab] = useState("general");

  // Load everything
  useEffect(() => {
    async function loadSettings() {
      try {
        const [terms, prefs, sys] = await Promise.all([
          fetchProtectedTerms(),
          fetchPreferences(),
          fetchSystemInfo(),
        ]);
        setProtectedTerms(terms);
        setPreferences(prefs);
        setSystemInfo(sys);
      } catch (e) {
        console.error("Error loading settings:", e);
      } finally {
        setLoadingSys(false);
      }
    }
    loadSettings();
  }, []);

  // Update theme on change
  const handleThemeChange = (newTheme) => {
    setTheme(newTheme);
    document.documentElement.setAttribute("data-theme", newTheme);
    localStorage.setItem("theme", newTheme);
  };

  const handleAddTerm = (e) => {
    e.preventDefault();
    const clean = newTerm.trim();
    if (!clean) return;
    if (protectedTerms.includes(clean)) {
      setNewTerm("");
      return;
    }
    setProtectedTerms([...protectedTerms, clean]);
    setNewTerm("");
  };

  const handleRemoveTerm = (termToRemove) => {
    setProtectedTerms(protectedTerms.filter((t) => t !== termToRemove));
  };

  const handleSaveAll = async () => {
    setSaving(true);
    setSaveStatus(null);
    try {
      // Save protected terms to backend
      await saveProtectedTerms(protectedTerms);
      // Save preferences to backend
      await savePreferences(preferences);

      // Save account details to localStorage
      localStorage.setItem("settings_username", account.username);
      localStorage.setItem("settings_email", account.email);
      localStorage.setItem("settings_apiKey", account.apiKey);

      setSaveStatus({ type: "success", message: "All settings saved successfully!" });
      setTimeout(() => setSaveStatus(null), 3000);
    } catch (err) {
      setSaveStatus({ type: "error", message: `Failed to save: ${err.message}` });
    } finally {
      setSaving(false);
    }
  };

  const handleReset = async () => {
    if (!window.confirm("Are you sure you want to reset settings to defaults?")) return;
    setSaving(true);
    try {
      const defaultPrefs = {
        ollama_host: "http://192.168.19.21:11434",
        ollama_model: "qwen2.5-coder:7b",
        languagetool_language: "en-US",
        confidence_threshold: 40,
      };
      const defaultTerms = [];
      const defaultAccount = {
        username: "sanju_intern",
        email: "sanju@internship.org",
        apiKey: "pk_live_51Pproofreader...",
      };

      setPreferences(defaultPrefs);
      setProtectedTerms(defaultTerms);
      setAccount(defaultAccount);
      handleThemeChange("light");

      await saveProtectedTerms(defaultTerms);
      await savePreferences(defaultPrefs);

      setSaveStatus({ type: "success", message: "Settings reset to defaults!" });
      setTimeout(() => setSaveStatus(null), 3000);
    } catch (err) {
      setSaveStatus({ type: "error", message: `Failed to reset: ${err.message}` });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={styles.container}>
      <div style={styles.header}>
        <div>
          <h1 style={styles.title}>Settings</h1>
          <p style={styles.subtitle}>Configure layout-aware proofreading preferences and integration keys</p>
        </div>
        <div style={styles.headerBtns}>
          <button style={styles.resetBtn} onClick={handleReset} disabled={saving}>
            Reset Defaults
          </button>
          <button style={styles.saveBtn} onClick={handleSaveAll} disabled={saving}>
            {saving ? "Saving..." : "Save changes"}
          </button>
        </div>
      </div>

      {saveStatus && (
        <div
          style={{
            ...styles.alert,
            background: saveStatus.type === "success" ? "var(--green-light)" : "var(--red-light)",
            color: saveStatus.type === "success" ? "var(--green)" : "var(--red)",
            border: `1px solid ${saveStatus.type === "success" ? "rgba(34,197,94,0.15)" : "rgba(225,85,85,0.15)"}`,
          }}
        >
          {saveStatus.message}
        </div>
      )}

      <div style={{ display: "flex", gap: 16, borderBottom: "1px solid var(--border)", marginBottom: 16 }}>
        <button
          onClick={() => setActiveSubTab("general")}
          style={{
            background: "none", border: "none", borderBottom: activeSubTab === "general" ? "2px solid var(--brand)" : "2px solid transparent",
            color: activeSubTab === "general" ? "var(--brand)" : "var(--text-secondary)",
            padding: "8px 12px", fontSize: 13.5, fontWeight: 700, cursor: "pointer", transition: "all 0.15s"
          }}
        >
          General Settings
        </button>
        <button
          onClick={() => setActiveSubTab("advanced")}
          style={{
            background: "none", border: "none", borderBottom: activeSubTab === "advanced" ? "2px solid var(--brand)" : "2px solid transparent",
            color: activeSubTab === "advanced" ? "var(--brand)" : "var(--text-secondary)",
            padding: "8px 12px", fontSize: 13.5, fontWeight: 700, cursor: "pointer", transition: "all 0.15s"
          }}
        >
          Advanced Settings
        </button>
      </div>

      {activeSubTab === "general" ? (
        <div style={styles.grid}>
          {/* General Tab: Left Column */}
          <div style={styles.leftCol}>
            {/* Card 1: Theme */}
            <div style={styles.card}>
              <h2 style={styles.cardTitle}>Appearance</h2>
              <p style={styles.cardDesc}>Choose how the interface looks on your screen</p>
              <div style={styles.themeGroup}>
                <button
                  style={{ ...styles.themeOption, ...(theme === "light" ? styles.themeOptionActive : {}) }}
                  onClick={() => handleThemeChange("light")}
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ marginRight: 6 }}>
                    <circle cx="12" cy="12" r="5" /><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42" />
                  </svg>
                  Light
                </button>
                <button
                  style={{ ...styles.themeOption, ...(theme === "dark" ? styles.themeOptionActive : {}) }}
                  onClick={() => handleThemeChange("dark")}
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ marginRight: 6 }}>
                    <path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z" />
                  </svg>
                  Dark
                </button>
              </div>
            </div>
          </div>

          {/* General Tab: Right Column */}
          <div style={styles.rightCol}>
            {/* Card 4: Account settings */}
            <div style={styles.card}>
              <h2 style={styles.cardTitle}>Account Credentials</h2>
              <p style={styles.cardDesc}>Manage your profile details and preferences</p>
              
              <div style={styles.formGroup}>
                <label style={styles.label}>Username</label>
                <input
                  type="text"
                  style={styles.input}
                  value={account.username}
                  onChange={(e) => setAccount({ ...account, username: e.target.value })}
                />
              </div>
              <div style={styles.formGroup}>
                <label style={styles.label}>Email Address</label>
                <input
                  type="email"
                  style={styles.input}
                  value={account.email}
                  onChange={(e) => setAccount({ ...account, email: e.target.value })}
                />
              </div>
            </div>
          </div>
        </div>
      ) : (
        <div style={styles.grid}>
          {/* Advanced Tab: Left Column */}
          <div style={styles.leftCol}>
            {/* Card 2: Engine Preferences */}
            <div style={styles.card}>
              <h2 style={styles.cardTitle}>Engine Configuration</h2>
              <p style={styles.cardDesc}>Tune the LanguageTool and Ollama LLM integration settings</p>
              
              <div style={styles.formGroup}>
                <label style={styles.label}>Ollama Host Hostname/IP</label>
                <input
                  type="text"
                  style={styles.input}
                  value={preferences.ollama_host}
                  onChange={(e) => setPreferences({ ...preferences, ollama_host: e.target.value })}
                  placeholder="http://192.168.19.21:11434"
                />
              </div>

              <div style={styles.formGroup}>
                <label style={styles.label}>Ollama LLM Model</label>
                <input
                  type="text"
                  style={styles.input}
                  value={preferences.ollama_model}
                  onChange={(e) => setPreferences({ ...preferences, ollama_model: e.target.value })}
                  placeholder="qwen2.5-coder:7b"
                />
              </div>

              <div style={styles.formGroup}>
                <label style={styles.label}>LanguageTool Code</label>
                <select
                  style={styles.input}
                  value={preferences.languagetool_language}
                  onChange={(e) => setPreferences({ ...preferences, languagetool_language: e.target.value })}
                >
                  <option value="en-US">English (US)</option>
                  <option value="en-GB">English (UK)</option>
                  <option value="de-DE">German (Germany)</option>
                  <option value="fr-FR">French (France)</option>
                </select>
              </div>

              <div style={styles.formGroup}>
                <label style={styles.label}>Confidence Filter: {preferences.confidence_threshold}%</label>
                <input
                  type="range"
                  min="0"
                  max="100"
                  step="5"
                  style={styles.rangeInput}
                  value={preferences.confidence_threshold}
                  onChange={(e) => setPreferences({ ...preferences, confidence_threshold: parseInt(e.target.value) })}
                />
                <span style={styles.rangeHint}>Only show corrections with confidence strictly above this threshold. (Must be at least 40% per rules)</span>
              </div>
            </div>
          </div>

          {/* Advanced Tab: Right Column */}
          <div style={styles.rightCol}>
            {/* Card 3: Protected Terms */}
            <div style={styles.card}>
              <h2 style={styles.cardTitle}>Global Protected Terms</h2>
              <p style={styles.cardDesc}>Protected terms will bypass downstream grammar and spelling checks.</p>
              
              <form onSubmit={handleAddTerm} style={styles.addTermRow}>
                <input
                  type="text"
                  style={styles.inputCompact}
                  value={newTerm}
                  onChange={(e) => setNewTerm(e.target.value)}
                  placeholder="Add term (e.g. Docling, spaCy)"
                />
                <button type="submit" style={styles.addBtn}>Add</button>
              </form>

              <div style={styles.termsBox}>
                {protectedTerms.length === 0 ? (
                  <span style={styles.emptyTerms}>No custom whitelisted terms added yet.</span>
                ) : (
                  protectedTerms.map((term) => (
                    <span key={term} style={styles.termTag}>
                      {term}
                      <button style={styles.deleteTagBtn} onClick={() => handleRemoveTerm(term)}>&times;</button>
                    </span>
                  ))
                )}
              </div>
            </div>

            {/* Card 4: API Key */}
            <div style={styles.card}>
              <h2 style={styles.cardTitle}>API Keys</h2>
              <p style={styles.cardDesc}>Manage platform API tokens for enterprise endpoints</p>
              <div style={styles.formGroup}>
                <label style={styles.label}>API Key</label>
                <input
                  type="password"
                  style={styles.input}
                  value={account.apiKey}
                  onChange={(e) => setAccount({ ...account, apiKey: e.target.value })}
                />
              </div>
            </div>

            {/* Card 5: System Diagnostics */}
            <div style={styles.card}>
              <h2 style={styles.cardTitle}>System Diagnostics</h2>
              <p style={styles.cardDesc}>Live technical parameters and hardware info</p>
              
              {loadingSys ? (
                <p style={styles.loadingSys}>Loading technical parameters...</p>
              ) : systemInfo ? (
                <div style={styles.diagGrid}>
                  <div style={styles.diagRow}>
                    <span style={styles.diagLabel}>Host Platform</span>
                    <span style={styles.diagValue}>{systemInfo.os} ({systemInfo.os_version?.substring(0, 10)})</span>
                  </div>
                  <div style={styles.diagRow}>
                    <span style={styles.diagLabel}>Python Environment</span>
                    <span style={styles.diagValue}>{systemInfo.python_version}</span>
                  </div>
                  <div style={styles.diagRow}>
                    <span style={styles.diagLabel}>Ollama Status</span>
                    <span style={{
                      ...styles.diagValue,
                      color: systemInfo.ollama_status === "Online" ? "var(--green)" : "var(--red)",
                      fontWeight: 650,
                    }}>
                      {systemInfo.ollama_status}
                    </span>
                  </div>
                  <div style={styles.diagRow}>
                    <span style={styles.diagLabel}>Active Ollama Model</span>
                    <span style={styles.diagValue}>{systemInfo.active_model}</span>
                  </div>
                </div>
              ) : (
                <p style={{ color: "var(--red)", fontSize: 12.5 }}>Failed to load system diagnostics.</p>
              )}
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
  headerBtns: { display: "flex", gap: 8 },
  saveBtn: {
    background: "var(--brand)", color: "white", border: "none", borderRadius: 8,
    padding: "8px 16px", fontSize: 13, fontWeight: 600, cursor: "pointer",
  },
  resetBtn: {
    background: "transparent", color: "var(--text-secondary)", border: "1px solid var(--border)",
    borderRadius: 8, padding: "8px 16px", fontSize: 13, fontWeight: 600, cursor: "pointer",
  },
  alert: { padding: "10px 16px", borderRadius: 8, fontSize: 13, fontWeight: 550 },
  grid: { display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 },
  leftCol: { display: "flex", flexDirection: "column", gap: 16 },
  rightCol: { display: "flex", flexDirection: "column", gap: 16 },
  card: {
    background: "var(--bg-card)", border: "1px solid var(--border)",
    borderRadius: "var(--radius-card)", padding: 16, boxShadow: "var(--shadow-card)",
  },
  cardTitle: { margin: 0, fontSize: 15, fontWeight: 700 },
  cardDesc: { margin: "4px 0 16px", fontSize: 12.5, color: "var(--text-muted)" },
  themeGroup: { display: "flex", gap: 8 },
  themeOption: {
    flex: 1, padding: "10px", borderRadius: 8, border: "1px solid var(--border)",
    background: "transparent", color: "var(--text-primary)", fontSize: 13, fontWeight: 600,
    display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer",
  },
  themeOptionActive: {
    borderColor: "var(--brand)", background: "var(--brand-light)", color: "var(--brand)",
  },
  formGroup: { display: "flex", flexDirection: "column", gap: 6, marginBottom: 12 },
  label: { fontSize: 12.5, fontWeight: 600, color: "var(--text-secondary)" },
  input: {
    background: "var(--bg-page)", border: "1px solid var(--border)", borderRadius: 8,
    padding: "8px 12px", fontSize: 13.5, color: "var(--text-primary)", outline: "none", width: "100%",
  },
  rangeInput: { width: "100%", accentColor: "var(--brand)", cursor: "pointer" },
  rangeHint: { fontSize: 11, color: "var(--text-muted)", marginTop: 4 },
  addTermRow: { display: "flex", gap: 8, marginBottom: 12 },
  inputCompact: {
    flex: 1, background: "var(--bg-page)", border: "1px solid var(--border)", borderRadius: 8,
    padding: "6px 12px", fontSize: 12.5, color: "var(--text-primary)", outline: "none",
  },
  addBtn: {
    background: "var(--brand-light)", color: "var(--brand)", border: "none", borderRadius: 8,
    padding: "6px 14px", fontSize: 12.5, fontWeight: 650, cursor: "pointer",
  },
  termsBox: {
    display: "flex", flexWrap: "wrap", gap: 6, padding: "8px 0",
    minHeight: 40, alignContent: "flex-start",
  },
  emptyTerms: { fontSize: 12.5, color: "var(--text-muted)", width: "100%", alignSelf: "center", textAlign: "center" },
  termTag: {
    display: "inline-flex", alignItems: "center", gap: 4, background: "var(--brand-light)",
    color: "var(--brand)", fontSize: 11.5, fontWeight: 600, padding: "2px 8px", borderRadius: 6,
  },
  deleteTagBtn: {
    background: "none", border: "none", color: "var(--brand)", fontSize: 13, fontWeight: "bold",
    cursor: "pointer", padding: 0, marginLeft: 2, display: "flex", alignItems: "center",
  },
  loadingSys: { fontSize: 12.5, color: "var(--text-muted)" },
  diagGrid: { display: "flex", flexDirection: "column", gap: 8 },
  diagRow: { display: "flex", justifyContent: "space-between", borderBottom: "1px solid var(--border)", paddingBottom: 6 },
  diagLabel: { fontSize: 12.5, color: "var(--text-secondary)" },
  diagValue: { fontSize: 12.5, fontWeight: 600, color: "var(--text-primary)" },
};
