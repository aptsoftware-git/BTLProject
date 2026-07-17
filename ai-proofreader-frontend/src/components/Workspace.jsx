import React, { useState, useEffect, useRef, useMemo } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { fetchDocument, fetchPreferences } from "../api";
import Assistant from "./Assistant";
import ContextAnalysis from "./ContextAnalysis";


const buildDecidedText = (rawText, issues, decisions) => {
  if (!rawText) return "";
  if (!issues) return rawText;

  const sortedIssues = [...issues]
    .filter(i => i && i.char_start !== undefined && i.char_end !== undefined)
    .sort((a, b) => a.char_start - b.char_start);

  let result = "";
  let cursor = 0;

  sortedIssues.forEach((issue) => {
    if (issue.char_start < cursor || issue.char_start > rawText.length) {
      return;
    }

    if (issue.char_start > cursor) {
      result += rawText.slice(cursor, issue.char_start);
    }

    const originalIndex = issues.indexOf(issue);
    const decision = decisions ? decisions[originalIndex] : undefined;

    if (decision === "accepted") {
      result += issue.suggested_text || "";
    } else {
      result += rawText.slice(issue.char_start, issue.char_end);
    }

    cursor = issue.char_end;
  });

  if (cursor < rawText.length) {
    result += rawText.slice(cursor);
  }

  return result;
};

const getCategory = (reason) => {
  if (!reason) return "Technical Terms";
  const lower = String(reason).toLowerCase();
  if (lower.includes("user")) return "User-defined Terms";
  if (lower.includes("person") || lower.includes("author")) return "Person Names";
  if (lower.includes("org") || lower.includes("company")) return "Company Names";
  if (lower.includes("product")) return "Product Names";
  if (lower.includes("brand")) return "Brand Names";
  if (lower.includes("pronoun")) return "Pronouns";
  return "Technical Terms";
};

