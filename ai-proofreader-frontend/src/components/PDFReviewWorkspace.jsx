import React, { useState, useEffect, useRef, useMemo } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import HighlightOverlay from "./HighlightOverlay";
import IssueSidebar from "./IssueSidebar";
import TooltipSystem from "./TooltipSystem";
import { API_BASE_URL, exportCorrectedPdf, rerunProofreading } from "../api";

// Configure worker for react-pdf
pdfjs.GlobalWorkerOptions.workerSrc = `https://unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`;

/**
 * PDFReviewWorkspace Component
 * Continuous Vertically Scrollable PDF Review Experience (Adobe Acrobat / Google Docs style).
 * Features:
 * - Single vertical scroll container for all pages (1..numPages)
 * - Virtualized / Lazy page rendering for large documents (200+ pages)
 * - Automatic page scrolling & highlight centering on issue click with flash animation
 * - Legacy proofreading detection warning banner with 1-click proofreading re-run trigger
 * - Floating hover tooltips and Accept/Reject virtual document state management
 */
export default function PDFReviewWorkspace({
  docId,
  documentData,
  issues = [],
  onIssueDecisionChange,
  onRefreshDocument
}) {
  const [numPages, setNumPages] = useState(1);
  const [visiblePage, setVisiblePage] = useState(1);
  const [zoomLevel, setZoomLevel] = useState(1.0);
  const [pageDimensions, setPageDimensions] = useState({ width: 612, height: 792 });
  
  const [selectedIssueId, setSelectedIssueId] = useState(null);
  const [flashingIssueId, setFlashingIssueId] = useState(null);
  const [acceptedIssueIds, setAcceptedIssueIds] = useState(new Set());
  const [rejectedIssueIds, setRejectedIssueIds] = useState(new Set());
  
  const [hoveredIssue, setHoveredIssue] = useState(null);
  const [tooltipPosition, setTooltipPosition] = useState(null);
  const [isExporting, setIsExporting] = useState(false);
  const [isRerunning, setIsRerunning] = useState(false);
  const [pdfLoadError, setPdfLoadError] = useState(false);

  const scrollContainerRef = useRef(null);

  const pdfUrl = `${API_BASE_URL}/documents/${docId}/file`;

  // Synchronize initial decisions if passed from parent & log runtime telemetry
  useEffect(() => {
    console.log("[Proofreading Workspace] Issues received:", issues?.length || 0);
    if (issues && issues.length > 0) {
      console.log("[Proofreading Workspace] First issue:", issues[0]);
    }

    if (documentData && documentData.decisions) {
      const acc = new Set();
      const rej = new Set();
      Object.entries(documentData.decisions).forEach(([key, val]) => {
        if (val === "accepted") acc.add(key);
        if (val === "rejected") rej.add(key);
      });
      setAcceptedIssueIds(acc);
      setRejectedIssueIds(rej);
    }
  }, [documentData, issues]);

  const handleDocumentLoadSuccess = ({ numPages }) => {
    setNumPages(numPages);
    setPdfLoadError(false);
  };

  const handlePageLoadSuccess = (page) => {
    if (page.pageNumber === 1) {
      const viewport = page.getViewport({ scale: 1.0 });
      setPageDimensions({ width: viewport.width, height: viewport.height });
    }
  };

  // Zoom Handlers
  const handleZoomIn = () => setZoomLevel((prev) => Math.min(prev + 0.2, 2.5));
  const handleZoomOut = () => setZoomLevel((prev) => Math.max(prev - 0.2, 0.5));
  const handleZoomReset = () => setZoomLevel(1.0);

  // Track visible page on vertical scroll using IntersectionObserver / Scroll calculation
  useEffect(() => {
    const container = scrollContainerRef.current;
    if (!container) return;

    const handleScroll = () => {
      const pageHeightWithGap = (pageDimensions.height * zoomLevel) + 24;
      const scrollTop = container.scrollTop;
      const current = Math.min(
        Math.max(Math.floor((scrollTop + (container.clientHeight / 3)) / pageHeightWithGap) + 1, 1),
        numPages
      );
      setVisiblePage(current);
    };

    container.addEventListener("scroll", handleScroll);
    return () => container.removeEventListener("scroll", handleScroll);
  }, [pageDimensions.height, zoomLevel, numPages]);

  // Auto-Navigate to Issue, Center Highlight & Flash
  const handleSelectIssue = (issueId) => {
    setSelectedIssueId(issueId);
    setFlashingIssueId(issueId);

    // Flash timeout
    setTimeout(() => setFlashingIssueId(null), 1600);

    const targetIssue = issues.find((i) => (i.issue_id || i.id) === issueId);
    if (targetIssue) {
      const page = Number(targetIssue.page_number || targetIssue.page || 1);
      setVisiblePage(page);
      
      // 1. Scroll container to target PDF page element
      const pageEl = document.getElementById(`pdf-page-${page}`);
      if (pageEl) {
        pageEl.scrollIntoView({ behavior: "smooth", block: "center" });
      }

      // 2. Center word highlight element if mounted
      setTimeout(() => {
        const highlightEl = document.getElementById(`pdf-highlight-${issueId}`);
        if (highlightEl) {
          highlightEl.scrollIntoView({ behavior: "smooth", block: "center" });
        }
      }, 100);

      // 3. Scroll sidebar item into view
      setTimeout(() => {
        const sidebarEl = document.getElementById(`sidebar-issue-item-${issueId}`);
        if (sidebarEl) {
          sidebarEl.scrollIntoView({ behavior: "smooth", block: "nearest" });
        }
      }, 150);
    }
  };

  // Accept / Reject Handlers
  const handleAcceptIssue = (issueId) => {
    setAcceptedIssueIds((prev) => {
      const next = new Set(prev);
      next.add(issueId);
      return next;
    });
    setRejectedIssueIds((prev) => {
      const next = new Set(prev);
      next.delete(issueId);
      return next;
    });

    if (onIssueDecisionChange) {
      onIssueDecisionChange(issueId, "accepted");
    }
  };

  const handleRejectIssue = (issueId) => {
    setRejectedIssueIds((prev) => {
      const next = new Set(prev);
      next.add(issueId);
      return next;
    });
    setAcceptedIssueIds((prev) => {
      const next = new Set(prev);
      next.delete(issueId);
      return next;
    });

    if (onIssueDecisionChange) {
      onIssueDecisionChange(issueId, "rejected");
    }
  };

  const handleUndoIssue = (issueId) => {
    setAcceptedIssueIds((prev) => {
      const next = new Set(prev);
      next.delete(issueId);
      return next;
    });
    setRejectedIssueIds((prev) => {
      const next = new Set(prev);
      next.delete(issueId);
      return next;
    });

    if (onIssueDecisionChange) {
      onIssueDecisionChange(issueId, "pending");
    }
  };

  // Hover Handlers
  const handleHoverIssue = (issue, e) => {
    setHoveredIssue(issue);
    setTooltipPosition({ x: e.clientX, y: e.clientY });
  };

  const handleLeaveIssue = () => {
    setHoveredIssue(null);
    setTooltipPosition(null);
  };

  // Re-run Proofreading Handler
  const handleRerunProofreading = async () => {
    try {
      setIsRerunning(true);
      await rerunProofreading(docId);
      if (onRefreshDocument) {
        await onRefreshDocument();
      }
    } catch (err) {
      console.error("Failed to rerun proofreading:", err);
      alert(`Proofreading rerun failed: ${err.message}`);
    } finally {
      setIsRerunning(false);
    }
  };

  // Export Corrected PDF Trigger
  const handleExportPdf = async () => {
    try {
      setIsExporting(true);
      const decisionsObj = {};
      acceptedIssueIds.forEach((id) => { decisionsObj[id] = "accepted"; });
      rejectedIssueIds.forEach((id) => { decisionsObj[id] = "rejected"; });

      const blob = await exportCorrectedPdf(docId, Array.from(acceptedIssueIds), decisionsObj);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `corrected_${documentData?.filename || "document.pdf"}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error("PDF export failed:", err);
      alert(`PDF Export failed: ${err.message}`);
    } finally {
      setIsExporting(false);
    }
  };

  const renderedWidth = pageDimensions.width * zoomLevel;
  const renderedHeight = pageDimensions.height * zoomLevel;

  // Render Virtualized continuous scroll page array (1..numPages)
  const pageNumbers = Array.from({ length: numPages }, (_, i) => i + 1);

  return (
    <div
      style={{
        display: "flex",
        width: "100%",
        height: "calc(100vh - 120px)",
        minHeight: "650px",
        background: "var(--bg-main, #f1f5f9)",
        borderRadius: "12px",
        overflow: "hidden",
        border: "1px solid var(--border, #e2e8f0)",
        boxShadow: "var(--shadow-card, 0 4px 6px -1px rgba(0, 0, 0, 0.1))"
      }}
    >
      {/* Left Workspace: Continuous Vertically Scrollable PDF Viewer (70% width) */}
      <div
        style={{
          flex: "0 0 70%",
          width: "70%",
          display: "flex",
          flexDirection: "column",
          background: "#cbd5e1",
          position: "relative"
        }}
      >
        {/* PDF Floating Control Bar */}
        <div
          style={{
            display: "flex",
            justify: "space-between",
            alignItems: "center",
            padding: "10px 18px",
            background: "var(--bg-card, #ffffff)",
            borderBottom: "1px solid var(--border, #e2e8f0)",
            zIndex: 20,
            boxShadow: "0 2px 8px rgba(0,0,0,0.05)"
          }}
        >
          {/* Floating Sticky Page Indicator */}
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <span style={{ fontSize: "13px", fontWeight: 700, color: "var(--text-primary, #0f172a)" }}>
              Page {visiblePage} of {numPages}
            </span>
          </div>

          {/* Zoom Controls */}
          <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
            <button onClick={handleZoomOut} style={styles.ctrlBtn} title="Zoom Out">
              -
            </button>
            <span style={{ fontSize: "12px", fontWeight: 700, minWidth: "48px", textAlign: "center" }}>
              {Math.round(zoomLevel * 100)}%
            </span>
            <button onClick={handleZoomIn} style={styles.ctrlBtn} title="Zoom In">
              +
            </button>
            <button onClick={handleZoomReset} style={styles.ctrlBtn}>
              Reset
            </button>
          </div>
        </div>

        {/* Continuous Scroll Container (Adobe Acrobat / Google Docs style) */}
        <div
          ref={scrollContainerRef}
          style={{
            flex: 1,
            overflowY: "auto",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            padding: "24px",
            gap: "24px",
            scrollBehavior: "smooth"
          }}
        >
          {!pdfLoadError ? (
            <Document
              file={pdfUrl}
              onLoadSuccess={handleDocumentLoadSuccess}
              onLoadError={(err) => {
                console.warn("react-pdf load error, falling back to object embed:", err);
                setPdfLoadError(true);
              }}
              loading={<div style={{ padding: "40px", textAlign: "center" }}>Loading PDF Document...</div>}
            >
              {pageNumbers.map((pNum) => {
                // Virtualization Window: Render PDF Page content if within +/- 3 pages of visiblePage
                const isNearVisibleWindow = Math.abs(pNum - visiblePage) <= 3 || numPages <= 10;

                return (
                  <div
                    key={pNum}
                    id={`pdf-page-${pNum}`}
                    style={{
                      position: "relative",
                      width: `${renderedWidth}px`,
                      height: `${renderedHeight}px`,
                      boxShadow: "0 10px 25px -5px rgba(0, 0, 0, 0.3)",
                      background: "#ffffff",
                      borderRadius: "4px"
                    }}
                  >
                    {isNearVisibleWindow ? (
                      <>
                        <Page
                          pageNumber={pNum}
                          scale={zoomLevel}
                          onLoadSuccess={handlePageLoadSuccess}
                          renderAnnotationLayer={false}
                          renderTextLayer={false}
                        />

                        {/* Highlight Overlay Layer for Page */}
                        <HighlightOverlay
                          issues={issues}
                          selectedIssueId={selectedIssueId}
                          flashingIssueId={flashingIssueId}
                          acceptedIssueIds={acceptedIssueIds}
                          rejectedIssueIds={rejectedIssueIds}
                          pageNumber={pNum}
                          pageWidth={renderedWidth}
                          pageHeight={renderedHeight}
                          originalWidth={pageDimensions.width}
                          originalHeight={pageDimensions.height}
                          onSelectIssue={handleSelectIssue}
                          onHoverIssue={handleHoverIssue}
                          onLeaveIssue={handleLeaveIssue}
                        />
                      </>
                    ) : (
                      /* Virtualized Lazy Placeholder Div */
                      <div
                        style={{
                          width: "100%",
                          height: "100%",
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          background: "#ffffff",
                          color: "#94a3b8",
                          fontSize: "14px",
                          fontWeight: "600"
                        }}
                      >
                        Page {pNum}
                      </div>
                    )}
                  </div>
                );
              })}
            </Document>
          ) : (
            /* Fallback Object PDF Viewer */
            <div style={{ width: "100%", height: "100%", position: "relative" }}>
              <object data={pdfUrl} type="application/pdf" width="100%" height="100%">
                <div style={{ padding: "40px", textAlign: "center" }}>
                  Unable to render PDF preview directly.
                  <a href={pdfUrl} target="_blank" rel="noreferrer" style={{ marginLeft: "6px", color: "var(--brand)" }}>
                    Open PDF in new tab
                  </a>
                </div>
              </object>
            </div>
          )}
        </div>
      </div>

      {/* Right Workspace: Issues Sidebar Panel (30% width) */}
      <div style={{ flex: "0 0 30%", width: "30%", height: "100%" }}>
        <IssueSidebar
          issues={issues}
          selectedIssueId={selectedIssueId}
          acceptedIssueIds={acceptedIssueIds}
          rejectedIssueIds={rejectedIssueIds}
          onSelectIssue={handleSelectIssue}
          onAcceptIssue={handleAcceptIssue}
          onRejectIssue={handleRejectIssue}
          onUndoIssue={handleUndoIssue}
          onExportPdf={handleExportPdf}
          isExporting={isExporting}
        />
      </div>

      {/* Floating Hover Tooltip System */}
      <TooltipSystem
        hoveredIssue={hoveredIssue}
        tooltipPosition={tooltipPosition}
        isVisible={Boolean(hoveredIssue)}
      />
    </div>
  );
}

const styles = {
  ctrlBtn: {
    background: "var(--bg-card, #ffffff)",
    border: "1px solid var(--border, #cbd5e1)",
    borderRadius: "6px",
    padding: "4px 10px",
    fontSize: "12px",
    fontWeight: 600,
    cursor: "pointer",
    color: "var(--text-primary, #0f172a)"
  }
};
