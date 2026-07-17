import React, { useState, useEffect, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchDocuments,
  fetchRagModels,
  sendRagMessage,
  fetchRagHistory,
  clearRagHistory,
  triggerRagIndex,
  fetchRagStats
} from "../api";

const SUGGESTED_QUESTIONS = [
  "Summarize this document.",
  "What are the key findings?",
  "Who are the people mentioned?",
  "List all recommendations.",
  "Explain Table 2.",
  "What does Figure 3 show?",
  "What dates are mentioned?"
];

// Reusable Markdown parser for grounding answers
const parseMarkdown = (text) => {
  if (!text) return "";
  
  let html = text;
  
  // 1. Escape HTML entities to prevent XSS
  html = html
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
    
  // 2. Code blocks: ```language ... ```
  html = html.replace(/```([\s\S]*?)```/g, (match, code) => {
    return `<pre style="background:#0e1117; color:#c9d1d9; border:1px solid var(--border); padding:12px; border-radius:8px; overflow-x:auto; font-family:monospace; margin:10px 0; text-align:left; line-height:1.4;"><code>${code.trim()}</code></pre>`;
  });
  
  // 3. Inline code: `code`
  html = html.replace(/`([^`]+)`/g, '<code style="background:var(--border); padding:2px 5px; border-radius:4px; font-family:monospace; font-size:12px;">$1</code>');
  
  // 4. Markdown Tables
  const lines = html.split('\n');
  let inTable = false;
  let tableRows = [];
  let parsedLines = [];
  
  lines.forEach((line) => {
    if (line.trim().startsWith('|') && line.trim().endsWith('|')) {
      if (!inTable) {
        inTable = true;
        tableRows = [];
      }
      tableRows.push(line);
    } else {
      if (inTable) {
        parsedLines.push(parseMarkdownTable(tableRows));
        inTable = false;
      }
      parsedLines.push(line);
    }
  });
  if (inTable) {
    parsedLines.push(parseMarkdownTable(tableRows));
  }
  html = parsedLines.join('\n');
  
  // 5. Bold: **text**
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  
  // 6. Bullet lists
  html = html.replace(/^\s*[-*]\s+(.+)$/gm, '<li style="margin-left:18px; margin-bottom:4px; list-style-type:disc; text-align:left;">$1</li>');
  
  // Wrap consecutive list items in <ul>
  html = html.replace(/(<li[\s\S]*?<\/li>)/g, '<ul style="margin:6px 0; padding-left:0;">$1</ul>');
  html = html.replace(/<\/ul>\s*<ul style="margin:6px 0; padding-left:0;">/g, '');
  
  // 7. Headings
  html = html.replace(/^###\s+(.+)$/gm, '<h3 style="font-size:14px; font-weight:600; margin:14px 0 6px; text-align:left; color:var(--text-primary);">$1</h3>');
  html = html.replace(/^##\s+(.+)$/gm, '<h2 style="font-size:15px; font-weight:700; margin:18px 0 8px; text-align:left; color:var(--text-primary);">$1</h2>');
  html = html.replace(/^#\s+(.+)$/gm, '<h1 style="font-size:17px; font-weight:800; margin:22px 0 10px; text-align:left; color:var(--text-primary);">$1</h1>');
  
  // 8. Convert newlines to paragraph line-breaks
  html = html.replace(/\n\n/g, '<br/><br/>');
  
  return html;
};

const parseMarkdownTable = (rows) => {
  if (rows.length === 0) return "";
  
  let tableHtml = '<div style="overflow-x:auto; margin:12px 0;"><table style="border-collapse:collapse; width:100%; border:1px solid var(--border); font-size:12px; text-align:left;">';
  
  rows.forEach((row, idx) => {
    const cols = row.split('|').map(c => c.trim()).filter((c, i, arr) => i > 0 && i < arr.length - 1);
    if (row.includes('---')) return;
    
    const isHeader = idx === 0;
    tableHtml += `<tr style="${isHeader ? 'background:var(--brand-light); font-weight:600;' : 'border-bottom:1px solid var(--border);'}">`;
    cols.forEach((col) => {
      tableHtml += `<t${isHeader ? 'h' : 'd'} style="padding:8px 10px; border:1px solid var(--border);">${col}</t${isHeader ? 'h' : 'd'}>`;
    });
    tableHtml += '</tr>';
  });
  
  tableHtml += '</table></div>';
  return tableHtml;
};

export default function Assistant() {
  const { id } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const chatEndRef = useRef(null);
  
  const [selectedDocId, setSelectedDocId] = useState(id || "");
  const [messages, setMessages] = useState([]);
  const [inputValue, setInputValue] = useState("");
  const [isTyping, setIsTyping] = useState(false);
  const [error, setError] = useState("");
  const [indexingStatus, setIndexingStatus] = useState(""); // idle | indexing | success | error
  
  // RAG Optimization States
  const [debugEnabled, setDebugEnabled] = useState(false);
  const [docStats, setDocStats] = useState({ chunks: 0, tables: 0, images: 0, pages: 0 });
  const [statsLoading, setStatsLoading] = useState(false);

  // Fetch document list
  const { data: documents = [], isLoading: docsLoading } = useQuery({
    queryKey: ["documents"],
    queryFn: fetchDocuments,
  });

  // Fetch RAG models list
  const { data: models = [], isLoading: modelsLoading } = useQuery({
    queryKey: ["ragModels"],
    queryFn: fetchRagModels,
  });

  const [selectedModel, setSelectedModel] = useState("");

  // Sync selected doc id from route id
  useEffect(() => {
    if (id) {
      setSelectedDocId(id);
    }
  }, [id]);

  // Load model default
  useEffect(() => {
    if (models.length > 0 && !selectedModel) {
      const recommended = models.find(m => m.recommended);
      setSelectedModel(recommended ? recommended.id : models[0].id);
    }
  }, [models, selectedModel]);

  // Load chat history when selected document changes
  useEffect(() => {
    if (selectedDocId) {
      setError("");
      setMessages([]);
      fetchRagHistory(selectedDocId)
        .then((res) => {
          if (res && res.history) {
            const formatted = res.history.map((msg) => ({
              role: msg.role,
              content: msg.content,
              timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
            }));
            setMessages(formatted);
          }
        })
        .catch((err) => {
          console.error("Error loading chat history:", err);
          setError("Failed to load chat history. The document may not be indexed yet.");
        });

      // Fetch RAG document statistics
      setStatsLoading(true);
      fetchRagStats(selectedDocId)
        .then((res) => {
          setDocStats(res);
        })
        .catch((err) => console.error("Error fetching stats:", err))
        .finally(() => setStatsLoading(false));
    } else {
      setDocStats({ chunks: 0, tables: 0, images: 0, pages: 0 });
    }
  }, [selectedDocId]);

  // Scroll to bottom
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isTyping]);

  const activeDoc = documents.find(d => d.id === selectedDocId);

  const handleDocChange = (e) => {
    const nextId = e.target.value;
    setSelectedDocId(nextId);
    if (nextId) {
      navigate(`/assistant/${nextId}`);
    } else {
      navigate("/assistant");
    }
  };

  const handleSendMessage = async (textToSend) => {
    const text = textToSend || inputValue;
    if (!text.trim() || !selectedDocId) return;

    if (!textToSend) {
      setInputValue("");
    }
    setError("");

    // Add user message
    const userMsg = {
      role: "user",
      content: text,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    };
    setMessages(prev => [...prev, userMsg]);
    setIsTyping(true);

    try {
      const res = await sendRagMessage(selectedDocId, text, selectedModel);
      
      const assistantMsg = {
        role: "assistant",
        content: res.answer,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        pageReferences: res.page_references,
        usedChunks: res.used_chunk_ids,
        statistics: res.retrieval_statistics,
        generationTime: res.generation_time,
        model: res.selected_model,
        debugInfo: res.metadata?.debug_info // Populated in Phase 6 Optimization
      };

      setMessages(prev => [...prev, assistantMsg]);
    } catch (err) {
      console.error("Error generating answer:", err);
      let errMsg = "An error occurred while calling the LLM backend.";
      if (err.message.includes("500") || err.message.includes("fetch")) {
        errMsg = "LLM Server (Ollama) is currently unreachable. Please check settings or connection status.";
      }
      setError(errMsg);
    } finally {
      setIsTyping(false);
    }
  };

  const handleClearHistory = async () => {
    if (!selectedDocId) return;
    try {
      await clearRagHistory(selectedDocId);
      setMessages([]);
      setError("");
    } catch (err) {
      console.error("Failed to clear history:", err);
      setError("Failed to clear conversation memory.");
    }
  };

  const handleReindex = async () => {
    if (!selectedDocId) return;
    setIndexingStatus("indexing");
    try {
      await triggerRagIndex(selectedDocId);
      setIndexingStatus("success");
      
      // Refresh stats
      const nextStats = await fetchRagStats(selectedDocId);
      setDocStats(nextStats);
      
      setTimeout(() => setIndexingStatus("idle"), 3000);
    } catch (err) {
      console.error("Failed to trigger index:", err);
      setIndexingStatus("error");
      setError("Failed to trigger manual document indexing.");
    }
  };

  const handleCopyText = (content) => {
    navigator.clipboard.writeText(content);
  };

  const handlePageClick = (page) => {
    // Navigate user to interactive workspace for specific document context
    window.open(`/documents/${selectedDocId}`, "_blank");
  };

  const handleExportConversation = () => {
    if (messages.length === 0) return;
    const chatText = messages.map(m => {
      const roleLabel = m.role === "user" ? "USER" : "ASSISTANT";
      const statsStr = m.generationTime ? ` (Model: ${m.model || selectedModel} | Latency: ${m.generationTime.toFixed(2)}s)` : "";
      return `[${m.timestamp}] ${roleLabel}${statsStr}:\n${m.content}\n-----------------------------------------\n`;
    }).join("\n");
    
    const blob = new Blob([chatText], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `chat_history_${selectedDocId}_${new Date().toISOString().slice(0, 10)}.txt`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const handleOpenInspectionReport = () => {
    if (!selectedDocId) return;
    let origin = "http://localhost:8000";
    if (window.location.hostname) {
      origin = `${window.location.protocol}//${window.location.hostname}:8000`;
    }
    const url = `${origin}/outputs/${selectedDocId}/inspection_report.html`;
    window.open(url, "_blank");
  };

  return (
    <div style={styles.container}>
      {/* Page Header */}
      <div style={styles.header}>
        <div>
          <h1 style={styles.title}>AI Document Assistant</h1>
          <p style={styles.subtitle}>Interact with your documents using layout-aware grounded retrieval-augmented generation (RAG)</p>
        </div>
        {selectedDocId && messages.length > 0 && (
          <button onClick={handleExportConversation} style={styles.exportTopBtn}>
            Export Chat
          </button>
        )}
      </div>

      <div style={styles.workspace}>
        {/* LEFT PANEL: Document metadata & configurations */}
        <div style={styles.leftPanel}>
          {/* Document selection */}
          <div style={styles.card}>
            <h2 style={styles.cardTitle}>Document Context</h2>
            <label style={styles.label}>Select Document</label>
            <select
              value={selectedDocId}
              onChange={handleDocChange}
              style={styles.select}
              disabled={docsLoading}
            >
              <option value="">-- Choose an uploaded document --</option>
              {documents
                .filter(d => d.status === "completed")
                .map(d => (
                  <option key={d.id} value={d.id}>{d.filename}</option>
                ))}
            </select>

            {activeDoc ? (
              <div style={styles.docMeta}>
                <div style={styles.metaRow}>
                  <span style={styles.metaLabel}>Format:</span>
                  <span style={styles.metaVal}>{activeDoc.fileType}</span>
                </div>
                <div style={styles.metaRow}>
                  <span style={styles.metaLabel}>Size:</span>
                  <span style={styles.metaVal}>{activeDoc.size}</span>
                </div>
                
                {/* RAG Stat Grid */}
                <div style={styles.statGrid}>
                  <div style={styles.statBox}>
                    <span style={styles.statNum}>{docStats.pages || 1}</span>
                    <span style={styles.statLabel}>Pages</span>
                  </div>
                  <div style={styles.statBox}>
                    <span style={styles.statNum}>{docStats.chunks || 0}</span>
                    <span style={styles.statLabel}>Chunks</span>
                  </div>
                  <div style={styles.statBox}>
                    <span style={styles.statNum}>{docStats.tables || 0}</span>
                    <span style={styles.statLabel}>Tables</span>
                  </div>
                  <div style={styles.statBox}>
                    <span style={styles.statNum}>{docStats.images || 0}</span>
                    <span style={styles.statLabel}>Images</span>
                  </div>
                </div>

                {/* Extra stats */}
                <div style={styles.extraStats}>
                  <div style={styles.extraRow}>
                    <span>OCR Chunks:</span>
                    <strong>{docStats.ocr || 0}</strong>
                  </div>
                  <div style={styles.extraRow}>
                    <span>Total Embeddings:</span>
                    <strong>{docStats.embeddings || 0}</strong>
                  </div>
                  <div style={styles.extraRow}>
                    <span>Vision Processed:</span>
                    <strong>{docStats.vision_processed || 0}</strong>
                  </div>
                  <div style={styles.extraRow}>
                    <span>Processing Time:</span>
                    <strong>{docStats.processing_time ? docStats.processing_time.toFixed(1) + 's' : '0.0s'}</strong>
                  </div>
                </div>

                <button style={styles.inspectionBtn} onClick={handleOpenInspectionReport}>
                  Open Inspection Report ↗
                </button>

                <button style={styles.reindexBtn} onClick={handleReindex}>
                  {indexingStatus === "indexing" ? "Indexing..." : 
                   indexingStatus === "success" ? "Indexed ✓" : 
                   indexingStatus === "error" ? "Re-index Failed 𐄂" : "Re-index Document"}
                </button>
              </div>
            ) : (
              <p style={styles.emptyText}>Please select a successfully processed document from the dropdown above to start chatting.</p>
            )}
          </div>

          {/* Model selection */}
          <div style={styles.card}>
            <h2 style={styles.cardTitle}>LLM Generation Model</h2>
            <label style={styles.label}>Select Model</label>
            <select
              value={selectedModel}
              onChange={(e) => setSelectedModel(e.target.value)}
              style={styles.select}
              disabled={modelsLoading || models.length === 0}
            >
              {models.map(m => (
                <option key={m.id} value={m.id}>
                  {m.display_name} {m.recommended ? "(Recommended)" : ""}
                </option>
              ))}
            </select>
            {selectedModel && models.length > 0 && (
              <p style={styles.modelDesc}>
                {models.find(m => m.id === selectedModel)?.description}
              </p>
            )}

            {/* Debug Mode Toggle */}
            <div style={styles.debugToggleRow}>
              <input
                type="checkbox"
                id="debug_check"
                checked={debugEnabled}
                onChange={(e) => setDebugEnabled(e.target.checked)}
                style={styles.checkbox}
              />
              <label htmlFor="debug_check" style={styles.debugLabel}>
                Enable Developer Debug Mode
              </label>
            </div>
          </div>

          {/* Suggested Questions */}
          <div style={styles.card}>
            <h2 style={styles.cardTitle}>Suggested Questions</h2>
            <div style={styles.suggestedContainer}>
              {SUGGESTED_QUESTIONS.map((q, idx) => (
                <button
                  key={idx}
                  onClick={() => handleSendMessage(q)}
                  style={styles.suggestedBtn}
                  disabled={!selectedDocId || isTyping}
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* RIGHT PANEL: Chat Workspace */}
        <div style={styles.rightPanel}>
          {/* Chat Messages Log */}
          <div style={styles.chatLog}>
            {!selectedDocId ? (
              <div style={styles.emptyChatState}>
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="var(--text-muted)" strokeWidth="1.5">
                  <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" />
                </svg>
                <h3>No Document Selected</h3>
                <p>Select a document from the left panel to begin a grounded AI consultation session.</p>
              </div>
            ) : messages.length === 0 && !isTyping ? (
              <div style={styles.emptyChatState}>
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="var(--brand)" strokeWidth="1.5">
                  <circle cx="12" cy="12" r="10" />
                  <path d="M12 16v-4" />
                  <path d="M12 8h.01" />
                </svg>
                <h3>Ask a Question</h3>
                <p>Ask a question about the document's contents, tables, or sections. The assistant will answer using ONLY the grounded context.</p>
              </div>
            ) : (
              <div style={styles.messagesList}>
                {messages.map((msg, idx) => (
                  <div
                    key={idx}
                    style={{
                      ...styles.messageRow,
                      justifyContent: msg.role === "user" ? "flex-end" : "flex-start"
                    }}
                  >
                    <div
                      style={{
                        ...styles.messageBubble,
                        ...(msg.role === "user" ? styles.userBubble : styles.assistantBubble)
                      }}
                    >
                      {/* Message Content */}
                      {msg.role === "user" ? (
                        <div style={styles.userText}>{msg.content}</div>
                      ) : (
                        <div>
                          {/* Current Model Badge */}
                          <div style={styles.assistantBadge}>
                            <span>{msg.model || selectedModel}</span>
                          </div>

                          <div 
                            dangerouslySetInnerHTML={{ __html: parseMarkdown(msg.content) }}
                            style={styles.assistantText}
                          />

                          {/* Sources & References */}
                          {(msg.pageReferences && msg.pageReferences.length > 0) && (
                            <div style={styles.sourceFooter}>
                              <div style={styles.sourceTitle}>Page References:</div>
                              <div style={styles.pagePills}>
                                {msg.pageReferences.map((page, pIdx) => (
                                  <button 
                                    key={pIdx} 
                                    onClick={() => handlePageClick(page)} 
                                    style={styles.pagePillBtn}
                                    title="Open document at page"
                                  >
                                    Page {page}
                                  </button>
                                ))}
                              </div>
                            </div>
                          )}

                          {/* Metadata footer */}
                          <div style={styles.msgMetadata}>
                            <span>Time: {msg.generationTime ? `${msg.generationTime.toFixed(2)}s` : ""}</span>
                            <span> • </span>
                            <span>Chunks used: {msg.usedChunks?.length || 0}</span>
                            <button 
                              onClick={() => handleCopyText(msg.content)} 
                              style={styles.copyBtn} 
                              title="Copy to clipboard"
                            >
                              Copy Answer
                            </button>
                          </div>

                          {/* Developer Debug accordion */}
                          {debugEnabled && msg.debugInfo && (
                            <div style={styles.debugPanel}>
                              <div style={styles.debugHeader}>Developer Retrieval Debug</div>
                              <div style={styles.debugRow}>
                                <span>Query Intent:</span> <strong>{msg.debugInfo.intent}</strong>
                              </div>
                              <div style={styles.debugRow}>
                                <span>Depth Config (Retrieve -&gt; Rerank -&gt; Final):</span>
                                <strong>{msg.debugInfo.top_k_retrieve} -&gt; {msg.debugInfo.top_k_rerank} -&gt; {msg.debugInfo.top_k_final}</strong>
                              </div>
                              <div style={styles.debugRow}>
                                <span>Total Candidates Reranked:</span> <strong>{msg.debugInfo.total_candidates_reranked}</strong>
                              </div>
                              <div style={styles.debugCandidates}>
                                <strong>Top Candidates:</strong>
                                <ul style={{ margin: "4px 0", paddingLeft: 14, fontSize: 11, fontFamily: "monospace" }}>
                                  {msg.debugInfo.candidates?.map((cand, cIdx) => (
                                    <li key={cIdx} style={{ marginBottom: 6, borderBottom: "1px dotted var(--border)", paddingBottom: 4 }}>
                                      <strong>{cand.chunk_id}</strong> (Page {cand.page}) <br/>
                                      RRF Score: {cand.rrf_score?.toFixed(4)} | Sem: {cand.similarity_score?.toFixed(4)} <br/>
                                      <span style={{ color: "var(--text-secondary)" }}>Heading: {cand.heading || "None"}</span> <br/>
                                      <span style={{ color: "var(--text-muted)" }}>Section: {cand.section || "None"}</span>
                                    </li>
                                  ))}
                                </ul>
                              </div>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                ))}

                {isTyping && (
                  <div style={styles.messageRow}>
                    <div style={{ ...styles.messageBubble, ...styles.assistantBubble }}>
                      <div style={styles.typingContainer}>
                        <span className="assistant-typing-dot"></span>
                        <span className="assistant-typing-dot"></span>
                        <span className="assistant-typing-dot"></span>
                      </div>
                    </div>
                  </div>
                )}
                <div ref={chatEndRef} />
              </div>
            )}
          </div>

          {/* Error Banner */}
          {error && (
            <div style={styles.errorBanner}>
              <span>{error}</span>
              <button onClick={() => handleSendMessage()} style={styles.retryBtn}>Retry</button>
            </div>
          )}

          {/* Message Input Bar */}
          <div style={styles.inputBar}>
            <input
              type="text"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              placeholder={selectedDocId ? "Ask a question about this document..." : "Please select a document first"}
              style={styles.input}
              disabled={!selectedDocId || isTyping}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  handleSendMessage();
                }
              }}
            />
            <button
              onClick={() => handleSendMessage()}
              style={{
                ...styles.sendBtn,
                opacity: (!selectedDocId || isTyping || !inputValue.trim()) ? 0.6 : 1
              }}
              disabled={!selectedDocId || isTyping || !inputValue.trim()}
            >
              Send
            </button>
            {messages.length > 0 && (
              <button onClick={handleClearHistory} style={styles.clearBtn} title="Clear conversation">
                Clear
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

const styles = {
  container: {
    display: "flex",
    flexDirection: "column",
    height: "calc(100vh - 100px)",
    maxWidth: 1140,
    width: "100%",
    margin: "0 auto",
  },
  header: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 16,
  },
  title: { margin: 0, fontSize: 24, fontWeight: 700, textAlign: "left" },
  subtitle: { margin: "4px 0 0", fontSize: 13, color: "var(--text-secondary)", textAlign: "left" },
  exportTopBtn: {
    padding: "8px 16px",
    background: "transparent",
    color: "var(--brand)",
    border: "1px solid var(--brand)",
    borderRadius: 8,
    fontSize: 12.5,
    fontWeight: 600,
    cursor: "pointer",
    transition: "all 0.2s",
  },
  workspace: {
    display: "flex",
    flex: 1,
    gap: 16,
    minHeight: 0,
  },
  leftPanel: {
    width: 290,
    display: "flex",
    flexDirection: "column",
    gap: 12,
    flexShrink: 0,
    overflowY: "auto",
  },
  rightPanel: {
    flex: 1,
    display: "flex",
    flexDirection: "column",
    border: "1px solid var(--border)",
    borderRadius: 16,
    background: "var(--bg-card)",
    overflow: "hidden",
    minHeight: 0,
  },
  card: {
    background: "var(--bg-card)",
    border: "1px solid var(--border)",
    borderRadius: 14,
    padding: 14,
    textAlign: "left",
  },
  cardTitle: {
    margin: "0 0 10px",
    fontSize: 13,
    fontWeight: 700,
    color: "var(--text-primary)",
    textTransform: "uppercase",
    letterSpacing: "0.5px",
  },
  label: {
    display: "block",
    fontSize: 12,
    color: "var(--text-secondary)",
    marginBottom: 6,
  },
  select: {
    width: "100%",
    padding: "8px 10px",
    borderRadius: 8,
    border: "1px solid var(--border)",
    background: "var(--bg-input, #fff)",
    color: "var(--text-primary)",
    fontSize: 13,
    outline: "none",
  },
  emptyText: {
    margin: "8px 0 0",
    fontSize: 11.5,
    color: "var(--text-muted)",
    lineHeight: 1.4,
  },
  docMeta: {
    marginTop: 10,
    paddingTop: 8,
    borderTop: "1px solid var(--border)",
    display: "flex",
    flexDirection: "column",
    gap: 6,
  },
  metaRow: {
    display: "flex",
    justifyContent: "space-between",
    fontSize: 12,
  },
  metaLabel: { color: "var(--text-secondary)" },
  metaVal: { color: "var(--text-primary)", fontWeight: 500 },
  
  // Stat Grid Styles
  statGrid: {
    display: "grid",
    gridTemplateColumns: "1fr 1fr",
    gap: 8,
    marginTop: 10,
    marginBottom: 8,
  },
  statBox: {
    background: "var(--bg-page)",
    border: "1px solid var(--border)",
    borderRadius: 8,
    padding: "8px 10px",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
  },
  statNum: {
    fontSize: 15,
    fontWeight: 700,
    color: "var(--brand)",
  },
  statLabel: {
    fontSize: 10,
    color: "var(--text-secondary)",
    textTransform: "uppercase",
    marginTop: 2,
    fontWeight: 500,
  },

  reindexBtn: {
    marginTop: 4,
    padding: "7px",
    fontSize: 11,
    borderRadius: 8,
    border: "1px solid var(--border)",
    background: "transparent",
    color: "var(--text-secondary)",
    cursor: "pointer",
    fontWeight: 600,
    transition: "all 0.2s",
  },
  extraStats: {
    display: "flex",
    flexDirection: "column",
    gap: 4,
    marginTop: 6,
    paddingTop: 6,
    borderTop: "1px solid var(--border)",
  },
  extraRow: {
    display: "flex",
    justifyContent: "space-between",
    fontSize: 11.5,
    color: "var(--text-secondary)",
  },
  inspectionBtn: {
    marginTop: 8,
    padding: "8px",
    fontSize: 11.5,
    borderRadius: 8,
    border: "none",
    background: "var(--brand)",
    color: "#fff",
    cursor: "pointer",
    fontWeight: 600,
    transition: "all 0.2s",
    textAlign: "center",
  },
  modelDesc: {
    margin: "8px 0 0",
    fontSize: 11.5,
    color: "var(--text-secondary)",
    lineHeight: 1.4,
  },
  debugToggleRow: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    marginTop: 12,
    paddingTop: 8,
    borderTop: "1px dotted var(--border)",
  },
  checkbox: {
    cursor: "pointer",
  },
  debugLabel: {
    fontSize: 12,
    color: "var(--text-secondary)",
    fontWeight: 500,
    cursor: "pointer",
  },
  suggestedContainer: {
    display: "flex",
    flexDirection: "column",
    gap: 6,
  },
  suggestedBtn: {
    width: "100%",
    padding: "8px 10px",
    borderRadius: 8,
    border: "1px solid var(--border)",
    background: "transparent",
    color: "var(--text-secondary)",
    fontSize: 12,
    textAlign: "left",
    cursor: "pointer",
    transition: "all 0.2s",
    lineHeight: 1.3,
  },
  chatLog: {
    flex: 1,
    overflowY: "auto",
    padding: 20,
    display: "flex",
    flexDirection: "column",
  },
  emptyChatState: {
    margin: "auto",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    maxWidth: 320,
    textAlign: "center",
    color: "var(--text-secondary)",
  },
  messagesList: {
    display: "flex",
    flexDirection: "column",
    gap: 16,
  },
  messageRow: {
    display: "flex",
    width: "100%",
  },
  messageBubble: {
    maxWidth: "85%",
    padding: "14px 18px",
    borderRadius: 14,
    lineHeight: 1.5,
    fontSize: 13.5,
    textAlign: "left",
    boxShadow: "0 1px 3px rgba(0,0,0,0.03)",
  },
  userBubble: {
    background: "var(--brand)",
    color: "#fff",
    borderRadius: "16px 16px 2px 16px",
  },
  assistantBubble: {
    background: "var(--bg-panel, #f8fafc)",
    color: "var(--text-primary)",
    borderRadius: "16px 16px 16px 2px",
    border: "1px solid var(--border)",
  },
  userText: { whiteSpace: "pre-wrap" },
  assistantBadge: {
    display: "inline-block",
    fontSize: 10,
    fontWeight: 700,
    color: "var(--brand)",
    background: "var(--brand-light)",
    padding: "2px 6px",
    borderRadius: 4,
    marginBottom: 6,
    textTransform: "uppercase",
  },
  assistantText: {
    fontSize: 13.5,
    color: "var(--text-primary)",
  },
  sourceFooter: {
    marginTop: 12,
    paddingTop: 8,
    borderTop: "1px dotted var(--border)",
  },
  sourceTitle: {
    fontSize: 11,
    fontWeight: 600,
    color: "var(--text-secondary)",
    marginBottom: 6,
  },
  pagePills: {
    display: "flex",
    flexWrap: "wrap",
    gap: 6,
  },
  pagePillBtn: {
    fontSize: 10.5,
    background: "var(--brand-light)",
    color: "var(--brand)",
    padding: "3px 8px",
    borderRadius: 6,
    fontWeight: 600,
    border: "none",
    cursor: "pointer",
    transition: "transform 0.1s",
    "&:hover": {
      transform: "translateY(-1px)",
    }
  },
  msgMetadata: {
    marginTop: 10,
    fontSize: 11,
    color: "var(--text-muted)",
    display: "flex",
    alignItems: "center",
    gap: 6,
  },
  copyBtn: {
    marginLeft: "auto",
    background: "transparent",
    border: "none",
    color: "var(--brand)",
    fontSize: 11,
    cursor: "pointer",
    padding: "0 4px",
    fontWeight: 650,
  },
  typingContainer: {
    display: "flex",
    alignItems: "center",
    gap: 4,
    padding: "4px 0",
  },
  
  // Debug Accordion Panel
  debugPanel: {
    marginTop: 12,
    padding: "10px 12px",
    background: "var(--bg-page)",
    border: "1px solid var(--border)",
    borderRadius: 8,
    fontSize: 11.5,
  },
  debugHeader: {
    fontWeight: 700,
    color: "var(--text-primary)",
    textTransform: "uppercase",
    fontSize: 10,
    letterSpacing: "0.5px",
    marginBottom: 6,
    borderBottom: "1px solid var(--border)",
    paddingBottom: 4,
  },
  debugRow: {
    display: "flex",
    justifyContent: "space-between",
    marginBottom: 4,
  },
  debugCandidates: {
    marginTop: 8,
  },

  errorBanner: {
    padding: "10px 16px",
    background: "var(--red-light)",
    color: "var(--red)",
    borderTop: "1px solid rgba(225,85,85,0.15)",
    borderBottom: "1px solid rgba(225,85,85,0.15)",
    fontSize: 12.5,
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    textAlign: "left",
  },
  retryBtn: {
    background: "var(--red)",
    color: "#fff",
    border: "none",
    borderRadius: 6,
    padding: "4px 10px",
    fontSize: 11,
    cursor: "pointer",
    fontWeight: 600,
  },
  inputBar: {
    display: "flex",
    padding: 14,
    borderTop: "1px solid var(--border)",
    gap: 8,
    alignItems: "center",
    background: "var(--bg-panel, #f9fafb)",
  },
  input: {
    flex: 1,
    padding: "11px 16px",
    borderRadius: 8,
    border: "1px solid var(--border)",
    outline: "none",
    fontSize: 13.5,
    background: "var(--bg-input, #fff)",
    color: "var(--text-primary)",
  },
  sendBtn: {
    padding: "11px 20px",
    borderRadius: 8,
    background: "var(--brand)",
    color: "#fff",
    border: "none",
    fontWeight: 600,
    fontSize: 13,
    cursor: "pointer",
    transition: "background 0.2s",
  },
  clearBtn: {
    padding: "11px 16px",
    borderRadius: 8,
    background: "transparent",
    color: "var(--text-secondary)",
    border: "1px solid var(--border)",
    fontWeight: 500,
    fontSize: 13,
    cursor: "pointer",
    transition: "all 0.2s",
  }
};
