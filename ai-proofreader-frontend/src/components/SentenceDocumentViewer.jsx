import React, { useState, useEffect, useRef, useCallback, useMemo } from "react";
import { fetchPageCount, fetchPageText } from "../api";

const RENDER_WINDOW = 3; // pages rendered on either side of the current viewport
const PREFETCH_WINDOW = 6; // pages whose text is fetched ahead of time

/**
 * SentenceDocumentViewer
 * ------------------------
 * Virtualized, page-on-demand document viewer built from the Page + Sentence
 * Mapping architecture (03_page_text / 04_sentences). Renders every sentence
 * wrapped in <span data-sentence-id="..."> and highlights only the specific
 * offending word (<mark>) rather than the whole sentence/page, so it stays
 * usable on 200+ page documents without ever mounting the full document.
 */
export default function SentenceDocumentViewer({
  docId,
  findings = [],
  selectedFindingId,
  flashingFindingId,
  acceptedFindingIds = new Set(),
  rejectedFindingIds = new Set(),
  onSelectFinding,
  scrollRequest, // { sentenceId, pageNumber, findingId, nonce }
}) {
  const [pageCount, setPageCount] = useState(0);
  const [visiblePage, setVisiblePage] = useState(1);
  const [pageCache, setPageCache] = useState(new Map());
  const containerRef = useRef(null);
  const pageNodeRefs = useRef(new Map());
  const fetchingRef = useRef(new Set());
  const observerRef = useRef(null);

  // Findings grouped by page, then by sentence, for O(1) lookup while rendering.
  const findingsByPage = useMemo(() => {
    const byPage = new Map();
    for (const f of findings || []) {
      if (!f || !f.page_number) continue;
      if (!byPage.has(f.page_number)) byPage.set(f.page_number, new Map());
      const bySentence = byPage.get(f.page_number);
      if (!bySentence.has(f.sentence_id)) bySentence.set(f.sentence_id, []);
      bySentence.get(f.sentence_id).push(f);
    }
    return byPage;
  }, [findings]);

  useEffect(() => {
    if (!docId) return;
    fetchPageCount(docId)
      .then((res) => setPageCount(res.page_count || 0))
      .catch(() => setPageCount(0));
  }, [docId]);

  const loadPage = useCallback((pageNumber) => {
    if (!docId || pageNumber < 1) return;
    if (pageCache.has(pageNumber) || fetchingRef.current.has(pageNumber)) return;
    fetchingRef.current.add(pageNumber);
    fetchPageText(docId, pageNumber)
      .then((res) => {
        setPageCache((prev) => {
          const next = new Map(prev);
          next.set(pageNumber, { text: res.text || "", sentences: res.sentences || [] });
          return next;
        });
      })
      .catch(() => {
        setPageCache((prev) => {
          const next = new Map(prev);
          next.set(pageNumber, { text: "", sentences: [], error: true });
          return next;
        });
      })
      .finally(() => fetchingRef.current.delete(pageNumber));
  }, [docId, pageCache]);

  // Prefetch text for pages around the current viewport.
  useEffect(() => {
    for (let p = Math.max(1, visiblePage - PREFETCH_WINDOW); p <= Math.min(pageCount, visiblePage + PREFETCH_WINDOW); p++) {
      loadPage(p);
    }
  }, [visiblePage, pageCount, loadPage]);

  // Track which page is currently in view via IntersectionObserver (robust to variable page heights).
  useEffect(() => {
    if (!containerRef.current || pageCount === 0) return;

    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio);
        if (visible.length > 0) {
          const pageNum = Number(visible[0].target.dataset.page);
          if (pageNum) setVisiblePage(pageNum);
        }
      },
      { root: containerRef.current, threshold: [0.1, 0.5] }
    );
    observerRef.current = observer;

    pageNodeRefs.current.forEach((node) => observer.observe(node));
    return () => observer.disconnect();
  }, [pageCount]);

  const registerPageNode = useCallback((pageNumber, node) => {
    const observer = observerRef.current;
    const prev = pageNodeRefs.current.get(pageNumber);
    if (prev && observer) observer.unobserve(prev);
    if (node) {
      pageNodeRefs.current.set(pageNumber, node);
      if (observer) observer.observe(node);
    } else {
      pageNodeRefs.current.delete(pageNumber);
    }
  }, []);

  // Handle navigation requests coming from the findings panel.
  useEffect(() => {
    if (!scrollRequest || !scrollRequest.pageNumber) return;
    const { sentenceId, pageNumber, findingId } = scrollRequest;

    const scrollToTarget = () => {
      const pageEl = pageNodeRefs.current.get(pageNumber);
      if (pageEl) pageEl.scrollIntoView({ behavior: "smooth", block: "start" });
      setTimeout(() => {
        // Prefer scrolling to the exact flagged word (<mark data-finding-id>);
        // fall back to the containing sentence if the finding has no resolved
        // word-level offsets (so no <mark> was rendered for it at all).
        const wordEl = findingId ? document.querySelector(`[data-finding-id="${findingId}"]`) : null;
        const target = wordEl || document.querySelector(`[data-sentence-id="${sentenceId}"]`);
        if (target) target.scrollIntoView({ behavior: "smooth", block: "center" });
      }, 180);
    };

    if (!pageCache.has(pageNumber)) {
      loadPage(pageNumber);
      const check = setInterval(() => {
        if (pageCache.has(pageNumber)) {
          clearInterval(check);
          setVisiblePage(pageNumber);
          setTimeout(scrollToTarget, 50);
        }
      }, 100);
      setTimeout(() => clearInterval(check), 5000);
    } else {
      setVisiblePage(pageNumber);
      scrollToTarget();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scrollRequest]);

  const renderSentence = (sentence, pageNumber) => {
    const bySentence = findingsByPage.get(pageNumber);
    const sentFindings = bySentence ? bySentence.get(sentence.sentence_id) || [] : [];

    if (sentFindings.length === 0) {
      return <span key={sentence.sentence_id} data-sentence-id={sentence.sentence_id}>{sentence.text} </span>;
    }

    // Build a list of (start, end, finding) spans sorted left-to-right, skipping
    // findings without resolved word-level offsets or that were rejected.
    const spans = sentFindings
      .filter((f) => f.token_start !== null && f.token_end !== null && f.token_start !== undefined)
      .filter((f) => !rejectedFindingIds.has(f.finding_id))
      .sort((a, b) => a.token_start - b.token_start);

    const text = sentence.text;
    const nodes = [];
    let cursor = 0;
    spans.forEach((f, i) => {
      if (f.token_start < cursor) return; // overlapping finding, skip
      if (f.token_start > cursor) nodes.push(text.slice(cursor, f.token_start));

      const isAccepted = acceptedFindingIds.has(f.finding_id);
      const isSelected = selectedFindingId === f.finding_id;
      const isFlashing = flashingFindingId === f.finding_id;
      const original = text.slice(f.token_start, f.token_end);

      nodes.push(
        <mark
          key={f.finding_id}
          data-finding-id={f.finding_id}
          className={isFlashing ? "finding-flash" : undefined}
          onClick={(e) => {
            e.stopPropagation();
            if (onSelectFinding) onSelectFinding(f.finding_id);
          }}
          title={`${f.error_type}: ${f.reason || ""} -> "${f.suggestion}"`}
          style={{
            cursor: "pointer",
            borderRadius: "3px",
            padding: "0 2px",
            transition: "background 0.2s ease",
            background: isAccepted ? "#dcfce7" : isSelected ? "#c7d2fe" : "#fef3c7",
            outline: isSelected ? "1.5px solid #4f46e5" : "none",
            color: isAccepted ? "#166534" : "#78350f",
          }}
        >
          {isAccepted ? (
            <>
              <span style={{ textDecoration: "line-through", opacity: 0.55 }}>{original}</span>{" "}
              <span style={{ fontWeight: 700 }}>{f.suggestion}</span>
            </>
          ) : (
            original
          )}
        </mark>
      );
      cursor = f.token_end;
    });
    if (cursor < text.length) nodes.push(text.slice(cursor));

    return (
      <span key={sentence.sentence_id} data-sentence-id={sentence.sentence_id}>
        {nodes}{" "}
      </span>
    );
  };

  const pageNumbers = Array.from({ length: pageCount }, (_, i) => i + 1);

  return (
    <div
      ref={containerRef}
      style={{
        flex: 1,
        overflowY: "auto",
        padding: "24px",
        background: "#f1f5f9",
        scrollBehavior: "smooth",
      }}
    >
      <div style={{ maxWidth: "820px", margin: "0 auto", display: "flex", flexDirection: "column", gap: "20px" }}>
        {pageCount === 0 && (
          <div style={{ padding: "60px 0", textAlign: "center", color: "#64748b", fontSize: "13px" }}>
            Loading document pages…
          </div>
        )}
        {pageNumbers.map((pNum) => {
          const inRenderWindow = Math.abs(pNum - visiblePage) <= RENDER_WINDOW || pageCount <= 10;
          const page = pageCache.get(pNum);
          return (
            <div
              key={pNum}
              data-page={pNum}
              ref={(node) => registerPageNode(pNum, node)}
              style={{
                background: "#ffffff",
                borderRadius: "8px",
                boxShadow: "0 4px 12px rgba(0,0,0,0.06)",
                minHeight: "300px",
                padding: "36px 44px",
              }}
            >
              <div style={{ fontSize: "11px", fontWeight: 700, color: "#94a3b8", marginBottom: "14px", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                Page {pNum} of {pageCount}
              </div>
              {inRenderWindow ? (
                page ? (
                  page.text ? (
                    <div style={{ fontFamily: "Georgia, serif", fontSize: "14.5px", lineHeight: 1.85, color: "#1e293b", whiteSpace: "pre-wrap" }}>
                      {page.sentences.length > 0
                        ? page.sentences.map((s) => renderSentence(s, pNum))
                        : page.text}
                    </div>
                  ) : (
                    <div style={{ color: "#94a3b8", fontSize: "12.5px", fontStyle: "italic" }}>
                      (No running text on this page — table/image/figure content only)
                    </div>
                  )
                ) : (
                  <div style={{ color: "#94a3b8", fontSize: "12.5px" }}>Loading page {pNum}…</div>
                )
              ) : (
                <div style={{ color: "#cbd5e1", fontSize: "12.5px" }}>Page {pNum} — scroll to load</div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
