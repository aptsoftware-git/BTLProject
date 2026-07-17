// Central place for every call to the backend (app.py / routes.py).
// In dev, Vite proxies "/api" to http://localhost:8000 (see vite.config.js).
// In production, set VITE_API_BASE_URL to your deployed backend URL.

const BASE_URL = import.meta.env.VITE_API_BASE_URL || "/api";

async function request(path, options = {}) {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: options.body instanceof FormData ? {} : { "Content-Type": "application/json" },
    ...options,
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  return res.json();
}

// GET /api/documents -> list of recent documents + summary stats.
// Adjust the path to whatever routes.py actually exposes.
export function fetchDocuments() {
  return request("/documents");
}

// GET /api/stats -> { totalDocuments, grammarAccuracy, issuesResolvedToday, documentsToday }
export function fetchStats() {
  return request("/stats");
}

// GET /api/system-status -> [{ name, online }]
export function fetchSystemStatus() {
  return request("/system-status");
}

// POST /api/documents (multipart) -> kicks off a proofreading job.
export function uploadDocument(file, onProgress, xhrRef) {
  const formData = new FormData();
  formData.append("file", file);

  // Using XHR instead of fetch here so we can report upload progress,
  // which fetch doesn't support natively.
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    if (xhrRef) {
      xhrRef.current = xhr;
    }
    xhr.open("POST", `${BASE_URL}/documents`);
    xhr.upload.onprogress = (e) => {
      if (onProgress && e.lengthComputable) {
        onProgress(Math.round((e.loaded / e.total) * 100));
      }
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(JSON.parse(xhr.responseText));
      } else {
        reject(new Error(`Upload failed: ${xhr.status}`));
      }
    };
    xhr.onerror = () => reject(new Error("Upload failed: network error"));
    xhr.onabort = () => reject(new Error("Upload cancelled by user"));
    xhr.send(formData);
  });
}

// GET /api/documents/:id -> full proofreading result for the workspace page.
export function fetchDocument(id) {
  return request(`/documents/${id}`);
}

// DELETE /api/documents/:id -> delete a document and its data
export function deleteDocument(id) {
  return request(`/documents/${id}`, { method: "DELETE" });
}

// GET /api/notifications -> list of notifications
export function fetchNotifications() {
  return request("/notifications");
}

// GET /api/settings/protected-terms -> list of whitelisted terms
export function fetchProtectedTerms() {
  return request("/settings/protected-terms");
}

// POST /api/settings/protected-terms -> updates whitelisted terms
export function saveProtectedTerms(terms) {
  return request("/settings/protected-terms", {
    method: "POST",
    body: JSON.stringify({ terms }),
  });
}

// GET /api/settings/preferences -> user preferences
export function fetchPreferences() {
  return request("/settings/preferences");
}

// POST /api/settings/preferences -> updates preferences
export function savePreferences(preferences) {
  return request("/settings/preferences", {
    method: "POST",
    body: JSON.stringify({ preferences }),
  });
}

// GET /api/settings/system-info -> system info
export function fetchSystemInfo() {
  return request("/settings/system-info");
}

// Phase 6: RAG API methods
export function fetchRagModels() {
  return request("/rag/models");
}

export function sendRagMessage(documentId, question, selectedModel, historyDepth = 5) {
  return request("/rag/chat", {
    method: "POST",
    body: JSON.stringify({
      document_id: documentId,
      question: question,
      selected_model: selectedModel,
      conversation_history_depth: historyDepth
    })
  });
}

export function fetchRagHistory(documentId) {
  return request(`/rag/history/${documentId}`);
}

export function clearRagHistory(documentId) {
  return request(`/rag/history/${documentId}`, {
    method: "DELETE"
  });
}

export function triggerRagIndex(documentId) {
  return request("/rag/index", {
    method: "POST",
    body: JSON.stringify({ document_id: documentId })
  });
}

export function fetchRagStats(documentId) {
  return request(`/rag/stats/${documentId}`);
}

export function fetchContextAnalysisReport(jobId) {
  return request(`/context-analysis/report/${jobId}`);
}

export function runContextAnalysis(jobId) {
  return request(`/context-analysis/run/${jobId}`, {
    method: "POST"
  });
}

export const API_BASE_URL = BASE_URL;





