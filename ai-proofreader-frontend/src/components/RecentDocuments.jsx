import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { deleteDocument } from "../api";

export default function RecentDocuments({ documents = [], onRefresh }) {
  const navigate = useNavigate();
  const [search, setSearch] = useState("");
  const [sortBy, setSortBy] = useState("recent");
  const [currentPage, setCurrentPage] = useState(1);
  const [docDetails, setDocDetails] = useState({});
  const itemsPerPage = 8;

  // Fetch document details in parallel to load the quality scores/assessments
  useEffect(() => {
    async function loadAllDetails() {
      const detailsMap = {};
      const completedDocs = documents.filter(d => d.status === "completed");
      
      await Promise.all(
        completedDocs.map(async (doc) => {
          try {
            const res = await fetch(`/api/documents/${doc.id}`);
            if (res.ok) {
              const data = await res.json();
              detailsMap[doc.id] = data;
            }
          } catch (e) {
            console.error("Error loading document details:", e);
          }
        })
      );
      setDocDetails(detailsMap);
    }
    
    if (documents && documents.length > 0) {
      loadAllDetails();
    }
  }, [documents]);

  const handleOpen = (id) => {
    navigate(`/documents/${id}?tab=proofreading`);
  };

  const handleDelete = async (e, id, filename) => {
    e.stopPropagation();
    const confirmed = window.confirm(`Are you sure you want to delete "${filename}"? This action cannot be undone.`);
    if (!confirmed) return;

    try {
      await deleteDocument(id);
      onRefresh?.();
    } catch (err) {
      alert(`Failed to delete document: ${err.message}`);
    }
  };

  const getAssessmentText = (doc) => {
    if (doc.status === "failed") return "Failed";
    if (doc.status === "processing" || doc.status === "pending") return "In Progress";
    if (doc.status !== "completed") return "Pending";
    
    const detail = docDetails[doc.id];
    if (!detail || !detail.statistics) return "Analyzing...";
    const total = detail.statistics.total_issues || 0;
    if (total === 0) return "Suitable for publication";
    if (total <= 10) return "Needs attention";
    return "Significant revisions recommended";
  };

  const getAssessmentStyle = (text) => {
    if (text === "Suitable for publication") return { color: "var(--green)", fontWeight: 650 };
    if (text === "Needs attention") return { color: "var(--amber)", fontWeight: 650 };
    if (text === "Significant revisions recommended") return { color: "var(--red)", fontWeight: 650 };
    return { color: "var(--text-secondary)" };
  };

  // 1. Filter documents
  const filteredDocs = documents.filter((doc) => {
    return doc.filename.toLowerCase().includes(search.toLowerCase());
  });

  // 2. Sort documents
  const sortedDocs = [...filteredDocs].sort((a, b) => {
    if (sortBy === "recent") {
      return 0; // Maintain default API order (which is newest first)
    }
    if (sortBy === "name") {
      return a.filename.localeCompare(b.filename);
    }
    if (sortBy === "assessment") {
      const getIssuesCount = (doc) => {
        if (doc.status !== "completed") return 999;
        const detail = docDetails[doc.id];
        return detail?.statistics?.total_issues ?? 0;
      };
      return getIssuesCount(b) - getIssuesCount(a);
    }
    if (sortBy === "status") {
      return a.status.localeCompare(b.status);
    }
    return 0;
  });

  // 3. Paginate
  const totalItems = sortedDocs.length;
  const totalPages = Math.ceil(totalItems / itemsPerPage) || 1;
  const startIndex = (currentPage - 1) * itemsPerPage;
  const paginatedDocs = sortedDocs.slice(startIndex, startIndex + itemsPerPage);

  const getStatusBadgeStyle = (status) => {
    switch (status) {
      case "completed":
        return { bg: "var(--green-light)", color: "var(--green)" };
      case "processing":
      case "pending":
        return { bg: "var(--amber-light)", color: "var(--amber)" };
      case "failed":
        return { bg: "var(--red-light)", color: "var(--red)" };
      default:
        return { bg: "var(--border)", color: "var(--text-secondary)" };
    }
  };

  return (
    <div style={styles.container}>
      <div style={styles.header}>
        <h2 style={styles.sectionTitle}>Recent Documents</h2>
        <div style={styles.actions}>
          <div style={styles.searchWrapper}>
            <svg style={styles.searchIcon} width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <circle cx="11" cy="11" r="8" /><path d="M21 21l-4.3-4.3" />
            </svg>
            <input
              type="text"
              style={styles.searchInput}
              placeholder="Search documents..."
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setCurrentPage(1);
              }}
            />
          </div>
          <select
            style={styles.sortSelect}
            value={sortBy}
            onChange={(e) => {
              setSortBy(e.target.value);
              setCurrentPage(1);
            }}
          >
            <option value="recent">Sort by: Recent</option>
            <option value="name">Sort by: Name</option>
            <option value="assessment">Sort by: Assessment</option>
            <option value="status">Sort by: Status</option>
          </select>
        </div>
      </div>

      {totalItems === 0 ? (
        <div style={styles.emptyState}>
          <p style={{ margin: 0, color: "var(--text-muted)", fontSize: 13.5 }}>
            {search ? "No documents match your search query." : "No documents uploaded yet."}
          </p>
        </div>
      ) : (
        <div style={styles.tableWrapper}>
          <table style={styles.table}>
            <thead>
              <tr style={styles.thRow}>
                <th style={styles.th}>Document Name</th>
                <th style={{ ...styles.th, width: 100 }}>Pages</th>
                <th style={{ ...styles.th, width: 150 }}>Upload Date</th>
                <th style={{ ...styles.th, width: 120 }}>Status</th>
                <th style={{ ...styles.th, width: 220 }}>Detailed Status</th>
                <th style={{ ...styles.th, width: 260, textAlign: "right" }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {paginatedDocs.map((doc) => {
                const s = getStatusBadgeStyle(doc.status);
                const assessmentText = getAssessmentText(doc);
                const aStyle = getAssessmentStyle(assessmentText);
                return (
                  <tr key={doc.id} style={styles.tr} onClick={() => handleOpen(doc.id)}>
                    <td style={{ ...styles.td, fontWeight: 600, color: "var(--text-primary)" }}>
                      {doc.filename}
                    </td>
                    <td style={{ ...styles.td, color: "var(--text-secondary)" }}>
                      {doc.total_pages || doc.pages || 1}
                    </td>
                    <td style={{ ...styles.td, color: "var(--text-secondary)" }}>
                      {doc.uploadedLabel}
                    </td>
                    <td style={styles.td}>
                      <span style={{ ...styles.badge, backgroundColor: s.bg, color: s.color }}>
                        {doc.status === "completed" ? "Ready" : doc.status === "processing" ? "Reviewing" : doc.status}
                      </span>
                    </td>
                    <td style={{ ...styles.td, ...aStyle }}>
                      {assessmentText}
                    </td>
                    <td style={{ ...styles.td, textAlign: "right" }} onClick={(e) => e.stopPropagation()}>
                      <div style={styles.btnRow}>
                        <button
                          className="btn-action-link"
                          onClick={() => navigate(`/documents/${doc.id}?tab=proofreading`)}
                        >
                          Proofread
                        </button>
                        <button
                          className="btn-action-link"
                          onClick={() => navigate(`/documents/${doc.id}?tab=assistant`)}
                        >
                          Ask AI
                        </button>
                        <button
                          className="btn-action-link"
                          onClick={() => navigate(`/documents/${doc.id}?tab=reports`)}
                        >
                          Reports
                        </button>
                        <button
                          className="btn-delete-link"
                          onClick={(e) => handleDelete(e, doc.id, doc.filename)}
                          title="Delete Record"
                        >
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>

          {/* Pagination Footer */}
          {totalPages > 1 && (
            <div style={styles.pagination}>
              <span style={styles.paginationText}>
                Page <strong>{currentPage}</strong> of <strong>{totalPages}</strong> ({totalItems} items)
              </span>
              <div style={styles.paginationBtns}>
                <button
                  style={{ ...styles.pageBtn, ...(currentPage === 1 ? styles.pageBtnDisabled : {}) }}
                  onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                  disabled={currentPage === 1}
                >
                  Previous
                </button>
                <button
                  style={{ ...styles.pageBtn, ...(currentPage === totalPages ? styles.pageBtnDisabled : {}) }}
                  onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                  disabled={currentPage === totalPages}
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

const styles = {
  container: { display: "flex", flexDirection: "column", gap: 12, marginTop: 8 },
  header: { display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12, marginBottom: 4 },
  sectionTitle: { margin: 0, fontSize: 14, fontWeight: 700, color: "var(--text-primary)" },
  actions: { display: "flex", alignItems: "center", gap: 8 },
  searchWrapper: { position: "relative" },
  searchIcon: { position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)", color: "var(--text-muted)" },
  searchInput: {
    background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 6,
    padding: "6px 10px 6px 30px", fontSize: 12.5, width: 200, outline: "none", color: "var(--text-primary)",
    transition: "border-color 0.15s",
  },
  sortSelect: {
    background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 6,
    padding: "6px 10px", fontSize: 12.5, color: "var(--text-primary)", cursor: "pointer", outline: "none",
  },
  emptyState: {
    padding: "36px 16px", background: "var(--bg-card)", border: "1px dashed var(--border)",
    borderRadius: 8, textAlign: "center",
  },
  tableWrapper: {
    background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 8,
    overflow: "hidden",
  },
  table: { width: "100%", borderCollapse: "collapse", borderSpacing: 0, textAlign: "left" },
  thRow: { background: "var(--bg-page)", borderBottom: "1px solid var(--border)" },
  th: { padding: "10px 16px", fontSize: 11, fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: 0.5 },
  tr: { borderBottom: "1px solid var(--border)", cursor: "pointer", transition: "background-color 0.15s" },
  td: { padding: "11px 16px", fontSize: 13 },
  typeTag: {
    fontSize: 9.5, fontWeight: 750, color: "var(--brand)", background: "var(--brand-light)",
    padding: "2px 5px", borderRadius: 4, textTransform: "uppercase",
  },
  badge: {
    fontSize: 10, fontWeight: 700, padding: "2px 8px", borderRadius: 999, textTransform: "capitalize",
    display: "inline-block",
  },
  btnRow: { display: "flex", gap: 6, justifyContent: "flex-end" },
  openBtn: {
    background: "var(--brand-light)", color: "var(--brand)", border: "none", borderRadius: 4,
    padding: "4px 10px", fontSize: 11.5, fontWeight: 650, cursor: "pointer", transition: "opacity 0.15s",
  },
  deleteBtn: {
    background: "transparent", color: "var(--red)", border: "1px solid rgba(225,85,85,0.12)", borderRadius: 4,
    padding: "4px 10px", fontSize: 11.5, fontWeight: 600, cursor: "pointer", transition: "all 0.15s",
  },
  pagination: {
    display: "flex", justifyContent: "space-between", alignItems: "center", padding: "10px 16px",
    background: "var(--bg-page)", borderTop: "1px solid var(--border)",
  },
  paginationText: { fontSize: 12, color: "var(--text-secondary)" },
  paginationBtns: { display: "flex", gap: 6 },
  pageBtn: {
    background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 4,
    padding: "4px 8px", fontSize: 11.5, color: "var(--text-primary)", fontWeight: 600, cursor: "pointer",
  },
  pageBtnDisabled: { opacity: 0.5, cursor: "not-allowed" },
};
