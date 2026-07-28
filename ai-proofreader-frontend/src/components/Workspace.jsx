import React, { useState, useEffect, useRef, useMemo } from "react";
import { useParams, useNavigate, useLocation } from "react-router-dom";
import { fetchDocument, fetchPreferences, fetchComparativeAnalysis } from "../api";
import Assistant from "./Assistant";
import ContextAnalysis from "./ContextAnalysis";
import Reports from "./Reports";
import ComparativeAnalysisView from "./ComparativeAnalysisView";


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

const getTimelineStages = (doc) => {
  if (!doc) return [];
  const percent = doc.progress_percentage || 0;
  const isCompleted = doc.status === "completed";
  const stageStr = (doc.current_stage || "").toLowerCase();

  const stages = [
    { id: 1, label: "Stage 1: Extraction", minPct: 0 },
    { id: 2, label: "Stage 2: Chunking", minPct: 15 },
    { id: 3, label: "Stage 3: Embeddings", minPct: 30 },
    { id: 4, label: "Stage 4: Proofreading", minPct: 45 },
    { id: 5, label: "Stage 5: RAG", minPct: 60 },
    { id: 6, label: "Stage 6: Local LLM Ambiguity Detection", minPct: 70 },
    { id: 7, label: "Stage 7: Claude Verification", minPct: 82 },
    { id: 8, label: "Stage 8: Executive Report Generation", minPct: 92 }
  ];

  return stages.map((stage) => {
    let state = "pending";
    
    if (isCompleted) {
      state = "completed";
    } else if (doc.status === "failed") {
      state = "pending";
    } else {
      if (percent >= stage.minPct) {
        const isLast = stage.id === stages.length;
        const nextStage = isLast ? null : stages[stage.id];
        if (isLast || percent < nextStage.minPct) {
          state = "active";
        } else {
          state = "completed";
        }
      }
    }

    return {
      ...stage,
      state
    };
  });
};

