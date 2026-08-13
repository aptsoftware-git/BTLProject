import React from "react";

const SEVERITY_COLORS = {
  low: { color: "#166534", background: "#dcfce7" },
  medium: { color: "#92400e", background: "#fef3c7" },
  high: { color: "#9a3412", background: "#ffedd5" },
  critical: { color: "#991b1b", background: "#fee2e2" },
};

/**
 * FindingPopover
 * -----------------
 * Click-to-inspect card for a single highlighted finding on the original
 * PDF: Category / Original / Suggested / Reason / Severity + Accept/Reject.
 * Positioned by the caller (absolute, near the clicked highlight box);
 * this component only renders content + actions.
 */
export default function FindingPopover({ finding, style, onAccept, onReject, onClose }) {
  if (!finding) return null;
  const severityStyle = SEVERITY_COLORS[String(finding.severity || "medium").toLowerCase()] || SEVERITY_COLORS.medium;
  const isDone = finding.status === "accepted" || finding.status === "rejected";

  const handleClose = (e) => {
    if (e) {
      e.stopPropagation();
      e.preventDefault();
    }
    if (onClose) {
      onClose();
    }
  };

  const handleAccept = (e) => {
    if (e) {
      e.stopPropagation();
      e.preventDefault();
    }
    if (onAccept) {
      onAccept(finding.finding_id);
    }
  };

  const handleReject = (e) => {
    if (e) {
      e.stopPropagation();
      e.preventDefault();
    }
    if (onReject) {
      onReject(finding.finding_id);
    }
  };

  return (
    <div
      onClick={(e) => e.stopPropagation()}
      style={{
        position: "absolute",
        zIndex: 60,
        width: "280px",
        background: "#ffffff",
        border: "1px solid #e2e8f0",
        borderRadius: "10px",
        boxShadow: "0 12px 28px -6px rgba(15, 23, 42, 0.25)",
        padding: "14px 16px",
        fontFamily: "'Inter', system-ui, -apple-system, sans-serif",
        ...style,
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "10px" }}>
        <span style={{ fontSize: "10.5px", fontWeight: 800, letterSpacing: "0.03em", color: "#4f46e5", background: "#eef2ff", padding: "3px 9px", borderRadius: "999px" }}>
          {finding.error_type ? finding.error_type.toUpperCase() : "ISSUE"}
        </span>
        <button
          type="button"
          onClick={handleClose}
          aria-label="Close"
          style={{ background: "none", border: "none", color: "#94a3b8", cursor: "pointer", fontSize: "14px", fontWeight: 700, lineHeight: 1 }}
        >
          ✕
        </button>
      </div>

      <div style={{ fontSize: "12.5px", marginBottom: "8px" }}>
        <div style={{ color: "#64748b", fontWeight: 700, fontSize: "10.5px", marginBottom: "2px" }}>Original</div>
        <div style={{ color: "#991b1b", textDecoration: "line-through", fontWeight: 600 }}>{finding.original}</div>
      </div>

      <div style={{ fontSize: "12.5px", marginBottom: "10px" }}>
        <div style={{ color: "#64748b", fontWeight: 700, fontSize: "10.5px", marginBottom: "2px" }}>Suggested</div>
        <div style={{ color: "#166534", fontWeight: 600 }}>{finding.suggestion}</div>
      </div>

      {finding.reason && (
        <div style={{ fontSize: "12px", color: "#334155", marginBottom: "10px", lineHeight: 1.4 }}>
          <div style={{ color: "#64748b", fontWeight: 700, fontSize: "10.5px", marginBottom: "2px" }}>Reason</div>
          {finding.reason}
        </div>
      )}

      <div style={{ marginBottom: "12px" }}>
        <span style={{ fontSize: "10.5px", fontWeight: 700, padding: "2px 8px", borderRadius: "999px", ...severityStyle }}>
          Severity: {finding.severity ? finding.severity.charAt(0).toUpperCase() + finding.severity.slice(1) : "Medium"}
        </span>
      </div>

      {isDone ? (
        <div style={{ fontSize: "12px", fontWeight: 700, color: finding.status === "accepted" ? "#166534" : "#991b1b" }}>
          {finding.status === "accepted" ? "✓ Accepted" : "✕ Rejected"}
        </div>
      ) : (
        <div style={{ display: "flex", gap: "8px" }}>
          <button
            type="button"
            onClick={handleAccept}
            style={{ flex: 1, background: "#166534", color: "#ffffff", border: "none", borderRadius: "6px", padding: "7px 0", fontSize: "12px", fontWeight: 700, cursor: "pointer" }}
          >
            Accept
          </button>
          <button
            type="button"
            onClick={handleReject}
            style={{ flex: 1, background: "#991b1b", color: "#ffffff", border: "none", borderRadius: "6px", padding: "7px 0", fontSize: "12px", fontWeight: 700, cursor: "pointer" }}
          >
            Reject
          </button>
        </div>
      )}
    </div>
  );
}
