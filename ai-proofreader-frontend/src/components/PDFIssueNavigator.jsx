import React from "react";

/**
 * PDFIssueNavigator Component
 * Individual issue card item in the sidebar list.
 * Highlights active selection, displays issue metadata, and provides quick Accept / Reject triggers.
 */
export default function PDFIssueNavigator({
  issue,
  index,
  isSelected,
  isAccepted,
  isRejected,
  onSelect,
  onAccept,
  onReject
}) {
  if (!issue) return null;

  const iid = issue.issue_id || `issue_${index + 1}`;
  const issueType = (issue.issue_type || "grammar").toLowerCase();

  const getTypeStyle = (t) => {
    if (t.includes("spell")) return { label: "Spelling", bg: "#fef08a", color: "#854d0e", border: "#eab308" };
    if (t.includes("gramm") || t.includes("tense")) return { label: "Grammar", bg: "#fecaca", color: "#991b1b", border: "#ef4444" };
    if (t.includes("style")) return { label: "Style", bg: "#bfdbfe", color: "#1e40af", border: "#3b82f6" };
    if (t.includes("punct")) return { label: "Punctuation", bg: "#fed7aa", color: "#9a3412", border: "#f97316" };
    return { label: "Quality", bg: "#f1f5f9", color: "#334155", border: "#cbd5e1" };
  };

  const typeInfo = getTypeStyle(issueType);
  const pageNum = issue.page || issue.page_number || 1;

  const cardStyle = {
    padding: "12px 14px",
    borderRadius: "8px",
    background: isSelected ? "var(--bg-hover, #f8fafc)" : "var(--bg-card, #ffffff)",
    border: isSelected ? `1.5px solid ${typeInfo.border}` : "1px solid var(--border, #e2e8f0)",
    boxShadow: isSelected ? "0 4px 12px rgba(0, 0, 0, 0.05)" : "none",
    cursor: "pointer",
    transition: "all 0.15s ease-in-out",
    opacity: (isAccepted || isRejected) ? 0.5 : 1,
    position: "relative"
  };

  return (
    <div
      id={`sidebar-issue-item-${iid}`}
      style={cardStyle}
      onClick={() => onSelect(iid)}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
        <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
          <span
            style={{
              fontSize: "11px",
              fontWeight: 700,
              padding: "2px 7px",
              borderRadius: "4px",
              background: typeInfo.bg,
              color: typeInfo.color
            }}
          >
            {typeInfo.label}
          </span>
          <span style={{ fontSize: "11px", color: "var(--text-secondary, #64748b)", fontWeight: 600 }}>
            Page {pageNum}
          </span>
        </div>

        {/* Status indicator if decided */}
        {isAccepted && (
          <span style={{ fontSize: "11px", color: "#166534", fontWeight: 700, background: "#dcfce7", padding: "1px 6px", borderRadius: "4px" }}>
            ✓ Accepted
          </span>
        )}
        {isRejected && (
          <span style={{ fontSize: "11px", color: "#991b1b", fontWeight: 700, background: "#fee2e2", padding: "1px 6px", borderRadius: "4px" }}>
            ✕ Rejected
          </span>
        )}
      </div>

      <div style={{ fontSize: "13px", lineHeight: "1.4", margin: "6px 0" }}>
        <span style={{ textDecoration: "line-through", color: "#ef4444", background: "#fee2e2", padding: "1px 4px", borderRadius: "3px" }}>
          {issue.original_text}
        </span>
        <span style={{ margin: "0 6px", color: "var(--text-secondary)" }}>→</span>
        <span style={{ color: "#16a34a", background: "#dcfce7", fontWeight: 600, padding: "1px 4px", borderRadius: "3px" }}>
          {issue.suggested_text}
        </span>
      </div>

      {issue.reason && (
        <div style={{ fontSize: "11.5px", color: "var(--text-secondary, #64748b)", marginTop: 4, fontStyle: "italic" }}>
          {issue.reason}
        </div>
      )}

      {/* Quick Action buttons */}
      {!isAccepted && !isRejected && (
        <div style={{ display: "flex", gap: 6, marginTop: 8, justifyContent: "flex-end" }}>
          <button
            title="Accept fix"
            style={{
              padding: "3px 10px",
              fontSize: "11px",
              fontWeight: 700,
              background: "#166534",
              color: "#ffffff",
              border: "none",
              borderRadius: "4px",
              cursor: "pointer"
            }}
            onClick={(e) => {
              e.stopPropagation();
              onAccept(iid);
            }}
          >
            Accept ✓
          </button>
          <button
            title="Reject fix"
            style={{
              padding: "3px 10px",
              fontSize: "11px",
              fontWeight: 700,
              background: "#f1f5f9",
              color: "#64748b",
              border: "1px solid #cbd5e1",
              borderRadius: "4px",
              cursor: "pointer"
            }}
            onClick={(e) => {
              e.stopPropagation();
              onReject(iid);
            }}
          >
            Reject ✕
          </button>
        </div>
      )}
    </div>
  );
}
