import React, { useState, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { deleteDocument } from "../api";

function statusPill(status) {
  const map = {
    completed: { bg: "var(--green-light)", fg: "var(--green)", label: "Completed" },
    processing: { bg: "var(--amber-light)", fg: "var(--amber)", label: "Processing" },
    pending: { bg: "var(--amber-light)", fg: "var(--amber)", label: "Pending" },
    failed: { bg: "var(--red-light)", fg: "var(--red)", label: "Failed" },
  };
  const s = map[status] || map.completed;
  return (
    <span style={{ ...styles.pill, background: s.bg, color: s.fg }}>
      {status === "completed" && (
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
          <path d="M20 6L9 17l-5-5" />
        </svg>
      )}
      {s.label}
    </span>
  );
}

export default function RecentDocuments({ documents = [], onRefresh, limit = 5, isFullList = false }) {
  const navigate = useNavigate();
  const [activeMenuId, setActiveMenuId] = useState(null);
  const dropdownRef = useRef(null);

  const displayDocs = isFullList ? documents : documents.slice(0, limit);

  // Close menu on click outside or escape
  useEffect(() => {
    function handleClickOutside(event) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setActiveMenuId(null);
      }
    }
    function handleKeyDown(event) {
      if (event.key === "Escape") {
        setActiveMenuId(null);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, []);

  const handleOpen = (id) => {
    navigate(`/documents/${id}`);
  };

  const handleDownload = (id) => {
    // Navigate/download directly from the API endpoint
    window.open(`/api/download/${id}/corrected_document.html`, "_blank");
    setActiveMenuId(null);
  };

  const handleDelete = async (id, filename) => {
    setActiveMenuId(null);
    const confirmed = window.confirm(`Are you sure you want to delete the document "${filename}"? This action cannot be undone.`);
    if (!confirmed) return;

    try {
      await deleteDocument(id);
      alert("Document deleted successfully.");
      onRefresh?.();
    } catch (e) {
      alert(`Failed to delete document: ${e.message}`);
    }
  };

  const toggleMenu = (e, id) => {
    e.stopPropagation();
    setActiveMenuId(activeMenuId === id ? null : id);
  };

  return (
    <div style={styles.card}>
      <div style={styles.header}>
        <p style={styles.title}>{isFullList ? "All documents" : "Recent documents"}</p>
        {!isFullList && (
          <button style={styles.viewAll} onClick={() => navigate("/documents")}>
            View all
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M9 18l6-6-6-6" />
            </svg>
          </button>
        )}
      </div>

      {displayDocs.length === 0 ? (
        <p style={styles.empty}>No documents yet — upload one to get started.</p>
      ) : (
        displayDocs.map((doc) => (
          <div key={doc.id} style={styles.row} onClick={() => handleOpen(doc.id)}>
            <span style={styles.fileTag}>{doc.fileType || "PDF"}</span>
            <div style={styles.rowText}>
              <p style={styles.filename}>{doc.filename}</p>
              <p style={styles.meta}>{doc.uploadedLabel} · {doc.size}</p>
            </div>
            {statusPill(doc.status)}
            
            {/* Actions Menu */}
            <div style={{ position: "relative" }} ref={activeMenuId === doc.id ? dropdownRef : null}>
              <button 
                style={styles.moreBtn} 
                onClick={(e) => toggleMenu(e, doc.id)} 
                aria-label="More options"
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                  <circle cx="12" cy="5" r="1" /><circle cx="12" cy="12" r="1" /><circle cx="12" cy="19" r="1" />
                </svg>
              </button>

              {activeMenuId === doc.id && (
                <div style={styles.dropdown}>
                  <button style={styles.menuItem} onClick={() => handleOpen(doc.id)}>Open workspace</button>
                  {doc.status === "completed" && (
                    <button style={styles.menuItem} onClick={() => handleDownload(doc.id)}>Download corrected</button>
                  )}
                  <hr style={styles.hr} />
                  <button style={{ ...styles.menuItem, color: "var(--red)" }} onClick={() => handleDelete(doc.id, doc.filename)}>Delete</button>
                </div>
              )}
            </div>
          </div>
        ))
      )}
    </div>
  );
}

const styles = {
  card: {
    background: "var(--bg-card)", border: "1px solid var(--border)",
    borderRadius: "var(--radius-card)", padding: 16,
    boxShadow: "var(--shadow-card)",
    textAlign: "left",
  },
  header: { display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 },
  title: { margin: 0, fontSize: 14.5, fontWeight: 700 },
  viewAll: {
    display: "flex", alignItems: "center", gap: 4,
    background: "none", border: "none", color: "var(--brand)",
    fontSize: 12.5, fontWeight: 600, cursor: "pointer",
  },
  empty: { fontSize: 13, color: "var(--text-muted)", padding: "20px 4px" },
  row: {
    display: "flex", alignItems: "center", gap: 12,
    padding: "12px 8px", borderTop: "1px solid var(--border)",
    cursor: "pointer",
    position: "relative",
  },
  fileTag: {
    fontSize: 10, fontWeight: 700, color: "var(--brand)",
    background: "var(--brand-light)", padding: "3px 6px", borderRadius: 6,
  },
  rowText: { flex: 1, minWidth: 0 },
  filename: { margin: 0, fontSize: 13.5, fontWeight: 600, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" },
  meta: { margin: "2px 0 0", fontSize: 11.5, color: "var(--text-muted)" },
  pill: {
    display: "flex", alignItems: "center", gap: 4,
    fontSize: 11.5, fontWeight: 600, padding: "4px 10px", borderRadius: 999,
    whiteSpace: "nowrap",
  },
  moreBtn: { background: "none", border: "none", color: "var(--text-muted)", padding: 4, cursor: "pointer" },
  dropdown: {
    position: "absolute", top: 24, right: 0,
    width: 160, background: "var(--bg-card)", border: "1px solid var(--border)",
    borderRadius: 8, boxShadow: "0 2px 8px rgba(0, 0, 0, 0.1)", zIndex: 100,
    display: "flex", flexDirection: "column", padding: "4px 0",
  },
  menuItem: {
    background: "none", border: "none", textAlign: "left",
    padding: "8px 12px", fontSize: 12.5, color: "var(--text-primary)",
    cursor: "pointer", width: "100%",
  },
  hr: { margin: "2px 0", border: "none", borderTop: "1px solid var(--border)" },
};
