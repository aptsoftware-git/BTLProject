import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { fetchDocuments } from "../api";
import UploadZone from "./UploadZone";

export default function ProofreadingEmptyState() {
  const navigate = useNavigate();
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);

  const loadDocs = async () => {
    setLoading(true);
    try {
      const data = await fetchDocuments();
      setDocuments(data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDocs();
  }, []);

  const completedDocs = documents.filter((d) => d.status === "completed" || d.status === "processing" || d.status === "pending");

  return (
    <div style={styles.container}>
      <h1 style={styles.title}>Proofreading Workspace</h1>
      <p style={styles.subtitle}>Open an analyzed document to review and correct detected spelling/grammar errors</p>

      <div style={styles.grid}>
        {/* Left Col: Upload New */}
        <div style={styles.card}>
          <h2 style={styles.sectionTitle}>Start New Analysis</h2>
          <p style={styles.sectionDesc}>Upload a PDF, DOCX, or TXT file to launch our layout-aware validation checks.</p>
          <UploadZone onUploaded={() => navigate("/")} />
        </div>

        {/* Right Col: Pick Existing */}
        <div style={styles.card}>
          <h2 style={styles.sectionTitle}>Continue Proofreading</h2>
          <p style={styles.sectionDesc}>Choose an active document to load the interactive markup editor.</p>

          {loading ? (
            <div style={styles.loadingBox}>
              <div style={styles.spinner} />
            </div>
          ) : completedDocs.length === 0 ? (
            <div style={styles.emptyBox}>
              <p style={{ fontSize: 13.5, color: "var(--text-muted)", margin: 0 }}>No documents analyzed yet.</p>
            </div>
          ) : (
            <div style={styles.list}>
              {completedDocs.map((doc) => (
                <div
                  key={doc.id}
                  style={styles.row}
                  onClick={() => navigate(`/documents/${doc.id}`)}
                >
                  <div style={styles.rowInfo}>
                    <p style={styles.filename}>{doc.filename}</p>
                    <p style={styles.meta}>{doc.uploadedLabel} · {doc.size}</p>
                  </div>
                  <span
                    style={{
                      ...styles.badge,
                      backgroundColor: doc.status === "completed" ? "var(--green-light)" : "var(--amber-light)",
                      color: doc.status === "completed" ? "var(--green)" : "var(--amber)",
                    }}
                  >
                    {doc.status}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

const styles = {
  container: { display: "flex", flexDirection: "column", gap: 16, textAlign: "left" },
  title: { margin: 0, fontSize: 24, fontWeight: 700 },
  subtitle: { margin: "4px 0 20px", fontSize: 13, color: "var(--text-secondary)" },
  grid: { display: "grid", gridTemplateColumns: "1.2fr 1fr", gap: 16 },
  card: {
    background: "var(--bg-card)", border: "1px solid var(--border)",
    borderRadius: "var(--radius-card)", padding: 20, boxShadow: "var(--shadow-card)",
    display: "flex", flexDirection: "column",
  },
  sectionTitle: { margin: 0, fontSize: 16, fontWeight: 700 },
  sectionDesc: { margin: "4px 0 20px", fontSize: 13, color: "var(--text-muted)" },
  loadingBox: { display: "flex", justifyContent: "center", alignItems: "center", minHeight: 120 },
  spinner: {
    width: 20, height: 20, borderRadius: "50%",
    border: "2px solid var(--border)", borderTopColor: "var(--brand)",
    animation: "spin 0.8s linear infinite",
  },
  emptyBox: { display: "flex", alignItems: "center", justifyContent: "center", minHeight: 160, background: "var(--bg-page)", border: "1px dashed var(--border)", borderRadius: 12 },
  list: { display: "flex", flexDirection: "column", gap: 8, maxHeight: 300, overflowY: "auto" },
  row: {
    display: "flex", justifyContent: "space-between", alignItems: "center", padding: "10px 12px",
    background: "var(--bg-page)", border: "1px solid var(--border)", borderRadius: 8, cursor: "pointer",
    transition: "transform 0.15s, border-color 0.15s",
  },
  rowInfo: { minWidth: 0, marginRight: 12 },
  filename: { margin: 0, fontSize: 13, fontWeight: 650, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" },
  meta: { margin: "2px 0 0", fontSize: 11, color: "var(--text-muted)" },
  badge: { fontSize: 10, fontWeight: 700, padding: "2px 8px", borderRadius: 999, textTransform: "uppercase" },
};
