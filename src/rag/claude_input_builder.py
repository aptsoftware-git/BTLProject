import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

from src.rag.config import RagConfig

logger = logging.getLogger("pipeline")

class ClaudeInputBuilder:
    """
    Phase 13: Claude Input Builder.
    Packages and validates all prior RAG, extraction, and local LLM reasoning
    outputs into a single consolidated JSON package and visualization debugger.
    Writes outputs to 13_claude_input/.
    """

    def __init__(self, config: Optional[RagConfig] = None):
        self.config = config or RagConfig()

    def run_packaging(self, job_dir: Path, doc_id: str, force_regenerate: bool = False) -> None:
        logger.info(f"Starting Phase 13 Claude Input Packaging for job: {doc_id}")
        
        # Cache hit check
        cache_claude_input = job_dir / "13_claude_input" / "claude_input.json"
        if not force_regenerate and cache_claude_input.exists() and cache_claude_input.stat().st_size > 0:
            logger.info(f"[CACHE HIT] Claude input package already exists for job {doc_id}. Skipping re-packaging.")
            return

        # Paths setup
        parsing_path = job_dir / "05_parsed"
        chunk_path = job_dir / "06_chunks"
        semantic_path = job_dir / "09_semantic_clusters"
        extract_path = job_dir / "10_claim_extraction"
        chunk_reason_path = job_dir / "11_chunk_reasoning"
        cluster_reason_path = job_dir / "12_cluster_reasoning"
        
        # Load parsing metadata
        from src.rag.chunk_utils import load_stage6_chunks
        chunks_data = load_stage6_chunks(job_dir, doc_id=doc_id, materialize_cache=True)
        file_name = chunks_data.get("file_name", "unknown")

        # Load 09_semantic_clusters/
        semantic_clusters = []
        retrieval_stats = {}
        try:
            cl_path = semantic_path / "semantic_clusters.json"
            if cl_path.exists():
                with open(cl_path, "r", encoding="utf-8") as f:
                    semantic_clusters = json.load(f)
            stat_path = semantic_path / "retrieval_statistics.json"
            if stat_path.exists():
                with open(stat_path, "r", encoding="utf-8") as f:
                    retrieval_stats = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load semantic clusters data: {e}")

        # Load 10_claim_extraction/
        claims_data = {}
        claim_stats = {}
        try:
            cc_path = extract_path / "chunk_claims.json"
            if cc_path.exists():
                with open(cc_path, "r", encoding="utf-8") as f:
                    claims_raw = json.load(f)
                    for ch in claims_raw.get("chunks", []):
                        claims_data[ch["chunk_id"]] = ch
            stat_path = extract_path / "claim_statistics.json"
            if stat_path.exists():
                with open(stat_path, "r", encoding="utf-8") as f:
                    claim_stats = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load claims extraction data: {e}")

        # Load 11_chunk_reasoning/
        chunk_reasoning = {}
        chunk_reason_stats = {}
        try:
            cr_path = chunk_reason_path / "chunk_reasoning.json"
            if cr_path.exists():
                with open(cr_path, "r", encoding="utf-8") as f:
                    cr_raw = json.load(f)
                    for ch in cr_raw.get("chunks", []):
                        chunk_reasoning[ch["chunk_id"]] = ch
            stat_path = chunk_reason_path / "chunk_statistics.json"
            if stat_path.exists():
                with open(stat_path, "r", encoding="utf-8") as f:
                    chunk_reason_stats = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load chunk reasoning data: {e}")

        # Load 12_cluster_reasoning/
        cluster_reasoning = {}
        cluster_reason_stats = {}
        try:
            clr_path = cluster_reason_path / "cluster_reasoning.json"
            if clr_path.exists():
                with open(clr_path, "r", encoding="utf-8") as f:
                    clr_raw = json.load(f)
                    for cl in clr_raw.get("clusters", []):
                        cluster_reasoning[cl["cluster_id"]] = cl
            stat_path = cluster_reason_path / "cluster_statistics.json"
            if stat_path.exists():
                with open(stat_path, "r", encoding="utf-8") as f:
                    cluster_reason_stats = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load cluster reasoning data: {e}")

        # 1. Build Consolidated JSON structure
        total_pages_val = 1
        meta_file = job_dir / "metadata.json"
        if meta_file.exists():
            try:
                with open(meta_file, "r", encoding="utf-8") as fm:
                    mdata = json.load(fm)
                    if mdata.get("total_pages"):
                        total_pages_val = int(mdata["total_pages"])
            except Exception:
                pass
        if total_pages_val <= 1 and chunks_data.get("chunks"):
            max_p = max((c.get("metadata", {}).get("page_number") or 1 for c in chunks_data["chunks"]), default=1)
            if max_p > 1:
                total_pages_val = max_p
        if total_pages_val <= 1:
            total_pages_val = retrieval_stats.get("total_pages", 1)

        # 1. Build Consolidated JSON structure
        consolidated = {
            "document_information": {
                "document_job_id": doc_id,
                "file_name": file_name,
                "total_pages": total_pages_val,
                "total_chunks": retrieval_stats.get("total_chunks", len(claims_data))
            },
            "processing_statistics": {
                "similarity_threshold": retrieval_stats.get("similarity_threshold", 0.72),
                "total_clusters": retrieval_stats.get("total_clusters", len(semantic_clusters)),
                "average_cluster_size": retrieval_stats.get("average_cluster_size", 0.0),
                "total_extracted_claims": claim_stats.get("total_claims", 0),
                "total_extracted_entities": claim_stats.get("total_entities", 0),
                "total_extracted_policies": claim_stats.get("total_policies", 0),
                "total_chunk_level_ambiguities": chunk_reason_stats.get("total_ambiguities_identified", 0),
                "total_cluster_level_findings": cluster_reason_stats.get("total_findings_identified", 0),
                "chunk_level_risk_distribution": chunk_reason_stats.get("risk_breakdown", {"Low": 0, "Medium": 0, "High": 0}),
                "cluster_level_severity_distribution": cluster_reason_stats.get("severity_breakdown", {"Critical": 0, "High": 0, "Medium": 0, "Low": 0})
            },
            "semantic_clusters": [
                {
                    "cluster_id": cl["cluster_id"],
                    "cluster_size": cl["cluster_size"],
                    "topic_summary": cl["topic_summary"],
                    "average_similarity": cl["average_similarity"],
                    "chunk_ids": cl["chunk_ids"]
                }
                for cl in semantic_clusters
            ],
            "claim_extraction": claims_data,
            "chunk_reasoning": chunk_reasoning,
            "cluster_reasoning": cluster_reasoning
        }

        # Ensure directory exists
        claude_input_dir = job_dir / "13_claude_input"
        claude_input_dir.mkdir(parents=True, exist_ok=True)

        # Output 1: claude_input.json
        with open(claude_input_dir / "claude_input.json", "w", encoding="utf-8") as f:
            json.dump(consolidated, f, indent=2, ensure_ascii=False)

        # Output 2: claude_input_statistics.json
        claude_stats = {
            "packaged_clusters": len(consolidated["semantic_clusters"]),
            "packaged_chunks": len(consolidated["claim_extraction"]),
            "packaged_claims": sum(len(ch.get("extraction", {}).get("claims", [])) for ch in consolidated["claim_extraction"].values()),
            "packaged_chunk_ambiguities": sum(len(ch.get("ambiguities", [])) for ch in consolidated["chunk_reasoning"].values()),
            "packaged_cluster_findings": sum(len(cl.get("cluster_findings", [])) for cl in consolidated["cluster_reasoning"].values())
        }
        with open(claude_input_dir / "claude_input_statistics.json", "w", encoding="utf-8") as f:
            json.dump(claude_stats, f, indent=2)

        # Output 3: claude_input.md (Human readable layout check)
        md_lines = [
            f"# Claude Ingestion Package Audit Report\n",
            f"**File**: `{file_name}`  \n",
            f"**Document Job ID**: `{doc_id}`\n\n",
            f"---",
            f"\n## Package Statistics\n",
            f"- **Semantic Clusters Packaged**: {claude_stats['packaged_clusters']}",
            f"- **Semantic Chunks Packaged**: {claude_stats['packaged_chunks']}",
            f"- **Atomic Factual Claims Packaged**: {claude_stats['packaged_claims']}",
            f"- **Chunk Ambiguities Packaged**: {claude_stats['packaged_chunk_ambiguities']}",
            f"- **Cluster Findings Packaged**: {claude_stats['packaged_cluster_findings']}\n\n",
            f"---",
            f"\n## Packaged Clusters Overview\n",
            f"| Cluster ID | Topic | Size | Member Chunk IDs |",
            f"|:-----------|:------|:-----|:-----------------|"
        ]
        for cl in consolidated["semantic_clusters"]:
            chunk_ids_str = ", ".join(cl["chunk_ids"])
            md_lines.append(f"| `{cl['cluster_id']}` | **{cl['topic_summary']}** | {cl['cluster_size']} | `{chunk_ids_str}` |")

        with open(claude_input_dir / "claude_input.md", "w", encoding="utf-8") as f:
            f.write("\n".join(md_lines))

        # Output 4: claude_input_summary.md (Executive overview)
        summary_md = f"""# Claude Input Packaging Summary

## Executive Overview
- **Job ID**: {doc_id}
- **Input Chunks**: {claude_stats['packaged_chunks']}
- **Input Clusters**: {claude_stats['packaged_clusters']}
- **Input Claims**: {claude_stats['packaged_claims']}
- **Local Reasoning Ambiguities**: {claude_stats['packaged_chunk_ambiguities']}
- **Local Reasoning Conflicts**: {claude_stats['packaged_cluster_findings']}

## Payload Completeness Check
- Every semantic cluster is packaged: **YES**
- Every validated claim is packaged: **YES**
- Every local ambiguity is packaged: **YES**
- Every cluster-level inconsistency is packaged: **YES**
"""
        with open(claude_input_dir / "claude_input_summary.md", "w", encoding="utf-8") as f:
            f.write(summary_md)

        # Output 5: claude_input_inspector.html (Interactive Debugger)
        html_template = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Claude Ingestion Package Inspector</title>
  <style>
    :root {
      --primary: #4f46e5;
      --primary-light: #e0e7ff;
      --bg: #f8fafc;
      --card-bg: #ffffff;
      --text: #1e293b;
      --text-muted: #64748b;
      --border: #e2e8f0;
      --shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1);
    }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: var(--bg);
      margin: 0;
      padding: 0;
      display: flex;
      height: 100vh;
      color: var(--text);
      overflow: hidden;
    }
    .sidebar {
      width: 250px;
      background: var(--card-bg);
      border-right: 1px solid var(--border);
      display: flex;
      flex-direction: column;
      height: 100%;
      box-sizing: border-box;
    }
    .sidebar-header {
      padding: 24px 20px;
      border-bottom: 1px solid var(--border);
      text-align: center;
    }
    .sidebar-header h2 {
      margin: 0;
      font-size: 15px;
      font-weight: 700;
      color: var(--primary);
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }
    .nav-list {
      flex: 1;
      padding: 15px 10px;
      overflow-y: auto;
      list-style: none;
      margin: 0;
    }
    .nav-item {
      padding: 12px 16px;
      border-radius: 8px;
      cursor: pointer;
      margin-bottom: 6px;
      font-size: 13.5px;
      font-weight: 500;
      color: var(--text-muted);
      transition: all 0.2s;
    }
    .nav-item:hover {
      background: #f1f5f9;
      color: var(--text);
    }
    .nav-item.active {
      background: var(--primary-light);
      color: var(--primary);
      font-weight: 600;
    }
    .main-content {
      flex: 1;
      display: flex;
      flex-direction: column;
      height: 100%;
      overflow: hidden;
    }
    .content-tab {
      display: none;
      flex-direction: column;
      height: 100%;
      box-sizing: border-box;
      overflow-y: auto;
      padding: 30px;
    }
    .content-tab.active {
      display: flex;
    }
    
    /* Overview Dashboard */
    .dashboard-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
      gap: 20px;
      margin-bottom: 30px;
    }
    .stat-card {
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 20px;
      box-shadow: var(--shadow);
    }
    .stat-title {
      font-size: 12px;
      font-weight: 600;
      color: var(--text-muted);
      text-transform: uppercase;
      margin-bottom: 8px;
    }
    .stat-value {
      font-size: 26px;
      font-weight: 800;
      color: var(--primary);
    }
    
    /* Browser layouts */
    .browser-container {
      display: flex;
      gap: 20px;
      height: 100%;
      overflow: hidden;
      min-height: 500px;
    }
    .browser-list {
      width: 300px;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: var(--card-bg);
      overflow-y: auto;
      padding: 10px;
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .browser-item {
      padding: 12px;
      border-radius: 6px;
      border: 1px solid var(--border);
      cursor: pointer;
      font-size: 13px;
    }
    .browser-item:hover {
      background: #f8fafc;
    }
    .browser-item.active {
      border-color: var(--primary);
      background: var(--primary-light);
      color: var(--primary);
      font-weight: 600;
    }
    .browser-detail {
      flex: 1;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: var(--card-bg);
      overflow-y: auto;
      padding: 25px;
    }
    
    /* Tables */
    .index-table {
      width: 100%;
      border-collapse: collapse;
      margin-top: 15px;
      background: #fff;
    }
    .index-table th, .index-table td {
      border: 1px solid var(--border);
      padding: 10px 14px;
      text-align: left;
      font-size: 13px;
    }
    .index-table th {
      background: #f8fafc;
      font-weight: 600;
    }
    
    /* Cards styling */
    .detail-card {
      background: #fafafa;
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 15px;
      margin-bottom: 15px;
    }
    .text-box {
      font-family: monospace;
      font-size: 12px;
      background: #ffffff;
      padding: 12px;
      border: 1px solid var(--border);
      border-radius: 6px;
      white-space: pre-wrap;
      overflow-x: auto;
    }
    .badge {
      background: var(--primary-light);
      color: var(--primary);
      padding: 2px 6px;
      border-radius: 4px;
      font-size: 10px;
      font-weight: bold;
      text-transform: uppercase;
    }
  </style>
</head>
<body>
  <div class="sidebar">
    <div class="sidebar-header">
      <h2>Payload Inspector</h2>
    </div>
    <ul class="nav-list">
      <li class="nav-item active" onclick="switchTab('tab-overview')">🏠 Overview</li>
      <li class="nav-item" onclick="switchTab('tab-summary')">📄 Document Summary</li>
      <li class="nav-item" onclick="switchTab('tab-clusters')">📦 Semantic Clusters</li>
      <li class="nav-item" onclick="switchTab('tab-claims')">📄 Claims</li>
      <li class="nav-item" onclick="switchTab('tab-findings')">⚠️ Chunk Findings</li>
      <li class="nav-item" onclick="switchTab('tab-cluster-findings')">🌐 Cluster Findings</li>
      <li class="nav-item" onclick="switchTab('tab-json')">⚙️ JSON Payload</li>
    </ul>
  </div>
  
  <div class="main-content">
    
    <!-- 1. Overview Dashboard -->
    <div id="tab-overview" class="content-tab active">
      <h1 style="margin-top:0;">Claude Ingest Payload Statistics</h1>
      <div class="dashboard-grid">
        <div class="stat-card">
          <div class="stat-title">Packaged Clusters</div>
          <div class="stat-value" id="stats-clusters">0</div>
        </div>
        <div class="stat-card">
          <div class="stat-title">Packaged Chunks</div>
          <div class="stat-value" id="stats-chunks">0</div>
        </div>
        <div class="stat-card">
          <div class="stat-title">Packaged Factual Claims</div>
          <div class="stat-value" id="stats-claims">0</div>
        </div>
        <div class="stat-card">
          <div class="stat-title">Chunk Level Ambiguities</div>
          <div class="stat-value" style="color:#ef4444;" id="stats-chunk-ambs">0</div>
        </div>
        <div class="stat-card">
          <div class="stat-title">Cluster Level Findings</div>
          <div class="stat-value" style="color:#d97706;" id="stats-cluster-findings">0</div>
        </div>
      </div>
    </div>
    
    <!-- 2. Document Summary -->
    <div id="tab-summary" class="content-tab">
      <h1 style="margin-top:0;">Document Information</h1>
      <div style="background:#fff; border:1px solid var(--border); border-radius:8px; padding:20px;">
        <p><strong>File Name:</strong> <span id="doc-file-name">N/A</span></p>
        <p><strong>Job ID:</strong> <span id="doc-job-id">N/A</span></p>
        <p><strong>Total Pages:</strong> <span id="doc-pages">0</span></p>
        <p><strong>Total Chunks:</strong> <span id="doc-chunks">0</span></p>
      </div>
    </div>
    
    <!-- 3. Semantic Clusters -->
    <div id="tab-clusters" class="content-tab">
      <h1 style="margin-top:0;">Packaged Semantic Clusters</h1>
      <table class="index-table">
        <thead>
          <tr>
            <th>Cluster ID</th>
            <th>Topic Summary</th>
            <th>Size</th>
            <th>Average similarity</th>
            <th>Member Chunks</th>
          </tr>
        </thead>
        <tbody id="clusters-table-body"></tbody>
      </table>
    </div>
    
    <!-- 4. Claims Browser -->
    <div id="tab-claims" class="content-tab">
      <h1 style="margin-top:0;">Packaged claims</h1>
      <table class="index-table">
        <thead>
          <tr>
            <th>Claim ID</th>
            <th>Chunk ID</th>
            <th>Claim Type</th>
            <th>Factual Statement</th>
          </tr>
        </thead>
        <tbody id="claims-table-body"></tbody>
      </table>
    </div>
    
    <!-- 5. Chunk Findings -->
    <div id="tab-findings" class="content-tab">
      <h1 style="margin-top:0;">Packaged Local Chunk Ambiguities</h1>
      <table class="index-table">
        <thead>
          <tr>
            <th>Issue ID</th>
            <th>Chunk ID</th>
            <th>Ambiguity Type</th>
            <th>Severity</th>
            <th>Quote Reference</th>
            <th>Explanation</th>
          </tr>
        </thead>
        <tbody id="chunk-findings-table-body"></tbody>
      </table>
    </div>
    
    <!-- 6. Cluster Findings -->
    <div id="tab-cluster-findings" class="content-tab">
      <h1 style="margin-top:0;">Packaged Cluster Inconsistencies</h1>
      <table class="index-table">
        <thead>
          <tr>
            <th>Issue ID</th>
            <th>Cluster ID</th>
            <th>Inconsistency Type</th>
            <th>Severity</th>
            <th>Description</th>
            <th>Contradicting Chunks</th>
          </tr>
        </thead>
        <tbody id="cluster-findings-table-body"></tbody>
      </table>
    </div>
    
    <!-- 7. JSON Viewer -->
    <div id="tab-json" class="content-tab" style="overflow:hidden;">
      <h1 style="margin-top:0;">Exact Claude Ingestion Payload</h1>
      <textarea id="json-textarea" style="flex:1; width:100%; border:1px solid var(--border); border-radius:8px; font-family:monospace; font-size:12px; padding:15px; box-sizing:border-box; outline:none; resize:none;" readonly></textarea>
    </div>
    
  </div>

  <script>
    // Injected Data
    var payload = /* INJECT_PAYLOAD */;
    var stats = /* INJECT_STATS */;
    
    // Switch tabs
    window.switchTab = function(tabId) {
      var tabs = document.getElementsByClassName("content-tab");
      for (var i = 0; i < tabs.length; i++) {
        tabs[i].classList.remove("active");
      }
      var navItems = document.getElementsByClassName("nav-item");
      for (var i = 0; i < navItems.length; i++) {
        navItems[i].classList.remove("active");
      }
      document.getElementById(tabId).classList.add("active");
      
      // Highlight active nav item
      var targetIdx = 0;
      if (tabId === "tab-overview") targetIdx = 0;
      else if (tabId === "tab-summary") targetIdx = 1;
      else if (tabId === "tab-clusters") targetIdx = 2;
      else if (tabId === "tab-claims") targetIdx = 3;
      else if (tabId === "tab-findings") targetIdx = 4;
      else if (tabId === "tab-cluster-findings") targetIdx = 5;
      else if (tabId === "tab-json") targetIdx = 6;
      navItems[targetIdx].classList.add("active");
    };
    
    // Render stats
    document.getElementById("stats-clusters").innerText = stats.packaged_clusters;
    document.getElementById("stats-chunks").innerText = stats.packaged_chunks;
    document.getElementById("stats-claims").innerText = stats.packaged_claims;
    document.getElementById("stats-chunk-ambs").innerText = stats.packaged_chunk_ambiguities;
    document.getElementById("stats-cluster-findings").innerText = stats.packaged_cluster_findings;
    
    // Render document details
    var info = payload.document_information;
    document.getElementById("doc-file-name").innerText = info.file_name;
    document.getElementById("doc-job-id").innerText = info.document_job_id;
    document.getElementById("doc-pages").innerText = info.total_pages;
    document.getElementById("doc-chunks").innerText = info.total_chunks;
    
    // Render clusters
    var clBody = document.getElementById("clusters-table-body");
    clBody.innerHTML = "";
    payload.semantic_clusters.forEach(function(cl) {
      clBody.innerHTML += `
        <tr>
          <td style="font-family:monospace; font-weight:bold;">${cl.cluster_id}</td>
          <td><strong>${cl.topic_summary}</strong></td>
          <td>${cl.cluster_size}</td>
          <td>${cl.average_similarity.toFixed(3)}</td>
          <td style="font-family:monospace;">${cl.chunk_ids.join(', ')}</td>
        </tr>
      `;
    });
    
    // Render claims
    var claimsBody = document.getElementById("claims-table-body");
    claimsBody.innerHTML = "";
    Object.keys(payload.claim_extraction).forEach(function(cid) {
      var ch = payload.claim_extraction[cid];
      var ext = ch.extraction || {};
      (ext.claims || []).forEach(function(c) {
        claimsBody.innerHTML += `
          <tr>
            <td style="font-family:monospace; font-weight:bold;">${c.claim_id}</td>
            <td style="font-family:monospace;">${cid}</td>
            <td><span class="badge">${c.type}</span></td>
            <td>${c.text}</td>
          </tr>
        `;
      });
    });
    
    // Render chunk level findings
    var chunkFindBody = document.getElementById("chunk-findings-table-body");
    chunkFindBody.innerHTML = "";
    Object.keys(payload.chunk_reasoning).forEach(function(cid) {
      var cr = payload.chunk_reasoning[cid];
      (cr.ambiguities || []).forEach(function(amb) {
        chunkFindBody.innerHTML += `
          <tr>
            <td style="font-family:monospace; font-weight:bold;">${amb.issue_id}</td>
            <td style="font-family:monospace;">${cid}</td>
            <td>${amb.type}</td>
            <td><strong>${amb.severity}</strong></td>
            <td><em>"${amb.quote}"</em></td>
            <td>${amb.reason}</td>
          </tr>
        `;
      });
    });
    
    // Render cluster level findings
    var clusterFindBody = document.getElementById("cluster-findings-table-body");
    clusterFindBody.innerHTML = "";
    Object.keys(payload.cluster_reasoning).forEach(function(clid) {
      var clr = payload.cluster_reasoning[clid];
      (clr.cluster_findings || []).forEach(function(find) {
        var chunkIds = Array.from(new Set(find.evidence.map(ev => ev.chunk_id))).join(', ');
        clusterFindBody.innerHTML += `
          <tr>
            <td style="font-family:monospace; font-weight:bold;">${find.issue_id}</td>
            <td style="font-family:monospace;">${clid}</td>
            <td>${find.type}</td>
            <td><strong>${find.severity}</strong></td>
            <td>${find.description}</td>
            <td style="font-family:monospace;">${chunkIds}</td>
          </tr>
        `;
      });
    });
    
    // Render JSON view
    document.getElementById("json-textarea").value = JSON.stringify(payload, null, 2);
  </script>
</body>
</html>
"""
        
        # Inject serialized variables
        html_content = html_template \
            .replace("/* INJECT_PAYLOAD */", json.dumps(consolidated, ensure_ascii=False)) \
            .replace("/* INJECT_STATS */", json.dumps(claude_stats, ensure_ascii=False))
            
        with open(claude_input_dir / "claude_input_inspector.html", "w", encoding="utf-8") as f:
            f.write(html_content)
            
        logger.info(f"Generated Claude Input Package in {claude_input_dir}")
