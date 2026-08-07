import React from "react";

/**
 * HighlightOverlay Component
 * Renders word-level bounding box highlight overlays over PDF text canvas.
 * Enterprise styling:
 * - Spelling = Amber/Yellow (#d97706)
 * - Grammar = Red (#dc2626)
 * - Style = Indigo/Blue (#2563eb)
 * - Punctuation = Orange (#ea580c)
 * Strictly rendered when Number(issue.page_number || issue.page) === Number(pageNumber).
 */
export default function HighlightOverlay({
  issues = [],
  selectedIssueId,
  flashingIssueId,
  acceptedIssueIds = new Set(),
  rejectedIssueIds = new Set(),
  pageNumber = 1,
  pageWidth = 612,
  pageHeight = 865.518,
  originalWidth = 595.2755737304688,
  originalHeight = 841.8897705078125,
  onSelectIssue,
  onHoverIssue,
  onLeaveIssue
}) {
  if (!issues || issues.length === 0) return null;

  // Filter issues for current page ONLY (strict page matching)
  const pageIssues = (issues || []).filter((issue) => {
    if (!issue) return false;
    const issuePage = Number(issue.page_number || issue.page || 0);
    return issuePage === Number(pageNumber);
  });

  const getHighlightColor = (issueType, isSelected) => {
    const t = (issueType || "").toLowerCase();
    let base = {
      bg: "rgba(245, 158, 11, 0.25)",
      border: "#d97706",
      activeBg: "rgba(245, 158, 11, 0.65)",
      shadow: "rgba(217, 119, 6, 0.4)"
    };

    if (t.includes("spell")) {
      base = { bg: "rgba(245, 158, 11, 0.25)", border: "#d97706", activeBg: "rgba(245, 158, 11, 0.65)", shadow: "rgba(217, 119, 6, 0.4)" };
    } else if (t.includes("gramm") || t.includes("tense")) {
      base = { bg: "rgba(239, 68, 68, 0.25)", border: "#dc2626", activeBg: "rgba(239, 68, 68, 0.65)", shadow: "rgba(220, 38, 38, 0.4)" };
    } else if (t.includes("style")) {
      base = { bg: "rgba(59, 130, 246, 0.25)", border: "#2563eb", activeBg: "rgba(59, 130, 246, 0.65)", shadow: "rgba(37, 99, 235, 0.4)" };
    } else if (t.includes("punct")) {
      base = { bg: "rgba(249, 115, 22, 0.25)", border: "#ea580c", activeBg: "rgba(249, 115, 22, 0.65)", shadow: "rgba(234, 88, 12, 0.4)" };
    }

    if (isSelected) {
      base.bg = base.activeBg;
    }
    return base;
  };

  // PDF Page points dimensions
  const pdfWidth = (originalWidth && originalWidth > 0) ? originalWidth : 595.2755737304688;
  const pdfHeight = (originalHeight && originalHeight > 0) ? originalHeight : 841.8897705078125;

  // Exact Scale factor from PDF points to CSS rendered canvas pixels
  const scaleX = pageWidth / pdfWidth;
  const scaleY = pageHeight / pdfHeight;

  return (
    <div
      aria-label={`Highlight overlay layer for page ${pageNumber}`}
      style={{
        position: "absolute",
        top: 0,
        left: 0,
        width: `${pageWidth}px`,
        height: `${pageHeight}px`,
        pointerEvents: "none",
        zIndex: 10
      }}
    >
      <style>
        {`
          @keyframes flashGlow {
            0% { transform: scale(1); box-shadow: 0 0 0 0 rgba(79, 70, 229, 0.8); }
            50% { transform: scale(1.04); box-shadow: 0 0 16px 4px rgba(79, 70, 229, 0.9); }
            100% { transform: scale(1); box-shadow: 0 0 0 0 rgba(79, 70, 229, 0); }
          }
        `}
      </style>

      {pageIssues.map((issue, idx) => {
        const iid = issue.issue_id || issue.id || `issue_${idx + 1}`;
        const isAccepted = acceptedIssueIds.has(iid);
        const isRejected = rejectedIssueIds.has(iid);

        // Hide overlay if rejected
        if (isRejected) return null;

        const isSelected = selectedIssueId === iid;
        const isFlashing = flashingIssueId === iid;
        const color = getHighlightColor(issue.issue_type, isSelected);

        const bbox = issue.bbox || {};
        let x0 = Number(bbox.x0 ?? bbox.l ?? 0);
        let y0 = Number(bbox.y0 ?? bbox.t ?? 0);
        let x1 = Number(bbox.x1 ?? bbox.r ?? 0);
        let y1 = Number(bbox.y1 ?? bbox.b ?? 0);

        // Normalize 0..1 coordinates if needed
        if (x1 <= 1.0 && y1 <= 1.0 && (x1 > 0 || y1 > 0)) {
          x0 *= pdfWidth;
          x1 *= pdfWidth;
          y0 *= pdfHeight;
          y1 *= pdfHeight;
        }

        const widthPt = Math.abs(x1 - x0);
        const heightPt = Math.abs(y1 - y0);

        // Do not render false top-left 0,0 box when bounding box is unmeasured
        if (widthPt === 0 && heightPt === 0) {
          return null;
        }

        const maxY = Math.max(y0, y1);
        const topPt = (maxY > 0 && maxY <= pdfHeight) ? (pdfHeight - maxY) : Math.min(y0, y1);
        const leftPt = Math.min(x0, x1);

        // Transform PDF points to CSS pixels
        let cssLeft = leftPt * scaleX;
        let cssTop = topPt * scaleY;
        let cssWidth = Math.max(widthPt * scaleX, 20);
        let cssHeight = Math.max(heightPt * scaleY, 14);

        if (isAccepted) {
          // Render Accepted Correction Overlay Layer (Requirement 12)
          return (
            <div
              key={iid}
              id={`pdf-highlight-${iid}`}
              style={{
                position: "absolute",
                left: `${cssLeft}px`,
                top: `${cssTop}px`,
                minWidth: `${cssWidth}px`,
                minHeight: `${cssHeight}px`,
                background: "linear-gradient(135deg, #16a34a, #15803d)",
                color: "#ffffff",
                border: "1.5px solid #166534",
                borderRadius: "4px",
                padding: "2px 6px",
                fontSize: "11px",
                fontWeight: "750",
                lineHeight: "1.2",
                display: "inline-flex",
                alignItems: "center",
                gap: "4px",
                boxShadow: "0 4px 10px rgba(22, 163, 74, 0.4)",
                cursor: "pointer",
                pointerEvents: "auto",
                zIndex: 15
              }}
              onClick={(e) => {
                e.stopPropagation();
                if (onSelectIssue) onSelectIssue(iid);
              }}
              onMouseEnter={(e) => {
                if (onHoverIssue) onHoverIssue(issue, e);
              }}
              onMouseLeave={() => {
                if (onLeaveIssue) onLeaveIssue();
              }}
              title={`[Accepted Correction] Original: "${issue.original_text}" -> Replacement: "${issue.suggested_text}"`}
            >
              <span>✓</span>
              <span>{issue.suggested_text || issue.corrected}</span>
            </div>
          );
        }

        // Render Pending Highlight Box
        const rectStyle = {
          position: "absolute",
          left: `${cssLeft}px`,
          top: `${cssTop}px`,
          width: `${cssWidth}px`,
          height: `${cssHeight}px`,
          background: color.bg,
          border: `1.5px solid ${color.border}`,
          borderRadius: "3px",
          cursor: "pointer",
          pointerEvents: "auto",
          boxShadow: isSelected
            ? `0 0 0 3px ${color.border}, 0 4px 12px ${color.shadow}`
            : "0 1px 3px rgba(0,0,0,0.1)",
          transition: "all 0.15s ease-in-out",
          animation: isFlashing ? "flashGlow 0.8s ease-in-out 2" : "none"
        };

        return (
          <div
            key={iid}
            id={`pdf-highlight-${iid}`}
            style={rectStyle}
            onClick={(e) => {
              e.stopPropagation();
              if (onSelectIssue) onSelectIssue(iid);
            }}
            onMouseEnter={(e) => {
              if (onHoverIssue) onHoverIssue(issue, e);
            }}
            onMouseLeave={() => {
              if (onLeaveIssue) onLeaveIssue();
            }}
            title={`[${issue.issue_type || "Issue"}] Page ${pageNumber}: ${issue.original_text} -> ${issue.suggested_text}`}
          />
        );
      })}
    </div>
  );
}
