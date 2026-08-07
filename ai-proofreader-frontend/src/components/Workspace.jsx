import React, { useState, useEffect, useRef, useMemo } from "react";
import { useParams, useNavigate, useLocation } from "react-router-dom";
import { fetchDocument, fetchPreferences, fetchComparativeAnalysis, retryJobStage } from "../api";
import Assistant from "./Assistant";
import ContextAnalysis from "./ContextAnalysis";
import Reports from "./Reports";
import ComparativeAnalysisView from "./ComparativeAnalysisView";
import PDFReviewWorkspace from "./PDFReviewWorkspace";


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

const STAGE_NAME_MAP = {
  "Upload Complete": "Document Uploaded",
  "Document Extraction": "Document Content Extraction",
  "Spell Checking": "Language & Spelling Review",
  "Grammar Checking": "Grammar & Writing Quality Review",
  "RAG Index Construction": "Knowledge Index Creation",
  "Contextual Consistency Analysis": "Consistency & Contradiction Review",
  "Comparative Analysis": "Competitive Benchmark Analysis",
  "Executive Report Generation": "Executive Insights Report"
};

const REQUIRED_8_STAGES = [
  { id: 1, name: "Document Uploaded", description: "Document successfully received and queued.", feature: "Document Uploaded", flag: "upload_ready" },
  { id: 2, name: "Document Content Extraction", description: "Extracting text, tables, images and document structure.", feature: "Document Viewer", flag: "document_viewer_ready" },
  { id: 3, name: "Language & Spelling Review", description: "Identifying spelling and language issues.", feature: "Proofreading", flag: "spell_ready" },
  { id: 4, name: "Grammar & Writing Quality Review", description: "Analyzing grammar, readability and writing quality.", feature: "Grammar Results", flag: "grammar_ready" },
  { id: 5, name: "Knowledge Index Creation", description: "Preparing document knowledge base for AI Q&A.", feature: "AI Assistant", flag: "rag_ready" },
  { id: 6, name: "Consistency & Contradiction Review", description: "Checking document consistency and detecting conflicts.", feature: "Context Analysis", flag: "context_analysis_ready" },
  { id: 7, name: "Competitive Benchmark Analysis", description: "Comparing document against industry and peer references.", feature: "Comparative Analysis", flag: "comparative_analysis_ready" },
  { id: 8, name: "Executive Insights Report", description: "Generating management-ready executive insights.", feature: "Reports", flag: "reports_ready" }
];

const getTimelineStages = (doc) => {
  if (!doc) return [];

  if (Array.isArray(doc.stages) && doc.stages.length > 0) {
    return doc.stages.map((st, idx) => {
      const mappedName = STAGE_NAME_MAP[st.name] || st.name || REQUIRED_8_STAGES[idx]?.name || `Stage ${idx + 1}`;
      const desc = REQUIRED_8_STAGES[idx]?.description || "";
      return {
        id: idx + 1,
        stage_id: st.stage_id,
        label: mappedName,
        description: desc,
        feature: st.unlocked_feature || REQUIRED_8_STAGES[idx]?.feature || "Feature",
        status: st.status || "Pending",
        duration: st.duration,
        errors: st.errors,
        output_location: st.output_location,
        state: st.status === "Completed" ? "completed" : st.status === "Running" ? "active" : st.status === "Failed" ? "failed" : "pending"
      };
    });
  }

  const percent = doc.progress_percentage || 0;
  const isCompleted = doc.status === "completed";

  return REQUIRED_8_STAGES.map((st) => {
    let status = "Pending";
    if (isCompleted || doc[st.flag]) {
      status = "Completed";
    } else if (doc.current_stage && doc.current_stage.toLowerCase().includes(st.name.toLowerCase())) {
      status = "Running";
    } else if (doc.status === "failed") {
      status = "Failed";
    }
    return {
      id: st.id,
      stage_id: `stage_${st.id}`,
      label: st.name,
      description: st.description,
      feature: st.feature,
      status: status,
      duration: null,
      errors: null,
      state: status === "Completed" ? "completed" : status === "Running" ? "active" : status === "Failed" ? "failed" : "pending"
    };
  });
};