export default function Workspace() {
  const { id } = useParams();
  const navigate = useNavigate();

  const [doc, setDoc] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // User preferences & threshold
  const [preferences, setPreferences] = useState({ confidence_threshold: 40 });

  // Workspace active states
  const [activeTab, setActiveTab] = useState("annotated"); // annotated | corrected
  const [activeIssueIdx, setActiveIssueIdx] = useState(null);
  const [issueDecisions, setIssueDecisions] = useState({});
  
  // HTML state
  const [annotatedHtml, setAnnotatedHtml] = useState("");

  // Toolbar states
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("all");
  const [sortBy, setSortBy] = useState("index");

  const [protectedOpen, setProtectedOpen] = useState(false);
  const textContainerRef = useRef(null);

  const handleShowInDocument = (page, text, objectId) => {
    setActiveTab("annotated");
    setTimeout(() => {
      const container = textContainerRef.current;
      if (!container) return;

      // Clear previous context highlights
      const oldHighlights = container.querySelectorAll(".context-highlight");
      oldHighlights.forEach(el => {
        el.classList.remove("context-highlight");
        el.style.backgroundColor = "";
        el.style.outline = "";
        el.style.boxShadow = "";
      });

      // Find the element containing the text or page index
      const cleanText = (text || "").replace(/["'...]/g, "").trim().substring(0, 100);
      let foundEl = null;

      if (cleanText.length > 5) {
        const els = container.querySelectorAll("p, div, span, h1, h2, h3, h4, h5, li, mark");
        for (let el of els) {
          if (el.textContent.includes(cleanText)) {
            foundEl = el;
            break;
          }
        }
      }

      if (!foundEl && page) {
        // Fallback: search for page marker in text
        const els = container.querySelectorAll("p, div, span, h1, h2, h3, h4, h5, li");
        for (let el of els) {
          const t = el.textContent;
          if (t.includes(`Page ${page}`) || t.includes(`[Page ${page}]`) || t.includes(`page ${page}`)) {
            foundEl = el;
            break;
          }
        }
      }

      if (foundEl) {
        foundEl.scrollIntoView({ behavior: "smooth", block: "center" });
        foundEl.classList.add("context-highlight");
        foundEl.style.backgroundColor = "rgba(254, 240, 138, 0.7)";
        foundEl.style.outline = "2px solid #eab308";
        foundEl.style.borderRadius = "4px";
      }
    }, 200);
  };


  // Dynamic status check polling
  useEffect(() => {
    let active = true;
    let timerId = null;

    async function load() {
      try {
        const [data, prefs] = await Promise.all([
          fetchDocument(id),
          fetchPreferences().catch(() => ({ confidence_threshold: 40 }))
        ]);
        
        if (!active) return;
        setPreferences(prefs || { confidence_threshold: 40 });
        setDoc(data);

        // Process HTML/State only once when loaded
        if (data && data.status === "completed") {
          const threshold = ((prefs && prefs.confidence_threshold !== undefined) ? prefs.confidence_threshold : 40) / 100;
          const initialStatus = {};

          if (data.raw_text) {
            setIssueDecisions({});
          } else if (data.annotated_html && !annotatedHtml) {
            const parser = new DOMParser();
            const htmlDoc = parser.parseFromString(data.annotated_html, "text/html");
            const marks = htmlDoc.querySelectorAll("mark");

            (data.issues || []).forEach((issue, idx) => {
              if (!issue) return;
              const conf = issue.final_confidence || issue.confidence || 0;
              const mark = marks[idx];
              
              if (conf <= threshold) {
                if (mark && mark.parentNode) {
                  const textNode = htmlDoc.createTextNode(mark.textContent);
                  mark.parentNode.replaceChild(textNode, mark);
                }
              } else {
                if (mark) {
                  mark.setAttribute("data-issue-idx", String(idx));
                  const severity = issue.severity || "medium";
                  mark.className = `sev-${severity} pending-highlight`;
                }
              }
            });

            setIssueDecisions({});
            setAnnotatedHtml(htmlDoc.body.innerHTML);
          }
        }

        setLoading(false);
        
        // If still processing or pending, poll every 2 seconds
        if (data.status === "processing" || data.status === "pending") {
          timerId = setTimeout(load, 2000);
        }
      } catch (err) {
        if (active) {
          setError(err.message || "Failed to load document.");
          setLoading(false);
        }
      }
    }

    load();

    return () => {
      active = false;
      if (timerId) clearTimeout(timerId);
    };
  }, [id]);

  // Select an issue and scroll suggestions sidebar and/or markup
  const handleSelectIssue = (idx) => {
    setActiveIssueIdx(idx);
    
    // Scroll editor view to the mark
    const mark = textContainerRef.current?.querySelector(`mark[data-issue-idx="${idx}"]`);
    if (mark) {
      mark.scrollIntoView({ behavior: "smooth", block: "center" });
      const allMarks = textContainerRef.current.querySelectorAll("mark");
      allMarks.forEach((m) => m.classList.remove("active-highlight", "active-glow"));
      mark.classList.add("active-highlight", "active-glow");
    }

    // Scroll sidebar suggestion card into view
    const card = document.getElementById(`suggestion-${idx}`);
    if (card) {
      card.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  };

  // Helper to extract paragraph body from HTML
  const getParagraphBody = (htmlStr) => {
    if (!htmlStr) return "";
    try {
      const parser = new DOMParser();
      const tempDoc = parser.parseFromString(htmlStr, "text/html");
      const paragraphs = tempDoc.querySelectorAll(".paragraph");
      if (paragraphs.length === 0) {
        return tempDoc.body.innerHTML || htmlStr;
      }
      return Array.from(paragraphs).map(p => p.outerHTML).join("\n");
    } catch (e) {
      return htmlStr;
    }
  };

  // Render document markup dynamically from raw text + issue boundaries
  const renderDocumentMarkup = () => {
    if (!doc || !doc.raw_text) return null;

    // 1. Sort a copy of issues by char_start ascending
    const sortedIssues = (doc.issues || [])
      .map((issue, idx) => (issue ? { ...issue, originalIndex: idx } : null))
      .filter((issue) => {
        return issue && !isFiltered(issue);
      });

    sortedIssues.sort((a, b) => (a.char_start || 0) - (b.char_start || 0));

    // 2. Walk doc.raw_text
    const elements = [];
    let cursor = 0;

    sortedIssues.forEach((issue) => {
      const idx = issue.originalIndex;
      
      if (issue.char_start < cursor || issue.char_start > doc.raw_text.length) {
        return;
      }

      // Add text before the issue
      if (issue.char_start > cursor) {
        elements.push(doc.raw_text.slice(cursor, issue.char_start));
      }

      const decision = issueDecisions[idx];

      if (decision === "accepted") {
        elements.push(
          <mark
            key={`mark-${idx}`}
            className="applied"
            style={{
              backgroundColor: "#E2F0D9", // light green background
              color: "#385723",
              padding: "1px 2px",
              borderRadius: "3px",
              textDecoration: "none",
              border: "none",
              cursor: "default"
            }}
          >
            {issue.suggested_text}
          </mark>
        );
      } else if (decision === "rejected") {
        elements.push(doc.raw_text.slice(issue.char_start, issue.char_end));
      } else {
        const severity = issue.severity || "medium";
        const accentClass = `sev-${severity}`;
        const isSelected = activeIssueIdx === idx;

        elements.push(
          <mark
            key={`mark-${idx}`}
            data-issue-idx={idx}
            className={`${accentClass} pending-highlight ${isSelected ? "active-highlight active-glow" : ""}`}
            style={{ cursor: "pointer" }}
            onClick={() => handleSelectIssue(idx)}
          >
            {doc.raw_text.slice(issue.char_start, issue.char_end)}
          </mark>
        );
      }

      cursor = issue.char_end;
    });

    // Add trailing text
    if (cursor < doc.raw_text.length) {
      elements.push(doc.raw_text.slice(cursor));
    }

    return elements;
  };

  // Helper to determine if an issue is confidence filtered
  const isFiltered = (issue) => {
    if (!issue) return true;
    const conf = issue.final_confidence || issue.confidence || 0;
    const threshold = ((preferences && preferences.confidence_threshold !== undefined) ? preferences.confidence_threshold : 40) / 100;
    return conf <= threshold;
  };

  // 1. Get filtered issues list based on search/filters
  const visibleIssues = useMemo(() => {
    if (!doc || !doc.issues) return [];
    
    return (doc.issues || [])
      .map((issue, idx) => (issue ? { ...issue, originalIndex: idx } : null))
      .filter((issue) => {
        if (!issue) return false;
        
        // Exclude filtered (confidence <= threshold)
        if (isFiltered(issue)) return false;

        // Apply Search with safety fallbacks
        const origText = issue.original_text || "";
        const sugText = issue.suggested_text || "";
        const reasonText = issue.reason || "";
        const query = search || "";

        const matchSearch =
          origText.toLowerCase().includes(query.toLowerCase()) ||
          sugText.toLowerCase().includes(query.toLowerCase()) ||
          reasonText.toLowerCase().includes(query.toLowerCase());

        // Apply Type Filter
        let matchType = true;
        if (typeFilter !== "all") {
          const type = issue.issue_type || "";
          if (typeFilter === "spelling") {
            matchType = type === "spelling" || type === "punctuation";
          } else {
            matchType = type === typeFilter;
          }
        }

        return matchSearch && matchType;
      })
      .sort((a, b) => {
        // Apply Sort
        if (sortBy === "confidence") {
          const confA = a.final_confidence || a.confidence || 0;
          const confB = b.final_confidence || b.confidence || 0;
          return confB - confA;
        }
        if (sortBy === "confidence-asc") {
          const confA = a.final_confidence || a.confidence || 0;
          const confB = b.final_confidence || b.confidence || 0;
          return confA - confB;
        }
        if (sortBy === "alphabetical") {
          const textA = a.original_text || "";
          const textB = b.original_text || "";
          return textA.localeCompare(textB);
        }
        // Default: original index
        return (a.originalIndex ?? 0) - (b.originalIndex ?? 0);
      });
  }, [doc, search, typeFilter, sortBy, preferences?.confidence_threshold]);

  const groupedTerms = useMemo(() => {
    const groups = {
      "User-defined Terms": [],
      "Person Names": [],
      "Company Names": [],
      "Product Names": [],
      "Brand Names": [],
      "Technical Terms": [],
      "Pronouns": []
    };
    
    if (doc && doc.protected_terms) {
      doc.protected_terms.forEach((term) => {
        if (!term) return;
        const cat = getCategory(term.reason);
        if (groups[cat]) {
          const termText = term.text || "";
          if (!groups[cat].some(t => (t.text || "").toLowerCase() === termText.toLowerCase())) {
            groups[cat].push(term);
          }
        }
      });
    }
    return groups;
  }, [doc]);

  // Handle Accept
  const acceptIssue = (idx) => {
    setIssueDecisions((prev) => ({ ...prev, [idx]: "accepted" }));

    // Fallback path DOM update
    if (!doc.raw_text && annotatedHtml) {
      const issue = doc.issues[idx];
      const parser = new DOMParser();
      const tempDoc = parser.parseFromString(annotatedHtml, "text/html");
      const mark = tempDoc.querySelector(`mark[data-issue-idx="${idx}"]`);
      if (mark) {
        mark.textContent = issue.suggested_text;
        mark.className = "corrected";
        mark.style.backgroundColor = "var(--green-light)";
        mark.style.color = "var(--green)";
        mark.style.borderBottom = "none";
        mark.style.textDecoration = "none";
        mark.removeAttribute("data-tooltip");
      }
      setAnnotatedHtml(tempDoc.body.innerHTML);
    }
  };

  // Handle Reject
  const rejectIssue = (idx) => {
    setIssueDecisions((prev) => ({ ...prev, [idx]: "rejected" }));

    // Fallback path DOM update
    if (!doc.raw_text && annotatedHtml) {
      const parser = new DOMParser();
      const tempDoc = parser.parseFromString(annotatedHtml, "text/html");
      const mark = tempDoc.querySelector(`mark[data-issue-idx="${idx}"]`);
      if (mark && mark.parentNode) {
        const textNode = tempDoc.createTextNode(mark.textContent);
        mark.parentNode.replaceChild(textNode, mark);
      }
      setAnnotatedHtml(tempDoc.body.innerHTML);
    }
  };

  // Handle Undo
  const undoDecision = (idx) => {
    setIssueDecisions((prev) => {
      const { [idx]: omitted, ...rest } = prev;
      return rest;
    });

    // Fallback path DOM update
    if (!doc.raw_text && annotatedHtml) {
      const threshold = (preferences.confidence_threshold !== undefined ? preferences.confidence_threshold : 40) / 100;
      const parser = new DOMParser();
      const htmlDoc = parser.parseFromString(doc.annotated_html, "text/html");
      const marks = htmlDoc.querySelectorAll("mark");

      doc.issues.forEach((issue, i) => {
        const conf = issue.final_confidence || issue.confidence || 0;
        const mark = marks[i];
        
        if (conf <= threshold) {
          if (mark && mark.parentNode) {
            const textNode = htmlDoc.createTextNode(mark.textContent);
            mark.parentNode.replaceChild(textNode, mark);
          }
        } else {
          if (mark) {
            mark.setAttribute("data-issue-idx", String(i));
            const status = i === idx ? undefined : issueDecisions[i];
            if (status === "accepted") {
              mark.textContent = issue.suggested_text;
              mark.className = "corrected";
              mark.style.backgroundColor = "var(--green-light)";
              mark.style.color = "var(--green)";
              mark.style.borderBottom = "none";
              mark.style.textDecoration = "none";
              mark.removeAttribute("data-tooltip");
            } else if (status === "rejected") {
              if (mark.parentNode) {
                const textNode = htmlDoc.createTextNode(mark.textContent);
                mark.parentNode.replaceChild(textNode, mark);
              }
            } else {
              const severity = issue.severity || "medium";
              mark.className = `sev-${severity} pending-highlight`;
            }
          }
        }
      });
      setAnnotatedHtml(htmlDoc.body.innerHTML);
    }
  };

  // Handle Accept All
  const handleAcceptAll = () => {
    const nextDecisions = { ...issueDecisions };
    visibleIssues.forEach((issue) => {
      const idx = issue.originalIndex;
      if (nextDecisions[idx] === undefined) {
        nextDecisions[idx] = "accepted";
      }
    });
    setIssueDecisions(nextDecisions);

    // Fallback path DOM update
    if (!doc.raw_text && annotatedHtml) {
      const parser = new DOMParser();
      const tempDoc = parser.parseFromString(annotatedHtml, "text/html");
      visibleIssues.forEach((issue) => {
        const idx = issue.originalIndex;
        const mark = tempDoc.querySelector(`mark[data-issue-idx="${idx}"]`);
        if (mark) {
          mark.textContent = issue.suggested_text;
          mark.className = "corrected";
          mark.style.backgroundColor = "var(--green-light)";
          mark.style.color = "var(--green)";
          mark.style.borderBottom = "none";
          mark.style.textDecoration = "none";
          mark.removeAttribute("data-tooltip");
        }
      });
      setAnnotatedHtml(tempDoc.body.innerHTML);
    }
  };

  // Handle Reject All
  const handleRejectAll = () => {
    const nextDecisions = { ...issueDecisions };
    visibleIssues.forEach((issue) => {
      const idx = issue.originalIndex;
      if (nextDecisions[idx] === undefined) {
        nextDecisions[idx] = "rejected";
      }
    });
    setIssueDecisions(nextDecisions);

    // Fallback path DOM update
    if (!doc.raw_text && annotatedHtml) {
      const parser = new DOMParser();
      const tempDoc = parser.parseFromString(annotatedHtml, "text/html");
      visibleIssues.forEach((issue) => {
        const idx = issue.originalIndex;
        const mark = tempDoc.querySelector(`mark[data-issue-idx="${idx}"]`);
        if (mark && mark.parentNode) {
          const textNode = tempDoc.createTextNode(mark.textContent);
          mark.parentNode.replaceChild(textNode, mark);
        }
      });
      setAnnotatedHtml(tempDoc.body.innerHTML);
    }
  };

  // Navigate to next issue in visible list
  const handleNextIssue = () => {
    if (visibleIssues.length === 0) return;
    const currentPos = visibleIssues.findIndex(i => i.originalIndex === activeIssueIdx);
    const nextPos = (currentPos + 1) % visibleIssues.length;
    handleSelectIssue(visibleIssues[nextPos].originalIndex);
  };

  // Navigate to previous issue in visible list
  const handlePrevIssue = () => {
    if (visibleIssues.length === 0) return;
    const currentPos = visibleIssues.findIndex(i => i.originalIndex === activeIssueIdx);
    const prevPos = (currentPos - 1 + visibleIssues.length) % visibleIssues.length;
    handleSelectIssue(visibleIssues[prevPos].originalIndex);
  };

  // Download Corrected Document with user's modifications applied
  const handleDownloadCorrected = () => {
    if (!doc) return;
    
    let fullHtml = "";
    if (doc.raw_text) {
      const cleanBody = buildDecidedText(doc.raw_text, doc.issues, issueDecisions);
      fullHtml = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Corrected - ${doc.filename}</title>
<style>
  body { font-family: -apple-system, Segoe UI, Roboto, Arial, sans-serif; max-width: 800px; margin: 40px auto; padding: 0 20px; line-height: 1.7; color: #1a1a1a; }
  h1 { font-size: 1.4rem; border-bottom: 1px solid #eee; padding-bottom: 8px; }
  .paragraph { margin-bottom: 18px; white-space: pre-wrap; }
</style>
</head>
<body>
  <h1>Corrected Output</h1>
  <div class="paragraph">${cleanBody}</div>
</body>
</html>`;
    } else {
      // Parse our current annotatedHtml state to build a clean HTML document
      const parser = new DOMParser();
      const tempDoc = parser.parseFromString(annotatedHtml, "text/html");
      const marks = tempDoc.querySelectorAll("mark");
      
      marks.forEach((mark) => {
        // Replace mark tag with its inner text
        const textNode = tempDoc.createTextNode(mark.textContent);
        mark.parentNode.replaceChild(textNode, mark);
      });

      const cleanBody = tempDoc.body.innerHTML;
      
      // Reconstruct a beautiful full HTML page
      fullHtml = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Corrected - ${doc.filename}</title>
<style>
  body { font-family: -apple-system, Segoe UI, Roboto, Arial, sans-serif; max-width: 800px; margin: 40px auto; padding: 0 20px; line-height: 1.7; color: #1a1a1a; }
  h1 { font-size: 1.4rem; border-bottom: 1px solid #eee; padding-bottom: 8px; }
  .paragraph { margin-bottom: 18px; white-space: pre-wrap; }
</style>
</head>
<body>
  <h1>Corrected Output</h1>
  <div class="paragraph">${getParagraphBody(cleanBody)}</div>
</body>
</html>`;
    }

    const blob = new Blob([fullHtml], { type: "text/html" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${doc.filename.replace(/\.[^/.]+$/, "")}_corrected.html`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  // Generate updated JSON reports reflecting accepted/rejected statuses
  const handleGenerateReport = () => {
    if (!doc) return;

    const report = {
      job_id: doc.id,
      filename: doc.filename,
      generatedAt: new Date().toISOString(),
      issues: doc.issues.map((issue, idx) => ({
        ...issue,
        user_action: issueDecisions[idx] || "unresolved",
      })),
      statistics: {
        total_issues_detected: doc.issues.length,
        issues_accepted: Object.values(issueDecisions).filter(v => v === "accepted").length,
        issues_rejected: Object.values(issueDecisions).filter(v => v === "rejected").length,
        issues_filtered_out: doc.issues.filter(i => isFiltered(i)).length,
      }
    };

    const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(report, null, 2));
    const link = document.createElement("a");
    link.href = dataStr;
    link.download = `${doc.filename.replace(/\.[^/.]+$/, "")}_proofread_report.json`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  // Helper to retrieve currently selected issue details
  const activeIssue = useMemo(() => {
    if (activeIssueIdx === null || !doc || !doc.issues) return null;
    return { ...doc.issues[activeIssueIdx], originalIndex: activeIssueIdx };
  }, [activeIssueIdx, doc]);

  if (error) {
    return (
      <div style={styles.centerContainer}>
        <p style={{ color: "var(--red)", fontSize: 14, fontWeight: 650 }}>Failed to Load Workspace</p>
        <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4 }}>{error}</p>
        <button style={styles.backBtn} onClick={() => navigate("/")}>Go back home</button>
      </div>
    );
  }

  if (loading || !doc) {
    return (
      <div style={styles.centerContainer}>
        <div style={styles.spinner} />
        <p style={{ marginTop: 12, fontSize: 13.5, color: "var(--text-secondary)" }}>Loading workspace analysis…</p>
      </div>
    );
  }

  // Processing stages
  if (doc.status === "processing" || doc.status === "pending" || doc.status === "uploaded") {
    const isProcessing = doc.status === "processing";
    const percent = doc.progress_percentage || 0;
    const curPage = doc.current_page || 0;
    const totPages = doc.total_pages || 0;
    const curBatch = doc.current_batch || 0;
    const totBatches = doc.total_batches || 0;
    const estTime = doc.estimated_remaining_time || "Estimating...";
    const safeMode = doc.memory_safe_mode || false;
    const curStage = doc.current_stage || "Starting";

    return (
      <div style={styles.centerContainer}>
        <div style={styles.spinner} />
        <div style={{ marginTop: 20, textAlign: "center", maxWidth: 450, width: "100%", padding: "0 20px" }}>
          <h3 style={{ fontSize: 16, fontWeight: 700, color: "var(--text-primary)", margin: "0 0 8px 0" }}>
            {isProcessing ? "Processing Document Analysis" : "Job Queued"}
          </h3>
          
          {/* Progress bar */}
          <div style={{ width: "100%", height: 6, background: "var(--border)", borderRadius: 3, overflow: "hidden", marginBottom: 16 }}>
            <div style={{ width: `${percent}%`, height: "100%", background: "var(--brand)", transition: "width 0.3s ease" }} />
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 10, textAlign: "left", background: "var(--bg-hover)", padding: 16, borderRadius: 8, border: "1px solid var(--border)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12.5 }}>
              <span style={{ fontWeight: 600, color: "var(--text-secondary)" }}>Current Stage</span>
              <span style={{ fontWeight: 700, color: "var(--brand)" }}>{curStage}</span>
            </div>
            
            {totPages > 0 && (
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12.5 }}>
                <span style={{ fontWeight: 600, color: "var(--text-secondary)" }}>Page Progress</span>
                <span style={{ fontWeight: 700, color: "var(--text-primary)" }}>Page {curPage} of {totPages}</span>
              </div>
            )}

            {totBatches > 0 && (
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12.5 }}>
                <span style={{ fontWeight: 600, color: "var(--text-secondary)" }}>Current Batch</span>
                <span style={{ fontWeight: 700, color: "var(--text-primary)" }}>Batch {curBatch} of {totBatches}</span>
              </div>
            )}

            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12.5 }}>
              <span style={{ fontWeight: 600, color: "var(--text-secondary)" }}>Est. Time Remaining</span>
              <span style={{ fontWeight: 700, color: "var(--brand)" }}>{estTime}</span>
            </div>

            {safeMode && (
              <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 6, marginTop: 8, padding: "4px 8px", background: "rgba(22, 163, 74, 0.1)", border: "1px solid rgba(22, 163, 74, 0.2)", borderRadius: 6, fontSize: 11, color: "var(--green)", fontWeight: 700, textTransform: "uppercase", letterSpacing: 0.5 }}>
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" style={{ marginRight: 2 }}><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
                Memory Safe Mode: Active
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }


  if (doc.status === "failed") {
    return (
      <div style={styles.centerContainer}>
        <p style={{ color: "var(--red)", fontSize: 14.5, fontWeight: 700 }}>Proofreading Failed</p>
        <div style={styles.errorLogs}>
          <pre style={{ margin: 0 }}>{doc.error}</pre>
        </div>
        <button style={styles.backBtn} onClick={() => navigate("/")}>Go back home</button>
      </div>
    );
  }

  const issues = (doc?.issues || []).filter(i => i);
  const activeUnresolvedCount = visibleIssues.filter((issue) => issue && issueDecisions[issue.originalIndex] === undefined).length;
  const spellingCount = issues.filter((i, idx) => i && issueDecisions[idx] === undefined && !isFiltered(i) && (i.issue_type === "spelling" || i.issue_type === "punctuation")).length;
  const grammarCount = issues.filter((i, idx) => i && issueDecisions[idx] === undefined && !isFiltered(i) && (i.issue_type !== "spelling" && i.issue_type !== "punctuation")).length;
  
  const acceptedCount = Object.values(issueDecisions).filter(v => v === "accepted").length;
  const rejectedCount = Object.values(issueDecisions).filter(v => v === "rejected").length;
  const totalChecked = acceptedCount + rejectedCount;
  
  const score = Math.max(45, 100 - (issues.length - acceptedCount));

  const totalProtectedCount = doc?.protected_terms?.length || 0;

  const handleOpenProtectedTerms = async () => {
    setProtectedOpen(true);
    try {
      const data = await fetchDocument(id);
      setDoc(data);
    } catch (e) {
      console.error("Error fetching latest protected terms: ", e);
    }
  };

  // Copy Corrected Document text directly to clipboard
  const copyCorrectedText = () => {
    if (!doc) return;
    
    let textToCopy = "";
    if (doc.raw_text) {
      textToCopy = buildDecidedText(doc.raw_text, doc.issues, issueDecisions);
    } else {
      // Fallback: parse doc.corrected_html through a temporary DOM element
      const tempDiv = document.createElement("div");
      tempDiv.innerHTML = doc.corrected_html || "";
      textToCopy = tempDiv.textContent || tempDiv.innerText || "";
    }
    
    navigator.clipboard.writeText(textToCopy).catch((err) => {
      console.error("Failed to copy text: ", err);
    });
  };

  return (
    <div style={styles.workspace}>
      
      {/* 1. Header bar */}
      <div style={styles.header}>
        <div style={styles.titleCol}>
          <div style={styles.iconBox}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" /><path d="M14 2v6h6" /></svg>
          </div>
          <div>
            <h2 style={styles.filename}>{doc.filename}</h2>
            <p style={styles.subtext}>Job ID: {doc.id?.substring(0, 8)}... · {doc.size}</p>
          </div>
        </div>

        <div style={styles.actionCol}>
          <div style={styles.scorePill}>
            Score: <strong>{score}</strong>
          </div>
          <button style={styles.exportBtn} onClick={() => navigate(`/assistant/${doc.id}`)}>
            Open AI Assistant
          </button>
          <button style={styles.exportBtn} onClick={handleGenerateReport}>
            Generate Report
          </button>
          {activeTab === "corrected" && (
            <button style={styles.copyBtn} onClick={copyCorrectedText}>
              Copy Text
            </button>
          )}
          <button style={styles.downloadBtn} onClick={handleDownloadCorrected}>
            Download Clean Document
          </button>
        </div>
      </div>

      {/* 2. Tabs view selector */}
      <div style={styles.tabsRow}>
        <button
          style={{ ...styles.tab, ...(activeTab === "annotated" ? styles.tabActive : {}) }}
          onClick={() => setActiveTab("annotated")}
        >
          Interactive Workspace
        </button>
        <button
          style={{ ...styles.tab, ...(activeTab === "corrected" ? styles.tabActive : {}) }}
          onClick={() => setActiveTab("corrected")}
        >
          Clean Preview
        </button>
        <button
          style={{ ...styles.tab, ...(activeTab === "assistant" ? styles.tabActive : {}) }}
          onClick={() => setActiveTab("assistant")}
        >
          AI Assistant
        </button>
        <button
          style={{ ...styles.tab, ...(activeTab === "context" ? styles.tabActive : {}) }}
          onClick={() => setActiveTab("context")}
        >
          Context Analysis
        </button>
      </div>


      {/* 3. Main editor split pane */}
      {activeTab === "annotated" ? (
        <div style={styles.splitGrid}>
          
          {/* Left panel: Document text with inline highlights */}
          <div style={styles.editorPanel}>
            {doc.raw_text ? (
              <div 
                ref={textContainerRef}
                style={{ ...styles.textView, whiteSpace: "pre-wrap" }}
              >
                {renderDocumentMarkup()}
              </div>
            ) : (
              <div 
                ref={textContainerRef}
                style={styles.textView}
                dangerouslySetInnerHTML={{ __html: getParagraphBody(annotatedHtml) }}
              />
            )}
          </div>

          {/* Right panel: Suggestions rail */}
          <div style={styles.sidebarPanel}>
            
            {/* Toolbar - Search, Sort, Filter */}
            <div style={styles.sidebarToolbar}>
              <input
                type="text"
                style={styles.sidebarSearch}
                placeholder="Search suggestions..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
              <div style={styles.sidebarFilterRow}>
                <select
                  style={styles.sidebarSelect}
                  value={typeFilter}
                  onChange={(e) => setTypeFilter(e.target.value)}
                >
                  <option value="all">All Types</option>
                  <option value="spelling">Spelling</option>
                  <option value="grammar">Grammar</option>
                  <option value="tense">Tense</option>
                </select>
                <select
                  style={styles.sidebarSelect}
                  value={sortBy}
                  onChange={(e) => setSortBy(e.target.value)}
                >
                  <option value="index">Default</option>
                  <option value="confidence">Confidence Desc</option>
                  <option value="confidence-asc">Confidence Asc</option>
                  <option value="alphabetical">A-Z</option>
                </select>
              </div>
            </div>

            <div style={styles.sidebarActionHeader}>
              <p style={styles.sidebarTitle}>Unresolved ({activeUnresolvedCount})</p>
              {activeUnresolvedCount > 0 && (
                <div style={styles.bulkRow}>
                  <button style={styles.bulkAccept} onClick={handleAcceptAll}>Accept All</button>
                  <button style={styles.bulkReject} onClick={handleRejectAll}>Reject All</button>
                </div>
              )}
            </div>

            <div style={styles.cardList}>
              {activeUnresolvedCount === 0 ? (
                <div style={styles.emptyCard}>
                  <p style={{ margin: "0 0 4px", fontWeight: 700, color: "var(--green)" }}>No active issues!</p>
                  <p style={{ margin: 0, fontSize: 11.5 }}>All spelling/grammar mistakes resolved or filtered.</p>
                </div>
              ) : (
                visibleIssues.map((issue) => {
                  const idx = issue.originalIndex;
                  const SEVERITY_COLORS = { low: "#eab308", medium: "#f97316", high: "#ef4444", critical: "#b91c1c" };
                  const severity = issue.severity || "medium";
                  const accentColor = SEVERITY_COLORS[severity] || SEVERITY_COLORS.medium;
                  const isSelected = activeIssueIdx === idx;

                  return (
                    <div
                      key={idx}
                      id={`suggestion-${idx}`}
                      onClick={() => handleSelectIssue(idx)}
                      style={{
                        ...styles.suggestionCard,
                        borderLeftColor: accentColor,
                        ...(isSelected ? styles.suggestionSelected : {}),
                      }}
                    >
                      <div style={styles.cardTop}>
                        <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                          <span style={{ ...styles.cardLabel, color: accentColor }}>{issue.issue_type}</span>
                          <span style={{
                            fontSize: 9,
                            fontWeight: 700,
                            textTransform: "uppercase",
                            padding: "1px 4px",
                            borderRadius: 4,
                            backgroundColor: `${accentColor}15`,
                            color: accentColor,
                            border: `1px solid ${accentColor}30`
                          }}>
                            {severity}
                          </span>
                        </div>
                        <span style={styles.cardMeta}>Score: {Math.round((issue.final_confidence || issue.confidence || 0) * 100)}%</span>
                      </div>
                      <p style={styles.cardReason}>{issue.reason}</p>
                      <div style={styles.cardDiff}>
                        <span style={styles.diffOriginal}>{issue.original_text}</span>
                        <span style={{ margin: "0 6px", color: "var(--text-muted)" }}>➔</span>
                        <span style={styles.diffSuggested}>{issue.suggested_text}</span>
                      </div>

                      {issueDecisions[idx] === undefined ? (
                        <div style={styles.cardActions}>
                          <button
                            style={styles.cardRejectBtn}
                            onClick={(e) => {
                              e.stopPropagation();
                              rejectIssue(idx);
                            }}
                          >
                            Reject
                          </button>
                          <button
                            style={styles.cardAcceptBtn}
                            onClick={(e) => {
                              e.stopPropagation();
                              acceptIssue(idx);
                            }}
                          >
                            Accept
                          </button>
                        </div>
                      ) : (
                        <div style={styles.cardStatusLine}>
                          {issueDecisions[idx] === "accepted" ? (
                            <span style={styles.cardStatusApplied}>✓ Applied</span>
                          ) : (
                            <span style={styles.cardStatusDismissed}>✕ Dismissed</span>
                          )}
                          <button
                            style={styles.cardUndoBtn}
                            onClick={(e) => {
                              e.stopPropagation();
                              undoDecision(idx);
                            }}
                          >
                            Undo
                          </button>
                        </div>
                      )}
                    </div>
                  );
                })
              )}
            </div>

            {/* Suggestion Panel (Selected details) */}
            {activeIssue && (
              <div style={styles.detailPanel}>
                <h3 style={styles.detailTitle}>Selected Suggestion</h3>
                <p style={styles.detailReason}>{activeIssue.reason}</p>
                
                <div style={styles.detailDiffCard}>
                  <div>
                    <span style={styles.detailDiffLabel}>Original:</span>
                    <span style={{ ...styles.diffOriginal, marginLeft: 8 }}>{activeIssue.original_text}</span>
                  </div>
                  <div style={{ marginTop: 6 }}>
                    <span style={styles.detailDiffLabel}>Suggested:</span>
                    <span style={{ ...styles.diffSuggested, marginLeft: 8 }}>{activeIssue.suggested_text}</span>
                  </div>
                </div>

                {issueDecisions[activeIssue.originalIndex] === undefined ? (
                  <div style={styles.detailBtns}>
                    <button style={styles.rejectBtn} onClick={() => rejectIssue(activeIssue.originalIndex)}>
                      Reject
                    </button>
                    <button style={styles.acceptBtn} onClick={() => acceptIssue(activeIssue.originalIndex)}>
                      Accept
                    </button>
                  </div>
                ) : (
                  <div style={styles.cardStatusLine}>
                    {issueDecisions[activeIssue.originalIndex] === "accepted" ? (
                      <span style={styles.cardStatusApplied}>✓ Applied</span>
                    ) : (
                      <span style={styles.cardStatusDismissed}>✕ Dismissed</span>
                    )}
                    <button
                      style={styles.cardUndoBtn}
                      onClick={() => undoDecision(activeIssue.originalIndex)}
                    >
                      Undo
                    </button>
                  </div>
                )}

                <div style={styles.navRow}>
                  <button style={styles.navBtn} onClick={handlePrevIssue}>
                    &larr; Prev
                  </button>
                  <span style={styles.navText}>
                    {visibleIssues.findIndex(i => i.originalIndex === activeIssueIdx) + 1} of {visibleIssues.length}
                  </span>
                  <button style={styles.navBtn} onClick={handleNextIssue}>
                    Next &rarr;
                  </button>
                </div>
              </div>
            )}

          </div>

        </div>
      ) : activeTab === "corrected" ? (
        /* Corrected View (Clean Preview) */
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div style={{ ...styles.editorPanel, minHeight: 400 }}>
            {doc.raw_text ? (
              <div style={styles.textView}>
                {buildDecidedText(doc.raw_text, doc.issues, issueDecisions)}
              </div>
            ) : (
              <div 
                style={{ ...styles.textView, ...styles.correctedText }}
                className="clean-corrected-view"
                dangerouslySetInnerHTML={{ __html: getParagraphBody(annotatedHtml) }}
              />
            )}
          </div>
        </div>
      ) : activeTab === "assistant" ? (
        /* Embedded AI Assistant Chat Panel */
        <div style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 12, padding: 16, minHeight: 500 }}>
          <Assistant />
        </div>
      ) : (
        /* Context Analysis Report Dashboard */
        <div style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 12, padding: 20, minHeight: 500 }}>
          <ContextAnalysis id={id} onShowInDocument={handleShowInDocument} />
        </div>
      )}


      {/* 4. Footer legend bar */}
      <div style={styles.footerBar}>
        <div style={styles.legendGroup}>
          <div style={styles.legendItem}>
            <span style={{ ...styles.dot, background: "var(--amber)" }} />
            <span>{spellingCount} spelling pending</span>
          </div>
          <div style={styles.legendItem}>
            <span style={{ ...styles.dot, background: "var(--red)" }} />
            <span>{grammarCount} grammar pending</span>
          </div>
          {totalChecked > 0 && (
            <div style={styles.legendItem}>
              <span style={{ ...styles.dot, background: "var(--green)" }} />
              <span>{acceptedCount} accepted, {rejectedCount} rejected</span>
            </div>
          )}
          {doc.protected_terms?.length > 0 && (
            <div style={styles.legendItem}>
              <span style={{ ...styles.dot, background: "var(--brand)" }} />
              <span>{doc.protected_terms.length} protected</span>
            </div>
          )}
        </div>

        {doc.protected_terms?.length > 0 && (
          <button style={styles.whitelistBtn} onClick={handleOpenProtectedTerms}>
            View protected terms
          </button>
        )}
      </div>

      {/* Protected Terms Modal */}
      {protectedOpen && (
        <div style={styles.modalOverlay} onClick={() => setProtectedOpen(false)}>
          <div style={styles.modalCard} onClick={(e) => e.stopPropagation()}>
            <div style={styles.modalHeader}>
              <div>
                <h3 style={styles.modalTitle}>Protected Terms</h3>
                <p style={styles.modalSubtitle}>
                  Words and phrases bypassing proofreading checks for this document
                </p>
              </div>
              <button style={styles.modalCloseBtn} onClick={() => setProtectedOpen(false)}>
                &times;
              </button>
            </div>
            
            <div style={styles.modalBody}>
              {totalProtectedCount === 0 ? (
                <div style={styles.modalEmptyState}>
                  <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="var(--text-muted)" strokeWidth="1.5">
                    <path d="M12 22C17.5228 22 22 17.5228 22 12C22 6.47715 17.5228 2 12 2C6.47715 2 2 6.47715 2 12C2 17.5228 6.47715 22 12 22Z" />
                    <path d="M12 8V12" />
                    <path d="M12 16H12.01" />
                  </svg>
                  <p style={{ marginTop: 12, fontWeight: 600, color: "var(--text-secondary)" }}>
                    No protected terms found
                  </p>
                  <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4 }}>
                    Custom whitelist items or matched names/pronouns did not appear in this document.
                  </p>
                </div>
              ) : (
                <div style={styles.modalCategoryList}>
                  {Object.entries(groupedTerms).map(([category, items]) => {
                    if (items.length === 0) return null;
                    return (
                      <div key={category} style={styles.modalCategorySection}>
                        <h4 style={styles.modalCategoryHeader}>
                          {category} <span style={styles.modalCategoryBadge}>{items.length}</span>
                        </h4>
                        <div style={styles.modalBadgeGrid}>
                          {items.map((term, i) => (
                            <span key={i} style={styles.modalTermBadge} title={`Reason: ${term.reason}`}>
                              {term.text}
                            </span>
                          ))}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
            
            <div style={styles.modalFooter}>
              <button style={styles.modalCloseFooterBtn} onClick={() => setProtectedOpen(false)}>
                Close
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}

const styles = {
  workspace: { display: "flex", flexDirection: "column", gap: 16, maxWidth: 1040, margin: "0 auto", padding: "0 4px" },
  centerContainer: { display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", minHeight: 300, padding: 40 },
  spinner: {
    width: 28, height: 28, borderRadius: "50%",
    border: "3px solid var(--border)", borderTopColor: "var(--brand)",
    animation: "spin 0.8s linear infinite",
  },
  backBtn: {
    marginTop: 16, background: "var(--brand)", color: "white",
    border: "none", borderRadius: 8, padding: "8px 16px", fontSize: 13, fontWeight: 600,
    cursor: "pointer",
  },
  errorLogs: {
    width: "100%", maxWidth: 600, background: "#1E293B", color: "#FCA5A5",
    padding: 12, borderRadius: 8, fontSize: 11.5, fontFamily: "monospace",
    overflowX: "auto", margin: "12px 0", textAlign: "left",
  },
  header: { display: "flex", justifyContent: "space-between", alignItems: "center", paddingBottom: 12, borderBottom: "1px solid var(--border)" },
  titleCol: { display: "flex", alignItems: "center", gap: 12 },
  iconBox: {
    width: 38, height: 38, borderRadius: 8, background: "var(--brand-light)",
    color: "var(--brand)", display: "flex", alignItems: "center", justifyContent: "center",
  },
  filename: { margin: 0, fontSize: 16, fontWeight: 700, color: "var(--text-primary)", textAlign: "left" },
  subtext: { margin: "2px 0 0", fontSize: 11.5, color: "var(--text-muted)", textAlign: "left" },
  actionCol: { display: "flex", alignItems: "center", gap: 8 },
  scorePill: {
    padding: "6px 12px", background: "var(--brand-light)", color: "var(--brand)",
    fontSize: 12.5, fontWeight: 650, borderRadius: 999,
  },
  exportBtn: {
    padding: "8px 12px", background: "var(--bg-card)", border: "1px solid var(--border)",
    borderRadius: 8, fontSize: 12.5, fontWeight: 600, color: "var(--text-primary)", cursor: "pointer",
  },
  downloadBtn: {
    padding: "8px 14px", background: "var(--brand)", color: "white", border: "none",
    borderRadius: 8, fontSize: 12.5, fontWeight: 600, cursor: "pointer",
  },
  tabsRow: { display: "flex", gap: 16, borderBottom: "1px solid var(--border)", paddingBottom: 1 },
  tab: {
    background: "none", border: "none", borderBottom: "2px solid transparent",
    fontSize: 13.5, fontWeight: 600, color: "var(--text-secondary)",
    padding: "8px 4px", cursor: "pointer",
  },
  tabActive: {
    color: "var(--brand)", borderBottomColor: "var(--brand)",
  },
  splitGrid: { display: "grid", gridTemplateColumns: "1fr 280px", gap: 16, alignItems: "start" },
  editorPanel: {
    background: "var(--bg-card)", border: "1px solid var(--border)",
    borderRadius: "var(--radius-lg)", padding: 24, minHeight: 380, maxHeight: 540,
    overflowY: "auto", textAlign: "left",
  },
  textView: {
    fontSize: 14, lineHeight: 1.7, color: "var(--text-primary)", whiteSpace: "pre-wrap",
  },
  correctedText: {
    background: "none", border: "none", padding: 0,
  },
  sidebarPanel: { display: "flex", flexDirection: "column", gap: 12, maxHeight: 540 },
  sidebarToolbar: { display: "flex", flexDirection: "column", gap: 6 },
  sidebarSearch: {
    width: "100%", background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 6,
    padding: "6px 8px", fontSize: 12.5, outline: "none", color: "var(--text-primary)",
  },
  sidebarFilterRow: { display: "flex", gap: 6 },
  sidebarSelect: {
    flex: 1, background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 6,
    padding: "4px 6px", fontSize: 11, color: "var(--text-primary)", cursor: "pointer", outline: "none",
  },
  sidebarActionHeader: { display: "flex", justifyContent: "space-between", alignItems: "center" },
  sidebarTitle: { margin: 0, fontSize: 11, fontWeight: 750, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: 0.5, textAlign: "left" },
  bulkRow: { display: "flex", gap: 4 },
  bulkAccept: { background: "var(--green-light)", color: "var(--green)", border: "none", borderRadius: 4, padding: "2px 6px", fontSize: 10, fontWeight: 700, cursor: "pointer" },
  bulkReject: { background: "var(--red-light)", color: "var(--red)", border: "none", borderRadius: 4, padding: "2px 6px", fontSize: 10, fontWeight: 700, cursor: "pointer" },
  cardList: { display: "flex", flexDirection: "column", gap: 8, overflowY: "auto", flex: 1, maxHeight: 220, paddingRight: 4 },
  emptyCard: {
    padding: 16, background: "var(--bg-card)", border: "1px dashed var(--border)",
    borderRadius: 8, fontSize: 12.5, color: "var(--text-muted)", textAlign: "center",
  },
  suggestionCard: {
    padding: 10, background: "var(--bg-card)", border: "1px solid var(--border)",
    borderLeftWidth: 4, borderRadius: 6, cursor: "pointer", transition: "all 0.2s",
    textAlign: "left",
  },
  suggestionSelected: {
    borderColor: "var(--brand) !important",
    boxShadow: "0 2px 8px rgba(108, 92, 231, 0.08)",
    background: "var(--brand-light)",
  },
  cardTop: { display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 2 },
  cardLabel: { fontSize: 9.5, fontWeight: 700, textTransform: "uppercase", letterSpacing: 0.5 },
  cardMeta: { fontSize: 9, color: "var(--text-muted)" },
  cardReason: { margin: 0, fontSize: 12, fontWeight: 600, color: "var(--text-primary)", lineHeight: 1.3 },
  cardDiff: {
    marginTop: 4, display: "flex", alignItems: "center", flexWrap: "wrap",
    fontSize: 10.5, fontFamily: "monospace", color: "var(--text-secondary)",
  },
  diffOriginal: { textDecoration: "line-through", color: "var(--text-muted)" },
  diffSuggested: { color: "var(--green)", fontWeight: 700 },
  detailPanel: {
    background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 8,
    padding: 12, display: "flex", flexDirection: "column", gap: 8, textAlign: "left",
  },
  detailTitle: { margin: 0, fontSize: 13, fontWeight: 750, color: "var(--text-secondary)", textTransform: "uppercase" },
  detailReason: { margin: 0, fontSize: 12.5, color: "var(--text-primary)" },
  detailDiffCard: { padding: 8, background: "var(--bg-page)", borderRadius: 6, fontSize: 11.5, fontFamily: "monospace" },
  detailDiffLabel: { fontWeight: "bold", color: "var(--text-secondary)" },
  detailBtns: { display: "flex", gap: 6 },
  acceptBtn: {
    flex: 1, padding: "6px", background: "var(--brand)", color: "white", border: "none",
    borderRadius: 6, fontSize: 12, fontWeight: 650, cursor: "pointer",
  },
  rejectBtn: {
    flex: 1, padding: "6px", background: "transparent", color: "var(--text-secondary)", border: "1px solid var(--border)",
    borderRadius: 6, fontSize: 12, fontWeight: 600, cursor: "pointer",
  },
  navRow: { display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 4 },
  navBtn: { background: "none", border: "none", color: "var(--brand)", fontSize: 11, fontWeight: 700, cursor: "pointer" },
  navText: { fontSize: 11, color: "var(--text-secondary)" },
  footerBar: {
    display: "flex", justifyContent: "space-between", alignItems: "center",
    paddingTop: 12, borderTop: "1px solid var(--border)", fontSize: 12.5, color: "var(--text-secondary)",
  },
  legendGroup: { display: "flex", gap: 16, flexWrap: "wrap" },
  legendItem: { display: "flex", alignItems: "center", gap: 6 },
  dot: { width: 8, height: 8, borderRadius: "50%" },
  whitelistBtn: {
    background: "none", border: "none", color: "var(--brand)",
    fontSize: 12.5, fontWeight: 650, cursor: "pointer",
  },
  modalOverlay: {
    position: "fixed",
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: "rgba(15, 23, 42, 0.6)",
    backdropFilter: "blur(4px)",
    display: "flex",
    justifyContent: "center",
    alignItems: "center",
    zIndex: 9999,
  },
  modalCard: {
    background: "var(--bg-card)",
    borderRadius: 12,
    border: "1px solid var(--border)",
    width: "90%",
    maxWidth: 600,
    maxHeight: "85vh",
    display: "flex",
    flexDirection: "column",
    boxShadow: "0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)",
    overflow: "hidden",
  },
  modalHeader: {
    padding: "16px 20px",
    borderBottom: "1px solid var(--border)",
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    background: "var(--bg-page)",
  },
  modalTitle: {
    margin: 0,
    fontSize: 16,
    fontWeight: 700,
    color: "var(--text-primary)",
    textAlign: "left",
  },
  modalSubtitle: {
    margin: "4px 0 0",
    fontSize: 12,
    color: "var(--text-muted)",
    textAlign: "left",
  },
  modalCloseBtn: {
    background: "none",
    border: "none",
    fontSize: 24,
    color: "var(--text-muted)",
    cursor: "pointer",
    lineHeight: 1,
    padding: 4,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  },
  modalBody: {
    padding: 20,
    overflowY: "auto",
    flex: 1,
    textAlign: "left",
  },
  modalEmptyState: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    padding: "40px 20px",
    textAlign: "center",
  },
  modalCategoryList: {
    display: "flex",
    flexDirection: "column",
    gap: 20,
  },
  modalCategorySection: {
    display: "flex",
    flexDirection: "column",
    gap: 8,
  },
  modalCategoryHeader: {
    margin: 0,
    fontSize: 12,
    fontWeight: 700,
    textTransform: "uppercase",
    letterSpacing: 0.5,
    color: "var(--text-secondary)",
    display: "flex",
    alignItems: "center",
    gap: 8,
  },
  modalCategoryBadge: {
    fontSize: 10,
    fontWeight: 700,
    padding: "1px 6px",
    background: "var(--brand-light)",
    color: "var(--brand)",
    borderRadius: 999,
  },
  modalBadgeGrid: {
    display: "flex",
    flexWrap: "wrap",
    gap: 6,
  },
  modalTermBadge: {
    display: "inline-flex",
    alignItems: "center",
    background: "var(--bg-page)",
    color: "var(--text-secondary)",
    padding: "4px 10px",
    borderRadius: 6,
    fontSize: 12.5,
    fontWeight: 500,
    border: "1px solid var(--border)",
  },
  modalFooter: {
    padding: "12px 20px",
    borderTop: "1px solid var(--border)",
    display: "flex",
    justifyContent: "flex-end",
    background: "var(--bg-page)",
  },
  modalCloseFooterBtn: {
    padding: "8px 16px",
    background: "var(--brand)",
    color: "white",
    border: "none",
    borderRadius: 6,
    fontSize: 13,
    fontWeight: 600,
    cursor: "pointer",
  },
  copyBtn: {
    padding: "8px 12px", background: "var(--bg-card)", border: "1px solid var(--border)",
    borderRadius: 8, fontSize: 12.5, fontWeight: 600, color: "var(--text-primary)", cursor: "pointer",
  },
  expandBtn: {
    padding: "6px 12px", background: "var(--bg-card)", border: "1px solid var(--border)",
    borderRadius: 6, fontSize: 12, fontWeight: 600, color: "var(--text-secondary)", cursor: "pointer",
  },
  cardActions: {
    display: "flex", gap: 6, marginTop: 8, justifyContent: "flex-end",
  },
  cardAcceptBtn: {
    padding: "4px 10px", background: "var(--green-light)", color: "var(--green)",
    border: "none", borderRadius: 4, fontSize: 11, fontWeight: 700, cursor: "pointer",
  },
  cardRejectBtn: {
    padding: "4px 10px", background: "var(--red-light)", color: "var(--red)",
    border: "none", borderRadius: 4, fontSize: 11, fontWeight: 700, cursor: "pointer",
  },
  cardStatusLine: {
    display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 8, fontSize: 11,
  },
  cardStatusApplied: {
    color: "var(--green)", fontWeight: 700, display: "flex", alignItems: "center", gap: 4,
  },
  cardStatusDismissed: {
    color: "var(--text-muted)", fontWeight: 600, display: "flex", alignItems: "center", gap: 4,
  },
  cardUndoBtn: {
    background: "none", border: "none", color: "var(--brand)", fontSize: 11, fontWeight: 700,
    cursor: "pointer", padding: 0, textDecoration: "underline",
  },
};
