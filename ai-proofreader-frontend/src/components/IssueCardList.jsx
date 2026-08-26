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
  const allFindings = useMemo(() => {
    return (findings || []).filter(Boolean);
  }, [findings]);

  const reviewedCount = useMemo(
    () => allFindings.filter((f) => f.status === "accepted" || f.status === "rejected").length,
    [allFindings]
  );
  const total = allFindings.length;
  const pct = total > 0 ? Math.round((reviewedCount / total) * 100) : 0;

  const counts = useMemo(() => {
    let accepted = 0, rejected = 0;
    for (const f of allFindings) {
      if (f.status === "accepted") accepted++;
      else if (f.status === "rejected") rejected++;
    }
    return { accepted, rejected, pending: allFindings.length - accepted - rejected };
  }, [allFindings]);

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

  const selectedIndex = allFindings.findIndex((f) => f.finding_id === selectedFindingId);

  const goPrev = () => {
    if (total === 0) return;
    const idx = selectedIndex <= 0 ? total - 1 : selectedIndex - 1;
    onSelectFinding && onSelectFinding(allFindings[idx].finding_id, allFindings[idx]);
  };
  const goNext = () => {
    if (total === 0) return;
    const idx = selectedIndex >= total - 1 ? 0 : selectedIndex + 1;
    onSelectFinding && onSelectFinding(allFindings[idx].finding_id, allFindings[idx]);
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
        allFindings.map((f) => {
          const isSelected = f.finding_id === selectedFindingId;
          const isDone = f.status === "accepted" || f.status === "rejected";
          const origText = f.original_text || f.original || "";
          const sugText = f.suggested_text || f.suggestion || "";
          const errType = f.issue_type || f.error_type || "Spelling";
          const sev = (f.severity || "MEDIUM").toUpperCase();
          const reasonText = f.reason || f.explanation || "Spelling / grammar correction suggested";
          const isGrounded = f.pdf_grounded === true && !!f.bbox;

          const sevStyle = sev === "HIGH" || sev === "CRITICAL"
            ? { color: "#dc2626", background: "#fee2e2" }
            : (sev === "LOW" ? { color: "#475569", background: "#f1f5f9" } : { color: "#c2410c", background: "#ffedd5" });

          return (
            <div
              key={f.finding_id}
              id={`finding-card-${f.finding_id}`}
              onClick={() => onSelectFinding && onSelectFinding(f.finding_id, f)}
              style={{
                background: isSelected ? "#eef2ff" : "#ffffff",
                border: isSelected ? "2px solid #4f46e5" : "1px solid #e2e8f0",
                borderRadius: "10px",
                padding: "12px 14px",
                cursor: "pointer",
                boxShadow: isSelected ? "0 4px 12px rgba(79,70,229,0.15)" : "0 1px 2px rgba(15,23,42,0.04)",
                transition: "all 0.15s ease",
              }}
            >
              {/* Card Header: Error Type + Severity + Page + Grounding */}
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px", gap: "6px" }}>
                <div style={{ display: "flex", gap: "6px", alignItems: "center", flexWrap: "wrap" }}>
                  <span style={categoryPillStyle(errType)}>
                    {errType.charAt(0).toUpperCase() + errType.slice(1)}
                  </span>
                  <span style={{ fontSize: "10px", fontWeight: 800, padding: "2px 7px", borderRadius: "999px", ...sevStyle }}>
                    {sev}
                  </span>
                  <span style={{ fontSize: "10.5px", fontWeight: 700, color: "#64748b", background: "#f1f5f9", padding: "2px 8px", borderRadius: "999px" }}>
                    Page {f.page_number}
                  </span>
                </div>
                {isGrounded && (
                  <span
                    title="Located at exact bounding box on original PDF page"
                    style={{ fontSize: "10px", fontWeight: 800, color: "#166534", background: "#dcfce7", border: "1px solid #86efac", padding: "1px 7px", borderRadius: "999px" }}
                  >
                    PDF Grounded
                  </span>
                )}
              </div>

              {/* Original Text -> Suggested Correction */}
              <div style={{ fontSize: "13px", fontWeight: 650, marginBottom: "6px", opacity: isDone ? 0.6 : 1, lineHeight: 1.4 }}>
                <span style={{ color: "#dc2626", textDecoration: "line-through", background: "#fee2e2", padding: "1px 5px", borderRadius: "4px" }}>
                  {origText}
                </span>
                <span style={{ color: "#64748b", margin: "0 6px", fontWeight: 700 }}>→</span>
                <span style={{ color: "#166534", fontWeight: 700, background: "#dcfce7", padding: "1px 5px", borderRadius: "4px" }}>
                  {sugText}
                </span>
              </div>

              {/* Short Explanation */}
              <p style={{ margin: "0 0 10px", fontSize: "11.5px", color: "#475569", lineHeight: 1.35, display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
                {reasonText}
              </p>

              {/* Action Buttons */}
              <div style={{ display: "flex", justifyContent: "flex-end", alignItems: "center" }}>
                {isDone ? (
                  <div style={{ display: "flex", alignItems: "center", gap: "8px" }} onClick={(e) => e.stopPropagation()}>
                    {f.status === "accepted" ? (
                      <span style={pillAccepted}>✓ Accepted</span>
                    ) : (
                      <span style={pillRejected}>✕ Rejected</span>
                    )}
                    <button onClick={() => onUndoFinding(f.finding_id)} style={undoLinkStyle}>Undo</button>
                  </div>
                ) : (
                  <div style={{ display: "flex", gap: "6px" }} onClick={(e) => e.stopPropagation()}>
                    <button onClick={() => onAcceptFinding(f.finding_id)} style={acceptBtnStyle}>✓ Accept</button>
                    <button onClick={() => onRejectFinding(f.finding_id)} style={rejectBtnStyle}>✕ Reject</button>
                  </div>
                )}
              </div>
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
