import React, { useMemo } from "react";

/**
 * IssueCardList
 * ---------------
 * Simplified, secondary-to-the-document findings list for the Review tab.
 * One card per finding: original -> suggestion, page number, Accept/Reject.
 * No filters, search, bulk actions, or export controls -- those live
 * elsewhere now. Clicking a card (outside its buttons) navigates the
 * document viewer to the exact word via onSelectFinding.
 */
export default function IssueCardList({
  findings = [],
  selectedFindingId,
  onSelectFinding,
  onAcceptFinding,
  onRejectFinding,
  onUndoFinding,
  documentStatus,
}) {
  const reviewedCount = useMemo(
    () => findings.filter((f) => f.status === "accepted" || f.status === "rejected").length,
    [findings]
  );
  const total = findings.length;
  const pct = total > 0 ? Math.round((reviewedCount / total) * 100) : 0;

  const counts = useMemo(() => {
    let accepted = 0, rejected = 0;
    for (const f of findings) {
      if (f.status === "accepted") accepted++;
      else if (f.status === "rejected") rejected++;
    }
    return { accepted, rejected, pending: findings.length - accepted - rejected };
  }, [findings]);

  const emptyStateMessage = () => {
    if (documentStatus === "processing" || documentStatus === "pending") {
      return "Still scanning for issues…";
    }
    if (documentStatus === "recoverable") {
      return "Scan paused — rerun proofreading to continue.";
    }
    if (documentStatus === "failed") {
      return "Proofreading failed — see status above.";
    }
    if (documentStatus === "completed" || documentStatus === "completed_with_warnings") {
      return "No proofreading issues found.";
    }
    return "No findings yet.";
  };

  const selectedIndex = findings.findIndex((f) => f.finding_id === selectedFindingId);

  const goPrev = () => {
    if (total === 0) return;
    const idx = selectedIndex <= 0 ? total - 1 : selectedIndex - 1;
    onSelectFinding && onSelectFinding(findings[idx].finding_id, findings[idx]);
  };
  const goNext = () => {
    if (total === 0) return;
    const idx = selectedIndex >= total - 1 ? 0 : selectedIndex + 1;
    onSelectFinding && onSelectFinding(findings[idx].finding_id, findings[idx]);
  };

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        maxHeight: "calc(100vh - 140px)",
        gap: "10px",
        padding: "16px 14px",
        overflowY: "auto",
        fontFamily: "'Inter', system-ui, -apple-system, sans-serif",
      }}
    >
      <div>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: "11.5px", fontWeight: 700, color: "#64748b", marginBottom: "6px" }}>
          <span>Findings</span>
          <span>{total > 0 ? `${reviewedCount} of ${total} reviewed` : ""}</span>
        </div>
        <div style={{ height: "6px", background: "#e2e8f0", borderRadius: "3px", overflow: "hidden" }}>
          <div style={{ width: `${pct}%`, height: "100%", background: "#4f46e5", transition: "width 0.2s ease" }} />
        </div>
      </div>

      {total > 0 && (
        <div style={{ display: "flex", gap: "6px" }}>
          <span style={pillPending}>Pending: {counts.pending}</span>
          <span style={pillAccepted}>Accepted: {counts.accepted}</span>
          <span style={pillRejected}>Rejected: {counts.rejected}</span>
        </div>
      )}

      {total > 1 && (
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: "8px", padding: "5px 10px" }}>
          <button onClick={goPrev} style={navBtnStyle}>&larr; Prev</button>
          <span style={{ fontSize: "11px", fontWeight: 700, color: "#334155" }}>
            {selectedIndex >= 0 ? selectedIndex + 1 : 1} of {total}
          </span>
          <button onClick={goNext} style={navBtnStyle}>Next &rarr;</button>
        </div>
      )}

      {total === 0 ? (
        <div style={{ padding: "24px 12px", textAlign: "center", color: "#94a3b8", fontSize: "12.5px", background: "#f8fafc", borderRadius: "8px", border: "1px dashed #cbd5e1" }}>
          {emptyStateMessage()}
        </div>
      ) : (
        findings.map((f) => {
          const isSelected = f.finding_id === selectedFindingId;
          const isDone = f.status === "accepted" || f.status === "rejected";

          return (
            <div
              key={f.finding_id}
              id={`finding-card-${f.finding_id}`}
              onClick={() => onSelectFinding && onSelectFinding(f.finding_id, f)}
              style={{
                background: isSelected ? "#eef2ff" : "#ffffff",
                border: isSelected ? "1.5px solid #4f46e5" : "1px solid #e2e8f0",
                borderRadius: "10px",
                padding: "12px 14px",
                cursor: "pointer",
                boxShadow: "0 1px 2px rgba(15,23,42,0.04)",
              }}
            >
              <div style={{ fontSize: "13px", fontWeight: 650, marginBottom: "8px", opacity: isDone ? 0.55 : 1 }}>
                <span style={{ color: "#991b1b", textDecoration: "line-through" }}>{f.original}</span>
                {" → "}
                <span style={{ color: "#166534" }}>{f.suggestion}</span>
              </div>

              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div style={{ display: "flex", gap: "6px" }}>
                  <span style={categoryPillStyle(f.error_type)}>
                    {f.error_type ? f.error_type.charAt(0).toUpperCase() + f.error_type.slice(1) : "Issue"}
                  </span>
                  <span style={{ fontSize: "10.5px", fontWeight: 700, color: "#64748b", background: "#f1f5f9", padding: "2px 8px", borderRadius: "999px" }}>
                    Page {f.page_number}
                  </span>
                  {f.pdf_grounded === false && (
                    <span
                      title="Couldn't be located on the original PDF page -- no highlight is drawn for it."
                      style={{ fontSize: "10.5px", fontWeight: 700, color: "#9a3412", background: "#ffedd5", padding: "2px 8px", borderRadius: "999px" }}
                    >
                      Unanchored
                    </span>
                  )}
                </div>

                {isDone ? (
                  f.status === "accepted" ? (
                    <span style={pillAccepted}>✓ Accepted</span>
                  ) : (
                    <span style={pillRejected}>✕ Rejected</span>
                  )
                ) : (
                  <div style={{ display: "flex", gap: "6px" }} onClick={(e) => e.stopPropagation()}>
                    <button onClick={() => onAcceptFinding(f.finding_id)} style={acceptBtnStyle}>Accept</button>
                    <button onClick={() => onRejectFinding(f.finding_id)} style={rejectBtnStyle}>Reject</button>
                  </div>
                )}
              </div>

              {isDone && (
                <div style={{ marginTop: "6px", textAlign: "right" }} onClick={(e) => e.stopPropagation()}>
                  <button onClick={() => onUndoFinding(f.finding_id)} style={undoLinkStyle}>Undo</button>
                </div>
              )}
            </div>
          );
        })
      )}
    </div>
  );
}

