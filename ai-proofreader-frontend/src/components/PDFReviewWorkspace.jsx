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

const MIN_ZOOM = 0.25;
const MAX_ZOOM = 3.0;
const PAGE_VIEW_PADDING = 24; // must match the horizontal padding applied to the page-view wrapper below

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
  // Once the user explicitly zooms in/out, the page-view stops auto-fitting
  // to the panel width and stops auto-zooming to focus a newly selected
  // error -- the user's chosen zoom is preserved across error navigation
  // and panel resizes until they hit "Fit".
  const [hasManualZoom, setHasManualZoom] = useState(false);
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
  const [activeFocusTarget, setActiveFocusTarget] = useState(null);
  const [scrollRequest, setScrollRequest] = useState(null);
  const [isExportingCorrected, setIsExportingCorrected] = useState(false);
  const [findingActionError, setFindingActionError] = useState(null);

  const scrollContainerRef = useRef(null);
  const focusRetryTimeoutRef = useRef(null);
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

  const stage4Failed = documentData?.stages?.some((s) => s.stage_id === "stage_4_grammar" && s.status === "Failed");
  const proofreadingFailed = documentData?.proofreading_status === "failed" || stage4Failed;

  const docStatus = documentData?.status;
  const isProcessing = (docStatus === "processing" || docStatus === "pending") && !proofreadingFailed;
  const isFailed = docStatus === "failed" || proofreadingFailed;
  const isRecoverable = docStatus === "recoverable" && !proofreadingFailed;
  const isDone = (docStatus === "completed" || docStatus === "completed_with_warnings") && !proofreadingFailed;

  const proofreadingReady = (documentData?.proofreading_ready || documentData?.proofreading_status === "completed") && !proofreadingFailed;
  const proofreadingStatus = proofreadingFailed ? "failed" : (documentData?.proofreading_status || (proofreadingReady || isDone ? "completed" : "pending"));
  const proofreadingDone = proofreadingStatus === "completed" && proofreadingReady === true;
  const sidebarStatus = proofreadingFailed ? "failed" : (proofreadingDone ? "completed" : docStatus);

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

  function computeUnionBbox(bboxes) {
    if (!bboxes || bboxes.length === 0) return null;
    return bboxes.reduce(
      (acc, b) => ({
        x0: Math.min(acc.x0, b.x0),
        y0: Math.min(acc.y0, b.y0),
        x1: Math.max(acc.x1, b.x1),
        y1: Math.max(acc.y1, b.y1),
      }),
      { x0: Infinity, y0: Infinity, x1: -Infinity, y1: -Infinity }
    );
  }

  const calculateFitWidthZoom = () => {
    if (!scrollContainerRef.current || !pageDimensions.width) return 1.0;
    const cWidth = scrollContainerRef.current.clientWidth || 800;
    const available = Math.max(100, cWidth - PAGE_VIEW_PADDING * 2);
    const fitZoom = available / pageDimensions.width;
    return Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, fitZoom));
  };

  const calculateOptimalZoom = (unionBbox) => {
    if (!scrollContainerRef.current || !unionBbox) return 1.5;
    const cWidth = scrollContainerRef.current.clientWidth || 800;
    const cHeight = scrollContainerRef.current.clientHeight || 600;

    const bboxW = Math.max(16, unionBbox.x1 - unionBbox.x0);
    const bboxH = Math.max(16, unionBbox.y1 - unionBbox.y0);

    // Calculate zoom level to make the error word/phrase prominent (approx 35-45% of viewport)
    const fitWZoom = (cWidth * 0.45) / bboxW;
    const fitHZoom = (cHeight * 0.35) / bboxH;

    const idealZoom = Math.min(fitWZoom, fitHZoom);
    return Math.max(1.5, Math.min(2.2, idealZoom));
  };

  const performFocusAndCenter = (targetObj, currentZoom = zoomLevel) => {
    if (!targetObj || !scrollContainerRef.current) return false;
    const { pageNumber, unionBbox } = targetObj;
    const pageEl = document.getElementById(`pdf-page-${pageNumber}`);
    if (!pageEl) return false;

    const container = scrollContainerRef.current;
    const cWidth = container.clientWidth;
    const cHeight = container.clientHeight;
    if (cWidth === 0 || cHeight === 0) return false;

    const pageTop = pageEl.offsetTop;
    const pageLeft = pageEl.offsetLeft;

    let targetScrollTop = pageTop;
    let targetScrollLeft = 0;

    if (unionBbox) {
      const centerX = ((unionBbox.x0 + unionBbox.x1) / 2) * currentZoom;
      const centerY = ((unionBbox.y0 + unionBbox.y1) / 2) * currentZoom;

      const absoluteX = pageLeft + centerX;
      const absoluteY = pageTop + centerY;

      targetScrollTop = Math.max(0, absoluteY - cHeight / 2);
      targetScrollLeft = Math.max(0, absoluteX - cWidth / 2);
    } else {
      targetScrollTop = Math.max(0, pageTop - 20);
    }

    container.scrollTo({
      top: targetScrollTop,
      left: targetScrollLeft,
      behavior: "smooth"
    });
    return true;
  };

  const triggerFocus = (targetObj, desiredZoom) => {
    if (focusRetryTimeoutRef.current) clearTimeout(focusRetryTimeoutRef.current);
    if (!targetObj) return;

    const effectiveZoom = desiredZoom !== undefined ? desiredZoom : zoomLevel;
    let attempts = 0;

    const attemptScroll = () => {
      attempts++;
      const pageEl = document.getElementById(`pdf-page-${targetObj.pageNumber}`);
      if (pageEl) {
        performFocusAndCenter(targetObj, effectiveZoom);
      }
      if (attempts < 12) {
        focusRetryTimeoutRef.current = setTimeout(attemptScroll, 100);
      }
    };

    attemptScroll();
  };

  // Re-center when active focus target or zoom changes
  useEffect(() => {
    if (activeFocusTarget && viewMode === "pdf") {
      performFocusAndCenter(activeFocusTarget, zoomLevel);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeFocusTarget, zoomLevel, viewMode]);

  // Fit the page to the available panel width by default. Runs once the
  // first page's real dimensions are known, and again whenever the panel is
  // resized -- but only until the user takes manual control of zoom.
  useEffect(() => {
    if (viewMode !== "pdf" || hasManualZoom) return;
    setZoomLevel(calculateFitWidthZoom());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [viewMode, hasManualZoom, pageDimensions.width]);

  // Recalculate center position (and, while un-zoomed by the user, the
  // fit-to-width scale) when the PDF panel is resized.
  useEffect(() => {
    const container = scrollContainerRef.current;
    if (!container) return;

    const observer = new ResizeObserver(() => {
      if (viewMode !== "pdf") return;
      if (!hasManualZoom) {
        setZoomLevel(calculateFitWidthZoom());
      }
      if (activeFocusTarget) {
        triggerFocus(activeFocusTarget, hasManualZoom ? zoomLevel : calculateFitWidthZoom());
      }
    });

    observer.observe(container);
    return () => observer.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeFocusTarget, viewMode, zoomLevel, hasManualZoom, pageDimensions.width]);

  const handleClosePopover = (e) => {
    if (e && e.stopPropagation) {
      e.stopPropagation();
    }
    setPopoverFindingId(null);
    setSelectedFindingId(null);
    setActiveFocusTarget(null);
  };

  const handleSelectFinding = (findingId, findingObj) => {
    const target = findingObj || findings.find((f) => f.finding_id === findingId);
    if (!target) return;

    setSelectedFindingId(findingId);

    if (viewMode === "pdf") {
      const isGrounded = target.pdf_grounded === true && !!target.bbox;
      const bboxes = isGrounded ? normalizeBboxes(target.bbox) : [];

      if (isGrounded && bboxes.length > 0) {
        const unionBbox = computeUnionBbox(bboxes);
        // Once the user has taken manual control of zoom, respect it --
        // navigating between errors must never reset their chosen zoom
        // level, only scroll/center the page at that zoom.
        const targetZoom = hasManualZoom ? zoomLevel : calculateOptimalZoom(unionBbox);

        const focusTarget = {
          findingId,
          pageNumber: target.page_number,
          unionBbox,
          bboxes,
          timestamp: Date.now()
        };

        setFlashingFindingId(findingId);
        setPopoverFindingId(findingId);
        setActiveFocusTarget(focusTarget);
        setVisiblePage(target.page_number);

        if (!hasManualZoom && Math.abs(zoomLevel - targetZoom) > 0.05) {
          setZoomLevel(targetZoom);
        }

        triggerFocus(focusTarget, targetZoom);

        setTimeout(() => {
          setFlashingFindingId((current) => (current === findingId ? null : current));
        }, 5000);
      } else {
        // Grounded === false (Unanchored)
        setPopoverFindingId(null);
        setActiveFocusTarget(null);
        if (target.page_number) {
          setVisiblePage(target.page_number);
          setTimeout(() => {
            const pageEl = document.getElementById(`pdf-page-${target.page_number}`);
            if (pageEl && scrollContainerRef.current) {
              scrollContainerRef.current.scrollTo({
                top: Math.max(0, pageEl.offsetTop - 40),
                behavior: "smooth"
              });
            }
          }, 100);
        }
      }
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

  const handlePageRenderSuccess = (pageNumber) => {
    if (activeFocusTarget && activeFocusTarget.pageNumber === pageNumber) {
      performFocusAndCenter(activeFocusTarget, zoomLevel);
    }
  };

  const handleZoomIn = () => {
    setHasManualZoom(true);
    setZoomLevel((prev) => Math.min(prev + 0.2, MAX_ZOOM));
  };
  const handleZoomOut = () => {
    setHasManualZoom(true);
    setZoomLevel((prev) => Math.max(prev - 0.2, MIN_ZOOM));
  };
  const handleZoomReset = () => {
    setHasManualZoom(false);
    setZoomLevel(calculateFitWidthZoom());
  };

  // Trackpad pinch-to-zoom (and ctrl+scroll-wheel) support. Browsers report
  // both a two-finger trackpad pinch and an explicit ctrl+wheel as native
  // "wheel" events with ctrlKey set to true -- there is no separate pinch
  // event to listen for. A plain two-finger scroll (no ctrlKey) is left
  // alone so normal vertical/horizontal panning still works untouched.
  //
  // This is wired up as a native, non-passive addEventListener (see effect
  // below) rather than React's onWheel prop: React attaches wheel handlers
  // passively by default, so e.preventDefault() inside a synthetic onWheel
  // does not reliably stop the browser's own pinch-zoom/page-zoom.
  useEffect(() => {
    const container = scrollContainerRef.current;
    if (!container || viewMode !== "pdf") return;

    const onWheel = (e) => {
      if (!e.ctrlKey) return;
      e.preventDefault();
      setHasManualZoom(true);
      // deltaY is negative for zoom-in (pinch-out / scroll-up), positive for
      // zoom-out; scale the step down since trackpads report much larger
      // per-event deltas than a single click of the +/- buttons.
      const step = -e.deltaY * 0.01;
      setZoomLevel((prev) => Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, prev + step)));
    };

    container.addEventListener("wheel", onWheel, { passive: false });
    return () => container.removeEventListener("wheel", onWheel);
  }, [viewMode]);

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
        height: "calc(100vh - 108px)",
        minHeight: "600px",
        background: "var(--bg-main, #f1f5f9)",
        borderRadius: "10px",
        overflow: "hidden",
        border: "1px solid var(--border, #e2e8f0)",
        boxShadow: "var(--shadow-card, 0 2px 6px -1px rgba(0, 0, 0, 0.08))"
      }}
    >
      {/* Main pane: document is the primary focus */}
      <div
        style={{
          flex: viewMode !== "corrected" ? "1 1 80%" : "1 1 100%",
          minWidth: 0,
          display: "flex",
          flexDirection: "column",
          background: "#cbd5e1",
          position: "relative"
        }}
      >
        {/* Live Stage Processing Status Header -- compact, single line, no per-banner action button (the toolbar below owns the one Rerun/Reprocess pair). */}
        {proofreadingDone ? (
          <div style={styles.statusBar}>
            <span style={{ ...styles.statusPill, background: "#16a34a" }}>PROOFREADING COMPLETED</span>
            <span>100% complete</span>
            {documentData?.total_pages > 0 && <span>• {documentData.total_pages} pages</span>}
            {isProcessing && <span style={{ color: "#64748b", fontStyle: "italic" }}>• Additional analysis still running in background</span>}
          </div>
        ) : isProcessing ? (
          <div style={{ ...styles.statusBar, background: "#fffbeb", borderBottom: "1px solid #f59e0b" }}>
            <span style={{ ...styles.statusPill, background: "#d97706" }}>SCAN IN PROGRESS</span>
            <span>{documentData?.current_stage || "Scanning Text & Grammar Issues"}</span>
            <span>• {documentData?.overall_progress || Math.round(documentData?.progress_percentage || 45)}%</span>
            <span>• ETA {documentData?.estimated_remaining_time || "~1 min"}</span>
          </div>
        ) : null}

        {isFailed && (
          <div style={{ ...styles.statusBar, background: "#fef2f2", borderBottom: "1px solid #dc2626" }}>
            <span style={{ ...styles.statusPill, background: "#dc2626" }}>PROOFREADING FAILED</span>
            <span>{documentData.current_stage || "Unknown stage"}</span>
            {documentData.error && (
              <span style={{ color: "#991b1b", maxWidth: "420px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={documentData.error}>
                • {String(documentData.error).split("\n")[0]}
              </span>
            )}
          </div>
        )}

        {isRecoverable && (
          <div style={{ ...styles.statusBar, background: "#eff6ff", borderBottom: "1px solid #3b82f6" }}>
            <span style={{ ...styles.statusPill, background: "#2563eb" }}>RECOVERABLE</span>
            <span>Interrupted -- resume to bring findings up to date.</span>
          </div>
        )}

        {/* Tab bar + toolbar (compact, single row) */}
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            flexWrap: "wrap",
            rowGap: 6,
            padding: "6px 14px",
            background: "var(--bg-card, #ffffff)",
            borderBottom: "1px solid var(--border, #e2e8f0)",
            zIndex: 20,
            boxShadow: "0 1px 4px rgba(0,0,0,0.04)"
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
                  <button onClick={handleZoomReset} style={styles.ctrlBtn} title="Fit to panel width">Fit</button>
                </div>
              </>
            )}
            {/* Single instance of each action button, always in the toolbar -- no duplicate copies in the status banners above. */}
            {(viewMode === "pdf" || viewMode === "review") && (isDone || isProcessing || isFailed || isRecoverable) && (
              <>
                <button onClick={handleRerunProofreading} style={styles.ctrlBtn} disabled={isRerunning} title="Re-run Spell, Grammar and Validation and refresh findings">
                  {isRerunning ? "Rerunning..." : isFailed ? "↻ Retry" : isRecoverable ? "↻ Resume Proofreading" : "↻ Rerun Proofreading"}
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
          <div
            ref={scrollContainerRef}
            style={{
              flex: 1,
              position: "relative",
              overflowY: "auto",
              overflowX: "auto",
              scrollBehavior: "smooth"
            }}
          >
            {/* Plain block wrapper, not a flex/align-items:center container --
                that combination clips the far edge of a scroll region when
                content overflows the viewport, making it impossible to
                scroll all the way to one side when zoomed in. margin:auto on
                a block box centers it when it's narrower than the panel
                while still allowing full scroll travel once it's wider. */}
            <div
              style={{
                width: "fit-content",
                minWidth: "100%",
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                padding: "24px",
                boxSizing: "border-box",
                gap: "24px",
                margin: "0 auto"
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
                  const isSelectedPage = activeFocusTarget?.pageNumber === pNum;
                  const isNearVisibleWindow = Math.abs(pNum - visiblePage) <= 3 || isSelectedPage || numPages <= 10;
                  const pageFindings = findings.filter(
                    (f) => f.page_number === pNum && f.pdf_grounded === true && f.bbox && f.status !== "rejected"
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
                            onRenderSuccess={() => handlePageRenderSuccess(pNum)}
                            renderAnnotationLayer={false}
                            renderTextLayer={false}
                          />
                          {/* Highlight overlay for pdf_grounded findings */}
                          <div style={{ position: "absolute", inset: 0, pointerEvents: "none" }}>
                            {pageFindings.map((f) => {
                              const isAccepted = f.status === "accepted";
                              const isSelected = f.finding_id === selectedFindingId;
                              const isFlashing = f.finding_id === flashingFindingId;
                              const bboxes = normalizeBboxes(f.bbox);
                              const union = bboxes.length > 1 ? computeUnionBbox(bboxes) : null;

                              return (
                                <React.Fragment key={f.finding_id}>
                                  {bboxes.map((b, bIdx) => {
                                    const left = b.x0 * zoomLevel;
                                    const top = b.y0 * zoomLevel;
                                    const width = Math.max(6, (b.x1 - b.x0) * zoomLevel);
                                    const height = Math.max(6, (b.y1 - b.y0) * zoomLevel);

                                    const bg = isAccepted
                                      ? (isSelected ? "rgba(34, 197, 94, 0.35)" : "rgba(34, 197, 94, 0.18)")
                                      : (isSelected || isFlashing ? "rgba(250, 204, 21, 0.45)" : "rgba(245, 158, 11, 0.28)");

                                    const border = isAccepted
                                      ? (isSelected ? "2px solid #15803d" : "1.5px solid #166534")
                                      : (isSelected || isFlashing ? "2.5px solid #d97706" : "1.5px solid #d97706");

                                    const boxShadow = isSelected || isFlashing
                                      ? "0 0 0 4px rgba(234, 179, 8, 0.5), 0 0 16px rgba(217, 119, 6, 0.6)"
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
                                            onClose={handleClosePopover}
                                          />
                                        )}
                                      </div>
                                    );
                                  })}

                                  {/* Multi-word phrase bounding outline if selected */}
                                  {union && (isSelected || isFlashing) && (
                                    <div
                                      style={{
                                        position: "absolute",
                                        left: union.x0 * zoomLevel - 3,
                                        top: union.y0 * zoomLevel - 3,
                                        width: (union.x1 - union.x0) * zoomLevel + 6,
                                        height: (union.y1 - union.y0) * union.y0 > 0 ? (union.y1 - union.y0) * zoomLevel + 6 : 12,
                                        pointerEvents: "none",
                                        border: "2px dashed #d97706",
                                        borderRadius: "4px",
                                        zIndex: 29,
                                      }}
                                    />
                                  )}
                                </React.Fragment>
                              );
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

      {/* Findings sidebar */}
      {(viewMode === "pdf" || viewMode === "review") && (
        <div style={{ flex: "0 0 clamp(260px, 20%, 340px)", height: "100%", borderLeft: "1px solid var(--border, #e2e8f0)", background: "#ffffff", overflow: "hidden" }}>
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
  },
  statusBar: {
    background: "#f0fdf4",
    borderBottom: "1px solid #22c55e",
    padding: "5px 14px",
    fontSize: "11.5px",
    display: "flex",
    alignItems: "center",
    gap: "8px",
    flexWrap: "wrap",
    zIndex: 25
  },
  statusPill: {
    color: "#ffffff",
    fontSize: "9.5px",
    fontWeight: 800,
    padding: "1.5px 6px",
    borderRadius: "4px",
    letterSpacing: "0.2px"
  }
};
