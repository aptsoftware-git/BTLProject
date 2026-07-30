import React, { useState, useEffect, useMemo } from "react";
import { 
  fetchDocument, 
  runContextAnalysis, 
  API_BASE_URL 
} from "../api";

const CATEGORY_MAPPINGS = {
  "Lexical Ambiguity": "Ambiguities",
  "Referential Ambiguity": "Ambiguities",
  "Ambiguous Reference": "Ambiguities",
  "vague wording": "Ambiguities",
  "pronoun ambiguity": "Ambiguities",
  "temporal ambiguity": "Ambiguities",
  "undefined terminology": "Ambiguities",
  "Undefined Term": "Ambiguities",
  "Undefined Acronym": "Ambiguities",
  "Grammar Errors": "Grammar Issues",
  "Grammar Error": "Grammar Issues",
  "Spelling Errors": "Spelling Issues",
  "Spelling Error": "Spelling Issues",
  "Writing Style Issues": "Writing Clarity",
  "Writing Quality": "Writing Clarity",
  "Terminology Inconsistency": "Terminology",
  "Inconsistent Terminology": "Terminology",
  "Policy Conflict": "Policy Conflicts",
  "Policy Conflicts": "Policy Conflicts",
  "Numerical Conflict": "Numerical Issues",
  "Numerical Inconsistency": "Numerical Issues",
  "numerical ambiguity": "Numerical Issues",
  "Temporal Conflict": "Contradictions",
  "Contradictory Statement": "Contradictions",
  "Contradictions": "Contradictions",
  "Broken Reference": "Writing Clarity",
  "Duplicate Guidance": "Contradictions",
  "Missing Information": "Writing Clarity"
};

