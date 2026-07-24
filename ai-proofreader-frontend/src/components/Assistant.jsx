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
    return `<pre style="background:#0e1117; color:#c9d1d9; border:1px solid var(--border); padding:12px; border-radius:8px; overflow-x:auto; font-family:monospace; margin:10px 0; text-align:left; line-height:1.4;"><code>${code.trim()}</code></pre>`;
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
      "Who is responsible for approving travel requests?",
      "List all general employee responsibilities.",
      "Explain the performance evaluation criteria.",
      "What are the remote work policies?",
      "Summarize benefits and health coverage."
    ];
  }
  if (lower.includes("financial") || lower.includes("report") || lower.includes("revenue") || lower.includes("annual") || lower.includes("quarterly") || lower.includes("budget") || lower.includes("fiscal")) {
    return [
      "Summarize the total revenue details.",
      "Show quarterly growth projections.",
      "List critical financial risks noted in this report.",
      "Explain cost reductions and budget limits.",
      "Summarize operational expenditures (OpEx).",
      "What is the profit margin analysis?"
    ];
  }
  if (lower.includes("tech") || lower.includes("install") || lower.includes("architecture") || lower.includes("dev") || lower.includes("spec") || lower.includes("guide") || lower.includes("manual")) {
    return [
      "Explain the server installation workflow.",
      "List all technical prerequisites.",
      "Summarize the software system architecture.",
      "Explain database schema configuration.",
      "List common troubleshooting alerts.",
      "Show deployment command steps."
    ];
  }
  // Default fallback
  return [
    "Summarize this document in a high-level executive report.",
    "What are the primary findings and recommendations?",
    "Identify the major risks or caveats mentioned.",
    "List the key dates and milestones from this text.",
    "Analyze structural consistency and policies.",
    "Suggest spelling or grammar improvements."
  ];
};

