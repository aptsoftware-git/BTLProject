import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { fetchDocuments, deleteDocument } from "../api";

export default function History() {
  const navigate = useNavigate();
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Search, Filter, Sort and Paginate States
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [typeFilter, setTypeFilter] = useState("all");
  const [sortBy, setSortBy] = useState("date-desc");
  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 8;

  const loadHistory = async () => {
    setLoading(true);
    try {
      const data = await fetchDocuments();
      setDocuments(data);
      setError(null);
    } catch (err) {
      setError("Failed to load document history. Ensure backend is running.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadHistory();
  }, []);

  const handleDelete = async (id, filename) => {
    const confirmed = window.confirm(`Are you sure you want to delete "${filename}"? This will delete all generated logs and artifacts.`);
    if (!confirmed) return;

    try {
      await deleteDocument(id);
      loadHistory();
    } catch (e) {
      alert(`Delete failed: ${e.message}`);
    }
  };

  const handleDownloadReport = (id) => {
    window.open(`/api/download/${id}/report.json`, "_blank");
  };

  // 1. Filter documents
  const filteredDocs = documents.filter((doc) => {
    const matchSearch = doc.filename.toLowerCase().includes(search.toLowerCase());
    const matchStatus = statusFilter === "all" || doc.status === statusFilter;
    const matchType = typeFilter === "all" || doc.fileType === typeFilter;
    return matchSearch && matchStatus && matchType;
  });

  // 2. Sort documents
  const sortedDocs = [...filteredDocs].sort((a, b) => {
    if (sortBy === "date-desc") {
      return new Date(b.created_at || 0) - new Date(a.created_at || 0); // fallback or compare strings
    }
    if (sortBy === "date-asc") {
      return new Date(a.created_at || 0) - new Date(b.created_at || 0);
    }
    if (sortBy === "alpha-asc") {
      return a.filename.localeCompare(b.filename);
    }
    if (sortBy === "alpha-desc") {
      return b.filename.localeCompare(a.filename);
    }
    if (sortBy === "size-desc") {
      const parseSize = (s) => parseFloat(s || "0") * (s?.includes("MB") ? 1024 : 1);
      return parseSize(b.size) - parseSize(a.size);
    }
    if (sortBy === "size-asc") {
      const parseSize = (s) => parseFloat(s || "0") * (s?.includes("MB") ? 1024 : 1);
      return parseSize(a.size) - parseSize(b.size);
    }
    return 0;
  });

  // 3. Paginate
  const totalItems = sortedDocs.length;
  const totalPages = Math.ceil(totalItems / itemsPerPage) || 1;
  const startIndex = (currentPage - 1) * itemsPerPage;
  const paginatedDocs = sortedDocs.slice(startIndex, startIndex + itemsPerPage);

  // Reset page when filters change
  useEffect(() => {
    setCurrentPage(1);
  }, [search, statusFilter, typeFilter, sortBy]);

  const getStatusStyle = (status) => {
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
      {/* Header */}
      <div style={styles.header}>
        <div>
          <h1 style={styles.title}>History</h1>
          <p style={styles.subtitle}>Browse and manage all previous document processing results</p>
        </div>
        <button style={styles.refreshBtn} onClick={loadHistory}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" style={{ marginRight: 6 }}>
            <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 11-.57-8.38l5.67-5.67" />
          </svg>
          Refresh
        </button>
      </div>

      {/* Toolbar - Search, Filters, Sort */}
      <div style={styles.toolbar}>
        <div style={styles.searchCol}>
          <svg style={styles.searchIcon} width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
            <circle cx="11" cy="11" r="8" /><path d="M21 21l-4.3-4.3" />
          </svg>
          <input
            type="text"
            style={styles.searchInput}
            placeholder="Search by filename..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>

        <div style={styles.filterGroup}>
          <select
            style={styles.select}
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            <option value="all">All Statuses</option>
            <option value="completed">Completed</option>
            <option value="processing">Processing</option>
            <option value="pending">Pending</option>
            <option value="failed">Failed</option>
          </select>

          <select
            style={styles.select}
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
          >
            <option value="all">All Formats</option>
            <option value="PDF">PDF</option>
            <option value="DOCX">DOCX</option>
            <option value="TXT">TXT</option>
          </select>

          <select
            style={styles.select}
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value)}
          >
            <option value="date-desc">Newest First</option>
            <option value="date-asc">Oldest First</option>
            <option value="alpha-asc">A-Z Name</option>
            <option value="alpha-desc">Z-A Name</option>
            <option value="size-desc">Largest Size</option>
            <option value="size-asc">Smallest Size</option>
          </select>
        </div>
      </div>

      {/* Main Table */}
      {loading ? (
        <div style={styles.loadingBox}>
          <div style={styles.spinner} />
          <p style={{ marginTop: 12, fontSize: 13, color: "var(--text-secondary)" }}>Loading history records...</p>
        </div>
      ) : error ? (
        <div style={styles.errorBox}>
          <p style={{ color: "var(--red)", fontWeight: 600 }}>{error}</p>
          <button style={styles.retryBtn} onClick={loadHistory}>Retry</button>
        </div>
      ) : paginatedDocs.length === 0 ? (
        <div style={styles.emptyBox}>
          <p style={{ fontSize: 14, color: "var(--text-muted)", margin: 0 }}>No documents match the active filters.</p>
        </div>
      ) : (
        <div style={styles.tableCard}>
          <table style={styles.table}>
            <thead>
              <tr style={styles.thRow}>
                <th style={{ ...styles.th, width: 80 }}>Type</th>
                <th style={styles.th}>Filename</th>
                <th style={{ ...styles.th, width: 100 }}>Size</th>
                <th style={{ ...styles.th, width: 180 }}>Upload Date</th>
                <th style={{ ...styles.th, width: 120 }}>Status</th>
                <th style={{ ...styles.th, width: 220, textAlign: "right" }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {paginatedDocs.map((doc) => {
                const s = getStatusStyle(doc.status);
                return (
                  <tr key={doc.id} style={styles.tr}>
                    <td style={styles.td}>
                      <span style={styles.typeTag}>{doc.fileType || "PDF"}</span>
                    </td>
                    <td style={{ ...styles.td, fontWeight: 600 }}>{doc.filename}</td>
                    <td style={styles.td}>{doc.size}</td>
                    <td style={styles.td}>{doc.uploadedLabel}</td>
                    <td style={styles.td}>
                      <span style={{ ...styles.statusBadge, backgroundColor: s.bg, color: s.color }}>
                        {doc.status}
                      </span>
                    </td>
                    <td style={{ ...styles.td, textAlign: "right" }}>
                      <div style={styles.actionBtnRow}>
                        <button
                          style={styles.actionOpen}
                          onClick={() => navigate(`/documents/${doc.id}`)}
                        >
                          Workspace
                        </button>
                        {doc.status === "completed" && (
                          <button
                            style={styles.actionReport}
                            onClick={() => handleDownloadReport(doc.id)}
                            title="Download JSON Report"
                          >
                            Report
                          </button>
                        )}
                        <button
                          style={styles.actionDelete}
                          onClick={() => handleDelete(doc.id, doc.filename)}
                          title="Delete Document History"
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
          <div style={styles.pagination}>
            <span style={styles.pageText}>
              Showing <strong>{startIndex + 1}</strong> to{" "}
              <strong>{Math.min(startIndex + itemsPerPage, totalItems)}</strong> of{" "}
              <strong>{totalItems}</strong> items
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
  refreshBtn: {
    background: "var(--bg-card)", color: "var(--text-primary)", border: "1px solid var(--border)",
    borderRadius: 8, padding: "8px 12px", fontSize: 12.5, fontWeight: 600, display: "flex", alignItems: "center",
    cursor: "pointer", boxShadow: "var(--shadow-card)",
  },
  toolbar: {
    display: "flex", gap: 12, flexWrap: "wrap", justifyContent: "space-between",
  },
  searchCol: {
    position: "relative", flex: "1 1 300px", maxWidth: 400,
  },
  searchIcon: {
    position: "absolute", left: 12, top: "50%", transform: "translateY(-50%)", color: "var(--text-muted)",
  },
  searchInput: {
    width: "100%", background: "var(--bg-card)", border: "1px solid var(--border)",
    borderRadius: 8, padding: "8px 12px 8px 36px", fontSize: 13, color: "var(--text-primary)", outline: "none",
  },
  filterGroup: { display: "flex", gap: 8 },
  select: {
    background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 8,
    padding: "8px 12px", fontSize: 12.5, color: "var(--text-primary)", cursor: "pointer", outline: "none",
  },
  loadingBox: { display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", minHeight: 240 },
  spinner: {
    width: 24, height: 24, borderRadius: "50%",
    border: "3px solid var(--border)", borderTopColor: "var(--brand)",
    animation: "spin 0.8s linear infinite",
  },
  errorBox: { display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: 24, background: "var(--bg-card)", borderRadius: 12, border: "1px solid var(--border)" },
  retryBtn: { marginTop: 8, background: "var(--brand)", color: "white", border: "none", borderRadius: 8, padding: "6px 12px", fontSize: 12, cursor: "pointer" },
  emptyBox: { display: "flex", alignItems: "center", justifyContent: "center", minHeight: 180, background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 12 },
  tableCard: {
    background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: "var(--radius-card)",
    boxShadow: "var(--shadow-card)", overflow: "hidden",
  },
  table: { width: "100%", borderCollapse: "collapse", borderSpacing: 0, textAlign: "left" },
  thRow: { background: "var(--bg-page)", borderBottom: "1px solid var(--border)" },
  th: { padding: "12px 16px", fontSize: 12, fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: 0.5 },
  tr: { borderBottom: "1px solid var(--border)", transition: "background 0.2s" },
  td: { padding: "12px 16px", fontSize: 13, color: "var(--text-primary)" },
  typeTag: {
    fontSize: 10, fontWeight: 700, color: "var(--brand)", background: "var(--brand-light)",
    padding: "3px 6px", borderRadius: 4, textTransform: "uppercase",
  },
  statusBadge: {
    fontSize: 10.5, fontWeight: 650, padding: "2px 8px", borderRadius: 999, textTransform: "capitalize",
    display: "inline-block",
  },
  actionBtnRow: { display: "flex", gap: 6, justifyContent: "flex-end" },
  actionOpen: {
    background: "var(--brand-light)", color: "var(--brand)", border: "none", borderRadius: 6,
    padding: "5px 10px", fontSize: 11.5, fontWeight: 650, cursor: "pointer",
  },
  actionReport: {
    background: "transparent", color: "var(--text-secondary)", border: "1px solid var(--border)",
    borderRadius: 6, padding: "5px 10px", fontSize: 11.5, fontWeight: 600, cursor: "pointer",
  },
  actionDelete: {
    background: "transparent", color: "var(--red)", border: "1px solid rgba(225,85,85,0.15)",
    borderRadius: 6, padding: "5px 10px", fontSize: 11.5, fontWeight: 600, cursor: "pointer",
  },
  pagination: {
    display: "flex", justifyContent: "space-between", alignItems: "center", padding: "12px 16px",
    background: "var(--bg-page)", borderTop: "1px solid var(--border)",
  },
  pageText: { fontSize: 12.5, color: "var(--text-secondary)" },
  paginationBtns: { display: "flex", gap: 6 },
  pageBtn: {
    background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 6,
    padding: "5px 10px", fontSize: 12, color: "var(--text-primary)", fontWeight: 600, cursor: "pointer",
  },
  pageBtnDisabled: { opacity: 0.5, cursor: "not-allowed" },
};
