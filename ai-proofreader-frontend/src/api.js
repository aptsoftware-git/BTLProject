const API_BASE = (import.meta.env && import.meta.env.VITE_API_BASE_URL) || "/api";

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

export function fetchJobStatus(id) {
  return request(`/jobs/${id}`);
}

export function retryJobStage(id, stageId = "all") {
  return request(`/jobs/${id}/retry?stage_id=${stageId}`, {
    method: "POST"
  });
}

export function deleteDocument(id) {
  return request(`/documents/${id}`, {
    method: "DELETE",
  });
}

export function uploadDocument(file, onProgress, xhrRef) {
  return new Promise((resolve, reject) => {
    if (!file) {
      const err = new Error("No file selected for upload.");
      if (import.meta.env?.DEV) console.error("[Upload] Error:", err);
      return reject(err);
    }

    const name = file.name || "";
    const ext = name.slice(name.lastIndexOf(".")).toLowerCase();
    const allowed = [".pdf", ".docx", ".txt"];
    if (!allowed.includes(ext)) {
      const err = new Error(`Unsupported file format "${ext}". Please upload a PDF, DOCX, or TXT document.`);
      if (import.meta.env?.DEV) console.error("[Upload] Error:", err);
      return reject(err);
    }

    const maxMB = 50;
    if (file.size > maxMB * 1024 * 1024) {
      const err = new Error(`File size exceeds maximum limit of ${maxMB}MB.`);
      if (import.meta.env?.DEV) console.error("[Upload] Error:", err);
      return reject(err);
    }

    const baseUrl = (import.meta.env && import.meta.env.VITE_API_BASE_URL) ? import.meta.env.VITE_API_BASE_URL.replace(/\/+$/, "") : "/api";
    const url = `${baseUrl}/documents/upload`;

    if (import.meta.env?.DEV) {
      console.debug("Uploading file:", file.name);
      console.debug("POST", url);
    }

    const xhr = new XMLHttpRequest();
    if (xhrRef) {
      xhrRef.current = xhr;
    }

    const formData = new FormData();
    formData.append("file", file);

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && typeof onProgress === "function") {
        const percent = Math.round((event.loaded / event.total) * 100);
        onProgress(percent);
      }
    };

    xhr.onload = () => {
      if (import.meta.env?.DEV) {
        console.debug("Upload response status:", xhr.status);
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          const responseJson = JSON.parse(xhr.responseText);
          if (import.meta.env?.DEV) {
            console.debug("Upload completed", responseJson);
          }
          resolve(responseJson);
        } catch (e) {
          reject(new Error("Invalid JSON response from server."));
        }
      } else {
        let errorMsg = `Upload failed with status ${xhr.status}`;
        try {
          const errData = JSON.parse(xhr.responseText);
          if (errData.detail) {
            errorMsg = typeof errData.detail === "string" ? errData.detail : JSON.stringify(errData.detail);
          }
        } catch (e) {
          if (xhr.responseText) errorMsg = xhr.responseText;
        }
        if (import.meta.env?.DEV) {
          console.error("Upload error:", errorMsg);
        }
        reject(new Error(errorMsg));
      }
    };

    xhr.onerror = () => {
      const err = new Error(`Network failure: Unable to connect to backend server at ${url}. Please check if the backend service is running.`);
      if (import.meta.env?.DEV) {
        console.error(err);
      }
      reject(err);
    };

    xhr.onabort = () => {
      const err = new Error("Upload cancelled by user.");
      if (import.meta.env?.DEV) {
        console.debug("Upload cancelled");
      }
      reject(err);
    };

    xhr.ontimeout = () => {
      const err = new Error("Upload timed out. Please try again.");
      if (import.meta.env?.DEV) {
        console.error(err);
      }
      reject(err);
    };

    xhr.open("POST", url, true);
    xhr.send(formData);
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

export async function exportCorrectedPdf(jobId, acceptedIssueIds = [], decisions = {}) {
  const url = `${API_BASE}/documents/${jobId}/export-pdf`;
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ accepted_issue_ids: acceptedIssueIds, decisions })
  });
  if (!response.ok) {
    throw new Error(`Failed to export PDF: ${response.statusText}`);
  }
  return response.blob();
}

export function rerunProofreading(jobId) {
  return request(`/documents/${jobId}/rerun-proofreading`, { method: "POST" });
}

export function validateJobOutputs(jobId) {
  return request(`/documents/${jobId}/validate-outputs`, { method: "GET" });
}

export function regenerateProofreadingReport(jobId) {
  return request(`/documents/${jobId}/regenerate-report`, { method: "POST" });
}

export function rerunStage(jobId, stageNumber) {
  return request(`/documents/${jobId}/rerun-stage?stage_number=${stageNumber}`, { method: "POST" });
}

export function rerunFromStage(jobId, stageNumber) {
  return request(`/documents/${jobId}/rerun-from-stage?stage_number=${stageNumber}`, { method: "POST" });
}

export function repairJob(jobId) {
  return request(`/documents/${jobId}/repair`, { method: "POST" });
}

export function resumeJob(jobId) {
  return request(`/jobs/${jobId}/resume`, { method: "POST" });
}

export function restartJob(jobId) {
  return request(`/jobs/${jobId}/restart`, { method: "POST" });
}

export function deleteJob(jobId) {
  return request(`/jobs/${jobId}`, { method: "DELETE" });
}

export function validateFinding(jobId, issueId) {
  return request(`/jobs/${jobId}/validate-finding/${issueId}`, { method: "GET" });
}

// ---------------------------------------------------------------------------
// Page + Sentence Mapping architecture
// ---------------------------------------------------------------------------

export function fetchPageCount(jobId) {
  return request(`/documents/${jobId}/page-count`);
}

export function fetchPageText(jobId, pageNumber) {
  return request(`/documents/${jobId}/pages/${pageNumber}`);
}

export function fetchSentenceMap(jobId) {
  return request(`/documents/${jobId}/sentence-map`);
}

export function fetchSentenceLookup(jobId) {
  return request(`/documents/${jobId}/sentence-lookup`);
}

export function fetchFindings(jobId) {
  return request(`/documents/${jobId}/findings`);
}

export function fetchDocumentImages(jobId) {
  return request(`/documents/${jobId}/images`);
}

export function updateFindingStatus(jobId, findingId, statusValue) {
  return request(`/documents/${jobId}/findings/${findingId}`, {
    method: "PATCH",
    body: JSON.stringify({ status: statusValue }),
  });
}

export function fetchCorrectedPreview(jobId) {
  return request(`/documents/${jobId}/corrected-preview`);
}

export async function exportCorrectedDocument(jobId, format = "pdf") {
  const url = `${API_BASE}/documents/${jobId}/export-corrected`;
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ format }),
  });
  if (!response.ok) {
    throw new Error(`Failed to export ${format.toUpperCase()}: ${response.statusText}`);
  }
  return response.blob();
}

export { API_BASE as API_BASE_URL };