export default function Assistant({ onSelectPage, activeDocId }) {
  const { id } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const chatEndRef = useRef(null);

  // Sync active document ID from prop, route parameter, or session storage context
  const selectedDocId = activeDocId || id || localStorage.getItem("currentlyOpenDocId") || "";

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
  const [debugEnabled, setDebugEnabled] = useState(false);
  const [docStats, setDocStats] = useState({ chunks: 0, tables: 0, images: 0, pages: 0 });
  const [statsLoading, setStatsLoading] = useState(false);
  const [inputValue, setInputValue] = useState("");
  const [isTyping, setIsTyping] = useState(false);
  const [error, setError] = useState("");
  const [suggestedQuestions, setSuggestedQuestions] = useState([]);

  // Session state synced per document
  const [sessions, setSessions] = useState(() => {
    if (!selectedDocId) return [];
    try {
      const stored = localStorage.getItem(`chatSessions_${selectedDocId}`);
      return stored ? JSON.parse(stored) : [];
    } catch (e) {
      console.error("Error reading chatSessions:", e);
      return [];
    }
  });

  const [selectedChatId, setSelectedChatId] = useState(() => {
    if (!selectedDocId) return null;
    return localStorage.getItem(`selectedChatId_${selectedDocId}`) || null;
  });

  const [renamingId, setRenamingId] = useState(null);
  const [renamingTitle, setRenamingTitle] = useState("");

  const activeDoc = documents.find(d => d.id === selectedDocId);

  // Redirection checks for direct URL access without active context
  useEffect(() => {
    if (!activeDocId) {
      const activeId = localStorage.getItem("currentlyOpenDocId");
      if (activeId && !id) {
        navigate(`/documents/${activeId}?tab=assistant`, { replace: true });
      }
    }
  }, [id, activeDocId, navigate]);

  // Sync session state when the loaded document context changes
  useEffect(() => {
    if (selectedDocId) {
      const stored = localStorage.getItem(`chatSessions_${selectedDocId}`);
      const parsed = stored ? JSON.parse(stored) : [];
      setSessions(parsed);
      
      const storedChatId = localStorage.getItem(`selectedChatId_${selectedDocId}`);
      if (storedChatId && parsed.some(s => s.id === storedChatId)) {
        setSelectedChatId(storedChatId);
      } else if (parsed.length > 0) {
        setSelectedChatId(parsed[0].id);
      } else {
        setSelectedChatId(null);
      }

      setStatsLoading(true);
      fetchRagStats(selectedDocId)
        .then(setDocStats)
        .catch(err => console.error("Error fetching stats:", err))
        .finally(() => setStatsLoading(false));
    } else {
      setSessions([]);
      setSelectedChatId(null);
      setDocStats({ chunks: 0, tables: 0, images: 0, pages: 0 });
    }
  }, [selectedDocId]);

  // Persist session changes
  useEffect(() => {
    if (selectedDocId) {
      localStorage.setItem(`chatSessions_${selectedDocId}`, JSON.stringify(sessions));
    }
  }, [sessions, selectedDocId]);

  useEffect(() => {
    if (selectedDocId && selectedChatId) {
      localStorage.setItem(`selectedChatId_${selectedDocId}`, selectedChatId);
    }
  }, [selectedChatId, selectedDocId]);

  // Create default initial chat session if none exist
  useEffect(() => {
    if (selectedDocId && sessions.length === 0) {
      const defaultChat = {
        id: `chat_${Date.now()}`,
        title: "New Chat",
        timestamp: Date.now(),
        messages: [],
        selectedModel: selectedModel || "gemma",
        documentId: selectedDocId
      };
      setSessions([defaultChat]);
      setSelectedChatId(defaultChat.id);
    }
  }, [selectedDocId, sessions.length, selectedModel]);

  // Set recommended default model
  useEffect(() => {
    if (models.length > 0 && !selectedModel) {
      const recommended = models.find(m => m.recommended);
      setSelectedModel(recommended ? recommended.id : models[0].id);
    }
  }, [models, selectedModel]);

  // Generate dynamic suggested questions based on the active doc
  useEffect(() => {
    if (activeDoc) {
      setSuggestedQuestions(getDynamicSuggestedQuestions(activeDoc.filename));
    } else {
      setSuggestedQuestions(getDynamicSuggestedQuestions(""));
    }
  }, [activeDoc]);

  // Live reload polling sync for document status
  useEffect(() => {
    function handleSync() {
      const activeId = localStorage.getItem("currentlyOpenDocId");
      if (activeId && activeId !== selectedDocId) {
        queryClient.invalidateQueries(["documents"]);
      }
    }
    window.addEventListener("activeDocChanged", handleSync);
    return () => window.removeEventListener("activeDocChanged", handleSync);
  }, [selectedDocId, queryClient]);

  // Scroll active chat into view
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [sessions, isTyping]);

  const activeSession = sessions.find(s => s.id === selectedChatId);
  const messages = activeSession ? activeSession.messages : [];

  const handleNewChat = () => {
    if (!selectedDocId) return;
    const newChatSession = {
      id: `chat_${Date.now()}`,
      title: "New Chat",
      timestamp: Date.now(),
      messages: [],
      selectedModel: selectedModel || "gemma",
      documentId: selectedDocId
    };
    setSessions(prev => [newChatSession, ...prev]);
    setSelectedChatId(newChatSession.id);
  };

  const generateChatTitle = (query) => {
    const q = query.toLowerCase();
    if (q.includes("summarize") || q.includes("summary")) return "Document Summary";
    if (q.includes("policy") || q.includes("policies") || q.includes("hr")) return "Company Policies";
    if (q.includes("financial") || q.includes("performance") || q.includes("revenue") || q.includes("growth")) return "Financial Performance";
    if (q.includes("contradiction") || q.includes("contradict") || q.includes("conflict")) return "Consistency Review";
    if (q.includes("ambiguity") || q.includes("ambiguous")) return "Ambiguity Mappings";
    
    const words = query.replace(/[^\w\s]/g, "").split(/\s+/).filter(Boolean);
    if (words.length === 0) return "General Chat";
    const chunk = words.slice(0, 4).map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(" ");
    return chunk.length > 22 ? chunk.substring(0, 22) + "..." : chunk;
  };

  const handleSendMessage = async (textToSend) => {
    const text = textToSend || inputValue;
    if (!text.trim() || !selectedDocId || !selectedChatId) return;

    if (!textToSend) {
      setInputValue("");
    }
    setError("");

    // If it is the first query in this session, update title
    if (messages.length === 0) {
      const generatedTitle = generateChatTitle(text);
      setSessions(prev => prev.map(s => s.id === selectedChatId ? { ...s, title: generatedTitle } : s));
    }

    // Add user message
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
        model: res.selected_model,
        debugInfo: res.metadata?.debug_info
      };

      setSessions(prev => prev.map(s => {
        if (s.id === selectedChatId) {
          return { ...s, messages: [...s.messages, assistantMsg] };
        }
        return s;
      }));
    } catch (err) {
      console.error("Error generating answer:", err);
      let errMsg = "An error occurred while calling the LLM backend.";
      if (err.message?.includes("500") || err.message?.includes("fetch")) {
        errMsg = "LLM Server (Ollama) is currently unreachable. Please check settings or connection status.";
      }
      setError(errMsg);
    } finally {
      setIsTyping(false);
    }
  };

  const handleRegenerate = async (idx) => {
    let prevUserPrompt = "";
    for (let i = idx - 1; i >= 0; i--) {
      if (messages[i] && messages[i].role === "user") {
        prevUserPrompt = messages[i].content;
        break;
      }
    }
    if (!prevUserPrompt) return;
    await handleSendMessage(prevUserPrompt);
  };

  const handleClearHistory = () => {
    setSessions(prev => prev.map(s => {
      if (s.id === selectedChatId) {
        return { ...s, messages: [] };
      }
      return s;
    }));
  };

  const startRename = (e, session) => {
    e.stopPropagation();
    setRenamingId(session.id);
    setRenamingTitle(session.title);
  };

  const saveRename = (e, id) => {
    e.stopPropagation();
    if (renamingTitle.trim()) {
      setSessions(prev => prev.map(s => s.id === id ? { ...s, title: renamingTitle } : s));
      setRenamingId(null);
    }
  };

  const handleKeyPressRename = (e, id) => {
    if (e.key === "Enter") {
      saveRename(e, id);
    }
  };

  const deleteSession = (e, id) => {
    e.stopPropagation();
    const confirmed = window.confirm("Are you sure you want to delete this chat session?");
    if (!confirmed) return;
    
    setSessions(prev => {
      const next = prev.filter(s => s.id !== id);
      if (selectedChatId === id) {
        setSelectedChatId(next.length > 0 ? next[0].id : null);
      }
      return next;
    });
  };

  const handlePageClick = (page) => {
    if (onSelectPage) {
      onSelectPage(page);
    } else {
      navigate(`/documents/${selectedDocId}?page=${page}`);
    }
  };

  const getGroupedSessions = () => {
    const today = [];
    const yesterday = [];
    const older = [];
    
    const oneDay = 24 * 60 * 60 * 1000;
    const now = Date.now();
    
    sessions.forEach(s => {
      const diff = now - s.timestamp;
      if (diff < oneDay) {
        today.push(s);
      } else if (diff < 2 * oneDay) {
        yesterday.push(s);
      } else {
        older.push(s);
      }
    });
    
    return { today, yesterday, older };
  };

  const groupedSessions = getGroupedSessions();

  const renderSessionRow = (session) => {
    const isSelected = selectedChatId === session.id;
    const isEditing = renamingId === session.id;

    return (
      <div
        key={session.id}
        onClick={() => setSelectedChatId(session.id)}
        style={{
          ...styles.sessionRow,
          background: isSelected ? "var(--brand-light)" : "transparent",
          color: isSelected ? "var(--brand)" : "var(--text-primary)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", minWidth: 0, flex: 1 }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ marginRight: 8, flexShrink: 0 }}><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
          {isEditing ? (
            <input
              type="text"
              value={renamingTitle}
              onChange={(e) => setRenamingTitle(e.target.value)}
              onBlur={(e) => saveRename(e, session.id)}
              onKeyDown={(e) => handleKeyPressRename(e, session.id)}
              onClick={(e) => e.stopPropagation()}
              style={styles.renameInput}
              autoFocus
            />
          ) : (
            <span style={styles.sessionTitleText}>{session.title}</span>
          )}
        </div>

        {!isEditing && (
          <div style={styles.sessionActions} className="chat-actions-hover">
            <button style={styles.sessionRowBtn} onClick={(e) => startRename(e, session)} title="Rename chat">
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 1 1 3 3L12 15l-4 1 1-4z"/></svg>
            </button>
            <button style={styles.sessionRowBtn} onClick={(e) => deleteSession(e, session.id)} title="Delete chat">
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
            </button>
          </div>
        )}
      </div>
    );
  };

  return (
    <div style={styles.container}>
      {/* 1. Dynamic Context Header Display */}
      {selectedDocId && (
        <div style={styles.contextHeader}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontSize: 11, fontWeight: 750, color: "var(--brand)", textTransform: "uppercase" }}>Currently Analyzing</span>
            <span style={{ color: "var(--border)", fontSize: 12 }}>|</span>
            <span style={{ color: "var(--text-primary)", fontWeight: 700 }}>{activeDoc?.filename || "Loading..."}</span>
          </div>
          <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
            <span>Pages: <strong>{docStats.pages || 1}</strong></span>
            <span>Model: <strong style={{ textTransform: "capitalize" }}>{selectedModel}</strong></span>
            <span style={{ 
              color: activeDoc?.status === "completed" ? "var(--green)" : "var(--amber)",
              fontWeight: 700
            }}>
              {activeDoc?.status === "completed" ? "✓ Ready" : "⚠ Processing"}
            </span>
          </div>
        </div>
      )}

      <div style={styles.workspace}>
        {/* 2. Left sidebar panel (ChatGPT style conversation list) */}
        <div style={styles.leftPanel}>
          <div style={styles.card}>
            <span style={{ fontSize: 10, fontWeight: 750, textTransform: "uppercase", color: "var(--text-secondary)", display: "block", marginBottom: 6, letterSpacing: 0.5 }}>Active Context</span>
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--brand)" strokeWidth="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
              <span style={{ fontSize: 12.5, fontWeight: 650, color: "var(--text-primary)", textOverflow: "ellipsis", overflow: "hidden", whiteSpace: "nowrap", flex: 1 }}>
                {activeDoc?.filename || "No document active"}
              </span>
            </div>

            {/* Model selector */}
            <div style={{ marginTop: 12 }}>
              <span style={{ fontSize: 10, fontWeight: 750, textTransform: "uppercase", color: "var(--text-secondary)", display: "block", marginBottom: 4, letterSpacing: 0.5 }}>LLM Model</span>
              <select
                value={selectedModel}
                onChange={(e) => setSelectedModel(e.target.value)}
                style={styles.select}
                disabled={modelsLoading || models.length === 0}
              >
                {models.map(m => (
                  <option key={m.id} value={m.id}>
                    {m.display_name}
                  </option>
                ))}
              </select>
            </div>

            {/* Debug Mode Accordion */}
            <div style={styles.debugToggleRow}>
              <input
                type="checkbox"
                id="debugCheck"
                checked={debugEnabled}
                onChange={(e) => setDebugEnabled(e.target.checked)}
                style={styles.checkbox}
              />
              <label htmlFor="debugCheck" style={styles.debugLabel}>
                Show Grounding Metrics
              </label>
            </div>
          </div>

          <button style={styles.newChatBtn} onClick={handleNewChat} disabled={!selectedDocId}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" style={{ marginRight: 6 }}><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
            New Chat
          </button>

          {/* Grouped conversations list */}
          <div style={styles.historyContainer}>
            {groupedSessions.today.length > 0 && (
              <div style={styles.historyGroup}>
                <span style={styles.historyGroupTitle}>Today</span>
                {groupedSessions.today.map(renderSessionRow)}
              </div>
            )}
            {groupedSessions.yesterday.length > 0 && (
              <div style={styles.historyGroup}>
                <span style={styles.historyGroupTitle}>Yesterday</span>
                {groupedSessions.yesterday.map(renderSessionRow)}
              </div>
            )}
            {groupedSessions.older.length > 0 && (
              <div style={styles.historyGroup}>
                <span style={styles.historyGroupTitle}>Older</span>
                {groupedSessions.older.map(renderSessionRow)}
              </div>
            )}
            {sessions.length === 0 && (
              <div style={styles.emptyHistory}>No chat history yet.</div>
            )}
          </div>
        </div>

        {/* 3. Main Chat view panel */}
        <div style={styles.rightPanel}>
          <div style={styles.chatLog}>
            {!selectedDocId ? (
              <div style={styles.emptyChatState}>
                <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="var(--text-muted)" strokeWidth="2" style={{ marginBottom: 12 }}>
                  <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                </svg>
                <h3 style={{ fontSize: 15, fontWeight: 700, margin: "0 0 4px", color: "var(--text-secondary)" }}>No Active Context</h3>
                <p style={{ fontSize: 12, color: "var(--text-muted)", margin: 0, maxWidth: 280 }}>Please upload or open a document from the Dashboard home to start a consultation.</p>
              </div>
            ) : messages.length === 0 && !isTyping ? (
              <div style={styles.emptyChatState}>
                <svg width="38" height="38" viewBox="0 0 24 24" fill="none" stroke="var(--brand)" strokeWidth="2" style={{ marginBottom: 12 }}>
                  <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
                </svg>
                <h3 style={{ fontSize: 16, fontWeight: 700, margin: "0 0 4px", color: "var(--text-primary)" }}>Document Intelligence Assistant</h3>
                <p style={{ fontSize: 12.5, color: "var(--text-secondary)", margin: "0 0 24px", maxWidth: 420 }}>
                  Ask questions about the loaded document context. Answers are verified and grounded directly in the document layout structures.
                </p>

                {/* Suggested Questions Grid */}
                <div style={{ width: "100%", maxWidth: 480 }}>
                  <span style={{ fontSize: 10, fontWeight: 750, textTransform: "uppercase", color: "var(--text-secondary)", display: "block", marginBottom: 8, textAlign: "left", letterSpacing: 0.5 }}>Suggested Queries</span>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                    {suggestedQuestions.map((q, idx) => (
                      <button
                        key={idx}
                        onClick={() => handleSendMessage(q)}
                        style={styles.suggestedQuestionCard}
                        disabled={isTyping}
                      >
                        {q} &rarr;
                      </button>
                    ))}
                  </div>
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
                                    title="Open document page"
                                  >
                                    Page {page}
                                  </button>
                                ))}
                              </div>
                            </div>
                          )}

                          <div style={styles.msgMetadata}>
                            <button 
                              onClick={() => navigator.clipboard.writeText(msg.content)} 
                              style={styles.copyBtn} 
                              title="Copy response to clipboard"
                            >
                              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" style={{ marginRight: 4, display: "inline-block", verticalAlign: "middle" }}><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
                              Copy
                            </button>
                            <button 
                              onClick={() => handleRegenerate(idx)} 
                              style={{ ...styles.copyBtn, marginLeft: 8 }} 
                              title="Regenerate this response"
                              disabled={isTyping}
                            >
                              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" style={{ marginRight: 4, display: "inline-block", verticalAlign: "middle" }}><path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38" /></svg>
                              Regenerate
                            </button>
                          </div>

                          {/* Grounding Info metrics */}
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
                                      <span style={{ color: "var(--text-secondary)" }}>Heading: {cand.heading || "None"}</span>
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

          {error && (
            <div style={styles.errorBanner}>
              <span>{error}</span>
              <button onClick={() => handleSendMessage()} style={styles.retryBtn}>Retry</button>
            </div>
          )}

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
    height: "calc(100vh - 120px)",
    width: "100%",
    margin: "0 auto",
  },
  contextHeader: {
    background: "var(--bg-card)",
    border: "1px solid var(--border)",
    borderRadius: 8,
    padding: "10px 16px",
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    fontSize: 12,
    color: "var(--text-secondary)",
    marginBottom: 12,
    textAlign: "left",
  },
  workspace: {
    display: "flex",
    flex: 1,
    gap: 16,
    minHeight: 0,
  },
  leftPanel: {
    width: 260,
    display: "flex",
    flexDirection: "column",
    gap: 12,
    flexShrink: 0,
    overflowY: "auto",
  },
  newChatBtn: {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    width: "100%",
    padding: "9px",
    borderRadius: 8,
    border: "1px dashed var(--brand)",
    background: "transparent",
    color: "var(--brand)",
    fontSize: 12.5,
    fontWeight: 650,
    cursor: "pointer",
    transition: "all 0.15s ease",
  },
  historyContainer: {
    display: "flex",
    flexDirection: "column",
    gap: 16,
    flex: 1,
    minHeight: 0,
    overflowY: "auto",
  },
  historyGroup: { display: "flex", flexDirection: "column", gap: 3 },
  historyGroupTitle: {
    fontSize: 10,
    fontWeight: 750,
    textTransform: "uppercase",
    color: "var(--text-muted)",
    letterSpacing: 0.5,
    marginBottom: 4,
    textAlign: "left",
    paddingLeft: 4,
  },
  sessionRow: {
    display: "flex",
    alignItems: "center",
    padding: "8px 10px",
    borderRadius: 8,
    cursor: "pointer",
    fontSize: 12.5,
    textAlign: "left",
    position: "relative",
    transition: "all 0.15s",
    justifyContent: "space-between",
  },
  sessionTitleText: {
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
    flex: 1,
  },
  renameInput: {
    flex: 1,
    background: "var(--bg-page)",
    border: "1px solid var(--brand)",
    borderRadius: 4,
    fontSize: 12,
    color: "var(--text-primary)",
    padding: "1px 5px",
    outline: "none",
    width: "100%",
  },
  sessionActions: {
    display: "flex",
    gap: 6,
    alignItems: "center",
  },
  sessionRowBtn: {
    background: "none",
    border: "none",
    color: "var(--text-secondary)",
    cursor: "pointer",
    padding: 2,
    display: "flex",
    alignItems: "center",
    transition: "color 0.15s",
  },
  emptyHistory: {
    fontSize: 12,
    color: "var(--text-muted)",
    textAlign: "center",
    padding: 12,
  },
  rightPanel: {
    flex: 1,
    display: "flex",
    flexDirection: "column",
    border: "1px solid var(--border)",
    borderRadius: 12,
    background: "var(--bg-card)",
    overflow: "hidden",
    minHeight: 0,
  },
  card: {
    background: "var(--bg-card)",
    border: "1px solid var(--border)",
    borderRadius: 10,
    padding: 12,
    textAlign: "left",
  },
  select: {
    width: "100%",
    padding: "6px 8px",
    borderRadius: 6,
    border: "1px solid var(--border)",
    background: "var(--bg-page)",
    color: "var(--text-primary)",
    fontSize: 12.5,
    outline: "none",
  },
  debugToggleRow: {
    display: "flex",
    alignItems: "center",
    gap: 6,
    marginTop: 10,
    paddingTop: 8,
    borderTop: "1px dotted var(--border)",
  },
  checkbox: { cursor: "pointer" },
  debugLabel: {
    fontSize: 11.5,
    color: "var(--text-secondary)",
    fontWeight: 500,
    cursor: "pointer",
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
    maxWidth: 480,
    textAlign: "center",
    color: "var(--text-secondary)",
  },
  suggestedQuestionCard: {
    background: "var(--bg-page)",
    border: "1px solid var(--border)",
    borderRadius: 8,
    padding: "10px 12px",
    fontSize: 12,
    fontWeight: 550,
    color: "var(--text-primary)",
    cursor: "pointer",
    textAlign: "left",
    transition: "all 0.15s ease",
    outline: "none",
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
    padding: "12px 16px",
    borderRadius: 12,
    lineHeight: 1.5,
    fontSize: 13.5,
    textAlign: "left",
  },
  userBubble: {
    background: "var(--brand)",
    color: "#fff",
    borderRadius: "14px 14px 2px 14px",
  },
  assistantBubble: {
    background: "var(--bg-page)",
    color: "var(--text-primary)",
    borderRadius: "14px 14px 14px 2px",
    border: "1px solid var(--border)",
  },
  userText: { whiteSpace: "pre-wrap" },
  assistantBadge: {
    display: "inline-block",
    fontSize: 9.5,
    fontWeight: 700,
    color: "var(--brand)",
    background: "var(--brand-light)",
    padding: "2px 5px",
    borderRadius: 4,
    marginBottom: 6,
    textTransform: "uppercase",
  },
  assistantText: {
    fontSize: 13.5,
    color: "var(--text-primary)",
  },
  sourceFooter: {
    marginTop: 10,
    paddingTop: 8,
    borderTop: "1px dotted var(--border)",
  },
  sourceTitle: {
    fontSize: 10.5,
    fontWeight: 600,
    color: "var(--text-secondary)",
    marginBottom: 4,
  },
  pagePills: {
    display: "flex",
    flexWrap: "wrap",
    gap: 4,
  },
  pagePillBtn: {
    fontSize: 10,
    background: "var(--brand-light)",
    color: "var(--brand)",
    padding: "2px 6px",
    borderRadius: 4,
    fontWeight: 600,
    border: "none",
    cursor: "pointer",
  },
  msgMetadata: {
    marginTop: 8,
    fontSize: 10.5,
    color: "var(--text-muted)",
    display: "flex",
    alignItems: "center",
  },
  copyBtn: {
    background: "transparent",
    border: "none",
    color: "var(--brand)",
    fontSize: 10.5,
    cursor: "pointer",
    fontWeight: 650,
    display: "flex",
    alignItems: "center",
  },
  typingContainer: {
    display: "flex",
    alignItems: "center",
    gap: 4,
    padding: "4px 0",
  },
  debugPanel: {
    marginTop: 10,
    padding: "8px 10px",
    background: "var(--bg-page)",
    border: "1px solid var(--border)",
    borderRadius: 6,
    fontSize: 11,
  },
  debugHeader: {
    fontWeight: 700,
    color: "var(--text-primary)",
    textTransform: "uppercase",
    fontSize: 9,
    letterSpacing: "0.5px",
    marginBottom: 4,
    borderBottom: "1px solid var(--border)",
    paddingBottom: 2,
  },
  debugRow: {
    display: "flex",
    justifyContent: "space-between",
    marginBottom: 2,
  },
  debugCandidates: {
    marginTop: 6,
  },
  errorBanner: {
    padding: "8px 12px",
    background: "var(--red-light)",
    color: "var(--red)",
    borderTop: "1px solid rgba(225,85,85,0.15)",
    fontSize: 12,
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
  },
  retryBtn: {
    background: "var(--red)",
    color: "#fff",
    border: "none",
    borderRadius: 4,
    padding: "3px 8px",
    fontSize: 10.5,
    cursor: "pointer",
    fontWeight: 600,
  },
  inputBar: {
    display: "flex",
    padding: 12,
    borderTop: "1px solid var(--border)",
    gap: 8,
    alignItems: "center",
    background: "var(--bg-page)",
  },
  input: {
    flex: 1,
    padding: "10px 14px",
    borderRadius: 6,
    border: "1px solid var(--border)",
    outline: "none",
    fontSize: 13,
    background: "var(--bg-card)",
    color: "var(--text-primary)",
  },
  sendBtn: {
    padding: "10px 16px",
    borderRadius: 6,
    background: "var(--brand)",
    color: "#fff",
    border: "none",
    fontWeight: 600,
    fontSize: 12.5,
    cursor: "pointer",
  },
  clearBtn: {
    padding: "10px 14px",
    borderRadius: 6,
    background: "transparent",
    color: "var(--text-secondary)",
    border: "1px solid var(--border)",
    fontWeight: 500,
    fontSize: 12.5,
    cursor: "pointer",
  }
};
