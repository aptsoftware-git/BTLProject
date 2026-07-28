const API_BASE = "http://localhost:8000/api";

async function request(endpoint, options = {}) {
  const url = `${API_BASE}${endpoint}`;
  const response = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
    ...options,
  });

  if (!response.ok) {
    const errorBody = await response.text();
    let errorMessage = `HTTP ${response.status} ${response.statusText}`;
    try {
      const parsed = JSON.parse(errorBody);
      if (parsed.detail) {
        errorMessage = typeof parsed.detail === "string" ? parsed.detail : JSON.stringify(parsed.detail);
      }
    } catch (e) {
      if (errorBody) errorMessage = errorBody;
    }
    throw new Error(errorMessage);
  }

  return response.json();
}

export function fetchDocuments() {
  return request("/documents");
}

export function fetchDocument(id) {
  return request(`/documents/${id}`);
}

export function deleteDocument(id) {
  return request(`/documents/${id}`, {
    method: "DELETE",
  });
}

export function uploadDocument(file) {
  const formData = new FormData();
  formData.append("file", file);
  return fetch(`${API_BASE}/documents/upload`, {
    method: "POST",
    body: formData,
  }).then(async (res) => {
    if (!res.ok) {
      const txt = await res.text();
      throw new Error(txt || `Upload failed with status ${res.status}`);
    }
    return res.json();
  });
}

export function fetchProofreadIssues(id) {
  return request(`/documents/${id}/issues`);
}

export function updateIssueStatus(id, issueId, status) {
  return request(`/documents/${id}/issues/${issueId}`, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });
}

export function fetchStats() {
  return request("/stats");
}

export function exportDocument(id, format) {
  return fetch(`${API_BASE}/documents/${id}/export?format=${format}`, {
    method: "GET",
  }).then(async (res) => {
    if (!res.ok) {
      throw new Error(`Export failed with status ${res.status}`);
    }
    return res.blob();
  });
}

export function fetchNotifications() {
  return request("/notifications").catch(() => [
    { id: 1, title: "System Ready", time: "Just now", read: false }
  ]);
}

export function fetchProtectedTerms() {
  return request("/settings/protected-terms").catch(() => []);
}

export function saveProtectedTerms(terms) {
  return request("/settings/protected-terms", {
    method: "POST",
    body: JSON.stringify({ terms })
  });
}

export function fetchPreferences() {
  return request("/settings/preferences").catch(() => ({
    auto_save: true,
    dark_mode: true,
    ollama_host: "",
    ollama_model: "",
    languagetool_language: "en-US",
    confidence_threshold: 40
  }));
}

export function savePreferences(preferences) {
  return request("/settings/preferences", {
    method: "POST",
    body: JSON.stringify(preferences)
  });
}

export function fetchSystemInfo() {
  return request("/settings/system-info");
}

export function fetchSystemStatus() {
  return fetchSystemInfo();
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

// Dedicated Backend Reports Endpoints
export function fetchFinalReport(jobId) {
  return request(`/reports/${jobId}/final-report`);
}

export function fetchClaudeVerificationReport(jobId) {
  return request(`/reports/${jobId}/claude-verification`);
}

export function fetchChunkReasoningReport(jobId) {
  return request(`/reports/${jobId}/chunk-reasoning`);
}

export function fetchClusterReasoningReport(jobId) {
  return request(`/reports/${jobId}/cluster-reasoning`);
}

// Comparative Analysis REST Endpoints
export function fetchComparativeAnalysis(jobId) {
  return request(`/reports/${jobId}/comparative-analysis`);
}

export function fetchCompanyProfile(jobId) {
  return request(`/reports/${jobId}/company-profile`);
}

export function fetchCompetitorProfiles(jobId) {
  return request(`/reports/${jobId}/competitor-profiles`);
}

export function fetchComparisonMatrix(jobId) {
  return request(`/reports/${jobId}/comparison-matrix`);
}

export function fetchSwotAnalysis(jobId) {
  return request(`/reports/${jobId}/swot`);
}

export function fetchRecommendations(jobId) {
  return request(`/reports/${jobId}/recommendations`);
}

export { API_BASE as API_BASE_URL };
