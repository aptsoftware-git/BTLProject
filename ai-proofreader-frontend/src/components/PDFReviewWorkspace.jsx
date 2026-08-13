import React, { useState, useEffect, useRef } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import SentenceDocumentViewer from "./SentenceDocumentViewer";
import IssueCardList from "./IssueCardList";
import CorrectedPreviewPanel from "./CorrectedPreviewPanel";
import FindingPopover from "./FindingPopover";
import {
  API_BASE_URL, rerunProofreading, rerunFromStage,
  fetchFindings, updateFindingStatus, exportCorrectedDocument,
} from "../api";

// Configure worker for react-pdf
pdfjs.GlobalWorkerOptions.workerSrc = `https://unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`;

/**
 * PDFReviewWorkspace Component
 * -----------------------------
 * Business-user-facing proofreading workspace. Three tabs:
 *   Review (Original PDF) - PRIMARY surface. Renders the real, untouched
 *                           original PDF via react-pdf, with findings
 *                           highlighted at their real, PDF-grounded
 *                           coordinates (never a whole-sentence highlight,
 *                           never a synthetic/guessed box -- see
 *                           src/pdf_bbox_resolver.py). Default tab for PDF
 *                           originals.
 *   Text View             - secondary/fallback: the reconstructed running
 *                           text (SentenceDocumentViewer), still
 *                           highlighted by character offsets. Default (and
 *                           only) tab for non-PDF (DOCX/TXT) originals,
 *                           since there is no PDF to render for those.
 *   Live Corrected Preview - read-only preview of accepted corrections,
 *                           plus export to pdf/docx/html.
 */