const StagePipelineCard = ({ doc, onRetryStage }) => {
  if (!doc) return null;
  const stages = getTimelineStages(doc);
  const overallProgress = doc.overall_progress !== undefined ? doc.overall_progress : Math.round(doc.progress_percentage || 0);

  return (
    <div style={{
      background: "var(--bg-card)",
      border: "1px solid var(--border)",
      borderRadius: 12,
      padding: "16px 20px",
      marginBottom: 20,
      boxShadow: "var(--shadow-card)"
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <div>
          <h3 style={{ margin: 0, fontSize: 15, fontWeight: 700, color: "var(--text-primary)" }}>
            Execution Architecture & Stage Pipeline
          </h3>
          <p style={{ margin: "2px 0 0", fontSize: 12, color: "var(--text-secondary)" }}>
            Asynchronous Stage Orchestration • Incremental Feature Unlocking
          </p>
        </div>
        <div style={{
          background: "var(--brand-light)", color: "var(--brand)",
          padding: "4px 12px", borderRadius: 999, fontSize: 12, fontWeight: 700
        }}>
          {overallProgress}% Complete
        </div>
      </div>

      {/* Progress Bar */}
      <div style={{ width: "100%", height: 6, background: "var(--border)", borderRadius: 3, overflow: "hidden", marginBottom: 16 }}>
        <div style={{ width: `${overallProgress}%`, height: "100%", background: "var(--brand)", transition: "width 0.4s ease" }} />
      </div>

      {/* Grid of 8 Stage Cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))", gap: 12 }}>
        {stages.map((st, idx) => {
          const isCompleted = st.status === "Completed";
          const isRunning = st.status === "Running";
          const isFailed = st.status === "Failed";

          return (
            <div key={st.stage_id || idx} style={{
              border: "1px solid var(--border)",
              borderColor: isRunning ? "var(--brand)" : isCompleted ? "var(--green)" : isFailed ? "var(--red)" : "var(--border)",
              background: isRunning ? "rgba(108, 92, 231, 0.05)" : isCompleted ? "rgba(34, 197, 94, 0.04)" : "var(--bg-card)",
              borderRadius: 8,
              padding: "12px 14px",
              display: "flex",
              flexDirection: "column",
              justify: "space-between",
              minHeight: 110
            }}>
              <div>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                  {/* Stage Number & Indicator Group */}
                  <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    {/* Circular Stage Number Badge - ALWAYS VISIBLE */}
                    <span style={{
                      width: 20, height: 20, borderRadius: "50%",
                      background: isCompleted ? "var(--green-light)" : isRunning ? "var(--brand-light)" : isFailed ? "var(--red-light)" : "var(--border)",
                      color: isCompleted ? "var(--green)" : isRunning ? "var(--brand)" : isFailed ? "var(--red)" : "var(--text-muted)",
                      display: "inline-flex", alignItems: "center", justifyContent: "center",
                      fontSize: 11, fontWeight: 800, flexShrink: 0
                    }}>
                      {idx + 1}
                    </span>

                    {/* Status Icon / Animated Spinner immediately to the right */}
                    {isRunning && (
                      <span style={{
                        width: 12, height: 12, borderRadius: "50%",
                        border: "2px solid var(--brand-light)",
                        borderTopColor: "var(--brand)",
                        animation: "spin 0.8s linear infinite",
                        display: "inline-block", flexShrink: 0
                      }} />
                    )}
                    {isCompleted && (
                      <span style={{ fontSize: 12, color: "var(--green)", fontWeight: 800, flexShrink: 0 }}>✓</span>
                    )}
                    {isFailed && (
                      <span style={{ fontSize: 12, color: "var(--red)", fontWeight: 800, flexShrink: 0 }}>⚠</span>
                    )}

                    <span style={{ fontSize: 12.5, fontWeight: 700, color: "var(--text-primary)" }}>
                      {st.label}
                    </span>
                  </div>

                  <span style={{
                    fontSize: 9.5, fontWeight: 700, padding: "2px 6px", borderRadius: 4,
                    background: isCompleted ? "var(--green-light)" : isRunning ? "var(--brand-light)" : isFailed ? "var(--red-light)" : "var(--border)",
                    color: isCompleted ? "var(--green)" : isRunning ? "var(--brand)" : isFailed ? "var(--red)" : "var(--text-muted)",
                    flexShrink: 0
                  }}>
                    {st.status}
                  </span>
                </div>

                <p style={{ margin: "4px 0 0", fontSize: 11, color: "var(--text-secondary)", lineHeight: 1.35 }}>
                  {st.description}
                </p>
              </div>

              <div style={{ marginTop: 8, display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 10.5, color: "var(--text-muted)" }}>
                <span>{isCompleted ? "✓ Completed" : isRunning ? "Processing..." : isFailed ? "Failed" : "Queued"}</span>
                {st.duration !== null && st.duration !== undefined && (
                  <span>{st.duration}s</span>
                )}
              </div>

              {onRetryStage && (isCompleted || isFailed) && !isRunning && (
                <button
                  style={{
                    marginTop: 6,
                    background: isFailed ? "var(--red)" : "var(--brand-light)",
                    color: isFailed ? "white" : "var(--brand)",
                    border: isFailed ? "none" : "1px solid var(--brand)",
                    borderRadius: 4,
                    padding: "4px 8px",
                    fontSize: 10.5,
                    fontWeight: 700,
                    cursor: "pointer",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    gap: 4
                  }}
                  onClick={() => onRetryStage(st.stage_id)}
                  title={`Click to rerun ${st.label}`}
                >
                  <span>🔄</span> {isFailed ? "Retry Stage" : "Rerun Stage"}
                </button>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

const WorkspaceSidebar = ({
  doc,
  stages,
  overallProgress,
  onRefresh,
  onViewRawText,
  onOpenAssistant,
  onDownloadOriginal,
  onRetryStage
}) => {
  if (!doc) return null;

  const [isRefreshing, setIsRefreshing] = useState(false);

  const isCompleted = doc.status === "completed";
  const isProcessing = doc.status === "processing" || doc.status === "pending";
  const isFailed = doc.status === "failed";

  const isExtractionReady = doc.document_viewer_ready || doc.extraction_ready || (doc.raw_text && doc.raw_text.length > 0) || isCompleted;
  const isAssistantReady = doc.rag_ready || doc.rag_status === "completed" || isCompleted;

  // Calculate live overall progress accurately from flags if missing/0
  const computedProgress = () => {
    if (isCompleted) return 100;
    if (doc.overall_progress !== undefined && doc.overall_progress > 0) return doc.overall_progress;
    if (doc.progress_percentage !== undefined && doc.progress_percentage > 0) return Math.round(doc.progress_percentage);
    
    if (doc.reports_ready) return 100;
    if (doc.comparative_analysis_ready || doc.comparative_analysis_status === "completed") return 87;
    if (doc.context_analysis_ready || doc.context_analysis_status === "completed") return 75;
    if (doc.rag_ready || doc.rag_status === "completed") return 62;
    if (doc.grammar_ready || doc.proofreading_ready) return 50;
    if (doc.spell_ready) return 37;
    if (doc.document_viewer_ready || doc.extraction_ready) return 25;
    if (doc.upload_ready) return 12;
    return 0;
  };

  const activeProgress = computedProgress();

  // Clean human-readable stage name calculation
  const getStageDisplayName = () => {
    if (isCompleted) return "Stage 8: Executive Insights Report (Completed)";
    if (doc.current_stage && doc.current_stage !== "Completed" && doc.current_stage !== "completed") {
      if (typeof doc.current_stage === "number") {
        const stageObj = REQUIRED_8_STAGES.find(s => s.id === doc.current_stage);
        return `Stage ${doc.current_stage}: ${stageObj ? stageObj.name : "Processing"}`;
      }
      return String(doc.current_stage);
    }
    if (doc.context_analysis_ready) return "Stage 7: Competitive Benchmark Analysis";
    if (doc.rag_ready) return "Stage 6: Consistency & Contradiction Review";
    if (doc.proofreading_ready || doc.grammar_ready) return "Stage 5: Knowledge Index Creation";
    if (doc.spell_ready) return "Stage 4: Grammar & Writing Quality Review";
    if (doc.document_viewer_ready || doc.extraction_ready) return "Stage 3: Language & Spelling Review";
    if (doc.upload_ready) return "Stage 2: Document Content Extraction";
    return "Stage 1: Document Uploaded";
  };

  const stageNameDisplay = getStageDisplayName();

  const handleRefreshClick = async () => {
    setIsRefreshing(true);
    if (onRefresh) await onRefresh();
    setTimeout(() => setIsRefreshing(false), 600);
  };

  const sidebarActionStyle = {
    display: "flex",
    alignItems: "center",
    gap: 8,
    width: "100%",
    padding: "8px 12px",
    borderRadius: 7,
    background: "var(--bg-card, #FFFFFF)",
    border: "1px solid var(--border, #E2E8F0)",
    color: "var(--text-primary, #1E293B)",
    fontSize: 12,
    fontWeight: 650,
    cursor: "pointer",
    transition: "all 0.15s ease",
    textAlign: "left"
  };

  return (
    <div style={{
      background: "var(--bg-card)",
      border: "1px solid var(--border)",
      borderRadius: 12,
      padding: 16,
      display: "flex",
      flexDirection: "column",
      gap: 16,
      boxShadow: "var(--shadow-card)",
      minWidth: 280,
      maxWidth: 340,
      width: "100%",
      flexShrink: 0,
      position: "sticky",
      top: 80,
      alignSelf: "flex-start"
    }}>
      
      {/* SECTION 1: DOCUMENT DETAILS */}
      <div style={{ borderBottom: "1px solid var(--border)", paddingBottom: 14 }}>
        <h4 style={{ margin: "0 0 10px", fontSize: 13.5, fontWeight: 750, color: "var(--text-primary)", display: "flex", alignItems: "center", gap: 6 }}>
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="var(--brand)" strokeWidth="2.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
          Document Details
        </h4>

        <div style={{ display: "flex", flexDirection: "column", gap: 8, fontSize: 12 }}>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span style={{ color: "var(--text-secondary)" }}>File Name:</span>
            <strong style={{ color: "var(--text-primary)", maxWidth: 150, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={doc.filename}>
              {doc.filename}
            </strong>
          </div>

          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span style={{ color: "var(--text-secondary)" }}>Pages:</span>
            <strong style={{ color: "var(--text-primary)" }}>{doc.total_pages || doc.pages || 1}</strong>
          </div>

          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span style={{ color: "var(--text-secondary)" }}>Uploaded:</span>
            <strong style={{ color: "var(--text-primary)" }}>{doc.uploadedLabel || "Aug 04, 2026"}</strong>
          </div>

          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ color: "var(--text-secondary)" }}>Status:</span>
            <span style={{
              fontSize: 10.5, fontWeight: 750, padding: "2px 8px", borderRadius: 4,
              background: isCompleted ? "var(--green-light)" : isFailed ? "var(--red-light)" : "var(--amber-light)",
              color: isCompleted ? "var(--green)" : isFailed ? "var(--red)" : "var(--amber)"
            }}>
              {isCompleted ? "Completed" : isFailed ? "Failed" : "Processing"}
            </span>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 2, marginTop: 2 }}>
            <span style={{ color: "var(--text-secondary)", fontSize: 11 }}>Current Stage:</span>
            <strong style={{ color: "var(--brand)", fontSize: 11.5, lineHeight: 1.3 }}>{stageNameDisplay}</strong>
          </div>

          <div style={{ marginTop: 4 }}>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, fontWeight: 700, marginBottom: 4 }}>
              <span>Pipeline Progress</span>
              <span style={{ color: "var(--brand)" }}>{activeProgress}%</span>
            </div>
            <div style={{ width: "100%", height: 6, background: "var(--border)", borderRadius: 3, overflow: "hidden" }}>
              <div style={{ width: `${activeProgress}%`, height: "100%", background: "var(--brand)", transition: "width 0.3s ease" }} />
            </div>
          </div>
        </div>
      </div>

      {/* SECTION 4: QUICK ACTIONS */}
      <div>
        <h4 style={{ margin: "0 0 10px", fontSize: 13.5, fontWeight: 750, color: "var(--text-primary)", display: "flex", alignItems: "center", gap: 6 }}>
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="var(--brand)" strokeWidth="2.5"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
          Quick Actions
        </h4>

        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <button onClick={handleRefreshClick} style={sidebarActionStyle}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" style={{ transform: isRefreshing ? "rotate(180deg)" : "none", transition: "transform 0.3s" }}>
              <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 11-.57-8.38l5.67-5.67"/>
            </svg>
            {isRefreshing ? "Updating Status..." : "✓ Refresh Status"}
          </button>

          <button
            onClick={() => isExtractionReady && onViewRawText()}
            disabled={!isExtractionReady}
            style={{
              ...sidebarActionStyle,
              opacity: isExtractionReady ? 1 : 0.5,
              cursor: isExtractionReady ? "pointer" : "not-allowed"
            }}
            title={isExtractionReady ? "View Extracted Text (Stage 2 Ready)" : "🔒 Available after Stage 2 Document Content Extraction"}
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>
            {isExtractionReady ? "✓ View Extracted Text" : "🔒 View Extracted Text"}
          </button>

          <button
            onClick={() => isAssistantReady && onOpenAssistant()}
            disabled={!isAssistantReady}
            style={{
              ...sidebarActionStyle,
              opacity: isAssistantReady ? 1 : 0.5,
              cursor: isAssistantReady ? "pointer" : "not-allowed"
            }}
            title={isAssistantReady ? "Ask AI Assistant (Stage 5 Ready)" : "🔒 Available after Stage 5 Knowledge Index Creation"}
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
            {isAssistantReady ? "✓ Ask AI Assistant" : "🔒 Ask AI Assistant"}
          </button>

          <button onClick={onDownloadOriginal} style={sidebarActionStyle} title="Download Original PDF Document">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
            ✓ Download Original
          </button>

          {isFailed && (
            <button onClick={() => onRetryStage("all")} style={{ ...sidebarActionStyle, background: "var(--red-light)", color: "var(--red)", border: "1px solid rgba(239,68,68,0.2)" }}>
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M1 4v6h6M23 20v-6h-6"/><path d="M20.49 9A9 9 0 0 0 5.64 5.64L1 10m22 4l-4.64 4.36A9 9 0 0 1 3.51 15"/></svg>
              Re-run Analysis
            </button>
          )}
        </div>
      </div>

    </div>
  );
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
  const [activeTab, setActiveTab] = useState(() => {
    const params = new URLSearchParams(window.location.search);
    const initialTab = params.get("tab") || "proofreading";
    console.log("[Workspace Runtime] Initialized activeTab:", initialTab);
    return initialTab;
  });
  const [isDownloadModalOpen, setIsDownloadModalOpen] = useState(false);
  const [isActionsDropdownOpen, setIsActionsDropdownOpen] = useState(false);
  const [rawTextOpen, setRawTextOpen] = useState(false);
  const [statusDetailsExpanded, setStatusDetailsExpanded] = useState(false);
  const [proofSubTab, setProofSubTab] = useState("annotated");
  const [zoomLevel, setZoomLevel] = useState(100);
  const [currentPage, setCurrentPage] = useState(1);
  const [documentViewMode, setDocumentViewMode] = useState("pdfOverlay");
  const [docCanvasMode, setDocCanvasMode] = useState("highlighted");
  const [isIssuesDrawerOpen, setIsIssuesDrawerOpen] = useState(true);
  const [isDocInfoOpen, setIsDocInfoOpen] = useState(false);
  const [comparativeData, setComparativeData] = useState(null);
  const [comparativeLoading, setComparativeLoading] = useState(false);
  const [reRunningPipeline, setReRunningPipeline] = useState(false);
  const actionsRef = useRef(null);

  const handleDownloadOriginal = () => {
    if (!id) return;
    const link = document.createElement("a");
    link.href = `/api/documents/${id}/file`;
    link.target = "_blank";
    link.download = doc?.filename || "document.pdf";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

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

  const updateDocWithLocalStorage = (data) => {
    if (!data) return;
    setDoc(data);
    localStorage.setItem("currentlyOpenDocId", data.id || data.job_id);
    localStorage.setItem("currentlyOpenDocName", data.filename || "Document");
    localStorage.setItem("currentlyOpenDocPages", data.total_pages || data.pages || 1);
    localStorage.setItem("currentlyOpenDocStatus", data.status || "pending");
    localStorage.setItem("currentlyOpenDocIssuesCount", (data.issues || []).length);
    localStorage.setItem("currentlyOpenDocConsistencyIssues", data.context_analysis_issues_count || 0);
    localStorage.setItem("currentlyOpenDocFlags", JSON.stringify({
      upload_ready: data.upload_ready,
      document_viewer_ready: data.document_viewer_ready || data.extraction_ready,
      spell_ready: data.spell_ready,
      grammar_ready: data.grammar_ready,
      proofreading_ready: data.proofreading_ready || data.spell_ready || data.grammar_ready || data.status === "completed",
      rag_ready: data.rag_ready || data.rag_status === "completed" || data.status === "completed",
      context_analysis_ready: data.context_analysis_ready || data.context_analysis_status === "completed" || data.status === "completed",
      comparative_analysis_ready: data.comparative_analysis_ready || data.comparative_analysis_status === "completed" || data.status === "completed",
      reports_ready: data.reports_ready || data.status === "completed"
    }));
    window.dispatchEvent(new CustomEvent("activeDocChanged", { detail: data }));
  };

  const handleRetryStage = async (stageId = "all") => {
    if (!id || reRunningPipeline) return;
    setReRunningPipeline(true);
    try {
      await retryJobStage(id, stageId);
      setDoc((prev) => (prev ? { ...prev, status: "processing" } : prev));

      let attempts = 0;
      const pollInterval = setInterval(async () => {
        attempts += 1;
        try {
          const freshData = await fetchDocument(id);
          if (freshData) {
            updateDocWithLocalStorage(freshData);
            if (freshData.status === "completed" || freshData.status === "failed" || attempts >= 30) {
              clearInterval(pollInterval);
              setReRunningPipeline(false);
            }
          }
        } catch (e) {
          console.error("Polling error during stage rerun:", e);
        }
      }, 1500);
    } catch (err) {
      console.error("Failed to retry/rerun stage:", err);
      setReRunningPipeline(false);
    }
  };

  const handleReRunProofreadPipeline = async () => {
    if (!id || reRunningPipeline) return;

    setReRunningPipeline(true);
    try {
      await retryJobStage(id, "all");
      setDoc((prev) => (prev ? { ...prev, status: "processing" } : prev));

      let attempts = 0;
      const pollInterval = setInterval(async () => {
        attempts += 1;
        try {
          const freshData = await fetchDocument(id);
          if (freshData) {
            updateDocWithLocalStorage(freshData);
            if (freshData.status === "completed" || freshData.status === "failed" || attempts >= 30) {
              clearInterval(pollInterval);
              setReRunningPipeline(false);
            }
          }
        } catch (e) {
          console.error("Polling error during re-run:", e);
        }
      }, 1500);

      setActiveTab("proofreading");
      setProofSubTab("annotated");
    } catch (err) {
      console.error("Failed to re-run proofreading pipeline:", err);
      setReRunningPipeline(false);
    }
  };

  // Auto-poll document status while document processing is in progress
  useEffect(() => {
    if (!id || !doc) return;
    if (doc.status === "completed" || doc.status === "failed") return;

    const interval = setInterval(async () => {
      try {
        const fresh = await fetchDocument(id);
        if (fresh) setDoc(fresh);
      } catch (e) {
        console.error("Auto-poll status error:", e);
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [id, doc?.status]);

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


  // Load preferences once on mount
  useEffect(() => {
    fetchPreferences()
      .then((prefs) => setPreferences(prefs || { confidence_threshold: 40 }))
      .catch(() => setPreferences({ confidence_threshold: 40 }));
  }, []);

  // Dynamic status check polling
  useEffect(() => {
    let active = true;
    let timerId = null;

    async function load() {
      if (!id) {
        if (active) {
          setError("No document ID specified.");
          setLoading(false);
        }
        return;
      }
      try {
        const data = await fetchDocument(id);
        if (data) {
          console.log("response.issues.length", data.issues?.length);
          console.log("statistics", data.statistics);
        }
        
        if (!active) return;
        if (!data) {
          setError("Document not found or backend service unreachable.");
          setLoading(false);
          return;
        }

        updateDocWithLocalStorage(data);

        // Process HTML/State as soon as proofreading is ready or document completed
        const isProofreadingAvailable = data && (
          data.status === "completed" ||
          data.proofreading_ready ||
          data.proofreading_status === "completed" ||
          (data.annotated_html && data.annotated_html.length > 0)
        );

        if (isProofreadingAvailable) {
          const threshold = ((preferences && preferences.confidence_threshold !== undefined) ? preferences.confidence_threshold : 40) / 100;

          if (data.raw_text) {
            setIssueDecisions({});
          } else if (data.annotated_html) {
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
                  mark.setAttribute("id", `doc-issue-mark-${idx}`);
                  const isSpelling = isSpellingIssue(issue);
                  const severity = issue.severity || "medium";
                  mark.className = `${isSpelling ? "spelling" : "grammar"} sev-${severity} pending-highlight`;
                  mark.setAttribute("title", `[Issue #${idx + 1}] Click to select: ${issue.reason || issue.issue_type}`);
                }
              }
            });

            setIssueDecisions({});
            setAnnotatedHtml(htmlDoc.body.innerHTML);
          }
        }

        setLoading(false);
        
        // Dynamic Real-Time Stage Polling: Poll every 1.5s as long as any stage is Running, Pending, or processing
        const hasRunningOrPendingStage = Array.isArray(data.stages) && data.stages.some(
          st => st.status === "Running" || st.status === "Pending" || st.status === "queued" || st.status === "processing"
        );
        const isPipelineIncomplete = data.status === "processing" ||
                                     data.status === "pending" ||
                                     data.status === "uploaded" ||
                                     (data.progress_percentage || 0) < 100 ||
                                     hasRunningOrPendingStage ||
                                     data.comparative_analysis_status === "running";

        if (data && isPipelineIncomplete && data.status !== "failed") {
          timerId = setTimeout(load, 1500);
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
  }, [id, preferences?.confidence_threshold]);

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
    const tabVal = params.get("tab") || "proofreading";
    console.log("[Workspace Runtime] Syncing activeTab from URL parameter:", tabVal);
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
    let conf = issue.final_confidence !== undefined ? issue.final_confidence : issue.confidence;
    if (conf === undefined || conf === null || conf === 0) conf = 0.85;
    if (conf > 1) conf = conf / 100;
    
    // Only filter if user explicitly configured a confidence threshold > 0
    const prefThreshold = (preferences && preferences.confidence_threshold !== undefined && preferences.confidence_threshold > 0)
      ? preferences.confidence_threshold
      : 0;
    const threshold = prefThreshold / 100;
    return conf < threshold;
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

  const getIssueCategoryInfo = (issue) => {
    if (!issue) return { cat: "grammar", label: "Grammar Error", bg: "#FEE2E2", border: "#DC2626", color: "#991B1B" };
    const type = (issue.issue_type || issue.category || issue.type || "").toLowerCase();

    if (type.includes("spell") || type.includes("typo")) {
      return { cat: "spelling", label: "Spelling Error", bg: "#FEF3C7", border: "#D97706", color: "#92400E" };
    }
    if (type.includes("style") || type.includes("clarity") || type.includes("readability") || type.includes("conciseness")) {
      return { cat: "style", label: "Style Suggestion", bg: "#E0F2FE", border: "#0284C7", color: "#075985" };
    }
    if (type.includes("consist") || type.includes("context") || type.includes("term")) {
      return { cat: "consistency", label: "Consistency Issue", bg: "#F3E8FF", border: "#9333EA", color: "#6B21A8" };
    }
    return { cat: "grammar", label: "Grammar Error", bg: "#FEE2E2", border: "#DC2626", color: "#991B1B" };
  };

  const renderHighlightedDocumentContent = () => {
    if (!doc) return null;

    if (doc.raw_text) {
      const issues = doc.issues || [];
      const validIssues = [];

      issues.forEach((iss, idx) => {
        if (!iss) return;
        let start = iss.char_start;
        let end = iss.char_end;

        if ((start === undefined || end === undefined) && iss.original_text) {
          const pos = doc.raw_text.indexOf(iss.original_text);
          if (pos !== -1) {
            start = pos;
            end = pos + iss.original_text.length;
          }
        }

        if (start !== undefined && end !== undefined && start >= 0 && end <= doc.raw_text.length) {
          validIssues.push({ ...iss, originalIndex: idx, char_start: start, char_end: end });
        }
      });

      validIssues.sort((a, b) => a.char_start - b.char_start);

      if (validIssues.length === 0) {
        return (
          <div style={{ whiteSpace: "pre-wrap", fontFamily: "Inter, sans-serif", fontSize: 15, lineHeight: 1.85, color: "#1E293B" }}>
            {doc.raw_text}
          </div>
        );
      }

      const elements = [];
      let cursor = 0;

      validIssues.forEach((issue) => {
        const start = issue.char_start;
        const end = issue.char_end;

        if (start < cursor || start > doc.raw_text.length) return;

        if (start > cursor) {
          elements.push(
            <span key={`txt-${cursor}`}>
              {doc.raw_text.slice(cursor, start)}
            </span>
          );
        }

        const idx = issue.originalIndex;
        const isSelected = activeIssueIdx === idx;
        const decision = issueDecisions[idx];
        const info = getIssueCategoryInfo(issue);

        if (decision === "accepted") {
          // Accept: Update document text live with suggested correction, remove highlight
          elements.push(
            <span key={`iss-acc-${idx}`} id={`doc-issue-mark-${idx}`} style={{ fontWeight: 650, color: "#059669", background: "#ECFDF5", padding: "0 2px", borderRadius: 3 }}>
              {issue.suggested_text || issue.original_text || doc.raw_text.slice(start, end)}
            </span>
          );
        } else if (decision === "rejected" || decision === "ignored") {
          // Reject: Keep original text, remove highlight
          elements.push(
            <span key={`iss-rej-${idx}`} id={`doc-issue-mark-${idx}`}>
              {issue.original_text || doc.raw_text.slice(start, end)}
            </span>
          );
        } else {
          // Pending Finding: Render color-coded highlight with wavy underline and compact tooltip
          elements.push(
            <mark
              key={`iss-mark-${idx}`}
              id={`doc-issue-mark-${idx}`}
              onClick={() => handleSelectIssue(idx)}
              style={{
                backgroundColor: isSelected ? (info.cat === "spelling" ? "#FDE68A" : info.cat === "style" ? "#BAE6FD" : info.cat === "consistency" ? "#E9D5FF" : "#FCA5A5") : info.bg,
                borderBottom: `2.5px wavy ${info.border}`,
                color: info.color,
                padding: "2px 6px",
                borderRadius: "4px",
                fontWeight: isSelected ? 850 : 700,
                cursor: "pointer",
                boxShadow: isSelected ? `0 0 0 3px ${info.border}, 0 2px 10px rgba(0,0,0,0.15)` : "0 1px 2px rgba(0,0,0,0.05)",
                transition: "all 0.15s ease-in-out",
                margin: "0 1px",
                display: "inline-block"
              }}
              title={info.label}
            >
              {issue.original_text || doc.raw_text.slice(start, end)}
            </mark>
          );
        }

        cursor = end;
      });

      if (cursor < doc.raw_text.length) {
        elements.push(<span key={`txt-end`}>{doc.raw_text.slice(cursor)}</span>);
      }

      return (
        <div style={{ whiteSpace: "pre-wrap", fontFamily: "Inter, sans-serif", fontSize: 15, lineHeight: 1.85, color: "#1E293B" }}>
          {elements}
        </div>
      );
    }

    if (annotatedHtml) {
      return (
        <div
          ref={textContainerRef}
          className="annotated-document-canvas"
          style={{ fontFamily: "Inter, sans-serif", fontSize: 15, lineHeight: 1.85, color: "#1E293B" }}
          dangerouslySetInnerHTML={{ __html: annotatedHtml }}
        />
      );
    }

    return (
      <div style={{ padding: 40, textAlign: "center", color: "var(--text-muted)", fontSize: 14 }}>
        No document text available to display highlights.
      </div>
    );
  };

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

  // Processing stages (show full screen scanner ONLY if extraction/document viewer is not yet ready)
  const isDocumentExtractionReady = doc.document_viewer_ready || doc.extraction_ready || doc.proofreading_ready || doc.proofreading_status === "completed" || (doc.annotated_html && doc.annotated_html.length > 0) || doc.status === "completed";

  if (!isDocumentExtractionReady && (doc.status === "processing" || doc.status === "pending" || doc.status === "uploaded")) {
    const percent = doc.progress_percentage || doc.overall_progress || 0;
    const curPage = doc.current_page || 0;
    const totPages = doc.total_pages || 0;
    const estTime = doc.estimated_remaining_time || "Estimating...";

    return (
      <div style={styles.centerContainer}>
        <div style={{ maxWidth: 700, width: "100%" }}>
          <div style={{ textAlign: "center", marginBottom: 20 }}>
            <h2 style={{ fontSize: 20, fontWeight: 700, margin: 0, color: "var(--text-primary)" }}>Initializing Document Intelligence...</h2>
            <p style={{ fontSize: 13, color: "var(--text-secondary)", margin: "4px 0 0" }}>
              Extracting document structure & metadata. Document Viewer will unlock momentarily.
            </p>
          </div>
          <StagePipelineCard doc={doc} onRetryStage={handleRetryStage} />
        </div>
      </div>
    );
  }

  if (doc.status === "failed" && (!doc.stages || doc.stages.every(s => s.status === "Failed"))) {
    return (
      <div style={styles.centerContainer}>
        <p style={{ color: "var(--red)", fontSize: 14.5, fontWeight: 700 }}>Processing Failed</p>
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

  const isCompleted = doc?.status === "completed";
  const isProofreadUnlocked = doc?.proofreading_ready || doc?.spell_ready || doc?.grammar_ready || isCompleted;
  const isAmbiguityUnlocked = doc?.context_analysis_ready || doc?.context_analysis_status === "completed" || isCompleted;
  const isAiAssistantUnlocked = doc?.rag_ready || doc?.rag_status === "completed" || isCompleted;
  const isComparativeUnlocked = doc?.comparative_analysis_ready || doc?.comparative_analysis_status === "completed" || isCompleted;
  const isReportsUnlocked = doc?.reports_ready || isCompleted;

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
    const reportKeyMap = {
      executive: "final-report",
      detailed: "chunk-reasoning",
      writing: "cluster-reasoning",
      ai_verification: "claude-verification",
      technical: "comparative-analysis"
    };
    const reportKey = reportKeyMap[packageName] || "final-report";
    
    if (format === "pdf") {
      const link = document.createElement("a");
      link.href = `/api/reports/${id}/${reportKey}/pdf`;
      link.download = `${reportKey}_${id}.pdf`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    } else if (format === "html") {
      window.open(`/api/reports/${id}/${reportKey}`, "_blank");
    } else if (format === "zip") {
      const link = document.createElement("a");
      link.href = `/api/documents/${id}/export`;
      link.download = `export_${id}.zip`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    } else {
      handleDownloadCorrected();
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

  const renderResultsOverview = () => {
    const totalIssues = doc?.issues?.length || 0;
    const consistencyIssues = doc?.context_analysis_issues_count || 0;
    const isCompleted = doc?.status === "completed";

    // Feature unlocking flags from backend
    const isProofreadUnlocked = doc?.proofreading_ready || doc?.spell_ready || doc?.grammar_ready || isCompleted;
    const isAmbiguityUnlocked = doc?.context_analysis_ready || doc?.context_analysis_status === "completed" || isCompleted;
    const isAiAssistantUnlocked = doc?.rag_ready || doc?.rag_status === "completed" || isCompleted;
    const isComparativeUnlocked = doc?.comparative_analysis_ready || doc?.comparative_analysis_status === "completed" || isCompleted;

    return (
      <div style={styles.overviewContainer}>
        <div style={styles.overviewHeader}>
          <h2 style={styles.overviewTitle}>Executive Overview</h2>
          <p style={styles.overviewSubtitle}>Formal assessment indicators generated from structural checking algorithms.</p>
        </div>
        
        <div style={styles.overviewGrid}>
          {/* Card 1: Proofreading */}
          <div style={{ ...styles.overviewCard, opacity: isProofreadUnlocked ? 1 : 0.85 }}>
            <div style={styles.overviewCardTop}>
              <span style={{
                ...styles.cardBadge,
                backgroundColor: !isProofreadUnlocked ? "var(--amber-light)" : totalIssues === 0 ? "var(--green-light)" : totalIssues <= 10 ? "var(--amber-light)" : "var(--red-light)",
                color: !isProofreadUnlocked ? "var(--amber)" : totalIssues === 0 ? "var(--green)" : totalIssues <= 10 ? "var(--amber)" : "var(--red)"
              }}>
                {!isProofreadUnlocked ? "Stage 3/4 Processing..." : totalIssues === 0 ? "Ready for Publication" : `${totalIssues} Issues Found`}
              </span>
              <h3 style={styles.overviewCardTitle}>Proofreading & Quality</h3>
            </div>
            <p style={styles.overviewCardDesc}>
              {isProofreadUnlocked
                ? "Spelling and structural grammar verification flags typographical bugs and formatting errors."
                : "Language, spelling & writing quality review runs in Stages 3 & 4."}
            </p>
            <button
              style={{
                ...styles.overviewCardBtn,
                opacity: isProofreadUnlocked ? 1 : 0.6,
                cursor: isProofreadUnlocked ? "pointer" : "not-allowed"
              }}
              disabled={!isProofreadUnlocked}
              onClick={() => isProofreadUnlocked && handleTabChange("proofreading")}
              title={isProofreadUnlocked ? "View Proofreading (Stage 3 & 4 Ready)" : "🔒 Available after Stage 3 Language & Spelling Review"}
            >
              {isProofreadUnlocked ? "✓ View Proofreading →" : "🔒 Proofreading Locked"}
            </button>
          </div>

          {/* Card 2: Ambiguity Analysis */}
          <div style={{ ...styles.overviewCard, opacity: isAmbiguityUnlocked ? 1 : 0.85 }}>
            <div style={styles.overviewCardTop}>
              <span style={{
                ...styles.cardBadge,
                backgroundColor: !isAmbiguityUnlocked ? "var(--amber-light)" : consistencyIssues === 0 ? "var(--green-light)" : "var(--amber-light)",
                color: !isAmbiguityUnlocked ? "var(--amber)" : consistencyIssues === 0 ? "var(--green)" : "var(--amber)"
              }}>
                {!isAmbiguityUnlocked ? "Stage 6 Pending..." : consistencyIssues === 0 ? "0 Conflicts Found" : `${consistencyIssues} Conflicts Mapped`}
              </span>
              <h3 style={styles.overviewCardTitle}>Ambiguity Analysis</h3>
            </div>
            <p style={styles.overviewCardDesc}>
              {isAmbiguityUnlocked
                ? "Audits conflicting sections, numerical mismatches, and undefined acronyms across clauses."
                : "Consistency and contradiction auditing will evaluate numerical mismatches and acronym conflicts in Stage 6."}
            </p>
            <button
              style={{
                ...styles.overviewCardBtn,
                opacity: isAmbiguityUnlocked ? 1 : 0.6,
                cursor: isAmbiguityUnlocked ? "pointer" : "not-allowed"
              }}
              disabled={!isAmbiguityUnlocked}
              onClick={() => isAmbiguityUnlocked && handleTabChange("analysis")}
              title={isAmbiguityUnlocked ? "View Ambiguity Analysis (Stage 6 Ready)" : "🔒 Available after Stage 6 Consistency & Contradiction Review"}
            >
              {isAmbiguityUnlocked ? "✓ View Ambiguity Analysis →" : "🔒 Ambiguity Analysis Locked"}
            </button>
          </div>

          {/* Card 3: AI Assistant */}
          <div style={{ ...styles.overviewCard, opacity: isAiAssistantUnlocked ? 1 : 0.85 }}>
            <div style={styles.overviewCardTop}>
              <span style={{
                ...styles.cardBadge,
                backgroundColor: !isAiAssistantUnlocked ? "var(--amber-light)" : "var(--brand-light)",
                color: !isAiAssistantUnlocked ? "var(--amber)" : "var(--brand)"
              }}>
                {!isAiAssistantUnlocked ? "Stage 5 Indexing..." : "Interactive Q&A Ready"}
              </span>
              <h3 style={styles.overviewCardTitle}>AI Assistant</h3>
            </div>
            <p style={styles.overviewCardDesc}>
              {isAiAssistantUnlocked
                ? "Ask questions across document text, financial tables, and verified domain knowledge."
                : "Knowledge Index Creation must complete in Stage 5 before AI document Q&A becomes available."}
            </p>
            <button
              style={{
                ...styles.overviewCardBtn,
                opacity: isAiAssistantUnlocked ? 1 : 0.6,
                cursor: isAiAssistantUnlocked ? "pointer" : "not-allowed"
              }}
              disabled={!isAiAssistantUnlocked}
              onClick={() => isAiAssistantUnlocked && handleTabChange("assistant")}
              title={isAiAssistantUnlocked ? "Ask AI Assistant (Stage 5 Ready)" : "🔒 Available after Stage 5 Knowledge Index Creation"}
            >
              {isAiAssistantUnlocked ? "✓ Ask AI Assistant →" : "🔒 AI Assistant Locked"}
            </button>
          </div>

          {/* Card 4: Comparative Analysis */}
          <div style={{ ...styles.overviewCard, opacity: isComparativeUnlocked ? 1 : 0.85 }}>
            <div style={styles.overviewCardTop}>
              <span style={{
                ...styles.cardBadge,
                backgroundColor: !isComparativeUnlocked ? "var(--amber-light)" : "#EFF6FF",
                color: !isComparativeUnlocked ? "var(--amber)" : "#2563EB"
              }}>
                {!isComparativeUnlocked ? "Stage 7 Pending..." : "Executive Benchmark Ready"}
              </span>
              <h3 style={styles.overviewCardTitle}>Comparative Analysis</h3>
            </div>
            <p style={styles.overviewCardDesc}>
              {isComparativeUnlocked
                ? "Deloitte/McKinsey executive benchmarking comparing capabilities against market peers."
                : "Competitive benchmark analysis against industry references runs in Stage 7."}
            </p>
            <button
              style={{
                ...styles.overviewCardBtn,
                opacity: isComparativeUnlocked ? 1 : 0.6,
                cursor: isComparativeUnlocked ? "pointer" : "not-allowed"
              }}
              disabled={!isComparativeUnlocked}
              onClick={() => isComparativeUnlocked && handleTabChange("comparative")}
              title={isComparativeUnlocked ? "View Comparative Analysis (Stage 7 Ready)" : "🔒 Available after Stage 7 Competitive Benchmark Analysis"}
            >
              {isComparativeUnlocked ? "✓ View Comparative Analysis →" : "🔒 Comparative Analysis Locked"}
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
                {doc.status === "completed" ? "✓ Scan Complete" : "⚠ In Progress"}
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
                <button
                  style={{ ...styles.dropdownMenuItem, opacity: isAiAssistantUnlocked ? 1 : 0.5, cursor: isAiAssistantUnlocked ? "pointer" : "not-allowed" }}
                  disabled={!isAiAssistantUnlocked}
                  onClick={() => { if (isAiAssistantUnlocked) { setIsActionsDropdownOpen(false); handleTabChange("assistant"); } }}
                  title={isAiAssistantUnlocked ? "Open AI Assistant (Stage 5 Ready)" : "🔒 Available after Stage 5 Knowledge Index Creation"}
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ marginRight: 8 }}><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
                  {isAiAssistantUnlocked ? "✓ Open AI Assistant" : "🔒 Open AI Assistant"}
                </button>

                <button
                  style={{ ...styles.dropdownMenuItem, opacity: isReportsUnlocked ? 1 : 0.5, cursor: isReportsUnlocked ? "pointer" : "not-allowed" }}
                  disabled={!isReportsUnlocked}
                  onClick={() => { if (isReportsUnlocked) { setIsActionsDropdownOpen(false); handleTabChange("reports"); } }}
                  title={isReportsUnlocked ? "Open Executive Report (Stage 8 Ready)" : "🔒 Available after Stage 8 Executive Insights Report"}
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ marginRight: 8 }}><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                  {isReportsUnlocked ? "✓ Open Executive Report" : "🔒 Open Executive Report"}
                </button>

                <button
                  style={{ ...styles.dropdownMenuItem, opacity: isReportsUnlocked ? 1 : 0.5, cursor: isReportsUnlocked ? "pointer" : "not-allowed" }}
                  disabled={!isReportsUnlocked}
                  onClick={() => { if (isReportsUnlocked) { setIsActionsDropdownOpen(false); setIsDownloadModalOpen(true); } }}
                  title={isReportsUnlocked ? "Download Reports (Stage 8 Ready)" : "🔒 Available after Stage 8 Executive Insights Report"}
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ marginRight: 8 }}><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                  {isReportsUnlocked ? "✓ Download Reports" : "🔒 Download Reports"}
                </button>

                <button
                  style={{ ...styles.dropdownMenuItem, opacity: isProofreadUnlocked ? 1 : 0.5, cursor: isProofreadUnlocked ? "pointer" : "not-allowed" }}
                  disabled={!isProofreadUnlocked}
                  onClick={() => { if (isProofreadUnlocked) { setIsActionsDropdownOpen(false); handleDownloadCorrected(); } }}
                  title={isProofreadUnlocked ? "Download Clean Document (Stage 3 Ready)" : "🔒 Available after Stage 3 Language & Spelling Review"}
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ marginRight: 8 }}><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>
                  {isProofreadUnlocked ? "✓ Download Clean Document" : "🔒 Download Clean Document"}
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

        {/* 3. Master-Detail Enterprise Workspace Split Layout (100% for Proofreading | 73%/27% for Overview and other tabs) */}
        {(() => {
          const isProofreadTab = activeTab === "proofreading" || activeTab === "proofread" || activeTab === "annotated" || activeTab === "corrected";
          console.log("[Workspace Render] activeTab runtime value:", activeTab, "| isProofreadTab:", isProofreadTab);

          return (
            <div style={{ display: "flex", gap: 20, alignItems: "flex-start", width: "100%" }}>
              
              {/* Main Left Workspace View (100% width when proofreading, 73% width otherwise) */}
              <div style={{ flex: isProofreadTab ? "1 1 100%" : "1 1 73%", minWidth: 0, display: "flex", flexDirection: "column", gap: 16 }}>
                {activeTab === "overview" ? (
                  <div>
                    <StagePipelineCard doc={doc} onRetryStage={handleRetryStage} />
                    {renderResultsOverview()}
                  </div>
                ) : isProofreadTab ? (
                  <PDFReviewWorkspace
                    docId={id}
                    documentData={doc}
                    issues={doc?.issues || []}
                    onIssueDecisionChange={(issueId, decision) => {
                      setIssueDecisions((prev) => ({ ...prev, [issueId]: decision }));
                    }}
                    onRefreshDocument={async () => {
                      const updated = await fetchDocument(id);
                      setDoc(updated);
                    }}
                  />
                ) : activeTab === "assistant" ? (
                  /* Embedded AI Assistant Chat Panel */
                  !(doc?.rag_ready || doc?.rag_status === "completed" || doc?.status === "completed") ? (
                    <div style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 12, padding: 40, textAlign: "center" }}>
                      <div style={{ fontSize: 36, marginBottom: 12 }}>🔒</div>
                      <h3 style={{ margin: 0, fontSize: 18, fontWeight: 700, color: "var(--text-primary)" }}>AI Assistant is Locked</h3>
                      <p style={{ fontSize: 13, color: "var(--text-secondary)", maxWidth: 500, margin: "8px auto 16px" }}>
                        Knowledge Index Creation (Stage 5) is currently processing or pending. The AI Assistant will unlock automatically once indexing completes.
                      </p>
                      <button style={styles.backBtn} onClick={() => handleTabChange("overview")}>Return to Overview</button>
                    </div>
                  ) : (
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
                  )
                ) : activeTab === "analysis" || activeTab === "context" ? (
                  /* Context Analysis Report Dashboard */
                  !(doc?.context_analysis_ready || doc?.context_analysis_status === "completed" || doc?.status === "completed") ? (
                    <div style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 12, padding: 40, textAlign: "center" }}>
                      <div style={{ fontSize: 36, marginBottom: 12 }}>🔒</div>
                      <h3 style={{ margin: 0, fontSize: 18, fontWeight: 700, color: "var(--text-primary)" }}>Ambiguity Analysis is Locked</h3>
                      <p style={{ fontSize: 13, color: "var(--text-secondary)", maxWidth: 500, margin: "8px auto 16px" }}>
                        Consistency & Contradiction Review (Stage 6) is currently processing or pending. Ambiguity Analysis will unlock automatically once stage 6 completes.
                      </p>
                      <button style={styles.backBtn} onClick={() => handleTabChange("overview")}>Return to Overview</button>
                    </div>
                  ) : (
                    <div style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 12, padding: 20, minHeight: 500 }}>
                      <ContextAnalysis id={id} onShowInDocument={handleShowInDocument} />
                    </div>
                  )
                ) : activeTab === "comparative" || activeTab === "comparative-analysis" ? (
                  /* Executive Comparative Analysis Workspace */
                  !(doc?.comparative_analysis_ready || doc?.comparative_analysis_status === "completed" || doc?.status === "completed") ? (
                    <div style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 12, padding: 40, textAlign: "center" }}>
                      <div style={{ fontSize: 36, marginBottom: 12 }}>🔒</div>
                      <h3 style={{ margin: 0, fontSize: 18, fontWeight: 700, color: "var(--text-primary)" }}>Comparative Analysis is Locked</h3>
                      <p style={{ fontSize: 13, color: "var(--text-secondary)", maxWidth: 500, margin: "8px auto 16px" }}>
                        Competitive Benchmark Analysis (Stage 7) is currently processing or pending. Comparative Analysis will unlock automatically once stage 7 completes.
                      </p>
                      <button style={styles.backBtn} onClick={() => handleTabChange("overview")}>Return to Overview</button>
                    </div>
                  ) : (
                    <div style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 12, padding: 20, minHeight: 500 }}>
                      <ComparativeAnalysisView
                        id={id}
                        data={comparativeData}
                        isRunning={
                          !(comparativeData?.company_profile || comparativeData?.data?.company_profile || comparativeData?.comparative_analysis) &&
                          (comparativeLoading || doc?.comparative_analysis_status === "running")
                        }
                        currentStage={doc?.current_stage || "Competitive Benchmark Analysis"}
                        onRerun={() => {
                          setComparativeLoading(true);
                          fetchComparativeAnalysis(id).then(res => {
                            setComparativeData(res);
                            setComparativeLoading(false);
                          }).catch(() => setComparativeLoading(false));
                        }}
                      />
                    </div>
                  )
                ) : (
                  /* Executive Reports Page */
                  !(doc?.reports_ready || doc?.status === "completed") ? (
                    <div style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 12, padding: 40, textAlign: "center" }}>
                      <div style={{ fontSize: 36, marginBottom: 12 }}>🔒</div>
                      <h3 style={{ margin: 0, fontSize: 18, fontWeight: 700, color: "var(--text-primary)" }}>Executive Reports are Locked</h3>
                      <p style={{ fontSize: 13, color: "var(--text-secondary)", maxWidth: 500, margin: "8px auto 16px" }}>
                        Executive Insights Report Generation (Stage 8) is currently processing or pending. Executive Reports will unlock automatically once stage 8 completes.
                      </p>
                      <button style={styles.backBtn} onClick={() => handleTabChange("overview")}>Return to Overview</button>
                    </div>
                  ) : (
                    <div style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 12, padding: 20, minHeight: 500 }}>
                      <Reports activeDocId={id} />
                    </div>
                  )
                )}
              </div>

              {/* Right Panel: Fixed Enterprise Document Details Sidebar (27% width, sticky, non-proofreading tabs) */}
              {!isProofreadTab && (
                <WorkspaceSidebar
                  doc={doc}
                  stages={getTimelineStages(doc)}
                  overallProgress={doc.overall_progress !== undefined ? doc.overall_progress : Math.round(doc.progress_percentage || 0)}
                  onRefresh={() => {
                    fetchDocument(id).then(data => { if (data) setDoc(data); });
                  }}
                  onViewRawText={() => setRawTextOpen(true)}
                  onOpenAssistant={() => handleTabChange("assistant")}
                  onDownloadOriginal={handleDownloadOriginal}
                  onRetryStage={handleRetryStage}
                />
              )}
            </div>
          );
        })()}

      {/* Extracted Raw Text View Modal */}
      {rawTextOpen && (
        <div style={styles.modalOverlay} onClick={() => setRawTextOpen(false)}>
          <div style={{ ...styles.modalCard, maxWidth: 850, width: "100%" }} onClick={(e) => e.stopPropagation()}>
            <div style={styles.modalHeader}>
              <div>
                <h3 style={styles.modalTitle}>📄 Extracted Document Text</h3>
                <p style={styles.modalSubtitle}>
                  Raw text output extracted during Stage 2 (Document Content Extraction)
                </p>
              </div>
              <button style={styles.modalCloseBtn} onClick={() => setRawTextOpen(false)}>
                &times;
              </button>
            </div>
            
            <div style={{ padding: "16px 20px", maxHeight: "60vh", overflowY: "auto", background: "var(--bg-app, #F8FAFC)", borderRadius: 8, border: "1px solid var(--border, #E2E8F0)", margin: "16px 0" }}>
              <pre style={{ margin: 0, whiteSpace: "pre-wrap", fontFamily: "monospace", fontSize: 12.5, lineHeight: 1.6, color: "var(--text-primary, #1E293B)" }}>
                {doc?.raw_text || "No extracted text available for this document."}
              </pre>
            </div>
            
            <div style={{ ...styles.modalFooter, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <button
                className="btn-premium-solid"
                onClick={() => {
                  navigator.clipboard.writeText(doc?.raw_text || "");
                }}
              >
                📋 Copy Extracted Text
              </button>
              <button style={styles.modalCancelBtn} onClick={() => setRawTextOpen(false)}>
                Close
              </button>
            </div>
          </div>
        </div>
      )}

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