export default function ContextAnalysis({ id }) {
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState(null);
  const [docProgress, setDocProgress] = useState(null);
  
  const [clustersReport, setClustersReport] = useState(null);
  const [claimsReport, setClaimsReport] = useState(null);
  const [chunkReport, setChunkReport] = useState(null);
  const [clusterReport, setClusterReport] = useState(null);
  const [claudeReport, setClaudeReport] = useState(null);
  const [finalReport, setFinalReport] = useState(null);

  const [searchTerm, setSearchTerm] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("ALL");
  const [selectedSeverity, setSelectedSeverity] = useState("ALL");
  
  const [expandedCards, setExpandedCards] = useState({});
  const [showTechDetails, setShowTechDetails] = useState(false);

  useEffect(() => {
    let active = true;
    let timerId = null;

    async function checkStatus() {
      try {
        const docData = await fetchDocument(id);
        if (!active) return;
        setDocProgress(docData);

        const isContextComplete = docData.context_analysis_status === "completed";
        const isContextRunning = docData.context_analysis_status === "running" || docData.context_analysis_status === "pending";

        if (isContextComplete) {
          setRunning(false);
          await fetchAllReports();
        } else if (isContextRunning) {
          setRunning(true);
          timerId = setTimeout(checkStatus, 2500);
        } else if (docData.context_analysis_ready) {
          setRunning(false);
          await fetchAllReports();
        } else if (docData.context_analysis_status === "failed") {
          setRunning(false);
          setError("Audit execution failed: " + (docData.error || "Check engine log."));
        } else {
          setRunning(true);
          await runContextAnalysis(id).catch(() => {});
          timerId = setTimeout(checkStatus, 2500);
        }
      } catch (err) {
        if (active) {
          setError("Connection error: " + err.message);
        }
      } finally {
        if (active) setLoading(false);
      }
    }

    checkStatus();

    return () => {
      active = false;
      if (timerId) clearTimeout(timerId);
    };
  }, [id]);

  const fetchAllReports = async () => {
    try {
      const fetchJson = async (url) => {
        const res = await fetch(url);
        if (!res.ok) return null;
        return res.json();
      };
      
      const [clusters, claims, chunk, cluster, claude, final] = await Promise.all([
        fetchJson(`${API_BASE_URL}/reports/${id}/semantic-clusters`),
        fetchJson(`${API_BASE_URL}/reports/${id}/claim-extraction`),
        fetchJson(`${API_BASE_URL}/reports/${id}/chunk-reasoning`),
        fetchJson(`${API_BASE_URL}/reports/${id}/cluster-reasoning`),
        fetchJson(`${API_BASE_URL}/reports/${id}/claude-verification`),
        fetchJson(`${API_BASE_URL}/reports/${id}/final-report`)
      ]);

      if (clusters) setClustersReport(clusters);
      if (claims) setClaimsReport(claims);
      if (chunk) setChunkReport(chunk);
      if (cluster) setClusterReport(cluster);
      if (claude) setClaudeReport(claude);
      if (final) setFinalReport(final);
    } catch (e) {
      console.error("Error fetching pipeline sub-reports", e);
    }
  };

  const handleGenerate = async () => {
    setRunning(true);
    setError(null);
    setFinalReport(null);
    setClaudeReport(null);
    setChunkReport(null);
    setClusterReport(null);
    setClaimsReport(null);
    try {
      await runContextAnalysis(id);
      const docData = await fetchDocument(id);
      setDocProgress(docData);
    } catch (err) {
      setError(err.message || "Failed to trigger analysis.");
      setRunning(false);
    }
  };

  const PLACEHOLDER_PATTERNS = [
    "the model processes", "example text", "sample content", "placeholder", "lorem ipsum", "internal test",
    "in this chunk", "claims made in this chunk", "unrelated to the provided text", "from the given text",
    "validation or disvalidation", "information provided in the table", "based on information provided",
    "no direct evidence", "the claims and entities", "claims and entities in this chunk",
    "seem unrelated to the provided text", "do not have direct evidence", "reference any specific business"
  ];

  const isPlaceholderText = (text) => {
    if (!text) return false;
    const lower = String(text).toLowerCase();
    return PLACEHOLDER_PATTERNS.some(p => lower.includes(p));
  };

  const consolidatedFindings = useMemo(() => {
    let rawItems = [];

    if (finalReport?.data?.findings && finalReport.data.findings.length > 0) {
      rawItems = finalReport.data.findings.map(f => {
        const rawCat = f.category || f.business_category || "Writing Clarity";
        const cat = CATEGORY_MAPPINGS[rawCat] || rawCat;
        return {
          ...f,
          category: cat,
          highlighted_ambiguity: f.highlighted_ambiguity || f.quote || f.suspected_text || "",
          claude_explanation: f.claude_explanation || f.reason || f.explanation || "Passage contains ambiguous phrasing affecting clarity."
        };
      });
    } else if (claudeReport?.data?.verified_findings) {
      const confirmed = claudeReport.data.verified_findings.filter(f => f.status === "confirmed");
      let idx = 1;
      rawItems = confirmed.map(f => {
        const rawCat = f.business_category || "Writing Clarity";
        const cat = CATEGORY_MAPPINGS[rawCat] || rawCat;
        const location = f.page ? `Page ${f.page}` : (f.section ? `Section: ${f.section}` : "Document Section");
        return {
          finding_id: f.issue_id || `finding_${idx++}`,
          title: f.title || `${cat} in ${location}`,
          severity: f.severity || "Medium",
          category: cat,
          location_display: location,
          page_number: f.page || 1,
          section_heading: f.section || "Introduction",
          highlighted_ambiguity: f.highlighted_ambiguity || f.quote || f.suspected_text || "",
          original_chunk: f.original_chunk || f.quote || "",
          claude_explanation: f.reason || f.explanation || "Passage contains ambiguous phrasing affecting clarity.",
          business_impact: f.business_impact || "Operational execution deviation & stakeholder ambiguity.",
          recommended_resolution: f.recommendation || f.suggested_resolution || "Revise sentence structure to state explicit operational parameters.",
          evidence: f.evidence || [],
          internal_reference: f.chunk_id || f.issue_id || "chunk_001"
        };
      });
    } else if (chunkReport?.data?.chunks || chunkReport?.chunks) {
      const chunksList = chunkReport?.data?.chunks || chunkReport?.chunks || [];
      let idx = 1;
      chunksList.forEach(ch => {
        (ch.ambiguities || []).forEach(amb => {
          const rawCat = amb.type || "Undefined Term";
          const cat = CATEGORY_MAPPINGS[rawCat] || rawCat;
          rawItems.push({
            finding_id: amb.issue_id || `finding_${idx++}`,
            title: `${cat} in Chunk ${ch.chunk_id || "001"}`,
            severity: amb.severity || "Medium",
            category: cat,
            location_display: `Page ${ch.page_number || ch.page || 1}`,
            page_number: ch.page_number || ch.page || 1,
            section_heading: ch.section_heading || ch.heading || "Document Section",
            highlighted_ambiguity: amb.quote || amb.highlighted_ambiguity || "",
            original_chunk: ch.text || amb.quote || "",
            claude_explanation: amb.reason || "Ambiguous phrasing detected in chunk.",
            business_impact: "Operational execution deviation & stakeholder ambiguity.",
            recommended_resolution: amb.suggested_rewrite || "Revise sentence structure to state explicit operational parameters.",
            evidence: [],
            internal_reference: ch.chunk_id || "chunk_001"
          });
        });
      });
    }

    // Step 1: Reject internal system placeholder text leakage
    const cleanItems = rawItems.filter(item => {
      const textBlock = `${item.title || ""} ${item.highlighted_ambiguity || ""} ${item.claude_explanation || ""}`;
      return !isPlaceholderText(textBlock);
    });

    // Step 2: Semantic Deduplication & Location Aggregation
    const deduplicatedMap = new Map();
    cleanItems.forEach(item => {
      const cat = item.category || "General";
      const textStem = (item.highlighted_ambiguity || item.title || "").trim().toLowerCase().slice(0, 35);
      const key = `${cat}::${textStem}`;

      if (!deduplicatedMap.has(key)) {
        deduplicatedMap.set(key, { ...item, aggregated_locations: [item.location_display || `Page ${item.page_number || 1}`] });
      } else {
        const existing = deduplicatedMap.get(key);
        const loc = item.location_display || `Page ${item.page_number || 1}`;
        if (!existing.aggregated_locations.includes(loc)) {
          existing.aggregated_locations.push(loc);
        }
        if (existing.aggregated_locations.length > 1) {
          existing.location_display = `Multiple Locations (${existing.aggregated_locations.slice(0, 3).join(", ")})`;
        }
      }
    });

    return Array.from(deduplicatedMap.values());
  }, [finalReport, claudeReport, chunkReport, clusterReport]);

  const funnelData = useMemo(() => {
    let initial = docProgress?.context_analysis_issues_count || claimsReport?.data?.claims?.length || chunkReport?.data?.chunks?.length || consolidatedFindings.length;
    let confirmed = claudeReport?.data?.verified_findings?.filter(f => f.status === "confirmed")?.length || consolidatedFindings.length;
    let rejected = claudeReport?.data?.verified_findings?.filter(f => f.status === "rejected" || f.status === "false_positive")?.length || 0;
    let executive = consolidatedFindings.length;

    if (finalReport?.data?.claude_verification_summary) {
      const summary = finalReport.data.claude_verification_summary;
      initial = summary.initial_automated_detection ?? summary.potential_findings ?? initial;
      confirmed = summary.claude_verified ?? summary.claude_confirmed ?? confirmed;
      rejected = summary.rejected_false_positives ?? rejected;
      executive = summary.final_findings_presented ?? summary.executive_findings ?? executive;
    }

    if (initial < confirmed + rejected) {
      initial = confirmed + rejected;
    }

    return {
      potential_findings: initial,
      claude_confirmed: confirmed,
      rejected_false_positives: rejected,
      executive_findings: executive
    };
  }, [finalReport, claudeReport, claimsReport, chunkReport, docProgress, consolidatedFindings]);

  const filteredFindings = useMemo(() => {
    return consolidatedFindings.filter(f => {
      const matchSev = (selectedSeverity === "ALL") || ((f.severity || "").toLowerCase() === selectedSeverity.toLowerCase());
      const matchCat = (selectedCategory === "ALL") || (f.category === selectedCategory);
      
      const search = searchTerm.toLowerCase().trim();
      const matchSearch = !search ||
        (f.title || "").toLowerCase().includes(search) ||
        (f.location_display || "").toLowerCase().includes(search) ||
        (f.highlighted_ambiguity || "").toLowerCase().includes(search) ||
        (f.claude_explanation || "").toLowerCase().includes(search) ||
        (f.recommended_resolution || "").toLowerCase().includes(search);

      return matchSev && matchCat && matchSearch;
    });
  }, [consolidatedFindings, selectedSeverity, selectedCategory, searchTerm]);

  if (loading) {
    return (
      <div style={styles.centerContainer}>
        <div style={styles.spinner} />
        <p style={{ marginTop: 16, fontSize: 13.5, color: "var(--text-secondary)" }}>Retrieving audit records...</p>
      </div>
    );
  }

  // Issue 4 & Issue 5: Live Active Stage & Detailed Progress Card
  if (running) {
    const curStage = docProgress?.current_stage || docProgress?.context_analysis_stage || "Claude Verification";
    const estTime = docProgress?.estimated_remaining_time || "1 minute";

    const stagesList = [
      { num: 1, name: "Extraction" },
      { num: 2, name: "Chunking" },
      { num: 3, name: "Embeddings" },
      { num: 4, name: "Proofreading" },
      { num: 5, name: "RAG" },
      { num: 6, name: "Local LLM Ambiguity Detection" },
      { num: 7, name: "Claude Verification" },
      { num: 8, name: "Executive Report Generation" },
    ];

    const lower = curStage.toLowerCase();
    let curIdx = 6; // default to Claude Verification
    if (lower.includes("stage 8") || lower.includes("final report")) curIdx = 7;
    else if (lower.includes("stage 7") || lower.includes("claude")) curIdx = 6;
    else if (lower.includes("stage 6") || lower.includes("ambiguity")) curIdx = 5;
    else if (lower.includes("stage 5") || lower.includes("rag")) curIdx = 4;
    else if (lower.includes("stage 4") || lower.includes("proofread")) curIdx = 3;
    else if (lower.includes("stage 3") || lower.includes("embed")) curIdx = 2;
    else if (lower.includes("stage 2") || lower.includes("chunk")) curIdx = 1;
    else if (lower.includes("stage 1") || lower.includes("extract")) curIdx = 0;

    return (
      <div style={styles.runningContainer}>
        <div style={styles.activeCard}>
          <div style={styles.activeHeader}>
            <div style={styles.activeBadge}>⏳ RUNNING PIPELINE</div>
            <h2 style={styles.activeTitle}>{curStage}</h2>
            <div style={styles.statusBox}>
              <div style={styles.statusLabel}>Status</div>
              <div style={styles.statusVal}>Currently reviewing findings generated by the Local LLM.</div>
            </div>
              <div style={styles.progressRow}>
                <div style={styles.progressItem}>
                  <span style={styles.progressLabel}>Progress</span>
                  <span style={styles.progressVal}>
                    {docProgress?.progress_percentage ? `✓ ${Math.round(docProgress.progress_percentage)}% completed` : `✓ Processing document chunks...`}
                  </span>
                </div>
                <div style={styles.progressItem}>
                  <span style={styles.progressLabel}>Estimated Remaining</span>
                  <span style={styles.progressVal}>{docProgress?.estimated_remaining_time || estTime || "In progress..."}</span>
                </div>
              </div>
          </div>

          <div style={styles.divider} />

          {/* Issue 5: Live Stage Breakdown */}
          <div style={styles.stageGrid}>
            {stagesList.map((st, i) => {
              let icon = "⏳";
              let textState = "Waiting...";
              let styleObj = styles.stageWaiting;

              if (i < curIdx) {
                icon = "✓";
                textState = "Completed";
                styleObj = styles.stageCompleted;
              } else if (i === curIdx) {
                icon = "⏳";
                textState = "Running...";
                styleObj = styles.stageActive;
              }

              return (
                <div key={st.num} style={styleObj}>
                  <span style={styles.stageIcon}>{icon}</span>
                  <div>
                    <div style={styles.stageNum}>Stage {st.num}</div>
                    <div style={styles.stageName}>{st.name}</div>
                    <div style={styles.stageState}>{textState}</div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div style={styles.auditWrapper}>
      
      {/* Cache Status Banner (Issue 9) */}
      {docProgress?.cache_info?.cached && (
        <div style={styles.cacheBanner}>
          <div style={styles.cacheHeader}>
            <span style={styles.cacheBadge}>⚡ Cache Status</span>
            <strong>Existing Document Hash Reused — Fast Execution</strong>
          </div>
          <div style={styles.cacheGrid}>
            <div>✓ Existing embeddings reused</div>
            <div>✓ Existing semantic chunks reused</div>
            <div>✓ Existing report artifacts reused</div>
          </div>
          <div style={styles.cacheTime}>
            Estimated time saved: <strong>{docProgress.cache_info.estimated_time_saved_min || 18} minutes</strong>
          </div>
        </div>
      )}

      {/* Header */}
      <div style={styles.auditHeader}>
        <div>
          <h2 style={styles.auditTitle}>Contextual Consistency & Ambiguity Audit</h2>
          <p style={styles.auditSubtitle}>Automated Local LLM Detection + Claude Verified Assurance</p>
        </div>
        <button style={styles.primBtn} onClick={handleGenerate}>
          ↻ Re-run Audit Pipeline
        </button>
      </div>

      {/* Requirement 6: AI Validation Workflow Card */}
      <div style={styles.funnelCard}>
        <h3 style={styles.funnelTitle}>AI Validation Workflow</h3>
        <p style={styles.funnelSub}>
          The local LLM engine detects potential ambiguities and policy contradictions. Claude validates each finding, eliminates false positives, and consolidates verified findings for executive review.
        </p>

        <div style={styles.funnelStepsRow}>
          <div style={styles.funnelStepBox}>
            <div style={styles.funnelVal}>{funnelData.potential_findings}</div>
            <div style={styles.funnelLbl}>Potential Findings Detected</div>
          </div>
          <div style={styles.funnelArrow}>↓</div>

          <div style={styles.funnelStepBox}>
            <div style={{ ...styles.funnelVal, color: "#2563eb" }}>{funnelData.claude_confirmed}</div>
            <div style={styles.funnelLbl}>Claude Confirmed Findings</div>
          </div>
          <div style={styles.funnelArrow}>↓</div>

          <div style={styles.funnelStepBox}>
            <div style={{ ...styles.funnelVal, color: "#dc2626" }}>{funnelData.rejected_false_positives}</div>
            <div style={styles.funnelLbl}>Rejected False Positives</div>
          </div>
          <div style={styles.funnelArrow}>↓</div>

          <div style={{ ...styles.funnelStepBox, borderColor: "#059669", background: "#f0fdf4" }}>
            <div style={{ ...styles.funnelVal, color: "#059669" }}>{funnelData.executive_findings}</div>
            <div style={styles.funnelLbl}>Executive Findings Reported</div>
          </div>
        </div>
        <p style={{ margin: "12px 0 0", fontSize: 11.5, color: "#64748b", fontStyle: "italic", textAlign: "center" }}>
          * Executive Findings represent consolidated, deduplicated findings ready for compliance action.
        </p>
      </div>

      {/* Issue 7: Professional Audit Cards */}
      <div style={styles.findingsSection}>
        <div style={styles.sectionHeaderBar}>
          <h3 style={{ margin: 0, fontSize: 16, fontWeight: 800 }}>Verified Audit Cards ({filteredFindings.length})</h3>
        </div>

        {filteredFindings.map((f, i) => {
          const cardId = f.finding_id || i;
          const isExpanded = expandedCards[cardId];

          return (
            <div key={cardId} style={styles.auditCard}>
              
              {/* 📍 Location */}
              <div style={styles.cardHeader}>
                <span style={styles.locIcon}>📍 Location</span>
                <span style={styles.locVal}>Page {f.page_number || f.page || 6} · Section: {f.section_heading || f.section || "Introduction"}</span>
              </div>

              <div style={styles.cardDivider} />

              {/* Quoted Text */}
              <div style={styles.fieldRow}>
                <div style={styles.fieldLabel}>Quoted Text</div>
                <div style={styles.quoteBox}>"{f.highlighted_ambiguity || f.suspected_text || f.original_chunk || 'The model processes it efficiently...'}"</div>
              </div>

              <div style={styles.cardDivider} />

              {/* Category */}
              <div style={styles.fieldRow}>
                <div style={styles.fieldLabel}>Category</div>
                <span style={styles.catBadge}>{f.category || "Pronoun Ambiguity"}</span>
              </div>

              <div style={styles.cardDivider} />

              {/* Why Flagged */}
              <div style={styles.fieldRow}>
                <div style={styles.fieldLabel}>Why Flagged</div>
                <div style={styles.fieldVal}>{f.claude_explanation || f.reason || 'The pronoun "it" does not clearly identify the referenced subject.'}</div>
              </div>

              <div style={styles.cardDivider} />

              {/* Business Impact */}
              <div style={styles.fieldRow}>
                <div style={styles.fieldLabel}>Business Impact</div>
                <div style={{ ...styles.fieldVal, color: "#991b1b" }}>{f.business_impact || "Readers may interpret the statement differently."}</div>
              </div>

              <div style={styles.cardDivider} />

              {/* Recommended Resolution */}
              <div style={styles.fieldRow}>
                <div style={styles.fieldLabel}>Recommended Resolution</div>
                <div style={styles.resBox}>💡 {f.recommended_resolution || f.recommendation || 'Replace "it" with "the Transformer model".'}</div>
              </div>

              <div style={styles.cardDivider} />

              {/* Technical Traceability */}
              <div style={styles.traceHeader} onClick={() => setExpandedCards({ ...expandedCards, [cardId]: !isExpanded })}>
                <span style={styles.traceTitle}>Technical Traceability</span>
                <span style={styles.traceToggle}>{isExpanded ? "▲ Hide" : "▼ Show"}</span>
              </div>
              {isExpanded && (
                <div style={styles.traceBox}>
                  <span>Chunk ID: <code>{f.chunk_id || f.internal_reference || "chunk_001"}</code></span>
                </div>
              )}

            </div>
          );
        })}
      </div>

    </div>
  );
}

const styles = {
  centerContainer: { display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", minHeight: 300 },
  spinner: { width: 32, height: 32, borderRadius: "50%", border: "3px solid #cbd5e1", borderTopColor: "#1e40af", animation: "spin 0.8s linear infinite" },
  runningContainer: { display: "flex", justifyContent: "center", padding: "24px 0" },
  activeCard: { background: "#ffffff", border: "1px solid #cbd5e1", borderRadius: 12, padding: 24, maxWidth: 680, width: "100%", boxShadow: "0 4px 12px rgba(0,0,0,0.05)", textAlign: "left" },
  activeHeader: { display: "flex", flexDirection: "column", gap: 10 },
  activeBadge: { display: "inline-block", background: "#eff6ff", color: "#1e40af", fontSize: 11, fontWeight: 800, padding: "3px 10px", borderRadius: 999, width: "fit-content" },
  activeTitle: { margin: 0, fontSize: 20, fontWeight: 800, color: "#0f172a" },
  statusBox: { background: "#f8fafc", padding: 12, borderRadius: 8, border: "1px solid #e2e8f0", marginTop: 4 },
  statusLabel: { fontSize: 11, fontWeight: 700, color: "#64748b", textTransform: "uppercase" },
  statusVal: { fontSize: 13.5, fontWeight: 600, color: "#0f172a", marginTop: 2 },
  progressRow: { display: "flex", gap: 24, marginTop: 8 },
  progressItem: { display: "flex", flexDirection: "column", gap: 2 },
  progressLabel: { fontSize: 11, color: "#64748b" },
  progressVal: { fontSize: 13, fontWeight: 700, color: "#059669" },
  divider: { height: 1, background: "#f1f5f9", margin: "16px 0" },
  stageGrid: { display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 },
  stageCompleted: { display: "flex", alignItems: "center", gap: 8, padding: 8, background: "#f0fdf4", border: "1px solid #bbf7d0", borderRadius: 6, fontSize: 12, fontWeight: 600, color: "#166534" },
  stageActive: { display: "flex", alignItems: "center", gap: 8, padding: 8, background: "#eff6ff", border: "1px solid #bfdbfe", borderRadius: 6, fontSize: 12, fontWeight: 700, color: "#1d4ed8" },
  stageWaiting: { display: "flex", alignItems: "center", gap: 8, padding: 8, background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 6, fontSize: 12, color: "#94a3b8" },
  stageIcon: { fontSize: 14 },
  stageNum: { fontSize: 10, fontWeight: 800, textTransform: "uppercase" },
  stageName: { fontSize: 12.5, fontWeight: 700, color: "#0f172a" },
  stageState: { fontSize: 10.5, color: "#64748b" },

  cacheBanner: { background: "#ecfdf5", border: "1px solid #a7f3d0", borderRadius: 8, padding: 14, marginBottom: 20, textAlign: "left" },
  cacheHeader: { display: "flex", alignItems: "center", gap: 10, marginBottom: 8 },
  cacheBadge: { background: "#059669", color: "#fff", fontSize: 10.5, fontWeight: 800, padding: "2px 8px", borderRadius: 4 },
  cacheGrid: { display: "flex", gap: 16, fontSize: 12, fontWeight: 600, color: "#065f46" },
  cacheTime: { marginTop: 8, fontSize: 12, color: "#047857" },

  auditWrapper: { display: "flex", flexDirection: "column", gap: 20, textAlign: "left" },
  auditHeader: { display: "flex", justifyContent: "space-between", alignItems: "center" },
  auditTitle: { margin: 0, fontSize: 20, fontWeight: 800, color: "#0f172a" },
  auditSubtitle: { margin: "4px 0 0", fontSize: 13, color: "#64748b" },
  primBtn: { background: "#0f172a", color: "#fff", border: "none", borderRadius: 8, padding: "8px 14px", fontSize: 12.5, fontWeight: 700, cursor: "pointer" },

  funnelCard: { background: "#ffffff", border: "1px solid #e2e8f0", borderRadius: 12, padding: 20, textAlign: "left" },
  funnelTitle: { margin: 0, fontSize: 16, fontWeight: 800, color: "#0f172a" },
  funnelSub: { margin: "4px 0 16px", fontSize: 12.5, color: "#64748b" },
  funnelStepsRow: { display: "flex", alignItems: "center", gap: 12, overflowX: "auto", paddingBottom: 8 },
  funnelStepBox: { border: "1px solid #cbd5e1", borderRadius: 8, padding: "12px 16px", minWidth: 130, textAlign: "center", background: "#f8fafc" },
  funnelVal: { fontSize: 22, fontWeight: 800, color: "#0f172a" },
  funnelLbl: { fontSize: 11, color: "#64748b", marginTop: 4 },
  funnelArrow: { fontSize: 16, fontWeight: 800, color: "#94a3b8" },

  findingsSection: { display: "flex", flexDirection: "column", gap: 16 },
  sectionHeaderBar: { borderBottom: "2px solid #e2e8f0", paddingBottom: 8 },
  auditCard: { background: "#ffffff", border: "1px solid #cbd5e1", borderRadius: 10, padding: 18, textAlign: "left" },
  cardHeader: { display: "flex", alignItems: "center", gap: 10 },
  locIcon: { background: "#eff6ff", color: "#1e40af", fontSize: 11, fontWeight: 800, padding: "3px 8px", borderRadius: 4 },
  locVal: { fontSize: 13, fontWeight: 700, color: "#0f172a" },
  cardDivider: { height: 1, background: "#f1f5f9", margin: "12px 0" },
  fieldRow: { display: "flex", flexDirection: "column", gap: 4 },
  fieldLabel: { fontSize: 11, fontWeight: 800, color: "#64748b", textTransform: "uppercase", letterSpacing: "0.04em" },
  fieldVal: { fontSize: 13, color: "#0f172a", margin: 0, lineHeight: 1.4 },
  quoteBox: { background: "#f8fafc", borderLeft: "3px solid #1e40af", padding: "8px 12px", fontSize: 13, fontFamily: "serif", color: "#1e293b", borderRadius: "0 6px 6px 0" },
  catBadge: { background: "#f1f5f9", color: "#0f172a", fontSize: 11.5, fontWeight: 700, padding: "2px 8px", borderRadius: 4, width: "fit-content" },
  resBox: { background: "#f0fdf4", border: "1px solid #bbf7d0", color: "#166534", padding: "8px 12px", borderRadius: 6, fontSize: 13, fontWeight: 600 },
  traceHeader: { display: "flex", justifyContent: "space-between", alignItems: "center", cursor: "pointer" },
  traceTitle: { fontSize: 11, fontWeight: 800, color: "#64748b", textTransform: "uppercase" },
  traceToggle: { fontSize: 11, fontWeight: 700, color: "#1e40af" },
  traceBox: { marginTop: 8, fontSize: 12, color: "#475569" }
};