export default function Workspace() {
  const { id } = useParams();
  const navigate = useNavigate();
  const location = useLocation();

  const [doc, setDoc] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // User preferences & threshold
  const [preferences, setPreferences] = useState({ confidence_threshold: 40 });

  // Workspace active states
  const [activeTab, setActiveTab] = useState("overview"); 
  const [isDownloadModalOpen, setIsDownloadModalOpen] = useState(false);
  const [isActionsDropdownOpen, setIsActionsDropdownOpen] = useState(false);
  const [statusDetailsExpanded, setStatusDetailsExpanded] = useState(false);
  const [proofSubTab, setProofSubTab] = useState("annotated");
  const [comparativeData, setComparativeData] = useState(null);
  const [comparativeLoading, setComparativeLoading] = useState(false);
  const actionsRef = useRef(null);

  useEffect(() => {
    function handleClickOutside(event) {
      if (actionsRef.current && !actionsRef.current.contains(event.target)) {
        setIsActionsDropdownOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  useEffect(() => {
    const handleOpenModal = () => setIsDownloadModalOpen(true);
    window.addEventListener("openDownloadModal", handleOpenModal);
    return () => window.removeEventListener("openDownloadModal", handleOpenModal);
  }, []);

  const [activeIssueIdx, setActiveIssueIdx] = useState(null);
  const [issueDecisions, setIssueDecisions] = useState({});
  
  // HTML state
  const [annotatedHtml, setAnnotatedHtml] = useState("");

  // Toolbar states
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("all"); // 'all', 'grammar', 'spelling'
  const [sortBy, setSortBy] = useState("index");

  const [protectedOpen, setProtectedOpen] = useState(false);
  const textContainerRef = useRef(null);

  // Helper functions to categorize issues
  const isSpellingIssue = (issue) => issue && (issue.issue_type === "spelling" || issue.issue_type === "punctuation");
  const isGrammarIssue = (issue) => issue && (issue.issue_type !== "spelling" && issue.issue_type !== "punctuation");

  // Synchronize document DOM highlights (fallback mode when annotatedHtml is rendered)
  useEffect(() => {
    if (!textContainerRef.current || doc?.raw_text) return;

    const marks = textContainerRef.current.querySelectorAll("mark[data-issue-idx]");
    marks.forEach((mark) => {
      const idxAttr = mark.getAttribute("data-issue-idx");
      if (idxAttr === null) return;
      const idx = parseInt(idxAttr, 10);
      const issue = doc?.issues?.[idx];
      if (!issue) return;

      const isSpelling = isSpellingIssue(issue);
      const isGrammar = isGrammarIssue(issue);

      let hide = false;
      if (typeFilter === "grammar" && !isGrammar) {
        hide = true;
      } else if (typeFilter === "spelling" && !isSpelling) {
        hide = true;
      }

      if (hide) {
        mark.classList.add("filter-hidden-mark");
      } else {
        mark.classList.remove("filter-hidden-mark");
      }
    });
  }, [typeFilter, annotatedHtml, doc]);

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
        if (data) {
          localStorage.setItem("currentlyOpenDocId", data.id);
          localStorage.setItem("currentlyOpenDocName", data.filename);
          localStorage.setItem("currentlyOpenDocPages", data.total_pages || data.pages || 1);
          localStorage.setItem("currentlyOpenDocStatus", data.status || "pending");
          localStorage.setItem("currentlyOpenDocIssuesCount", (data.issues || []).length);
          localStorage.setItem("currentlyOpenDocConsistencyIssues", data.context_analysis_issues_count || 0);
          window.dispatchEvent(new Event("activeDocChanged"));
        }

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

  // Handle initial page query parameter from standalone AI Assistant citations
  useEffect(() => {
    if (doc && doc.issues) {
      const params = new URLSearchParams(location.search);
      const pageParam = params.get("page");
      if (pageParam) {
        const pageNum = parseInt(pageParam);
        const firstIssueIdx = (doc.issues || []).findIndex(i => i && i.page_number === pageNum);
        if (firstIssueIdx !== -1) {
          handleSelectIssue(firstIssueIdx);
        }
      }
    }
  }, [doc, location.search]);

  const handleTabChange = (tabName) => {
    navigate(`/documents/${id}?tab=${tabName}`);
  };

  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const tabVal = params.get("tab") || "overview";
    setActiveTab(tabVal);
  }, [location.search]);

  useEffect(() => {
    if ((activeTab === "comparative" || activeTab === "comparative-analysis") && id) {
      let isMounted = true;
      let timerId = null;

      const loadCompData = async () => {
        setComparativeLoading(true);
        try {
          const res = await fetchComparativeAnalysis(id);
          if (!isMounted) return;

          const payload = res?.data || res;
          if (payload?.company_profile || payload?.data?.company_profile || payload?.comparative_analysis) {
            setComparativeData(payload);
            setComparativeLoading(false);
          } else {
            setComparativeData(res);
            setComparativeLoading(false);
            timerId = setTimeout(loadCompData, 3000);
          }
        } catch (err) {
          console.error("Error loading comparative analysis:", err);
          if (isMounted) setComparativeLoading(false);
        }
      };

      loadCompData();

      return () => {
        isMounted = false;
        if (timerId) clearTimeout(timerId);
      };
    }
  }, [activeTab, id]);

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
        const isSpelling = isSpellingIssue(issue);
        const isGrammar = isGrammarIssue(issue);

        let shouldHighlight = true;
        if (typeFilter === "grammar" && !isGrammar) {
          shouldHighlight = false;
        } else if (typeFilter === "spelling" && !isSpelling) {
          shouldHighlight = false;
        }

        if (shouldHighlight) {
          const severity = issue.severity || "medium";
          const accentClass = isSpelling ? "spelling" : "grammar";
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
        } else {
          // Render plain text without highlight when filtered out
          elements.push(doc.raw_text.slice(issue.char_start, issue.char_end));
        }
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

  // Unresolved issues count memoizers for filter pills
  const allUnresolvedCount = useMemo(() => {
    if (!doc || !doc.issues) return 0;
    return (doc.issues || []).filter((i, idx) => i && issueDecisions[idx] === undefined && !isFiltered(i)).length;
  }, [doc, issueDecisions, preferences]);

  const grammarUnresolvedCount = useMemo(() => {
    if (!doc || !doc.issues) return 0;
    return (doc.issues || []).filter((i, idx) => i && issueDecisions[idx] === undefined && !isFiltered(i) && isGrammarIssue(i)).length;
  }, [doc, issueDecisions, preferences]);

  const spellingUnresolvedCount = useMemo(() => {
    if (!doc || !doc.issues) return 0;
    return (doc.issues || []).filter((i, idx) => i && issueDecisions[idx] === undefined && !isFiltered(i) && isSpellingIssue(i)).length;
  }, [doc, issueDecisions, preferences]);

  // 1. Get filtered issues list based on search/filters
  const visibleIssues = useMemo(() => {
    if (!doc || !doc.issues) return [];
    
    return (doc.issues || [])
      .map((issue, idx) => (issue ? { ...issue, originalIndex: idx } : null))
      .filter((issue) => {
        if (!issue) return false;
        
        // Exclude filtered (confidence <= threshold) unless it is accepted or rejected where we want to show history
        if (isFiltered(issue) && typeFilter !== "accepted" && typeFilter !== "rejected") return false;

        // Apply Search with safety fallbacks
        const origText = issue.original_text || "";
        const sugText = issue.suggested_text || "";
        const reasonText = issue.reason || "";
        const query = search || "";

        const matchSearch =
          origText.toLowerCase().includes(query.toLowerCase()) ||
          sugText.toLowerCase().includes(query.toLowerCase()) ||
          reasonText.toLowerCase().includes(query.toLowerCase());

        // Apply Filter (All Issues, Grammar, Spelling, Protected Terms, Accepted, Rejected)
        let matchFilter = true;
        const decision = issueDecisions[issue.originalIndex];

        if (typeFilter === "all" || typeFilter === "unresolved") {
          matchFilter = decision === undefined;
        } else if (typeFilter === "grammar") {
          matchFilter = decision === undefined && isGrammarIssue(issue);
        } else if (typeFilter === "spelling") {
          matchFilter = decision === undefined && isSpellingIssue(issue);
        } else if (typeFilter === "protected") {
          const isProt = doc.protected_terms && doc.protected_terms.some(t => origText.toLowerCase().includes(t.toLowerCase()));
          matchFilter = isProt;
        } else if (typeFilter === "accepted") {
          matchFilter = decision === "accepted";
        } else if (typeFilter === "rejected") {
          matchFilter = decision === "rejected";
        }

        return matchSearch && matchFilter;
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
  }, [doc, search, typeFilter, sortBy, issueDecisions, preferences]);

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
    const percent = doc.progress_percentage || 0;
    const curPage = doc.current_page || 0;
    const totPages = doc.total_pages || 0;
    const estTime = doc.estimated_remaining_time || "Estimating...";
    const timeline = getTimelineStages(doc);
    const completedCount = timeline.filter(s => s.state === "completed").length;

    return (
      <div style={styles.centerContainer}>
        <div style={styles.processingGrid}>
          {/* Left Column: Animated Scanning Icon */}
          <div style={styles.processingLeft}>
            <div className="pulse-animation" style={styles.processingIconCircle}>
              <svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="var(--brand)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                <polyline points="14 2 14 8 20 8" />
                <line x1="16" y1="13" x2="8" y2="13" />
                <line x1="16" y1="17" x2="8" y2="17" />
                <line x1="10" y1="9" x2="8" y2="9" />
              </svg>
            </div>
            <p style={{ margin: "16px 0 0", fontSize: 13.5, fontWeight: 700, color: "var(--brand)" }}>AI Scanning Active</p>
            <p style={{ margin: "6px 0 0", fontSize: 11.5, color: "var(--text-muted)", maxWidth: 150, textAlign: "center", lineHeight: 1.4 }}>
              Extracting structural layout and cross-referencing policy statements.
            </p>
          </div>
          
          {/* Right Column: Processing Details & Collapsed Timeline */}
          <div style={styles.processingRight}>
            <div style={{ marginBottom: 16 }}>
              <h3 style={{ fontSize: 15.5, fontWeight: 700, color: "var(--text-primary)", margin: 0 }}>
                Analyzing Document Intelligence...
              </h3>
              <p style={{ margin: "2px 0 0", fontSize: 12.5, color: "var(--text-secondary)" }}>
                We are reviewing consistency, grammar, and statements. This may take a few minutes.
              </p>
            </div>

            {/* Progress bar */}
            <div style={{ width: "100%", height: 6, background: "var(--border)", borderRadius: 3, overflow: "hidden", marginBottom: 16 }}>
              <div style={{ width: `${percent}%`, height: "100%", background: "var(--brand)", transition: "width 0.3s ease" }} />
            </div>

            {/* Timeline Checklist */}
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {/* Collapsed completed stages */}
              {completedCount > 0 && (
                <div style={{ display: "flex", alignItems: "center", gap: 8, color: "var(--green)" }}>
                  <span style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", width: 18, height: 18, borderRadius: "50%", background: "var(--green-light)" }}>
                    <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                      <polyline points="20 6 9 17 4 12" />
                    </svg>
                  </span>
                  <span style={{ fontSize: 12.5, fontWeight: 650 }}>
                    {completedCount} stages completed
                  </span>
                </div>
              )}

              {/* Active and pending stages */}
              {timeline.filter(s => s.state !== "completed").map((s) => {
                const isActive = s.state === "active";
                return (
                  <div key={s.id} style={{ display: "flex", alignItems: "center", gap: 8, opacity: s.state === "pending" ? 0.45 : 1 }}>
                    {isActive ? (
                      <span className="pulse-animation" style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", width: 18, height: 18, borderRadius: "50%", background: "var(--brand-light)", color: "var(--brand)" }}>
                        <span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--brand)" }} />
                      </span>
                    ) : (
                      <span style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", width: 18, height: 18, borderRadius: "50%", border: "1.5px solid var(--text-muted)", color: "var(--text-muted)", fontSize: 9, fontWeight: 700 }}>
                        {s.id}
                      </span>
                    )}
                    <span style={{ fontSize: 12.5, fontWeight: isActive ? 700 : 550, color: isActive ? "var(--brand)" : "var(--text-primary)" }}>
                      {s.label}
                    </span>
                  </div>
                );
              })}
            </div>

            <div style={{ marginTop: 20, paddingTop: 12, borderTop: "1px solid var(--border)", display: "flex", justifyContent: "space-between", fontSize: 11.5, color: "var(--text-secondary)" }}>
              <span>Page Scope: Page {curPage} of {totPages || 1}</span>
              <span>Est. Remaining: {estTime}</span>
            </div>
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

  const publicationStatus = (issues.length - acceptedCount) === 0 ? "Ready for Publication" : (issues.length - acceptedCount) <= 3 ? "Requires Minor Revision" : "Requires Major Revision";

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

  const handleDownloadFormat = (packageName, format) => {
    alert(`Preparing ${packageName} report in ${format.toUpperCase()} format...`);
    handleDownloadCorrected();
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

  const renderResultsOverview = () => {
    const totalIssues = doc?.issues?.length || 0;
    const consistencyIssues = doc?.context_analysis_issues_count || 0;
    
    return (
      <div style={styles.overviewContainer}>
        <div style={styles.overviewHeader}>
          <h2 style={styles.overviewTitle}>Executive Overview</h2>
          <p style={styles.overviewSubtitle}>Formal assessment indicators generated from structural checking algorithms.</p>
        </div>
        
        <div style={styles.overviewGrid}>
          {/* Card 1: Overall Assessment */}
          <div style={styles.overviewCard}>
            <div style={styles.overviewCardTop}>
              <span style={{
                ...styles.cardBadge,
                backgroundColor: totalIssues === 0 ? "var(--green-light)" : totalIssues <= 10 ? "var(--amber-light)" : "var(--red-light)",
                color: totalIssues === 0 ? "var(--green)" : totalIssues <= 10 ? "var(--amber)" : "var(--red)"
              }}>
                {totalIssues === 0 ? "Ready for Publication" : totalIssues <= 10 ? "Needs Attention" : "Revisions Recommended"}
              </span>
              <h3 style={styles.overviewCardTitle}>Overall Assessment</h3>
            </div>
            <p style={styles.overviewCardDesc}>
              This document has been reviewed across spelling, structural grammar, and semantic contradiction layers.
            </p>
            <button style={styles.overviewCardBtn} onClick={() => handleTabChange("proofreading")}>
              View Proofreading &rarr;
            </button>
          </div>

          {/* Card 2: Writing Quality */}
          <div style={styles.overviewCard}>
            <div style={styles.overviewCardTop}>
              <span style={{
                ...styles.cardBadge,
                backgroundColor: totalIssues === 0 ? "var(--green-light)" : "var(--amber-light)",
                color: totalIssues === 0 ? "var(--green)" : "var(--amber)"
              }}>
                {totalIssues} Issues Found
              </span>
              <h3 style={styles.overviewCardTitle}>Writing Quality</h3>
            </div>
            <p style={styles.overviewCardDesc}>
              Spelling and structural grammar verification flags typographical bugs and formatting errors.
            </p>
            <button style={styles.overviewCardBtn} onClick={() => handleTabChange("proofreading")}>
              View Proofreading &rarr;
            </button>
          </div>

          {/* Card 3: Consistency Review */}
          <div style={styles.overviewCard}>
            <div style={styles.overviewCardTop}>
              <span style={{
                ...styles.cardBadge,
                backgroundColor: consistencyIssues === 0 ? "var(--green-light)" : "var(--amber-light)",
                color: consistencyIssues === 0 ? "var(--green)" : "var(--amber)"
              }}>
                {consistencyIssues} Conflicts Mapped
              </span>
              <h3 style={styles.overviewCardTitle}>Consistency Review</h3>
            </div>
            <p style={styles.overviewCardDesc}>
              Audits conflicting sections to check that clauses do not contradict.
            </p>
            <button style={styles.overviewCardBtn} onClick={() => handleTabChange("analysis")}>
              View Context Analysis &rarr;
            </button>
          </div>

          {/* Card 4: AI Verification */}
          <div style={styles.overviewCard}>
            <div style={styles.overviewCardTop}>
              <span style={{
                ...styles.cardBadge,
                backgroundColor: consistencyIssues === 0 ? "var(--green-light)" : "var(--amber-light)",
                color: consistencyIssues === 0 ? "var(--green)" : "var(--amber)"
              }}>
                Validation Run
              </span>
              <h3 style={styles.overviewCardTitle}>AI Verification</h3>
            </div>
            <p style={styles.overviewCardDesc}>
              Advanced cross-sectional logic checks verifying statements are factual and consistent.
            </p>
            <button style={styles.overviewCardBtn} onClick={() => handleTabChange("analysis")}>
              View Context Analysis &rarr;
            </button>
          </div>

          {/* Card 5: Reports Page */}
          <div style={styles.overviewCard}>
            <div style={styles.overviewCardTop}>
              <span style={{
                ...styles.cardBadge,
                backgroundColor: "var(--brand-light)",
                color: "var(--brand)"
              }}>
                Ready to Export
              </span>
              <h3 style={styles.overviewCardTitle}>Reports Archive</h3>
            </div>
            <p style={styles.overviewCardDesc}>
              Access intermediate logical analysis, cross references, and formal executive summaries.
            </p>
            <button style={styles.overviewCardBtn} onClick={() => handleTabChange("reports")}>
              View Reports &rarr;
            </button>
          </div>
        </div>
      </div>
    );
  };

  const totalIssuesCount = doc?.issues?.length || 0;
  const totalConsistencyCount = doc?.context_analysis_issues_count || 0;

  let primaryStatusText = "Currently Processing";
  let badgeColor = "var(--amber)";
  let badgeBg = "var(--amber-light)";
  
  if (doc.status === "completed") {
    if (totalIssuesCount === 0 && totalConsistencyCount === 0) {
      primaryStatusText = "Ready for Publishing";
      badgeColor = "var(--green)";
      badgeBg = "var(--green-light)";
    } else if (totalIssuesCount <= 5 && totalConsistencyCount === 0) {
      primaryStatusText = "Needs Minor Revision";
      badgeColor = "var(--green)";
      badgeBg = "var(--green-light)";
    } else if (totalIssuesCount <= 15) {
      primaryStatusText = "Needs Review";
      badgeColor = "var(--amber)";
      badgeBg = "var(--amber-light)";
    } else {
      primaryStatusText = "Requires Major Revision";
      badgeColor = "var(--red)";
      badgeBg = "var(--red-light)";
    }
  }

  return (
    <div style={styles.workspace}>
      
      {/* 1. Header bar */}
      <div style={styles.header}>
        <div style={styles.titleCol}>
          <div style={styles.iconBox}>
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" /><path d="M14 2v6h6" /></svg>
          </div>
          <div>
            <h2 style={styles.filename}>{doc.filename}</h2>
            <div style={{ display: "flex", gap: 12, fontSize: 12.5, color: "var(--text-secondary)", marginTop: 2, alignItems: "center" }}>
              <span>{doc.total_pages || doc.pages || 1} pages</span>
              <span>•</span>
              <span>Uploaded {doc.uploadedLabel || "Recently"}</span>
              <span>•</span>
              <span style={{ fontWeight: 650, color: doc.status === "completed" ? "var(--green)" : "var(--amber)" }}>
                {doc.status === "completed" ? "✓ Scan Complete" : "⚠ Under Review"}
              </span>
            </div>
            
            {/* Persistent Document Context Header - Clean primary status */}
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 8, flexWrap: "wrap", position: "relative" }}>
              <div 
                style={{
                  display: "inline-flex", alignItems: "center", gap: 6, cursor: "pointer",
                  padding: "4px 10px", borderRadius: 6, background: badgeBg, color: badgeColor,
                  fontSize: 12, fontWeight: 700, userSelect: "none"
                }}
                onClick={() => setStatusDetailsExpanded(!statusDetailsExpanded)}
                title="Click to view detailed metrics breakdown"
              >
                <span>{primaryStatusText}</span>
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" style={{ transform: statusDetailsExpanded ? "rotate(180deg)" : "none", transition: "transform 0.15s" }}>
                  <polyline points="6 9 12 15 18 9"/>
                </svg>
              </div>

              {statusDetailsExpanded && (
                <div style={{
                  position: "absolute", top: 32, left: 0, zIndex: 10,
                  background: "var(--bg-card)", border: "1px solid var(--border)",
                  borderRadius: 8, padding: "12px 16px", minWidth: 240,
                  boxShadow: "0 4px 12px rgba(0, 0, 0, 0.08)", display: "flex", flexDirection: "column", gap: 6
                }}>
                  <div style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", color: "var(--text-muted)", borderBottom: "1px solid var(--border)", paddingBottom: 4 }}>
                    Detailed Metrics Audit
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}>
                    <span>Writing Flags:</span>
                    <strong>{totalIssuesCount}</strong>
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}>
                    <span>Consistency Issues:</span>
                    <strong>{totalConsistencyCount}</strong>
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}>
                    <span>Protected Terms Checked:</span>
                    <strong>{doc.protected_terms?.length || 0}</strong>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>

        <div style={styles.actionCol}>
          {/* Actions Dropdown */}
          <div ref={actionsRef} style={{ position: "relative" }}>
            <button className="btn-premium-solid" onClick={() => setIsActionsDropdownOpen(!isActionsDropdownOpen)}>
              Actions
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" style={{ marginLeft: 6 }}><polyline points="6 9 12 15 18 9"/></svg>
            </button>
            {isActionsDropdownOpen && (
              <div style={styles.actionsDropdownMenu}>
                <button style={styles.dropdownMenuItem} onClick={() => { setIsActionsDropdownOpen(false); handleTabChange("assistant"); }}>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ marginRight: 8 }}><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
                  Open AI Assistant
                </button>
                <button style={styles.dropdownMenuItem} onClick={() => { setIsActionsDropdownOpen(false); handleTabChange("reports"); }}>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ marginRight: 8 }}><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                  Open Executive Report
                </button>
                <button style={styles.dropdownMenuItem} onClick={() => { setIsActionsDropdownOpen(false); setIsDownloadModalOpen(true); }}>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ marginRight: 8 }}><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                  Download Reports
                </button>
                <button style={styles.dropdownMenuItem} onClick={() => { setIsActionsDropdownOpen(false); handleDownloadCorrected(); }}>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ marginRight: 8 }}><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>
                  Download Clean Document
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

        {/* 3. Main editor split pane */}
        {activeTab === "overview" ? (
          renderResultsOverview()
        ) : activeTab === "proofreading" || activeTab === "annotated" || activeTab === "corrected" ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            {/* Sub-selector toggle */}
            <div style={{ display: "flex", gap: 8, margin: "4px 0" }}>
              <button
                style={{
                  background: proofSubTab === "annotated" ? "var(--brand-light)" : "var(--bg-card)",
                  border: "1px solid var(--border)",
                  borderRadius: 6, padding: "5px 12px", fontSize: 12, fontWeight: 700,
                  color: proofSubTab === "annotated" ? "var(--brand)" : "var(--text-secondary)",
                  cursor: "pointer", transition: "all 0.15s"
                }}
                onClick={() => setProofSubTab("annotated")}
              >
                Interactive Editor
              </button>
              <button
                style={{
                  background: proofSubTab === "corrected" ? "var(--brand-light)" : "var(--bg-card)",
                  border: "1px solid var(--border)",
                  borderRadius: 6, padding: "5px 12px", fontSize: 12, fontWeight: 700,
                  color: proofSubTab === "corrected" ? "var(--brand)" : "var(--text-secondary)",
                  cursor: "pointer", transition: "all 0.15s"
                }}
                onClick={() => setProofSubTab("corrected")}
              >
                Clean Preview
              </button>
            </div>

            {proofSubTab === "corrected" ? (
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
            ) : (
              /* Annotated split editor */
              <div style={styles.splitGrid}>
                {/* Left panel: Document text with inline highlights */}
                <div style={styles.editorPanel}>
                  {doc.raw_text ? (
                    <div 
                      ref={textContainerRef}
                      style={{ ...styles.textView, whiteSpace: "pre-wrap" }}
                      className="annotated-text-view"
                    >
                      {renderDocumentMarkup()}
                    </div>
                  ) : (
                    <div 
                      ref={textContainerRef}
                      style={styles.textView}
                      className="annotated-text-view"
                      dangerouslySetInnerHTML={{ __html: getParagraphBody(annotatedHtml) }}
                    />
                  )}
                </div>

                {/* Right panel: Suggestions rail */}
                <div style={styles.sidebarPanel}>
                  {/* Sticky Segmented Filter Bar */}
                  <div
                    className="segmented-filter-bar"
                    role="tablist"
                    aria-label="Correction issue category filters"
                    style={{
                      position: "sticky",
                      top: 0,
                      zIndex: 10,
                      background: "var(--bg-card)",
                      padding: "4px 0",
                      borderBottom: "1px solid var(--border)",
                      marginBottom: "4px"
                    }}
                  >
                    <div style={{
                      display: "flex",
                      background: "var(--bg-page)",
                      padding: "3px",
                      borderRadius: "10px",
                      border: "1px solid var(--border)",
                      gap: "3px"
                    }}>
                      {[
                        { id: "all", label: "All Issues", count: allUnresolvedCount },
                        { id: "grammar", label: "Grammar", count: grammarUnresolvedCount },
                        { id: "spelling", label: "Spelling", count: spellingUnresolvedCount }
                      ].map((tab) => {
                        const isSelected = typeFilter === tab.id;
                        return (
                          <button
                            key={tab.id}
                            role="tab"
                            id={`filter-tab-${tab.id}`}
                            aria-selected={isSelected}
                            aria-controls="corrections-card-list"
                            tabIndex={0}
                            className={`filter-pill-btn ${isSelected ? "active" : ""}`}
                            onClick={() => setTypeFilter(tab.id)}
                            onKeyDown={(e) => {
                              if (e.key === "Enter" || e.key === " ") {
                                e.preventDefault();
                                setTypeFilter(tab.id);
                              }
                            }}
                            style={{
                              flex: 1,
                              display: "flex",
                              alignItems: "center",
                              justifyContent: "center",
                              gap: "4px",
                              padding: "7px 6px",
                              fontSize: "12px",
                              fontWeight: isSelected ? 700 : 600,
                              borderRadius: "7px",
                              border: "none",
                              cursor: "pointer",
                              background: isSelected ? "var(--brand)" : "transparent",
                              color: isSelected ? "#ffffff" : "var(--text-secondary)",
                              boxShadow: isSelected ? "0 1px 3px rgba(0, 0, 0, 0.12)" : "none",
                              transition: "all 0.15s ease",
                              outline: "none"
                            }}
                          >
                            <span>{tab.label}</span>
                            <span style={{
                              fontSize: "10px",
                              fontWeight: 700,
                              padding: "1px 5px",
                              borderRadius: "999px",
                              background: isSelected ? "rgba(255, 255, 255, 0.25)" : "var(--border)",
                              color: isSelected ? "#ffffff" : "var(--text-muted)"
                            }}>
                              {tab.count}
                            </span>
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  {/* Toolbar - Search input */}
                  <div style={styles.sidebarToolbar}>
                    <input
                      type="text"
                      placeholder="Search issues..."
                      style={{ ...styles.sidebarSearch, padding: "8px 12px", border: "1px solid var(--border)", borderRadius: 8, width: "100%", outline: "none", fontSize: 12.5 }}
                      value={search}
                      onChange={(e) => setSearch(e.target.value)}
                    />
                  </div>

                  <div style={styles.sidebarActionHeader}>
                    <p style={styles.sidebarTitle}>
                      {typeFilter === "all" ? "All Unresolved" : typeFilter === "grammar" ? "Grammar Issues" : "Spelling Issues"} ({visibleIssues.length})
                    </p>
                    {visibleIssues.length > 0 && (
                      <div style={styles.bulkRow}>
                        <button style={styles.bulkAccept} onClick={handleAcceptAll}>Accept All</button>
                        <button style={styles.bulkReject} onClick={handleRejectAll}>Reject All</button>
                      </div>
                    )}
                  </div>

                  <div id="corrections-card-list" role="tabpanel" style={styles.cardList}>
                    {visibleIssues.length === 0 ? (
                      <div style={{ ...styles.emptyCard, padding: "24px 16px" }}>
                        <div style={{ display: "flex", justifyContent: "center", marginBottom: 8 }}>
                          <span style={{
                            display: "inline-flex", alignItems: "center", justifyContent: "center",
                            width: 36, height: 36, borderRadius: "50%",
                            background: "var(--green-light)", color: "var(--green)"
                          }}>
                            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                              <polyline points="20 6 9 17 4 12" />
                            </svg>
                          </span>
                        </div>
                        <p style={{ margin: "0 0 4px", fontWeight: 700, color: "var(--text-primary)", fontSize: 13.5 }}>
                          {typeFilter === "grammar"
                            ? "No grammar issues found."
                            : typeFilter === "spelling"
                            ? "No spelling issues found."
                            : "No active issues found."}
                        </p>
                        <p style={{ margin: 0, fontSize: 11.5, color: "var(--text-muted)", lineHeight: 1.4 }}>
                          {typeFilter === "grammar"
                            ? "Your document has no detected grammar or structural issues."
                            : typeFilter === "spelling"
                            ? "No spelling or punctuation errors were detected."
                            : "All spelling and grammar mistakes have been resolved or filtered."}
                        </p>
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
                              borderLeft: isSelected ? `3px solid var(--brand)` : "3px solid var(--border)",
                              boxShadow: isSelected ? "var(--shadow-card)" : "none",
                              backgroundColor: isSelected ? "var(--brand-light)" : "var(--bg-card)",
                              padding: "14px",
                              marginBottom: "10px",
                              borderRadius: "8px",
                              cursor: "pointer",
                              transition: "all 0.2s ease",
                              textAlign: "left",
                              border: "1px solid var(--border)"
                            }}
                          >
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                              <span style={{ fontSize: 11, fontWeight: 750, color: accentColor, textTransform: "uppercase", letterSpacing: 0.5 }}>
                                {issue.issue_type}
                              </span>
                              <span style={{ fontSize: 10.5, color: "var(--text-muted)", fontWeight: 500 }}>
                                Page {issue.page_number || 1}
                              </span>
                            </div>

                            <p style={{ margin: "4px 0", fontSize: 13, fontWeight: 600, color: "var(--text-primary)", lineHeight: 1.4 }}>
                              {issue.reason}
                            </p>

                            {isSelected ? (
                              <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 8 }}>
                                <div style={{ fontSize: 11.5, color: "var(--text-secondary)", lineHeight: 1.35 }}>
                                  <strong>Why it matters:</strong> Review spelling, phrasing, or dictionary compliance guidelines.
                                </div>

                                <div style={{ 
                                  display: "flex", alignItems: "center", gap: 6, 
                                  background: "var(--bg-page)", border: "1px solid var(--border)",
                                  padding: "6px 10px", borderRadius: 6, fontSize: 12
                                }}>
                                  <span style={{ textDecoration: "line-through", color: "var(--red)" }}>{issue.original_text}</span>
                                  <span style={{ color: "var(--text-muted)" }}>➔</span>
                                  <span style={{ color: "var(--green)", fontWeight: 700 }}>{issue.suggested_text}</span>
                                </div>

                                {issueDecisions[idx] === undefined ? (
                                  <div style={{ display: "flex", gap: 8, marginTop: 2 }}>
                                    <button
                                      style={{
                                        flex: 1, padding: "5px 10px", borderRadius: 6,
                                        border: "1px solid var(--border)", background: "var(--bg-card)",
                                        color: "var(--text-secondary)", fontSize: 11.5, fontWeight: 600,
                                        cursor: "pointer"
                                      }}
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        rejectIssue(idx);
                                      }}
                                    >
                                      Reject
                                    </button>
                                    <button
                                      style={{
                                        flex: 1, padding: "5px 10px", borderRadius: 6,
                                        border: "none", background: "var(--brand)",
                                        color: "white", fontSize: 11.5, fontWeight: 650,
                                        cursor: "pointer"
                                      }}
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        acceptIssue(idx);
                                      }}
                                    >
                                      Accept
                                    </button>
                                  </div>
                                ) : (
                                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 2 }}>
                                    <span style={{
                                      fontSize: 11.5, fontWeight: 700,
                                      color: issueDecisions[idx] === "accepted" ? "var(--green)" : "var(--text-muted)"
                                    }}>
                                      {issueDecisions[idx] === "accepted" ? "✓ Accepted" : "✕ Rejected"}
                                    </span>
                                    <button
                                      style={{
                                        padding: "3px 8px", borderRadius: 6, border: "1px solid var(--border)",
                                        background: "var(--bg-card)", color: "var(--text-secondary)",
                                        fontSize: 11, fontWeight: 600, cursor: "pointer"
                                      }}
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
                            ) : (
                              <div style={{ fontSize: 11.5, color: "var(--text-secondary)", marginTop: 4, borderTop: "1px solid var(--border)", paddingTop: 4, display: "flex", gap: 6, alignItems: "center" }}>
                                <span style={{ textDecoration: "line-through", color: "var(--text-muted)" }}>{issue.original_text}</span>
                                <span>➔</span>
                                <span style={{ color: "var(--green)", fontWeight: 650 }}>{issue.suggested_text}</span>
                              </div>
                            )}
                          </div>
                        );
                      })
                    )}
                  </div>
                </div>
              </div>
            )}
          </div>
        ) : activeTab === "assistant" ? (
          /* Embedded AI Assistant Chat Panel */
          <div style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 12, padding: 16, minHeight: 500 }}>
            <Assistant onSelectPage={(page) => {
              setActiveTab("proofreading");
              if (doc && doc.issues) {
                const firstIssueIdx = (doc.issues || []).filter(Boolean).findIndex(i => i.page_number === page);
                if (firstIssueIdx !== -1) {
                  handleSelectIssue(firstIssueIdx);
                }
              }
            }} />
          </div>
        ) : activeTab === "analysis" || activeTab === "context" ? (
          /* Context Analysis Report Dashboard */
          <div style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 12, padding: 20, minHeight: 500 }}>
            <ContextAnalysis id={id} onShowInDocument={handleShowInDocument} />
          </div>
        ) : activeTab === "comparative" || activeTab === "comparative-analysis" ? (
          /* Executive Comparative Analysis Workspace */
          <div style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 12, padding: 20, minHeight: 500 }}>
            <ComparativeAnalysisView
              data={comparativeData}
              isRunning={
                !(comparativeData?.company_profile || comparativeData?.data?.company_profile || comparativeData?.comparative_analysis) &&
                (comparativeLoading || doc?.comparative_analysis_status === "running")
              }
              currentStage={doc?.current_stage || "Stage 10: Comparative Analysis"}
            />
          </div>
        ) : (
          /* Executive Reports Page */
          <div style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 12, padding: 20, minHeight: 500 }}>
            <Reports activeDocId={id} />
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
      {/* Download Experience Modal */}
      {isDownloadModalOpen && (
        <div style={styles.modalOverlay} onClick={() => setIsDownloadModalOpen(false)}>
          <div style={styles.modalCard} onClick={(e) => e.stopPropagation()}>
            <div style={styles.modalHeader}>
              <h3 style={styles.modalTitle}>Download Export Packages</h3>
              <button style={styles.modalCloseBtn} onClick={() => setIsDownloadModalOpen(false)}>
                &times;
              </button>
            </div>
            <div style={styles.modalBody}>
              {/* Row 1 */}
              <div style={styles.downloadItemRow}>
                <div style={styles.downloadItemIcon}>
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--brand)" strokeWidth="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                </div>
                <div style={styles.downloadItemMeta}>
                  <h4 style={styles.downloadItemName}>Executive Report</h4>
                  <p style={styles.downloadItemDesc}>Executive summary, high level KPIs, overall readiness assessment.</p>
                </div>
                <div style={styles.downloadItemActions}>
                  <button style={styles.downloadFormatBtn} onClick={() => handleDownloadFormat("executive", "pdf")}>PDF</button>
                  <button style={styles.downloadFormatBtn} onClick={() => handleDownloadFormat("executive", "html")}>HTML</button>
                  <button style={styles.downloadFormatBtn} onClick={() => handleDownloadFormat("executive", "zip")}>ZIP</button>
                </div>
              </div>
              
              {/* Row 2 */}
              <div style={styles.downloadItemRow}>
                <div style={styles.downloadItemIcon}>
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--brand)" strokeWidth="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
                </div>
                <div style={styles.downloadItemMeta}>
                  <h4 style={styles.downloadItemName}>Detailed Analysis</h4>
                  <p style={styles.downloadItemDesc}>Expanded page-by-page writing issue breakdown & semantic highlights.</p>
                </div>
                <div style={styles.downloadItemActions}>
                  <button style={styles.downloadFormatBtn} onClick={() => handleDownloadFormat("detailed", "pdf")}>PDF</button>
                  <button style={styles.downloadFormatBtn} onClick={() => handleDownloadFormat("detailed", "html")}>HTML</button>
                  <button style={styles.downloadFormatBtn} onClick={() => handleDownloadFormat("detailed", "zip")}>ZIP</button>
                </div>
              </div>

              {/* Row 3 */}
              <div style={styles.downloadItemRow}>
                <div style={styles.downloadItemIcon}>
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--brand)" strokeWidth="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 1 1 3 3L12 15l-4 1 1-4z"/></svg>
                </div>
                <div style={styles.downloadItemMeta}>
                  <h4 style={styles.downloadItemName}>Writing Review</h4>
                  <p style={styles.downloadItemDesc}>Isolated proofreading flags, spelling mistakes, grammar edits.</p>
                </div>
                <div style={styles.downloadItemActions}>
                  <button style={styles.downloadFormatBtn} onClick={() => handleDownloadFormat("writing", "pdf")}>PDF</button>
                  <button style={styles.downloadFormatBtn} onClick={() => handleDownloadFormat("writing", "html")}>HTML</button>
                  <button style={styles.downloadFormatBtn} onClick={() => handleDownloadFormat("writing", "zip")}>ZIP</button>
                </div>
              </div>

              {/* Row 4 */}
              <div style={styles.downloadItemRow}>
                <div style={styles.downloadItemIcon}>
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--brand)" strokeWidth="2"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg>
                </div>
                <div style={styles.downloadItemMeta}>
                  <h4 style={styles.downloadItemName}>AI Verification</h4>
                  <p style={styles.downloadItemDesc}>Detailed factual claims checklist, logical verification results.</p>
                </div>
                <div style={styles.downloadItemActions}>
                  <button style={styles.downloadFormatBtn} onClick={() => handleDownloadFormat("ai_verification", "pdf")}>PDF</button>
                  <button style={styles.downloadFormatBtn} onClick={() => handleDownloadFormat("ai_verification", "html")}>HTML</button>
                  <button style={styles.downloadFormatBtn} onClick={() => handleDownloadFormat("ai_verification", "zip")}>ZIP</button>
                </div>
              </div>

              {/* Row 5 */}
              <div style={styles.downloadItemRow}>
                <div style={styles.downloadItemIcon}>
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--brand)" strokeWidth="2"><rect x="2" y="2" width="20" height="20" rx="2.18" ry="2.18"/><line x1="7" y1="2" x2="7" y2="22"/><line x1="17" y1="2" x2="17" y2="22"/><line x1="2" y1="12" x2="22" y2="12"/><line x1="2" y1="7" x2="7" y2="7"/><line x1="2" y1="17" x2="7" y2="17"/><line x1="17" y1="17" x2="22" y2="17"/><line x1="17" y1="7" x2="22" y2="7"/></svg>
                </div>
                <div style={styles.downloadItemMeta}>
                  <h4 style={styles.downloadItemName}>Technical Package</h4>
                  <p style={styles.downloadItemDesc}>Raw JSON outputs, document embeddings log, schema bindings.</p>
                </div>
                <div style={styles.downloadItemActions}>
                  <button style={styles.downloadFormatBtn} onClick={() => handleDownloadFormat("technical", "pdf")}>PDF</button>
                  <button style={styles.downloadFormatBtn} onClick={() => handleDownloadFormat("technical", "html")}>HTML</button>
                  <button style={styles.downloadFormatBtn} onClick={() => handleDownloadFormat("technical", "zip")}>ZIP</button>
                </div>
              </div>
            </div>
            <div style={styles.modalFooter}>
              <button style={styles.modalCloseFooterBtn} onClick={() => setIsDownloadModalOpen(false)}>
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
  topSummaryRow: {
    display: "flex",
    gap: 12,
    marginBottom: 4,
    width: "100%",
  },
  summaryMetric: {
    flex: 1,
    background: "var(--bg-card)",
    border: "1px solid var(--border)",
    borderRadius: 8,
    padding: "12px 16px",
    display: "flex",
    flexDirection: "column",
    gap: 4,
    textAlign: "left",
  },
  metricLabel: {
    fontSize: 10,
    fontWeight: 700,
    color: "var(--text-secondary)",
    textTransform: "uppercase",
    letterSpacing: 0.5,
  },
  metricValue: {
    fontSize: 18,
    fontWeight: 700,
    color: "var(--text-primary)",
  },
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
  cardList: { display: "flex", flexDirection: "column", gap: 6, overflowY: "auto", flex: 1, maxHeight: "calc(100vh - 280px)", paddingRight: 4 },
  emptyCard: {
    padding: 16, background: "var(--bg-card)", border: "1px dashed var(--border)",
    borderRadius: 8, fontSize: 12.5, color: "var(--text-muted)", textAlign: "center",
  },
  suggestionCard: {
    padding: "12px 14px", background: "transparent", borderBottom: "1px solid var(--border)",
    cursor: "pointer", transition: "all 0.15s", textAlign: "left",
  },
  suggestionSelected: {
    background: "var(--bg-page)",
    borderRadius: 8,
    borderBottomColor: "transparent",
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
  actionsDropdownMenu: {
    position: "absolute", top: 40, right: 0, width: 220,
    background: "var(--bg-card)", border: "1px solid var(--border)",
    borderRadius: 8, boxShadow: "var(--shadow-card)", zIndex: 1000,
    display: "flex", flexDirection: "column", padding: "6px 0",
  },
  dropdownMenuItem: {
    background: "none", border: "none", display: "flex", alignItems: "center",
    padding: "10px 14px", fontSize: 13, color: "var(--text-primary)",
    cursor: "pointer", width: "100%", textAlign: "left",
  },

  downloadItemRow: {
    display: "flex", alignItems: "center", gap: 12, padding: "14px 20px",
    borderBottom: "1px solid var(--border)",
  },
  downloadItemIcon: {
    width: 36, height: 36, borderRadius: 8, background: "var(--brand-light)",
    display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
  },
  downloadItemMeta: { flex: 1, minWidth: 0 },
  downloadItemName: { margin: 0, fontSize: 13.5, fontWeight: 700, color: "var(--text-primary)" },
  downloadItemDesc: { margin: "2px 0 0", fontSize: 11.5, color: "var(--text-muted)", lineHeight: 1.4 },
  downloadItemActions: { display: "flex", gap: 8, alignItems: "center" },
  downloadFormatBtn: {
    background: "none", border: "1px solid var(--border)", borderRadius: 6,
    padding: "6px 12px", fontSize: 12, fontWeight: 600, color: "var(--text-secondary)",
    cursor: "pointer",
  },
  tabIcon: {
    display: "flex", alignItems: "center", justifyContent: "center",
    width: 28, height: 28, borderRadius: 6,
    background: "var(--bg-page)", color: "var(--text-secondary)",
  },
  tabTitle: { fontSize: 12.5, fontWeight: 700, color: "var(--text-primary)" },
  tabSubtitle: { fontSize: 10, color: "var(--text-muted)", marginTop: 1 },
  processingGrid: {
    display: "grid", gridTemplateColumns: "180px 1fr", gap: 24,
    maxWidth: 680, width: "100%", padding: 24,
    background: "var(--bg-card)", border: "1px solid var(--border)",
    borderRadius: 12, boxShadow: "var(--shadow-card)",
  },
  processingLeft: {
    display: "flex", flexDirection: "column", alignItems: "center",
    justifyContent: "center", borderRight: "1px solid var(--border)",
    paddingRight: 24,
  },
  processingIconCircle: {
    width: 80, height: 80, borderRadius: "50%",
    background: "var(--brand-light)", display: "flex",
    alignItems: "center", justifyContent: "center",
  },
  processingRight: { textAlign: "left" },
  overviewContainer: { display: "flex", flexDirection: "column", gap: 16 },
  overviewHeader: { textAlign: "left" },
  overviewTitle: { margin: 0, fontSize: 20, fontWeight: 700, color: "var(--text-primary)" },
  overviewSubtitle: { margin: "4px 0 0", fontSize: 13, color: "var(--text-secondary)" },
  overviewGrid: { display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 },
  overviewCard: {
    background: "var(--bg-card)", border: "1px solid var(--border)",
    borderRadius: 8, padding: 16, display: "flex", flexDirection: "column",
    textAlign: "left", minHeight: 140,
  },
  overviewCardTop: { display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 },
  overviewCardTitle: { margin: 0, fontSize: 14, fontWeight: 700, color: "var(--text-secondary)" },
  overviewCardDesc: { margin: 0, fontSize: 12.5, color: "var(--text-muted)", flex: 1, lineHeight: 1.5, marginTop: 4 },
  overviewCardBtn: {
    background: "none", border: "none", color: "var(--brand)", fontSize: 12, fontWeight: 700,
    cursor: "pointer", padding: 0, alignSelf: "flex-start", marginTop: 12, display: "flex", alignItems: "center",
  },
  cardBadge: { fontSize: 10, fontWeight: 700, padding: "2px 8px", borderRadius: 999 },
};