const navBtnStyle = {
  background: "#ffffff", border: "1px solid #cbd5e1", borderRadius: "5px",
  padding: "4px 9px", fontSize: "11px", fontWeight: 700, color: "#334155", cursor: "pointer",
};
const acceptBtnStyle = {
  background: "#166534", color: "#ffffff", border: "none", borderRadius: "5px",
  padding: "4px 11px", fontSize: "11px", fontWeight: 700, cursor: "pointer",
};
const rejectBtnStyle = {
  background: "#991b1b", color: "#ffffff", border: "none", borderRadius: "5px",
  padding: "4px 11px", fontSize: "11px", fontWeight: 700, cursor: "pointer",
};
const undoLinkStyle = {
  background: "none", border: "none", color: "#64748b", fontSize: "10.5px",
  fontWeight: 700, cursor: "pointer", textDecoration: "underline",
};
const pillAccepted = {
  fontSize: "10.5px", fontWeight: 700, color: "#166534", background: "#dcfce7", padding: "2px 8px", borderRadius: "999px",
};
const pillRejected = {
  fontSize: "10.5px", fontWeight: 700, color: "#991b1b", background: "#fee2e2", padding: "2px 8px", borderRadius: "999px",
};
const pillPending = {
  fontSize: "10.5px", fontWeight: 700, color: "#64748b", background: "#f1f5f9", padding: "2px 8px", borderRadius: "999px",
};

const CATEGORY_COLORS = {
  spelling: { color: "#92400e", background: "#fef3c7" },
  punctuation: { color: "#92400e", background: "#fef3c7" },
  grammar: { color: "#3730a3", background: "#e0e7ff" },
  style: { color: "#166534", background: "#dcfce7" },
  terminology: { color: "#9d174d", background: "#fce7f3" },
  hyphenation: { color: "#155e75", background: "#cffafe" },
  whitespace: { color: "#475569", background: "#f1f5f9" },
};
const categoryPillStyle = (errorType) => {
  const colors = CATEGORY_COLORS[String(errorType || "").toLowerCase()] || { color: "#475569", background: "#f1f5f9" };
  return { fontSize: "10.5px", fontWeight: 700, padding: "2px 8px", borderRadius: "999px", ...colors };
};
