import React from "react";

const THEMES = {
  purple: { bg: "var(--brand-light)", fg: "var(--brand)" },
  amber: { bg: "var(--amber-light)", fg: "var(--amber)" },
  green: { bg: "var(--green-light)", fg: "var(--green)" },
  blue: { bg: "var(--blue-light)", fg: "var(--blue-icon)" },
};

export default function StatCard({ icon, value, label, sublabel, theme = "purple" }) {
  const t = THEMES[theme] || THEMES.purple;
  return (
    <div style={styles.card}>
      <div style={{ ...styles.iconWrap, background: t.bg, color: t.fg }}>{icon}</div>
      <div>
        <p style={styles.value}>{value}</p>
        <p style={styles.label}>{label}</p>
        <p style={styles.sublabel}>{sublabel}</p>
      </div>
    </div>
  );
}

const styles = {
  card: {
    display: "flex", alignItems: "center", gap: 12,
    background: "var(--bg-card)", border: "1px solid var(--border)",
    borderRadius: "var(--radius-card)", padding: "14px 16px",
    boxShadow: "var(--shadow-card)",
  },
  iconWrap: {
    width: 40, height: 40, borderRadius: "50%",
    display: "flex", alignItems: "center", justifyContent: "center",
    flexShrink: 0,
  },
  value: { margin: 0, fontSize: 20, fontWeight: 700, color: "var(--text-primary)" },
  label: { margin: "2px 0 0", fontSize: 12.5, fontWeight: 600, color: "var(--text-primary)" },
  sublabel: { margin: "1px 0 0", fontSize: 11, color: "var(--text-muted)" },
};
