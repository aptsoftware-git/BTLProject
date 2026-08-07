import React from "react";

/**
 * TooltipSystem Component
 * Displays a concise 2-3 word floating tooltip over hovered PDF highlights.
 */
export default function TooltipSystem({ hoveredIssue, tooltipPosition, isVisible }) {
  if (!isVisible || !hoveredIssue || !tooltipPosition) return null;

  const getConciseReason = (issue) => {
    const typeStr = (issue.issue_type || "issue").toLowerCase();
    const reason = (issue.reason || "").toLowerCase();

    if (typeStr.includes("spell")) {
      if (reason.includes("hyphen")) return "Spelling: Missing hyphen";
      if (reason.includes("cap")) return "Spelling: Capitalization typo";
      return "Spelling: Misspelled word";
    }
    if (typeStr.includes("gramm") || typeStr.includes("tense")) {
      if (reason.includes("verb") || reason.includes("agree")) return "Grammar: Subject-verb agreement";
      if (reason.includes("tense")) return "Grammar: Tense inconsistency";
      return "Grammar: Syntax error";
    }
    if (typeStr.includes("punct")) {
      if (reason.includes("comma")) return "Punctuation: Missing comma";
      return "Punctuation: Formatting typo";
    }
    if (typeStr.includes("style")) {
      return "Style: Word choice";
    }
    return `${typeStr.charAt(0).toUpperCase() + typeStr.slice(1)}: Suggested edit`;
  };

  const getBadgeColor = (issueType) => {
    const t = (issueType || "").toLowerCase();
    if (t.includes("spell")) return { bg: "#fef08a", color: "#854d0e", border: "#eab308" };
    if (t.includes("gramm") || t.includes("tense")) return { bg: "#fecaca", color: "#991b1b", border: "#ef4444" };
    if (t.includes("style")) return { bg: "#bfdbfe", color: "#1e40af", border: "#3b82f6" };
    if (t.includes("punct")) return { bg: "#fed7aa", color: "#9a3412", border: "#f97316" };
    return { bg: "#e2e8f0", color: "#334155", border: "#94a3b8" };
  };

  const colorScheme = getBadgeColor(hoveredIssue.issue_type);
  const text = getConciseReason(hoveredIssue);

  // Position offset to prevent mouse clipping
  const style = {
    position: "fixed",
    left: Math.min(tooltipPosition.x + 12, window.innerWidth - 220),
    top: Math.max(tooltipPosition.y - 36, 12),
    zIndex: 9999,
    pointerEvents: "none",
    background: "rgba(15, 23, 42, 0.92)",
    backdropFilter: "blur(8px)",
    color: "#f8fafc",
    padding: "6px 12px",
    borderRadius: "6px",
    fontSize: "12px",
    fontWeight: "600",
    boxShadow: "0 10px 25px -5px rgba(0, 0, 0, 0.3), 0 8px 10px -6px rgba(0, 0, 0, 0.3)",
    border: `1px solid ${colorScheme.border}`,
    display: "flex",
    alignItems: "center",
    gap: "8px",
    whiteSpace: "nowrap",
    transition: "opacity 0.15s ease-in-out, transform 0.15s ease-in-out"
  };

  const dotStyle = {
    width: "8px",
    height: "8px",
    borderRadius: "50%",
    background: colorScheme.border,
    boxShadow: `0 0 6px ${colorScheme.border}`
  };

  return (
    <div style={style} className="pdf-tooltip-bubble">
      <span style={dotStyle} />
      <span>{text}</span>
    </div>
  );
}
