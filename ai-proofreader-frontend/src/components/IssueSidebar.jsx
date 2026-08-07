import React, { useState, useMemo } from "react";

/**
 * IssueSidebar Component
 * Enterprise Deloitte / EY / PwC / KPMG Style Review Panel.
 * Single source of truth derived strictly from issues array prop.
 */
export default function IssueSidebar({
  issues = [],
  selectedIssueId,
  acceptedIssueIds = new Set(),
  rejectedIssueIds = new Set(),
  onSelectIssue,
  onAcceptIssue,
  onRejectIssue,
  onUndoIssue,
  onExportPdf,
  isExporting = false
}) {
  const [activeCategory, setActiveCategory] = useState("ALL");
  const [searchQuery, setSearchQuery] = useState("");

  // Categorize issues directly from issue.issue_type across all document issues
  const categorized = useMemo(() => {
    const counts = { ALL: 0, SPELLING: 0, GRAMMAR: 0, STYLE: 0, PUNCTUATION: 0 };
    (issues || []).forEach((issue) => {
      if (!issue) return;
      counts.ALL += 1;
      const t = (issue.issue_type || "grammar").toLowerCase();
      if (t.includes("spell")) counts.SPELLING += 1;
      else if (t.includes("gramm") || t.includes("tense")) counts.GRAMMAR += 1;
      else if (t.includes("style")) counts.STYLE += 1;
      else if (t.includes("punct")) counts.PUNCTUATION += 1;
      else counts.GRAMMAR += 1;
    });
    return counts;
  }, [issues]);

  // Filter issues ONLY by activeCategory and searchQuery
  const filteredIssues = useMemo(() => {
    return (issues || []).filter((issue) => {
      if (!issue) return false;

      const t = (issue.issue_type || "grammar").toLowerCase();
      if (activeCategory === "SPELLING" && !t.includes("spell")) return false;
      if (activeCategory === "GRAMMAR" && (!t.includes("gramm") && !t.includes("tense"))) return false;
      if (activeCategory === "STYLE" && !t.includes("style")) return false;
      if (activeCategory === "PUNCTUATION" && !t.includes("punct")) return false;

      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const orig = (issue.original_text || "").toLowerCase();
        const sug = (issue.suggested_text || "").toLowerCase();
        const reason = (issue.reason || "").toLowerCase();
        return orig.includes(q) || sug.includes(q) || reason.includes(q);
      }

      return true;
    });
  }, [issues, activeCategory, searchQuery]);

  // Selected issue index in filtered list
  const selectedIndex = useMemo(() => {
    if (!selectedIssueId) return -1;
    return filteredIssues.findIndex((i) => (i.issue_id || i.id) === selectedIssueId);
  }, [filteredIssues, selectedIssueId]);

  // Retrieve selected issue details object
  const selectedIssue = useMemo(() => {
    if (selectedIndex >= 0) return filteredIssues[selectedIndex];
    if (filteredIssues.length > 0) return filteredIssues[0];
    return null;
  }, [filteredIssues, selectedIndex]);

  const selectedIid = selectedIssue ? (selectedIssue.issue_id || selectedIssue.id) : null;
  const isSelectedAccepted = selectedIid ? acceptedIssueIds.has(selectedIid) : false;
  const isSelectedRejected = selectedIid ? rejectedIssueIds.has(selectedIid) : false;

  // Previous & Next issue navigation handlers
  const handlePrevIssue = () => {
    if (filteredIssues.length === 0) return;
    const prevIdx = selectedIndex <= 0 ? filteredIssues.length - 1 : selectedIndex - 1;
    const prevIssue = filteredIssues[prevIdx];
    if (prevIssue && onSelectIssue) {
      onSelectIssue(prevIssue.issue_id || prevIssue.id);
    }
  };

  const handleNextIssue = () => {
    if (filteredIssues.length === 0) return;
    const nextIdx = selectedIndex >= filteredIssues.length - 1 ? 0 : selectedIndex + 1;
    const nextIssue = filteredIssues[nextIdx];
    if (nextIssue && onSelectIssue) {
      onSelectIssue(nextIssue.issue_id || nextIssue.id);
    }
  };

  // Render confidence progress bar
  const renderConfidenceBar = (confidenceVal) => {
    const pct = Math.round((confidenceVal || 0.85) * 100);
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "4px", width: "100%" }}>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: "11px", color: "var(--text-secondary, #64748b)" }}>
          <span style={{ fontWeight: 600 }}>Confidence Score</span>
          <span style={{ fontWeight: 700, color: "var(--brand, #4f46e5)" }}>{pct}%</span>
        </div>
        <div style={{ width: "100%", height: "6px", background: "#e2e8f0", borderRadius: "3px", overflow: "hidden" }}>
          <div
            style={{
              width: `${pct}%`,
              height: "100%",
              background: pct >= 80 ? "#16a34a" : pct >= 60 ? "#d97706" : "#dc2626",
              borderRadius: "3px",
              transition: "width 0.3s ease"
            }}
          />
        </div>
      </div>
    );
  };

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        maxHeight: "calc(100vh - 180px)",
        background: "#ffffff",
        borderLeft: "1px solid #e2e8f0",
        padding: "16px",
        gap: "14px",
        overflowY: "auto",
        fontFamily: "'Inter', system-ui, -apple-system, sans-serif"
      }}
    >
      {/* SECTION A — REVIEW SUMMARY HEADER */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <h2 style={{ margin: 0, fontSize: "16px", fontWeight: 800, color: "#0f172a", letterSpacing: "-0.01em" }}>
            Document Review Summary
          </h2>
          <span style={{ fontSize: "12px", fontWeight: 600, color: "#64748b" }}>
            {categorized.ALL} Issues Detected
          </span>
        </div>

        <button
          onClick={onExportPdf}
          disabled={isExporting}
          style={{
            background: "#4f46e5",
            color: "#ffffff",
            border: "none",
            borderRadius: "6px",
            padding: "8px 14px",
            fontSize: "12px",
            fontWeight: 700,
            cursor: isExporting ? "wait" : "pointer",
            display: "flex",
            alignItems: "center",
            gap: "6px",
            boxShadow: "0 2px 4px rgba(79, 70, 229, 0.25)",
            opacity: isExporting ? 0.7 : 1
          }}
        >
          <span>{isExporting ? "Generating..." : "Export Corrected PDF"}</span>
        </button>
      </div>

      {/* SECTION B — STATISTICS METRIC CARDS (2x2 GRID) */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px" }}>
        {[
          { key: "ALL", label: "All Issues", count: categorized.ALL, color: "#4f46e5", bg: "#eef2ff" },
          { key: "SPELLING", label: "Spelling", count: categorized.SPELLING, color: "#d97706", bg: "#fef3c7" },
          { key: "GRAMMAR", label: "Grammar", count: categorized.GRAMMAR, color: "#dc2626", bg: "#fee2e2" },
          { key: "STYLE", label: "Style & Punct", count: categorized.STYLE + categorized.PUNCTUATION, color: "#2563eb", bg: "#dbeafe" }
        ].map((cat) => {
          const isActive = activeCategory === cat.key;
          return (
            <div
              key={cat.key}
              onClick={() => setActiveCategory(cat.key)}
              style={{
                background: isActive ? cat.bg : "#f8fafc",
                border: isActive ? `2px solid ${cat.color}` : "1px solid #e2e8f0",
                borderRadius: "8px",
                padding: "8px 10px",
                cursor: "pointer",
                transition: "all 0.15s ease",
                display: "flex",
                flexDirection: "column",
                gap: "2px"
              }}
            >
              <span style={{ fontSize: "11px", fontWeight: 700, color: isActive ? cat.color : "#64748b" }}>
                {cat.label}
              </span>
              <span style={{ fontSize: "18px", fontWeight: 800, color: isActive ? cat.color : "#0f172a" }}>
                {cat.count}
              </span>
            </div>
          );
        })}
      </div>

      {/* SEARCH FILTER INPUT */}
      <input
        type="text"
        placeholder="Search issues in document..."
        value={searchQuery}
        onChange={(e) => setSearchQuery(e.target.value)}
        style={{
          width: "100%",
          padding: "8px 12px",
          borderRadius: "6px",
          border: "1px solid #cbd5e1",
          fontSize: "12px",
          outline: "none",
          background: "#f8fafc"
        }}
      />

      {/* SECTION E — ISSUE NAVIGATION CONTROLS */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", background: "#f1f5f9", padding: "6px 10px", borderRadius: "6px" }}>
        <button
          onClick={handlePrevIssue}
          disabled={filteredIssues.length === 0}
          style={{
            background: "#ffffff",
            border: "1px solid #cbd5e1",
            borderRadius: "4px",
            padding: "4px 10px",
            fontSize: "11px",
            fontWeight: 700,
            color: "#334155",
            cursor: "pointer"
          }}
        >
          ← Previous Issue
        </button>

        <span style={{ fontSize: "11px", fontWeight: 700, color: "#475569" }}>
          {filteredIssues.length > 0 ? `Issue ${selectedIndex + 1} of ${filteredIssues.length}` : "0 Issues"}
        </span>

        <button
          onClick={handleNextIssue}
          disabled={filteredIssues.length === 0}
          style={{
            background: "#ffffff",
            border: "1px solid #cbd5e1",
            borderRadius: "4px",
            padding: "4px 10px",
            fontSize: "11px",
            fontWeight: 700,
            color: "#334155",
            cursor: "pointer"
          }}
        >
          Next Issue →
        </button>
      </div>

      {/* SECTION C — ENTERPRISE ISSUE DETAILS CARD */}
      {selectedIssue ? (
        <div
          style={{
            background: "#ffffff",
            border: "1.5px solid #4f46e5",
            borderRadius: "10px",
            padding: "14px",
            display: "flex",
            flexDirection: "column",
            gap: "12px",
            boxShadow: "0 4px 12px rgba(79, 70, 229, 0.08)"
          }}
        >
          {/* Card Header & Status Badge */}
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <span style={{ fontSize: "13px", fontWeight: 800, color: "#0f172a" }}>
                Issue #{selectedIndex >= 0 ? selectedIndex + 1 : 1}
              </span>
              <span style={{ fontSize: "10px", fontWeight: 700, background: "#e0e7ff", color: "#3730a3", padding: "2px 6px", borderRadius: "4px", textTransform: "uppercase" }}>
                {selectedIssue.issue_type || "Grammar"}
              </span>
            </div>

            {/* SECTION F — STATUS BADGES */}
            {isSelectedAccepted ? (
              <span style={{ fontSize: "11px", fontWeight: 700, background: "#dcfce7", color: "#166534", padding: "3px 8px", borderRadius: "12px" }}>
                ✓ Accepted
              </span>
            ) : isSelectedRejected ? (
              <span style={{ fontSize: "11px", fontWeight: 700, background: "#fee2e2", color: "#991b1b", padding: "3px 8px", borderRadius: "12px" }}>
                ✕ Rejected
              </span>
            ) : (
              <span style={{ fontSize: "11px", fontWeight: 700, background: "#fef3c7", color: "#92400e", padding: "3px 8px", borderRadius: "12px" }}>
                ● Pending Review
              </span>
            )}
          </div>

          {/* Meta Info */}
          <div style={{ display: "flex", gap: "12px", fontSize: "11px", color: "#64748b" }}>
            <span><strong>Severity:</strong> {selectedIssue.severity || "Medium"}</span>
            <span>•</span>
            <span><strong>Page:</strong> {selectedIssue.page_number || selectedIssue.page || 1}</span>
          </div>

          {/* Original Text Box */}
          <div style={{ background: "#fef2f2", borderLeft: "3px solid #ef4444", padding: "8px 10px", borderRadius: "4px" }}>
            <div style={{ fontSize: "10px", fontWeight: 700, color: "#991b1b", textTransform: "uppercase" }}>Original Text</div>
            <div style={{ fontSize: "13px", color: "#7f1d1d", textDecoration: "line-through", marginTop: "2px", fontWeight: 600 }}>
              {selectedIssue.original_text || "(empty)"}
            </div>
          </div>

          {/* Suggested Correction Box */}
          <div style={{ background: "#f0fdf4", borderLeft: "3px solid #22c55e", padding: "8px 10px", borderRadius: "4px" }}>
            <div style={{ fontSize: "10px", fontWeight: 700, color: "#166534", textTransform: "uppercase" }}>Suggested Correction</div>
            <div style={{ fontSize: "13px", color: "#14532d", fontWeight: 700, marginTop: "2px" }}>
              {selectedIssue.suggested_text || "(empty)"}
            </div>
          </div>

          {/* Explanation / Reason */}
          <div style={{ background: "#f8fafc", border: "1px solid #e2e8f0", padding: "8px 10px", borderRadius: "4px", fontSize: "11.5px", color: "#334155" }}>
            <strong style={{ color: "#0f172a" }}>Explanation: </strong>
            {selectedIssue.reason || "Standard grammatical revision recommended."}
          </div>

          {/* SECTION D — CONFIDENCE PROGRESS BAR */}
          {renderConfidenceBar(selectedIssue.final_confidence || selectedIssue.confidence)}

          {/* Accept / Reject Action Buttons */}
          <div style={{ display: "flex", gap: "8px", marginTop: "4px" }}>
            {!isSelectedAccepted && !isSelectedRejected ? (
              <>
                <button
                  onClick={() => onAcceptIssue(selectedIid)}
                  style={{
                    flex: 1,
                    padding: "8px",
                    background: "#166534",
                    color: "#ffffff",
                    border: "none",
                    borderRadius: "6px",
                    fontWeight: 700,
                    cursor: "pointer",
                    fontSize: "12px",
                    boxShadow: "0 1px 3px rgba(22, 101, 52, 0.2)"
                  }}
                >
                  Accept Change
                </button>
                <button
                  onClick={() => onRejectIssue(selectedIid)}
                  style={{
                    flex: 1,
                    padding: "8px",
                    background: "#991b1b",
                    color: "#ffffff",
                    border: "none",
                    borderRadius: "6px",
                    fontWeight: 700,
                    cursor: "pointer",
                    fontSize: "12px",
                    boxShadow: "0 1px 3px rgba(153, 27, 27, 0.2)"
                  }}
                >
                  Reject Change
                </button>
              </>
            ) : (
              <button
                onClick={() => onUndoIssue(selectedIid)}
                style={{
                  width: "100%",
                  padding: "6px",
                  background: "#f1f5f9",
                  color: "#334155",
                  border: "1px solid #cbd5e1",
                  borderRadius: "6px",
                  fontWeight: 600,
                  cursor: "pointer",
                  fontSize: "12px"
                }}
              >
                Undo Decision ({isSelectedAccepted ? "Accepted" : "Rejected"})
              </button>
            )}
          </div>
        </div>
      ) : (
        <div style={{ padding: "24px", textAlign: "center", color: "#64748b", fontSize: "13px" }}>
          No issue selected.
        </div>
      )}

      {/* ISSUES SCROLL LIST */}
      <div
        style={{
          flex: 1,
          overflowY: "auto",
          display: "flex",
          flexDirection: "column",
          gap: "8px",
          paddingRight: "2px"
        }}
      >
        {filteredIssues.map((issue, idx) => {
          const iid = issue.issue_id || issue.id || `issue_${idx + 1}`;
          const isSelected = (selectedIssueId === iid) || (selectedIid === iid);
          const isAcc = acceptedIssueIds.has(iid);
          const isRej = rejectedIssueIds.has(iid);

          return (
            <div
              key={iid}
              id={`sidebar-issue-item-${iid}`}
              onClick={() => onSelectIssue(iid)}
              style={{
                background: isSelected ? "#eef2ff" : "#ffffff",
                border: isSelected ? "1.5px solid #4f46e5" : "1px solid #e2e8f0",
                borderRadius: "6px",
                padding: "8px 10px",
                cursor: "pointer",
                display: "flex",
                justify: "space-between",
                alignItems: "center",
                transition: "all 0.15s ease"
              }}
            >
              <div style={{ display: "flex", flexDirection: "column", gap: "2px", overflow: "hidden", maxWidth: "70%" }}>
                <span style={{ fontSize: "11px", fontWeight: 700, color: isSelected ? "#4f46e5" : "#0f172a", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                  #{idx + 1} {issue.original_text || "Issue"} → {issue.suggested_text || ""}
                </span>
                <span style={{ fontSize: "10px", color: "#64748b" }}>
                  Page {issue.page_number || issue.page || 1} • {issue.issue_type || "Grammar"}
                </span>
              </div>

              <div>
                {isAcc ? (
                  <span style={{ fontSize: "10px", fontWeight: 700, color: "#166534", background: "#dcfce7", padding: "2px 6px", borderRadius: "4px" }}>
                    Accepted
                  </span>
                ) : isRej ? (
                  <span style={{ fontSize: "10px", fontWeight: 700, color: "#991b1b", background: "#fee2e2", padding: "2px 6px", borderRadius: "4px" }}>
                    Rejected
                  </span>
                ) : (
                  <span style={{ fontSize: "10px", fontWeight: 600, color: "#64748b" }}>
                    Pending
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
