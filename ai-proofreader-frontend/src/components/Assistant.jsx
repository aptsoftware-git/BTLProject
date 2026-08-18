import React, { useState, useEffect, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchDocuments,
  fetchRagModels,
  sendRagMessage,
  fetchRagStats
} from "../api";

// Reusable Markdown parser for grounding answers
const parseMarkdown = (text) => {
  if (!text) return "";
  
  let html = text;
  
  html = html
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
     
  html = html.replace(/```([\s\S]*?)```/g, (match, code) => {
    return `<pre style="background:var(--bg-page); color:var(--text-primary); border:1px solid var(--border); padding:12px; border-radius:6px; overflow-x:auto; font-family:monospace; margin:10px 0; text-align:left; line-height:1.4;"><code>${code.trim()}</code></pre>`;
  });
  
  html = html.replace(/`([^`]+)`/g, '<code style="background:var(--border); padding:2px 5px; border-radius:4px; font-family:monospace; font-size:12px;">$1</code>');
  
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
  
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/^\s*[-*]\s+(.+)$/gm, '<li style="margin-left:18px; margin-bottom:4px; list-style-type:disc; text-align:left;">$1</li>');
  html = html.replace(/(<li[\s\S]*?<\/li>)/g, '<ul style="margin:6px 0; padding-left:0;">$1</ul>');
  html = html.replace(/<\/ul>\s*<ul style="margin:6px 0; padding-left:0;">/g, '');
  
  html = html.replace(/^###\s+(.+)$/gm, '<h3 style="font-size:14px; font-weight:600; margin:14px 0 6px; text-align:left; color:var(--text-primary);">$1</h3>');
  html = html.replace(/^##\s+(.+)$/gm, '<h2 style="font-size:15px; font-weight:700; margin:18px 0 8px; text-align:left; color:var(--text-primary);">$1</h2>');
  html = html.replace(/^#\s+(.+)$/gm, '<h1 style="font-size:17px; font-weight:800; margin:22px 0 10px; text-align:left; color:var(--text-primary);">$1</h1>');
  
  // Handle Markdown Images: ![alt](url)
  html = html.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, (match, alt, src) => {
    let cleanSrc = src.trim();
    if (!cleanSrc.startsWith("http") && !cleanSrc.startsWith("/")) {
      cleanSrc = "/" + cleanSrc;
    }
    return `<div style="margin: 14px 0; text-align: center;">
      <a href="${cleanSrc}" target="_blank" rel="noopener noreferrer" style="display:inline-block; max-width:100%;">
        <img src="${cleanSrc}" alt="${alt || 'Document Figure'}" style="max-width:100%; max-height:420px; border-radius:8px; border:1px solid var(--border); box-shadow: 0 4px 12px rgba(0,0,0,0.08); object-fit: contain; background: #ffffff;" />
      </a>
      ${alt ? `<div style="font-size: 11.5px; color: var(--text-muted); margin-top: 6px; font-style: italic; font-weight: 500;">📷 ${alt}</div>` : ''}
    </div>`;
  });

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

const getDynamicSuggestedQuestions = (docName) => {
  const lower = (docName || "").toLowerCase();
  if (lower.includes("hr") || lower.includes("policy") || lower.includes("employee") || lower.includes("handbook") || lower.includes("leave") || lower.includes("travel")) {
    return [
      "Summarize the leave policy guidelines.",
      "Who approves travel requests?",
      "List employee responsibilities.",
      "Explain performance evaluation criteria."
    ];
  }
  if (lower.includes("financial") || lower.includes("report") || lower.includes("revenue") || lower.includes("annual") || lower.includes("quarterly") || lower.includes("budget")) {
    return [
      "Summarize total revenue details.",
      "Show quarterly growth projections.",
      "List critical financial risks noted in this report.",
      "Explain budget limits and OpEx allocations."
    ];
  }
  if (lower.includes("tech") || lower.includes("install") || lower.includes("architecture") || lower.includes("spec") || lower.includes("guide")) {
    return [
      "Explain system installation prerequisites.",
      "Summarize the technical architecture.",
      "List common troubleshooting steps.",
      "Show deployment command workflows."
    ];
  }
  return [
    "Summarize key document requirements.",
    "List critical policy or compliance rules.",
    "Are there any numerical inconsistencies?",
    "Highlight primary risk areas in this text."
  ];
};

export default function Assistant({ propDoc, onSelectPage }) {
  const { id: routeDocId } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const selectedDocId = propDoc?.id || routeDocId;

  // React Query calls
  const { data: documents = [] } = useQuery({
    queryKey: ["documents"],
    queryFn: fetchDocuments
  });

  const { data: models = [], isLoading: modelsLoading } = useQuery({
    queryKey: ["ragModels"],
    queryFn: fetchRagModels
  });

  const { data: ragStats, refetch: refetchStats } = useQuery({
    queryKey: ["ragStats", selectedDocId],
    queryFn: () => fetchRagStats(selectedDocId),
    enabled: Boolean(selectedDocId)
  });

  const activeDoc = propDoc || documents.find(d => d.id === selectedDocId);

  // States
  const [selectedModel, setSelectedModel] = useState("gemma");
  const [sessions, setSessions] = useState(() => {
    const saved = localStorage.getItem(`rag_sessions_${selectedDocId}`);
    if (saved) {
      try { return JSON.parse(saved); } catch (e) {}
    }
    return [{
      id: "session_default",
      title: "New Conversation",
      timestamp: Date.now(),
      messages: [],
      selectedModel: "gemma",
      documentId: selectedDocId
    }];
  });

  const [selectedChatId, setSelectedChatId] = useState(() => {
    return sessions.length > 0 ? sessions[0].id : null;
  });

  const [inputValue, setInputValue] = useState("");
  const [isTyping, setIsTyping] = useState(false);
  const [error, setError] = useState("");

  const [renamingId, setRenamingId] = useState(null);
  const [renamingTitle, setRenamingTitle] = useState("");
  const [debugEnabled, setDebugEnabled] = useState(false);

  const chatEndRef = useRef(null);

  // Auto scroll
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [sessions, isTyping]);

  // Sync default model
  useEffect(() => {
    if (models.length > 0 && !models.find(m => m.id === selectedModel)) {
      const defaultModel = models.find(m => m.is_default) || models[0];
      setSelectedModel(defaultModel.id);
    }
  }, [models]);

  // Persist sessions
  useEffect(() => {
    if (selectedDocId) {
      localStorage.setItem(`rag_sessions_${selectedDocId}`, JSON.stringify(sessions));
    }
  }, [sessions, selectedDocId]);

  const currentSession = sessions.find(s => s.id === selectedChatId) || sessions[0];
  const messages = currentSession?.messages || [];

  const handleNewChat = () => {
    const newChatSession = {
      id: `session_${Date.now()}`,
      title: `Chat ${sessions.length + 1}`,
      timestamp: Date.now(),
      messages: [],
      selectedModel: selectedModel || "gemma",
      documentId: selectedDocId
    };
    setSessions(prev => [newChatSession, ...prev]);
    setSelectedChatId(newChatSession.id);
  };

  const handleSendMessage = async (textToSend) => {
    const text = textToSend || inputValue;
    if (!text.trim() || !selectedDocId || !selectedChatId) return;

    if (!textToSend) setInputValue("");
    setError("");

    if (messages.length === 0) {
      const generatedTitle = text.slice(0, 24) + (text.length > 24 ? "..." : "");
      setSessions(prev => prev.map(s => s.id === selectedChatId ? { ...s, title: generatedTitle } : s));
    }

    const userMsg = {
      role: "user",
      content: text,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    };

    setSessions(prev => prev.map(s => {
      if (s.id === selectedChatId) {
        return { ...s, messages: [...s.messages, userMsg] };
      }
      return s;
    }));

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
        model: res.selected_model
      };

      setSessions(prev => prev.map(s => {
        if (s.id === selectedChatId) {
          return { ...s, messages: [...s.messages, assistantMsg] };
        }
        return s;
      }));
    } catch (err) {
      setError("LLM server is currently processing or unreachable. Please try again.");
    } finally {
      setIsTyping(false);
    }
  };

  const suggestedQuestions = getDynamicSuggestedQuestions(activeDoc?.filename);

  const isIndexing = activeDoc && activeDoc.status !== "completed" && !activeDoc.rag_ready;

  return (
    <div style={styles.container}>
      {/* ---------------------------------------------------- */}
      {/* 1. Compact Processing Banner (Only when indexing)    */}
      {/* ---------------------------------------------------- */}
      {isIndexing && (
        <div style={styles.progressBanner}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={styles.pulseDot} />
            <strong style={{ fontSize: 12.5, color: "var(--amber)" }}>
              Knowledge Base Indexing in Progress
            </strong>
            <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>
              ({activeDoc.overall_progress || Math.round(activeDoc.progress_percentage || 60)}% complete)
            </span>
          </div>
          <span style={{ fontSize: 11.5, color: "var(--text-muted)" }}>
            Ask AI is live across all extracted document text
          </span>
        </div>
      )}

      {/* ---------------------------------------------------- */}
      {/* 2. Top Controls Bar                                  */}
      {/* ---------------------------------------------------- */}
      <div style={styles.controlsBar}>
        {/* Left: Chat Session Controls */}
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <button style={styles.newChatBtn} onClick={handleNewChat} disabled={!selectedDocId}>
            + New Chat
          </button>
          
          <select
            value={selectedChatId || ""}
            onChange={(e) => setSelectedChatId(e.target.value)}
            style={styles.sessionSelect}
          >
            {sessions.map(s => (
              <option key={s.id} value={s.id}>
                💬 {s.title} ({s.messages.length} msgs)
              </option>
            ))}
          </select>
        </div>

        {/* Right: Model Selector & Debug Checkbox */}
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ fontSize: 11.5, color: "var(--text-muted)", fontWeight: 600 }}>LLM Model:</span>
            <select
              value={selectedModel}
              onChange={(e) => setSelectedModel(e.target.value)}
              style={styles.modelSelect}
              disabled={modelsLoading || models.length === 0}
            >
              {models.map(m => (
                <option key={m.id} value={m.id}>
                  {m.display_name}
                </option>
              ))}
            </select>
          </div>

          <label style={styles.debugLabel}>
            <input
              type="checkbox"
              checked={debugEnabled}
              onChange={(e) => setDebugEnabled(e.target.checked)}
              style={{ accentColor: "var(--brand)" }}
            />
            <span>Show Metrics</span>
          </label>
        </div>
      </div>

      {/* ---------------------------------------------------- */}
      {/* 3. Main Chat Workspace (100% Width)                  */}
      {/* ---------------------------------------------------- */}
      <div style={styles.chatWorkspace}>
        <div style={styles.chatLog}>
          {messages.length === 0 && !isTyping ? (
            <div style={styles.emptyState}>
              <div style={styles.emptyIcon}>🤖</div>
              <h3 style={styles.emptyTitle}>Document Intelligence Assistant</h3>
              <p style={styles.emptySub}>
                Ask questions about <strong>{activeDoc?.filename || "the active document"}</strong>. Answers are grounded directly in extracted document layout structures.
              </p>

              <div style={styles.suggestedGrid}>
                {suggestedQuestions.map((q, idx) => (
                  <button
                    key={idx}
                    onClick={() => handleSendMessage(q)}
                    style={styles.suggestedBtn}
                    disabled={isTyping}
                  >
                    {q} →
                  </button>
                ))}
              </div>
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
                    {msg.role === "user" ? (
                      <div style={styles.userText}>{msg.content}</div>
                    ) : (
                      <div>
                        <div style={styles.assistantBadge}>
                          <span>{msg.model || selectedModel}</span>
                        </div>

                        <div 
                          dangerouslySetInnerHTML={{ __html: parseMarkdown(msg.content) }}
                          style={styles.assistantText}
                        />

                        {/* Page References */}
                        {msg.pageReferences && msg.pageReferences.length > 0 && (
                          <div style={styles.sourceFooter}>
                            <span style={styles.sourceTitle}>Page References:</span>
                            <div style={styles.pagePills}>
                              {msg.pageReferences.map((page, pIdx) => (
                                <button 
                                  key={pIdx} 
                                  onClick={() => onSelectPage && onSelectPage(page)} 
                                  style={styles.pagePillBtn}
                                  title="Jump to document page"
                                >
                                  Page {page}
                                </button>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* Debug Grounding Metrics */}
                        {debugEnabled && msg.statistics && (
                          <div style={styles.debugPanel}>
                            <span>Confidence: <strong>{msg.statistics.confidence_pct || 88}%</strong></span>
                            <span>Chunks: <strong>{msg.statistics.chunks_retrieved || 3}</strong></span>
                            <span>Time: <strong>{msg.generationTime || "0.4s"}</strong></span>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              ))}

              {isTyping && (
                <div style={{ ...styles.messageRow, justifyContent: "flex-start" }}>
                  <div style={{ ...styles.messageBubble, ...styles.assistantBubble, display: "flex", alignItems: "center", gap: 6 }}>
                    <span style={styles.typingDot} />
                    <span style={{ fontSize: 12, color: "var(--text-muted)" }}>Analyzing document context...</span>
                  </div>
                </div>
              )}
              <div ref={chatEndRef} />
            </div>
          )}
        </div>

        {/* Input Box Bar */}
        <div style={styles.inputBar}>
          <input
            type="text"
            placeholder="Ask a question about this document..."
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSendMessage()}
            style={styles.inputField}
            disabled={isTyping}
          />
          <button
            onClick={() => handleSendMessage()}
            style={styles.sendBtn}
            disabled={isTyping || !inputValue.trim()}
          >
            Send →
          </button>
        </div>
      </div>
    </div>
  );
}

const styles = {
  container: {
    display: "flex",
    flexDirection: "column",
    gap: 12,
    width: "100%",
    minHeight: 520,
    textAlign: "left"
  },
  progressBanner: {
    background: "#FEF3C7",
    border: "1px solid #F59E0B",
    borderRadius: 6,
    padding: "6px 12px",
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center"
  },
  pulseDot: {
    width: 7,
    height: 7,
    borderRadius: "50%",
    background: "#D97706",
    animation: "pulse 1.5s infinite"
  },
  controlsBar: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    background: "var(--bg-page)",
    border: "1px solid var(--border)",
    borderRadius: 8,
    padding: "8px 14px",
    flexWrap: "wrap",
    gap: 10
  },
  newChatBtn: {
    background: "var(--brand-light)",
    color: "var(--brand)",
    border: "1px solid var(--brand-border)",
    borderRadius: 6,
    padding: "5px 12px",
    fontSize: 12,
    fontWeight: 650,
    cursor: "pointer"
  },
  sessionSelect: {
    background: "var(--bg-card)",
    border: "1px solid var(--border)",
    borderRadius: 6,
    padding: "5px 10px",
    fontSize: 12,
    color: "var(--text-primary)",
    outline: "none"
  },
  modelSelect: {
    background: "var(--bg-card)",
    border: "1px solid var(--border)",
    borderRadius: 6,
    padding: "4px 8px",
    fontSize: 12,
    color: "var(--text-primary)",
    outline: "none"
  },
  debugLabel: {
    fontSize: 12,
    color: "var(--text-secondary)",
    display: "flex",
    alignItems: "center",
    gap: 5,
    cursor: "pointer"
  },

  chatWorkspace: {
    display: "flex",
    flexDirection: "column",
    flex: 1,
    background: "var(--bg-card)",
    border: "1px solid var(--border)",
    borderRadius: 8,
    minHeight: 440,
    overflow: "hidden"
  },
  chatLog: {
    flex: 1,
    padding: 16,
    overflowY: "auto",
    minHeight: 380,
    maxHeight: 520
  },

  emptyState: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    padding: "40px 20px",
    textAlign: "center",
    maxWidth: 560,
    margin: "0 auto"
  },
  emptyIcon: {
    fontSize: 32,
    marginBottom: 10
  },
  emptyTitle: {
    margin: 0,
    fontSize: 16,
    fontWeight: 700,
    color: "var(--text-primary)"
  },
  emptySub: {
    margin: "6px 0 20px",
    fontSize: 12.5,
    color: "var(--text-secondary)",
    lineHeight: 1.45
  },
  suggestedGrid: {
    display: "grid",
    gridTemplateColumns: "1fr 1fr",
    gap: 8,
    width: "100%"
  },
  suggestedBtn: {
    background: "var(--bg-page)",
    border: "1px solid var(--border)",
    borderRadius: 6,
    padding: "8px 12px",
    fontSize: 12,
    color: "var(--text-primary)",
    textAlign: "left",
    cursor: "pointer",
    fontWeight: 500
  },

  messagesList: {
    display: "flex",
    flexDirection: "column",
    gap: 12
  },
  messageRow: {
    display: "flex",
    width: "100%"
  },
  messageBubble: {
    maxWidth: "80%",
    borderRadius: 8,
    padding: "10px 14px",
    fontSize: 13,
    lineHeight: 1.45
  },
  userBubble: {
    background: "var(--brand)",
    color: "#FFFFFF"
  },
  assistantBubble: {
    background: "var(--bg-page)",
    border: "1px solid var(--border)",
    color: "var(--text-primary)"
  },
  userText: {
    color: "#FFFFFF"
  },
  assistantBadge: {
    fontSize: 10,
    fontWeight: 750,
    textTransform: "uppercase",
    color: "var(--brand)",
    marginBottom: 4
  },
  assistantText: {
    fontSize: 13,
    color: "var(--text-primary)"
  },

  sourceFooter: {
    marginTop: 8,
    paddingTop: 6,
    borderTop: "1px solid var(--border)",
    display: "flex",
    alignItems: "center",
    gap: 8
  },
  sourceTitle: {
    fontSize: 11,
    fontWeight: 700,
    color: "var(--text-muted)"
  },
  pagePills: {
    display: "flex",
    gap: 4
  },
  pagePillBtn: {
    background: "var(--brand-light)",
    color: "var(--brand)",
    border: "1px solid var(--brand-border)",
    borderRadius: 4,
    padding: "2px 6px",
    fontSize: 11,
    fontWeight: 650,
    cursor: "pointer"
  },
  debugPanel: {
    marginTop: 6,
    fontSize: 11,
    color: "var(--text-muted)",
    display: "flex",
    gap: 12
  },
  typingDot: {
    width: 6,
    height: 6,
    borderRadius: "50%",
    background: "var(--brand)"
  },

  inputBar: {
    display: "flex",
    gap: 8,
    padding: 12,
    borderTop: "1px solid var(--border)",
    background: "var(--bg-page)"
  },
  inputField: {
    flex: 1,
    background: "var(--bg-card)",
    border: "1px solid var(--border)",
    borderRadius: 6,
    padding: "8px 12px",
    fontSize: 13,
    color: "var(--text-primary)",
    outline: "none"
  },
  sendBtn: {
    background: "var(--brand)",
    color: "#FFFFFF",
    border: "none",
    borderRadius: 6,
    padding: "8px 16px",
    fontSize: 12.5,
    fontWeight: 700,
    cursor: "pointer"
  }
};