export default function PDFReviewWorkspace({
  docId,
  documentData,
  onRefreshDocument,
}) {
  const isPdfOriginal = /\.pdf$/i.test(documentData?.filename || "");

  const [numPages, setNumPages] = useState(1);
  const [visiblePage, setVisiblePage] = useState(1);
  const [zoomLevel, setZoomLevel] = useState(1.0);
  const [pageDimensions, setPageDimensions] = useState({ width: 612, height: 792 });
  const [isRerunning, setIsRerunning] = useState(false);
  const [isReprocessing, setIsReprocessing] = useState(false);
  const [pdfLoadError, setPdfLoadError] = useState(false);
  const [viewMode, setViewMode] = useState(isPdfOriginal ? "pdf" : "review"); // "pdf" | "review" | "corrected"
  const [viewModeInitialized, setViewModeInitialized] = useState(false);

  // Page + Sentence Mapping architecture state
  const [findings, setFindings] = useState([]);
  const [selectedFindingId, setSelectedFindingId] = useState(null);
  const [flashingFindingId, setFlashingFindingId] = useState(null);
  const [popoverFindingId, setPopoverFindingId] = useState(null);
  const [scrollRequest, setScrollRequest] = useState(null);
  const [isExportingCorrected, setIsExportingCorrected] = useState(false);
  const [findingActionError, setFindingActionError] = useState(null);

  const scrollContainerRef = useRef(null);
  const pdfUrl = `${API_BASE_URL}/documents/${docId}/file`;

  // Load findings whenever the document changes or proofreading completes.
  const loadFindings = () => {
    if (!docId) return;
    fetchFindings(docId)
      .then((res) => setFindings(res.findings || []))
      .catch((err) => console.warn("[Review] Failed to load findings:", err));
  };

  useEffect(() => {
    loadFindings();
    setViewModeInitialized(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [docId]);

  const docStatus = documentData?.status;
  const isProcessing = docStatus === "processing" || docStatus === "pending";
  const isFailed = docStatus === "failed";
  const isRecoverable = docStatus === "recoverable";
  const isDone = docStatus === "completed" || docStatus === "completed_with_warnings";

  const proofreadingReady = documentData?.proofreading_ready || documentData?.proofreading_status === "completed";
  const proofreadingStatus = documentData?.proofreading_status || (proofreadingReady || isDone ? "completed" : "pending");
  const proofreadingDone = proofreadingStatus === "completed" || proofreadingReady === true;
  const sidebarStatus = proofreadingDone ? "completed" : docStatus;

  // Re-fetch findings automatically as soon as proofreading becomes ready/completed
  useEffect(() => {
    if (proofreadingDone) {
      loadFindings();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [proofreadingDone, documentData?.proofreading_status, documentData?.proofreading_ready]);

  // Set the default tab exactly once per document, once we actually know
  // its file type -- PDF originals default to the real-PDF review surface;
  // DOCX/TXT originals (no PDF to render) default to the text view.
  useEffect(() => {
    if (viewModeInitialized || !documentData?.filename) return;
    setViewMode(isPdfOriginal ? "pdf" : "review");
    setViewModeInitialized(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [documentData?.filename, viewModeInitialized]);

  const acceptedFindingIds = new Set(findings.filter((f) => f.status === "accepted").map((f) => f.finding_id));
  const rejectedFindingIds = new Set(findings.filter((f) => f.status === "rejected").map((f) => f.finding_id));

  const applyFindingStatusOptimistic = (findingId, status) => {
    setFindings((prev) => prev.map((f) => (f.finding_id === findingId ? { ...f, status } : f)));
  };

function normalizeBboxes(bbox) {
  if (!bbox) return [];
  if (typeof bbox === "object" && !Array.isArray(bbox) && "x0" in bbox) {
    return [bbox];
  }
  if (Array.isArray(bbox)) {
    if (bbox.length === 4 && typeof bbox[0] === "number") {
      return [{ x0: bbox[0], y0: bbox[1], x1: bbox[2], y1: bbox[3] }];
    }
    return bbox
      .map((b) => {
        if (Array.isArray(b) && b.length === 4) {
          return { x0: b[0], y0: b[1], x1: b[2], y1: b[3] };
        }
        return b;
      })
      .filter((b) => b && typeof b.x0 === "number");
  }
  return [];
}

  const handleSelectFinding = (findingId, findingObj) => {
    const target = findingObj || findings.find((f) => f.finding_id === findingId);
    if (!target) return;

    setSelectedFindingId(findingId);

    if (viewMode === "pdf") {
      const isGrounded = target.pdf_grounded !== false && !!target.bbox;
      if (isGrounded) {
        setFlashingFindingId(findingId);
        setPopoverFindingId(findingId);
        setTimeout(() => {
          setFlashingFindingId((current) => (current === findingId ? null : current));
        }, 5000);
      } else {
        setPopoverFindingId(null);
      }

      setVisiblePage(target.page_number);

      setTimeout(() => {
        const pageEl = document.getElementById(`pdf-page-${target.page_number}`);
        if (!pageEl || !scrollContainerRef.current) return;

        const bboxes = normalizeBboxes(target.bbox);
        let yOffset = 0;
        if (bboxes.length > 0) {
          yOffset = bboxes[0].y0 * zoomLevel;
        }

        const pageTop = pageEl.offsetTop;
        const targetScrollTop = Math.max(0, pageTop + yOffset - 130);

        scrollContainerRef.current.scrollTo({
          top: targetScrollTop,
          behavior: "smooth"
        });
      }, 80);
    } else {
      setFlashingFindingId(findingId);
      setTimeout(() => {
        setFlashingFindingId((current) => (current === findingId ? null : current));
      }, 5000);
      if (target) {
        setScrollRequest({ sentenceId: target.sentence_id, pageNumber: target.page_number, findingId: target.finding_id, nonce: Date.now() });
      }
    }

    setTimeout(() => {
      const cardEl = document.getElementById(`finding-card-${findingId}`);
      if (cardEl) cardEl.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }, 150);
  };

  const handleAcceptFinding = async (findingId) => {
    applyFindingStatusOptimistic(findingId, "accepted");
    try {
      await updateFindingStatus(docId, findingId, "accepted");
    } catch (err) {
      console.error("Failed to persist accept decision:", err);
      applyFindingStatusOptimistic(findingId, "pending");
      setFindingActionError(`Couldn't save "Accept" — ${err.message}. Reverted.`);
    }
  };

  const handleRejectFinding = async (findingId) => {
    applyFindingStatusOptimistic(findingId, "rejected");
    try {
      await updateFindingStatus(docId, findingId, "rejected");
    } catch (err) {
      console.error("Failed to persist reject decision:", err);
      applyFindingStatusOptimistic(findingId, "pending");
      setFindingActionError(`Couldn't save "Reject" — ${err.message}. Reverted.`);
    }
  };

  const handleUndoFinding = async (findingId) => {
    const previous = findings.find((f) => f.finding_id === findingId)?.status;
    applyFindingStatusOptimistic(findingId, "pending");
    try {
      await updateFindingStatus(docId, findingId, "pending");
    } catch (err) {
      console.error("Failed to persist undo decision:", err);
      if (previous) applyFindingStatusOptimistic(findingId, previous);
      setFindingActionError(`Couldn't save "Undo" — ${err.message}. Reverted.`);
    }
  };

  const handleExportCorrected = async (format) => {
    try {
      setIsExportingCorrected(true);
      const blob = await exportCorrectedDocument(docId, format);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `corrected_document.${format}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error("Corrected document export failed:", err);
      alert(`Export failed: ${err.message}`);
    } finally {
      setIsExportingCorrected(false);
    }
  };

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

  const handleZoomIn = () => setZoomLevel((prev) => Math.min(prev + 0.2, 2.5));
  const handleZoomOut = () => setZoomLevel((prev) => Math.max(prev - 0.2, 0.5));
  const handleZoomReset = () => setZoomLevel(1.0);

  // Track visible page on vertical scroll (Original PDF tab only)
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

  const handleRerunProofreading = async () => {
    try {
      setIsRerunning(true);
      await rerunProofreading(docId);
      if (onRefreshDocument) {
        await onRefreshDocument();
      }
      loadFindings();
    } catch (err) {
      console.error("Failed to rerun proofreading:", err);
      alert(`Proofreading rerun failed: ${err.message}`);
    } finally {
      setIsRerunning(false);
    }
  };

  const handleReprocessDocument = async () => {
    if (!window.confirm(
      "Reprocess Document re-runs the full extraction (Docling) and rebuilds the page/sentence mapping from scratch, " +
      "not just proofreading. This is slower and will regenerate everything downstream. Continue?"
    )) {
      return;
    }
    try {
      setIsReprocessing(true);
      await rerunFromStage(docId, 2);
      if (onRefreshDocument) {
        await onRefreshDocument();
      }
      loadFindings();
    } catch (err) {
      console.error("Failed to reprocess document:", err);
      alert(`Reprocess failed: ${err.message}`);
    } finally {
      setIsReprocessing(false);
    }
  };

  const renderedWidth = pageDimensions.width * zoomLevel;
  const renderedHeight = pageDimensions.height * zoomLevel;
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
      {/* Main pane: document is the primary focus, so it takes ~78% width
          when the findings sidebar is shown and 100% on the export-only tab. */}
      <div
        style={{
          flex: viewMode !== "corrected" ? "0 0 78%" : "1 1 100%",
          width: viewMode !== "corrected" ? "78%" : "100%",
          display: "flex",
          flexDirection: "column",
          background: "#cbd5e1",
          position: "relative"
        }}
      >
        {/* Live Stage Processing Status Header -- scoped to Proofreading pipeline completion */}
        {proofreadingDone ? (
          <div style={{
            background: "#f0fdf4",
            borderBottom: "1px solid #22c55e",
            padding: "8px 16px",
            fontSize: "12px",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            zIndex: 25
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: "12px", flexWrap: "wrap" }}>
              <span style={{ background: "#16a34a", color: "#ffffff", fontSize: "10px", fontWeight: 800, padding: "2px 6px", borderRadius: "4px" }}>
                PROOFREADING COMPLETED
              </span>
              <span><strong>Status:</strong> Completed</span>
              <span>•</span>
              <span><strong>Progress:</strong> 100%</span>
              {documentData?.total_pages > 0 && (
                <>
                  <span>•</span>
                  <span><strong>Pages:</strong> {documentData.total_pages}/{documentData.total_pages}</span>
                </>
              )}
              {documentData?.total_batches > 0 && (
                <>
                  <span>•</span>
                  <span><strong>Batch:</strong> {documentData.total_batches}/{documentData.total_batches}</span>
                </>
              )}
              <span>•</span>
              <span><strong>ETA:</strong> 0s</span>
              {isProcessing && (
                <span style={{ color: "#64748b", fontStyle: "italic", fontSize: "11px" }}>
                  (Downstream RAG & reports processing in background)
                </span>
              )}
            </div>
            <button onClick={handleRerunProofreading} style={{ ...styles.ctrlBtn, background: "#dcfce7", color: "#15803d", border: "1px solid #22c55e" }} disabled={isRerunning}>
              {isRerunning ? "Rerunning..." : "↻ Rerun Proofreading"}
            </button>
          </div>
        ) : isProcessing ? (
          <div style={{
            background: "#fffbeb",
            borderBottom: "1px solid #f59e0b",
            padding: "8px 16px",
            fontSize: "12px",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            zIndex: 25
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: "12px", flexWrap: "wrap" }}>
              <span style={{ background: "#d97706", color: "#ffffff", fontSize: "10px", fontWeight: 800, padding: "2px 6px", borderRadius: "4px" }}>
                PROOFREADING SCAN IN PROGRESS
              </span>
              <span><strong>Status:</strong> {documentData?.current_stage || "Scanning Text & Grammar Issues"}</span>
              <span>•</span>
              <span><strong>Progress:</strong> {documentData?.overall_progress || Math.round(documentData?.progress_percentage || 45)}%</span>
              {documentData?.total_pages > 0 && (
                <>
                  <span>•</span>
                  <span><strong>Pages:</strong> {documentData?.current_page || 0}/{documentData?.total_pages}</span>
                </>
              )}
              {documentData?.total_batches > 0 && (
                <>
                  <span>•</span>
                  <span><strong>Batch:</strong> {documentData?.current_batch || 0}/{documentData?.total_batches}</span>
                </>
              )}
              <span>•</span>
              <span><strong>ETA:</strong> {documentData?.estimated_remaining_time || "~1 min"}</span>
            </div>
            <button onClick={handleRerunProofreading} style={{ ...styles.ctrlBtn, background: "var(--brand-light)", color: "var(--brand)", border: "1px solid var(--brand)" }} disabled={isRerunning}>
              {isRerunning ? "Rerunning..." : "↻ Rerun Proofreading"}
            </button>
          </div>
        ) : null}

        {isFailed && (
          <div style={{
            background: "#fef2f2",
            borderBottom: "1px solid #dc2626",
            padding: "8px 16px",
            fontSize: "12px",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            zIndex: 25
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: "12px", flexWrap: "wrap" }}>
              <span style={{ background: "#dc2626", color: "#ffffff", fontSize: "10px", fontWeight: 800, padding: "2px 6px", borderRadius: "4px" }}>
                PROOFREADING FAILED
              </span>
              <span><strong>Failed stage:</strong> {documentData.current_stage || "Unknown"}</span>
              {documentData.error && (
                <span style={{ color: "#991b1b", maxWidth: "480px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={documentData.error}>
                  <strong>Reason:</strong> {String(documentData.error).split("\n")[0]}
                </span>
              )}
            </div>
            <button onClick={handleRerunProofreading} style={{ ...styles.ctrlBtn, background: "#fee2e2", color: "#991b1b", border: "1px solid #dc2626" }} disabled={isRerunning}>
              {isRerunning ? "Retrying..." : "↻ Retry"}
            </button>
          </div>
        )}

        {isRecoverable && (
          <div style={{
            background: "#eff6ff",
            borderBottom: "1px solid #3b82f6",
            padding: "8px 16px",
            fontSize: "12px",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            zIndex: 25
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: "12px", flexWrap: "wrap" }}>
              <span style={{ background: "#2563eb", color: "#ffffff", fontSize: "10px", fontWeight: 800, padding: "2px 6px", borderRadius: "4px" }}>
                RECOVERABLE
              </span>
              <span>Proofreading was interrupted and needs to be resumed before findings are up to date.</span>
            </div>
            <button onClick={handleRerunProofreading} style={{ ...styles.ctrlBtn, background: "#dbeafe", color: "#1d4ed8", border: "1px solid #3b82f6" }} disabled={isRerunning}>
              {isRerunning ? "Resuming..." : "↻ Resume / Rerun Proofreading"}
            </button>
          </div>
        )}

        {/* Tab bar */}
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            padding: "8px 16px",
            background: "var(--bg-card, #ffffff)",
            borderBottom: "1px solid var(--border, #e2e8f0)",
            zIndex: 20,
            boxShadow: "0 2px 8px rgba(0,0,0,0.05)"
          }}
        >
          <div style={{ display: "flex", gap: 4, background: "#f1f5f9", padding: 3, borderRadius: 6 }}>
            {isPdfOriginal && (
              <button
                onClick={() => setViewMode("pdf")}
                style={{
                  padding: "6px 16px", borderRadius: 5, fontSize: 12.5, fontWeight: 750, border: "none", cursor: "pointer",
                  background: viewMode === "pdf" ? "#ffffff" : "transparent",
                  color: viewMode === "pdf" ? "#4f46e5" : "#64748b",
                  boxShadow: viewMode === "pdf" ? "0 1px 3px rgba(0,0,0,0.1)" : "none"
                }}
              >
                Review
              </button>
            )}
            <button
              onClick={() => setViewMode("review")}
              style={{
                padding: "6px 16px", borderRadius: 5, fontSize: 12.5, fontWeight: 750, border: "none", cursor: "pointer",
                background: viewMode === "review" ? "#ffffff" : "transparent",
                color: viewMode === "review" ? "#4f46e5" : "#64748b",
                boxShadow: viewMode === "review" ? "0 1px 3px rgba(0,0,0,0.1)" : "none"
              }}
            >
              {isPdfOriginal ? "Text View" : "Review"}
            </button>
            <button
              onClick={() => setViewMode("corrected")}
              style={{
                padding: "6px 16px", borderRadius: 5, fontSize: 12.5, fontWeight: 750, border: "none", cursor: "pointer",
                background: viewMode === "corrected" ? "#ffffff" : "transparent",
                color: viewMode === "corrected" ? "#166534" : "#64748b",
                boxShadow: viewMode === "corrected" ? "0 1px 3px rgba(0,0,0,0.1)" : "none"
              }}
            >
              Live Corrected Preview
            </button>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            {viewMode === "pdf" && (
              <>
                <span style={{ fontSize: "12.5px", fontWeight: 700, color: "var(--text-primary, #0f172a)" }}>
                  Page {visiblePage} of {numPages}
                </span>
                <div style={{ display: "flex", alignItems: "center", gap: "4px" }}>
                  <button onClick={handleZoomOut} style={styles.ctrlBtn} title="Zoom Out">-</button>
                  <span style={{ fontSize: "11.5px", fontWeight: 700, minWidth: "40px", textAlign: "center" }}>
                    {Math.round(zoomLevel * 100)}%
                  </span>
                  <button onClick={handleZoomIn} style={styles.ctrlBtn} title="Zoom In">+</button>
                  <button onClick={handleZoomReset} style={styles.ctrlBtn}>Reset</button>
                </div>
              </>
            )}
            {isDone && (viewMode === "pdf" || viewMode === "review") && (
              /* Once completed, the status banner above is gone -- keep small,
                 always-reachable ways to re-check the document. */
              <>
                <button onClick={handleRerunProofreading} style={styles.ctrlBtn} disabled={isRerunning} title="Re-run Spell, Grammar and Validation and refresh findings">
                  {isRerunning ? "Rerunning..." : "↻ Rerun Proofreading"}
                </button>
                <button onClick={handleReprocessDocument} style={styles.ctrlBtn} disabled={isReprocessing} title="Re-run the full extraction (Docling) and rebuild page/sentence mapping from scratch">
                  {isReprocessing ? "Reprocessing..." : "⟳ Reprocess Document"}
                </button>
              </>
            )}
          </div>
        </div>

        {(viewMode === "pdf" || viewMode === "review") && findingActionError && (
          <div style={{
            display: "flex", justifyContent: "space-between", alignItems: "center",
            background: "#fef2f2", borderBottom: "1px solid #fecaca", color: "#991b1b",
            padding: "8px 16px", fontSize: "12px", fontWeight: 600,
          }}>
            <span>⚠ {findingActionError}</span>
            <button onClick={() => setFindingActionError(null)} style={{ background: "none", border: "none", color: "#991b1b", cursor: "pointer", fontWeight: 700 }}>✕</button>
          </div>
        )}

        {/* Tab content */}
        {viewMode === "pdf" ? (
          /* PRIMARY review surface: the real, untouched original PDF, with
             findings highlighted at their real PDF-grounded coordinates. */
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
                  const isNearVisibleWindow = Math.abs(pNum - visiblePage) <= 3 || numPages <= 10;
                  const pageFindings = findings.filter(
                    (f) => f.page_number === pNum && f.pdf_grounded && f.bbox && f.status !== "rejected"
                  );
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
                          {/* Highlight overlay: real bbox * zoomLevel, never a
                              synthetic box -- ungrounded findings simply have
                              no entry in pageFindings, so nothing is drawn. */}
                          <div style={{ position: "absolute", inset: 0, pointerEvents: "none" }}>
                            {pageFindings.map((f) => {
                              const isAccepted = f.status === "accepted";
                              const isSelected = f.finding_id === selectedFindingId;
                              const isFlashing = f.finding_id === flashingFindingId;
                              const bboxes = normalizeBboxes(f.bbox);

                              return bboxes.map((b, bIdx) => {
                                const left = b.x0 * zoomLevel;
                                const top = b.y0 * zoomLevel;
                                const width = Math.max(6, (b.x1 - b.x0) * zoomLevel);
                                const height = Math.max(6, (b.y1 - b.y0) * zoomLevel);

                                const bg = isAccepted
                                  ? (isSelected ? "rgba(22, 101, 52, 0.35)" : "rgba(22, 101, 52, 0.18)")
                                  : (isSelected || isFlashing ? "rgba(79, 70, 229, 0.38)" : "rgba(245, 158, 11, 0.28)");

                                const border = isAccepted
                                  ? (isSelected ? "2px solid #15803d" : "1.5px solid #166534")
                                  : (isSelected || isFlashing ? "2.5px solid #4f46e5" : "1.5px solid #d97706");

                                const boxShadow = isSelected || isFlashing
                                  ? "0 0 0 4px rgba(79, 70, 229, 0.45), 0 0 16px rgba(79, 70, 229, 0.7)"
                                  : "none";

                                return (
                                  <div
                                    key={`${f.finding_id}-${bIdx}`}
                                    style={{
                                      position: "absolute",
                                      left,
                                      top,
                                      width,
                                      height,
                                      pointerEvents: "auto",
                                      cursor: "pointer",
                                      background: bg,
                                      border,
                                      borderRadius: "3px",
                                      boxShadow,
                                      zIndex: isSelected || isFlashing ? 30 : 10,
                                      transition: "all 0.15s ease",
                                    }}
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      handleSelectFinding(f.finding_id, f);
                                    }}
                                  >
                                    {bIdx === 0 && popoverFindingId === f.finding_id && (
                                      <FindingPopover
                                        finding={f}
                                        style={{ top: height + 6, left: 0 }}
                                        onAccept={(id) => { handleAcceptFinding(id); }}
                                        onReject={(id) => { handleRejectFinding(id); }}
                                        onClose={() => setPopoverFindingId(null)}
                                      />
                                    )}
                                  </div>
                                );
                              });
                            })}
                          </div>
                        </>
                      ) : (
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
        ) : viewMode === "review" ? (
          <SentenceDocumentViewer
            docId={docId}
            findings={findings}
            selectedFindingId={selectedFindingId}
            flashingFindingId={flashingFindingId}
            acceptedFindingIds={acceptedFindingIds}
            rejectedFindingIds={rejectedFindingIds}
            onSelectFinding={handleSelectFinding}
            scrollRequest={scrollRequest}
          />
        ) : (
          <CorrectedPreviewPanel
            findings={findings}
            onExport={handleExportCorrected}
            isExporting={isExportingCorrected}
          />
        )}
      </div>

      {/* Findings sidebar -- Review tabs only (PDF or Text View); secondary
          to the document, used for navigation and accept/reject. */}
      {(viewMode === "pdf" || viewMode === "review") && (
        <div style={{ flex: "0 0 22%", width: "22%", height: "100%", borderLeft: "1px solid var(--border, #e2e8f0)", background: "#ffffff" }}>
          <IssueCardList
            findings={findings}
            selectedFindingId={selectedFindingId}
            onSelectFinding={handleSelectFinding}
            onAcceptFinding={handleAcceptFinding}
            onRejectFinding={handleRejectFinding}
            onUndoFinding={handleUndoFinding}
            documentStatus={sidebarStatus}
          />
        </div>
      )}
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
