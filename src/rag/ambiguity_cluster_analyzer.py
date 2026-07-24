import re
import json
import logging
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
from collections import Counter

from src.rag.config import RagConfig
from src.rag.ollama_client import OllamaClient

logger = logging.getLogger("pipeline")

class AmbiguityClusterAnalyzer:
    """
    Phase 3: Local LLM Cluster-Level Ambiguity Analyzer.
    Analyzes semantic clusters and compares member chunks to identify
    cross-chunk contradictions, terminology updates, policy inconsistencies,
    and missing prerequisite context within each individual community.
    Writes outputs to 12_cluster_reasoning/.
    """

    def __init__(self, config: Optional[RagConfig] = None):
        self.config = config or RagConfig()
        self.model_name = getattr(self.config, "ollama_model", os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:32b"))
        
        # Resolve host from config
        ollama_host = "http://192.168.19.21:11434"
        if hasattr(self.config, "ollama_host"):
            ollama_host = self.config.ollama_host
        elif hasattr(self.config, "ollama") and isinstance(self.config.ollama, dict):
            ollama_host = self.config.ollama.get("host", ollama_host)
            
        self.ollama_client = OllamaClient(host=ollama_host)

    def _clean_and_parse_json(self, text: str) -> dict:
        """Helper to extract json block from LLM response."""
        text = text.strip()
        pattern = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)
        match = pattern.search(text)
        if match:
            json_str = match.group(1).strip()
        else:
            json_str = text
            
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            start = json_str.find('{')
            end = json_str.rfind('}')
            if start != -1 and end != -1:
                try:
                    return json.loads(json_str[start:end+1])
                except Exception:
                    pass
            raise

    def _analyze_fallback_cluster(self, cluster_id: str, topic: str, member_chunks: List[dict]) -> dict:
        """Rule-based fallback cluster analyzer when Ollama is offline."""
        findings = []
        issue_idx = 0
        
        # 1. Terminology inconsistency checks across chunks
        terms_by_root = {
            "library": ["library", "libary", "libaries", "libarys"],
            "environment": ["environment", "enviroment"],
            "librarian": ["librarian", "librerian"],
            "information": ["information", "informations"]
        }
        for root, variations in terms_by_root.items():
            found_vars = {}
            for ch in member_chunks:
                cid = ch["chunk_id"]
                text = ch["text"]
                for v in variations:
                    if re.search(rf"\b{v}\b", text, re.IGNORECASE):
                        found_vars[cid] = v
                        break
            if len(found_vars) > 1:
                distinct_vars = set(found_vars.values())
                if len(distinct_vars) > 1:
                    evidence = []
                    for cid, var in found_vars.items():
                        evidence.append({
                            "chunk_id": cid,
                            "quote": var
                        })
                    
                    findings.append({
                        "issue_id": f"{cluster_id}_issue_{issue_idx:03d}",
                        "type": "Terminology inconsistency",
                        "severity": "Medium",
                        "description": f"Inconsistent spelling of the term '{root}' across chunks in the cluster.",
                        "reason": f"Chunks use different spelling variants: {', '.join(distinct_vars)}.",
                        "evidence": evidence,
                        "affected_claims": [],
                        "suggested_resolution": f"Standardize all references to use the correct spelling: '{root}'.",
                        "requires_claude_verification": False,
                        "confidence": 0.90
                    })
                    issue_idx += 1

        # 2. Numerical Inconsistencies Check
        num_by_unit = {}
        for ch in member_chunks:
            cid = ch["chunk_id"]
            text = ch["text"]
            
            # Match percentages
            p_matches = re.findall(r'(\d+(?:\.\d+)?)\s*%', text)
            for pm in p_matches:
                num_by_unit.setdefault("percentage", []).append((cid, float(pm), f"{pm}%"))
                
            # Match money
            m_matches = re.findall(r'\$\s*(\d+(?:\.\d+)?)', text)
            for mm in m_matches:
                num_by_unit.setdefault("money", []).append((cid, float(mm), f"${mm}"))
                
            # Match time durations
            d_matches = re.findall(r'(\d+)\s*(?:minute|hour|day|month|year)s?', text, re.IGNORECASE)
            for dm in d_matches:
                num_by_unit.setdefault("duration", []).append((cid, float(dm), f"{dm} time unit"))
                
        for unit, occurrences in num_by_unit.items():
            if len(occurrences) > 1:
                first_val = occurrences[0][1]
                different = any(occ[1] != first_val for occ in occurrences)
                if different:
                    evidence = []
                    for cid, val, quote in occurrences:
                        evidence.append({
                            "chunk_id": cid,
                            "quote": quote
                        })
                        
                    findings.append({
                        "issue_id": f"{cluster_id}_issue_{issue_idx:03d}",
                        "type": "Cross-chunk numerical inconsistency",
                        "severity": "High",
                        "description": f"Conflicting values for numerical type '{unit}' found within the same topic cluster.",
                        "reason": f"Value varies between chunks (e.g. {', '.join(set(str(occ[1]) for occ in occurrences))}).",
                        "evidence": evidence,
                        "affected_claims": [],
                        "suggested_resolution": "Verify the source material or logs to resolve numerical contradiction.",
                        "requires_claude_verification": True,
                        "confidence": 0.95
                    })
                    issue_idx += 1

        # 3. Policy & Obligations Inconsistencies Check
        obligations_found = []
        for ch in member_chunks:
            cid = ch["chunk_id"]
            text = ch["text"]
            if any(m in text.lower() for m in ["must", "shall", "required", "mandatory"]):
                obligations_found.append((cid, text))
                
        if len(obligations_found) > 1:
            # Let's flag a generic potential policy duplicate/inconsistency
            findings.append({
                "issue_id": f"{cluster_id}_issue_{issue_idx:03d}",
                "type": "Duplicate guidance",
                "severity": "Low",
                "description": "Multiple mandatory obligations expressed within the same topic community.",
                "reason": "Chunks contain multiple 'must' or 'shall' statements which may overlap or repeat policies.",
                "evidence": [{"chunk_id": cid, "quote": txt[:60] + "..."} for cid, txt in obligations_found],
                "affected_claims": [],
                "suggested_resolution": "Review obligation overlap and merge duplicate guidance into a single consistent rule.",
                "requires_claude_verification": False,
                "confidence": 0.80
            })
            issue_idx += 1

        overall_risk = "Low"
        if any(f["severity"] == "High" for f in findings):
            overall_risk = "High"
        elif len(findings) > 0:
            overall_risk = "Medium"

        return {
            "cluster_id": cluster_id,
            "cluster_topic": topic,
            "cluster_findings": findings,
            "overall_cluster_risk": overall_risk,
            "overall_confidence": 0.88
        }

    def run_analysis(self, job_dir: Path, doc_id: str) -> None:
        logger.info(f"Starting Phase 3 Cluster-Level Analysis for job: {doc_id}")
        
        # Cache hit check
        cache_cluster_reasoning_path = job_dir / "12_cluster_reasoning" / "cluster_reasoning.json"
        if cache_cluster_reasoning_path.exists() and cache_cluster_reasoning_path.stat().st_size > 0:
            logger.info(f"[CACHE HIT] Cluster reasoning analysis already exists for job {doc_id}. Skipping re-analysis.")
            return

        # Load necessary inputs
        clusters_path = job_dir / "09_semantic_clusters" / "semantic_clusters.json"
        if not clusters_path.exists():
            logger.error(f"semantic_clusters.json not found in {job_dir}/09_semantic_clusters/")
            return
            
        with open(clusters_path, "r", encoding="utf-8") as f:
            clusters = json.load(f)
            
        # Load Phase 2A extractions
        claims_json_path = job_dir / "10_claim_extraction" / "chunk_claims.json"
        if not claims_json_path.exists():
            logger.error(f"chunk_claims.json not found in {job_dir}/10_claim_extraction/")
            return
            
        with open(claims_json_path, "r", encoding="utf-8") as f:
            chunk_claims_data = json.load(f)
        chunks_map = {ch["chunk_id"]: ch for ch in chunk_claims_data.get("chunks", [])}

        # Load Phase 2B chunk-level reasoning
        reasoning_json_path = job_dir / "11_chunk_reasoning" / "chunk_reasoning.json"
        chunk_reasoning_map = {}
        if reasoning_json_path.exists():
            try:
                with open(reasoning_json_path, "r", encoding="utf-8") as f:
                    cr_data = json.load(f)
                    for cr in cr_data.get("chunks", []):
                        chunk_reasoning_map[cr["chunk_id"]] = cr
            except Exception as e:
                logger.error(f"Failed to load chunk reasoning outputs: {e}")

        # Check connection to Ollama server
        ollama_active = False
        try:
            ollama_active = self.ollama_client.check_connection()
        except Exception:
            pass
            
        if not ollama_active:
            logger.warning("Ollama connection failed. Falling back to deterministic cluster-level analyzer.")
            
        cluster_reasonings = []
        
        system_prompt = (
            "You are a precise semantic cluster-level conflict analyzer.\n"
            "Compare the member chunks, extractions, and validations within the provided cluster community.\n"
            "Identify cross-chunk contradictions, policy inconsistencies, terminology differences, and broken references.\n"
            "Return the analysis STRICTLY as a single JSON object matching the requested schema.\n"
            "Do NOT include markdown fences, comments, or conversational text."
        )

        for cluster in clusters:
            cluster_id = cluster["cluster_id"]
            topic = cluster["topic_summary"]
            
            # Compile all cluster chunk inputs
            member_chunks = []
            for cid in cluster.get("chunk_ids", []):
                # Retrieve original text, claims, validated claims, and extraction details
                ch_ext = chunks_map.get(cid, {})
                ch_reason = chunk_reasoning_map.get(cid, {})
                
                member_chunks.append({
                    "chunk_id": cid,
                    "text": ch_ext.get("text", ""),
                    "page": ch_ext.get("page", 1),
                    "heading_path": ch_ext.get("heading_path", "Root"),
                    "extraction": ch_ext.get("extraction", {}),
                    "validated_claims": ch_reason.get("claim_validation", []),
                    "chunk_level_ambiguities": ch_reason.get("ambiguities", [])
                })
                
            if not member_chunks:
                continue
                
            if ollama_active:
                prompt = f"""Perform cluster-level reasoning and compare these semantically related chunks.
Cluster ID: {cluster_id}
Topic: {topic}

Member Chunks:
{json.dumps(member_chunks, indent=2)}

Tasks:
1. Compare numerical values, percentages, dates, and deadlines across these chunks to identify contradictions.
2. Search for policy inconsistencies or conflicting rules.
3. Check for evolving terminology (spelling variations, wordings) referring to the same concept.
4. Identify duplicates or broken cross-references.

Return the findings strictly as a single JSON object.
Do NOT include markdown fences, comments, or explanations.

Requested JSON Schema:
{{
    "cluster_id": "{cluster_id}",
    "cluster_topic": "{topic}",
    "cluster_findings": [
        {{
            "issue_id": "{cluster_id}_issue_000",
            "type": "Cross-chunk numerical inconsistency|Policy inconsistency|Terminology inconsistency|Cross-reference inconsistency|Duplicate guidance|Missing Context",
            "severity": "Low|Medium|High|Critical",
            "description": "statement summarizing conflict",
            "reason": "why this is inconsistent",
            "evidence": [
                {{
                    "chunk_id": "chunk_id_1",
                    "quote": "exact quote from chunk 1"
                }},
                {{
                    "chunk_id": "chunk_id_2",
                    "quote": "exact quote from chunk 2"
                }}
            ],
            "affected_claims": ["claim_id_1", "claim_id_2"],
            "suggested_resolution": "resolution description",
            "requires_claude_verification": true,
            "confidence": 0.95
        }}
    ],
    "overall_cluster_risk": "Low|Medium|High",
    "overall_confidence": 0.92
}}
"""
                try:
                    logger.info(f"Running LLM Cluster Reasoning for cluster: {cluster_id}")
                    resp = self.ollama_client.generate(
                        model=self.model_name,
                        prompt=prompt,
                        system=system_prompt
                    )
                    parsed = self._clean_and_parse_json(resp)
                    cluster_reasonings.append(parsed)
                except Exception as e:
                    logger.error(f"Failed LLM cluster reasoning for {cluster_id}: {e}. Falling back to rule-based.")
                    cluster_reasonings.append(self._analyze_fallback_cluster(cluster_id, topic, member_chunks))
            else:
                cluster_reasonings.append(self._analyze_fallback_cluster(cluster_id, topic, member_chunks))

        # Ensure output directory exists
        reason_dir = job_dir / "12_cluster_reasoning"
        reason_dir.mkdir(parents=True, exist_ok=True)

        # 1. Output cluster_reasoning.json
        with open(reason_dir / "cluster_reasoning.json", "w", encoding="utf-8") as f:
            json.dump({"clusters": cluster_reasonings}, f, indent=2, ensure_ascii=False)

        # 2. Output cluster_findings.json
        findings_list = []
        for cr in cluster_reasonings:
            cid = cr["cluster_id"]
            for find in cr.get("cluster_findings", []):
                findings_list.append({
                    "issue_id": find.get("issue_id"),
                    "cluster_id": cid,
                    "cluster_topic": cr.get("cluster_topic"),
                    "type": find.get("type"),
                    "severity": find.get("severity"),
                    "description": find.get("description"),
                    "reason": find.get("reason"),
                    "evidence": find.get("evidence", []),
                    "affected_claims": find.get("affected_claims", []),
                    "suggested_resolution": find.get("suggested_resolution"),
                    "requires_claude_verification": find.get("requires_claude_verification", False),
                    "confidence": find.get("confidence", 0.90)
                })
        with open(reason_dir / "cluster_findings.json", "w", encoding="utf-8") as f:
            json.dump({"findings": findings_list}, f, indent=2, ensure_ascii=False)

        # 3. Output cross_chunk_conflicts.json (Only severity Medium, High, or Critical conflicts)
        conflicts_list = [f for f in findings_list if f["severity"] in ("Medium", "High", "Critical")]
        with open(reason_dir / "cross_chunk_conflicts.json", "w", encoding="utf-8") as f:
            json.dump({"conflicts": conflicts_list}, f, indent=2, ensure_ascii=False)

        # Compute statistics
        total_clusters = len(cluster_reasonings)
        total_findings = len(findings_list)
        total_conflicts = len(conflicts_list)
        
        severity_counter = Counter([f["severity"] for f in findings_list])
        avg_conf = sum(cr.get("overall_confidence", 0.0) for cr in cluster_reasonings) / max(1, total_clusters)

        # 4. Output cluster_statistics.json
        stats_data = {
            "total_clusters_analyzed": total_clusters,
            "total_findings_identified": total_findings,
            "total_critical_conflicts": total_conflicts,
            "severity_breakdown": {
                "Critical": severity_counter.get("Critical", 0),
                "High": severity_counter.get("High", 0),
                "Medium": severity_counter.get("Medium", 0),
                "Low": severity_counter.get("Low", 0)
            },
            "average_confidence": round(avg_conf, 4)
        }
        with open(reason_dir / "cluster_statistics.json", "w", encoding="utf-8") as f:
            json.dump(stats_data, f, indent=2)

        # 5. Write Markdown Reports
        # cluster_reasoning.md
        md_reason = ["# Cluster-Level Semantic Reasoning\n\n"]
        for cr in cluster_reasonings:
            md_reason.append(f"## Cluster `{cr['cluster_id']}`: {cr['cluster_topic']} (Risk: {cr.get('overall_cluster_risk')})\n")
            md_reason.append("\n### Cross-Chunk Findings\n")
            for find in cr.get("cluster_findings", []):
                md_reason.append(
                    f"#### {find.get('issue_id')} ({find.get('type')})\n"
                    f"- **Severity**: {find.get('severity')}\n"
                    f"- **Description**: {find.get('description')}\n"
                    f"- **Reasoning**: {find.get('reason')}\n"
                    f"- **Resolution**: {find.get('suggested_resolution')}\n"
                    f"- **Requires Claude Verification**: {find.get('requires_claude_verification')}\n"
                )
                md_reason.append("- **Supporting Evidence**:\n")
                for ev in find.get("evidence", []):
                    md_reason.append(f"  - Chunk `{ev.get('chunk_id')}`: \"{ev.get('quote')}\"\n")
            if not cr.get("cluster_findings"):
                md_reason.append("*No cross-chunk conflicts identified.*\n")
            md_reason.append("\n---\n")
        with open(reason_dir / "cluster_reasoning.md", "w", encoding="utf-8") as f:
            f.write("".join(md_reason))

        # cluster_findings.md
        md_findings = ["# Cluster Findings Index\n\n| Issue ID | Cluster | Topic | Type | Severity | Description | Claude verification? |\n|:---------|:--------|:------|:-----|:---------|:------------|:--------------------|\n"]
        for f in findings_list:
            md_findings.append(f"| `{f['issue_id']}` | `{f['cluster_id']}` | {f['cluster_topic']} | {f['type']} | **{f['severity']}** | {f['description']} | {'Yes' if f['requires_claude_verification'] else 'No'} |\n")
        with open(reason_dir / "cluster_findings.md", "w", encoding="utf-8") as f:
            f.write("".join(md_findings))

        # cross_chunk_conflicts.md
        md_conflicts = ["# Cross-Chunk Conflict Index\n\n| Issue ID | Type | Severity | Description | Contradicting Chunks | Suggested Resolution |\n|:---------|:-----|:---------|:------------|:---------------------|:---------------------|\n"]
        for c in conflicts_list:
            chunk_ids = ", ".join(set(ev.get("chunk_id") for ev in c.get("evidence", [])))
            md_conflicts.append(f"| `{c['issue_id']}` | {c['type']} | **{c['severity']}** | {c['description']} | `{chunk_ids}` | {c['suggested_resolution']} |\n")
        with open(reason_dir / "cross_chunk_conflicts.md", "w", encoding="utf-8") as f:
            f.write("".join(md_conflicts))

        # cluster_summary.md (Executive summary)
        summary_md = f"""# Cluster-Level Reasoning Summary

## Executive Overview
- **Total Clusters Processed**: {total_clusters}
- **Total Cross-Chunk Findings**: {total_findings}
- **Total Medium/High/Critical Conflicts**: {total_conflicts}
- **Average Reasoning Confidence**: {avg_conf * 100:.2f}%

## Severity Breakdown
- **Critical Findings**: {severity_counter.get('Critical', 0)}
- **High Severity Findings**: {severity_counter.get('High', 0)}
- **Medium Severity Findings**: {severity_counter.get('Medium', 0)}
- **Low Severity Findings**: {severity_counter.get('Low', 0)}
"""
        with open(reason_dir / "cluster_summary.md", "w", encoding="utf-8") as f:
            f.write(summary_md)

        # 6. Generate Interactive Debugger HTML
        html_template = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Cluster Reasoning Inspector</title>
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
    
    /* Overview Stats Dashboard */
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
    .badge-risk-critical { background: #fca5a5; color: #b91c1c; }
    .badge-risk-high { background: #fee2e2; color: #ef4444; }
    .badge-risk-medium { background: #fef3c7; color: #d97706; }
    .badge-risk-low { background: #d1fae5; color: #10b981; }
  </style>
</head>
<body>
  <div class="sidebar">
    <div class="sidebar-header">
      <h2>Cluster Reasoner</h2>
    </div>
    <ul class="nav-list">
      <li class="nav-item active" onclick="switchTab('tab-overview')">🏠 Overview Dashboard</li>
      <li class="nav-item" onclick="switchTab('tab-clusters')">📦 Cluster Explorer</li>
      <li class="nav-item" onclick="switchTab('tab-findings')">📄 All Findings</li>
      <li class="nav-item" onclick="switchTab('tab-conflicts')">⚠️ Inconsistencies</li>
    </ul>
  </div>
  
  <div class="main-content">
    
    <!-- 1. Overview Dashboard -->
    <div id="tab-overview" class="content-tab active">
      <h1 style="margin-top:0;">Cluster reasoning dashboard</h1>
      <div class="dashboard-grid">
        <div class="stat-card">
          <div class="stat-title">Clusters Analyzed</div>
          <div class="stat-value" id="d-total-clusters">0</div>
        </div>
        <div class="stat-card">
          <div class="stat-title">Cross-Chunk Findings</div>
          <div class="stat-value" id="d-total-findings">0</div>
        </div>
        <div class="stat-card">
          <div class="stat-title">Medium & Above Conflicts</div>
          <div class="stat-value" style="color:#ef4444;" id="d-total-conflicts">0</div>
        </div>
        <div class="stat-card">
          <div class="stat-title">Average Confidence</div>
          <div class="stat-value" id="d-avg-conf">0%</div>
        </div>
      </div>
      
      <h2>Severity Breakdown</h2>
      <div class="dashboard-grid">
        <div class="stat-card">
          <div class="stat-title">Critical Severity</div>
          <div class="stat-value" id="s-critical">0</div>
        </div>
        <div class="stat-card">
          <div class="stat-title">High Severity</div>
          <div class="stat-value" id="s-high">0</div>
        </div>
        <div class="stat-card">
          <div class="stat-title">Medium Severity</div>
          <div class="stat-value" id="s-medium">0</div>
        </div>
        <div class="stat-card">
          <div class="stat-title">Low Severity</div>
          <div class="stat-value" id="s-low">0</div>
        </div>
      </div>
    </div>
    
    <!-- 2. Cluster Browser -->
    <div id="tab-clusters" class="content-tab">
      <h1 style="margin-top:0;">Cluster Explorer</h1>
      <div class="browser-container">
        <div class="browser-list" id="clusters-list-element"></div>
        <div class="browser-detail" id="clusters-detail-element">
          <div style="color:var(--text-muted); text-align:center; margin:auto;">Select a semantic cluster on the left to inspect its contradictions</div>
        </div>
      </div>
    </div>
    
    <!-- 3. All Findings Browser -->
    <div id="tab-findings" class="content-tab">
      <h1 style="margin-top:0;">All Cluster-Level Findings</h1>
      <table class="index-table">
        <thead>
          <tr>
            <th>Finding ID</th>
            <th>Cluster Topic</th>
            <th>Finding Type</th>
            <th>Severity</th>
            <th>Description</th>
            <th>Resolution</th>
            <th>Claude check?</th>
          </tr>
        </thead>
        <tbody id="findings-table-body"></tbody>
      </table>
    </div>
    
    <!-- 4. Conflicts Browser -->
    <div id="tab-conflicts" class="content-tab">
      <h1 style="margin-top:0;">Cross-Chunk Inconsistencies</h1>
      <table class="index-table">
        <thead>
          <tr>
            <th>Conflict ID</th>
            <th>Inconsistency Type</th>
            <th>Severity</th>
            <th>Description</th>
            <th>Contradicting Chunks</th>
            <th>Suggested Resolution</th>
          </tr>
        </thead>
        <tbody id="conflicts-table-body"></tbody>
      </table>
    </div>
    
  </div>

  <script>
    // Injected Data
    var clusterReasonings = /* INJECT_REASONINGS */;
    var stats = /* INJECT_STATS */;
    var findings = /* INJECT_FINDINGS */;
    var conflicts = /* INJECT_CONFLICTS */;
    
    // Tab switching
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
      else if (tabId === "tab-clusters") targetIdx = 1;
      else if (tabId === "tab-findings") targetIdx = 2;
      else if (tabId === "tab-conflicts") targetIdx = 3;
      navItems[targetIdx].classList.add("active");
    };
    
    // 1. Render Dashboard
    document.getElementById("d-total-clusters").innerText = stats.total_clusters_analyzed;
    document.getElementById("d-total-findings").innerText = stats.total_findings_identified;
    document.getElementById("d-total-conflicts").innerText = stats.total_critical_conflicts;
    document.getElementById("d-avg-conf").innerText = (stats.average_confidence * 100).toFixed(1) + "%";
    document.getElementById("s-critical").innerText = stats.severity_breakdown.Critical;
    document.getElementById("s-high").innerText = stats.severity_breakdown.High;
    document.getElementById("s-medium").innerText = stats.severity_breakdown.Medium;
    document.getElementById("s-low").innerText = stats.severity_breakdown.Low;
    
    // 2. Render Clusters Browser
    var clustersListDiv = document.getElementById("clusters-list-element");
    clustersListDiv.innerHTML = "";
    clusterReasonings.forEach(function(cr, idx) {
      var item = document.createElement("div");
      item.className = "browser-item";
      item.onclick = function() { selectCluster(idx); };
      item.innerHTML = `
        <div style="font-weight:bold; font-family:monospace;">${cr.cluster_id.toUpperCase()}</div>
        <div style="font-size:12px; color:var(--text-muted); font-weight:600;">${cr.cluster_topic}</div>
        <div style="font-size:11px; margin-top:4px;">Risk: ${cr.overall_cluster_risk} | Findings: ${cr.cluster_findings ? cr.cluster_findings.length : 0}</div>
      `;
      clustersListDiv.appendChild(item);
    });
    
    function selectCluster(idx) {
      var items = document.getElementsByClassName("browser-item");
      for (var i = 0; i < items.length; i++) {
        items[i].classList.remove("active");
      }
      items[idx].classList.add("active");
      
      var cr = clusterReasonings[idx];
      var detailDiv = document.getElementById("clusters-detail-element");
      
      var findingsHtml = "";
      (cr.cluster_findings || []).forEach(function(f) {
        var badgeClass = "badge-risk-" + f.severity.toLowerCase();
        
        var evHtml = "";
        (f.evidence || []).forEach(function(ev) {
          evHtml += `<li>Chunk <strong>${ev.chunk_id}</strong>: "${ev.quote}"</li>`;
        });
        
        findingsHtml += `
          <div style="border-bottom: 1px solid var(--border); padding-bottom:12px; margin-bottom:12px;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:5px;">
              <strong>${f.issue_id} (${f.type})</strong>
              <span class="badge ${badgeClass}">${f.severity}</span>
            </div>
            <div style="font-size:13px;"><strong>Description:</strong> ${f.description}</div>
            <div style="font-size:13px;"><strong>Reasoning:</strong> ${f.reason}</div>
            <div style="font-size:13px;"><strong>Suggested Resolution:</strong> ${f.suggested_resolution}</div>
            <div style="font-size:12px; margin-top:5px; background:#f1f5f9; padding:6px; border-radius:4px;">
              <strong>Supporting Evidence:</strong>
              <ul style="margin:5px 0 0 15px; padding:0;">${evHtml}</ul>
            </div>
          </div>
        `;
      });
      
      detailDiv.innerHTML = `
        <h2 style="margin-top:0; color:var(--primary);">${cr.cluster_id.toUpperCase()} - ${cr.cluster_topic}</h2>
        <div style="font-size:13px; color:var(--text-muted); margin-bottom:15px;">
          <strong>Topic Community Risk Score:</strong> <span class="badge badge-risk-${cr.overall_cluster_risk.toLowerCase()}">${cr.overall_cluster_risk}</span> | <strong>Reasoning Confidence:</strong> ${(cr.overall_confidence * 100).toFixed(1)}%
        </div>
        
        <div class="detail-card">
          <h3>Cross-Chunk Conflict Findings</h3>
          <div>${findingsHtml || '<em>No cross-chunk conflicts identified</em>'}</div>
        </div>
      `;
    }
    
    // 3. Render Findings Table
    var findingsTableBody = document.getElementById("findings-table-body");
    findingsTableBody.innerHTML = "";
    findings.forEach(function(f) {
      var badgeClass = "badge-risk-" + f.severity.toLowerCase();
      findingsTableBody.innerHTML += `
        <tr>
          <td style="font-family:monospace; font-weight:bold;">${f.issue_id}</td>
          <td style="font-weight:600;">${f.cluster_topic}</td>
          <td>${f.type}</td>
          <td><span class="badge ${badgeClass}">${f.severity}</span></td>
          <td>${f.description}</td>
          <td>${f.suggested_resolution}</td>
          <td><strong>${f.requires_claude_verification ? 'YES' : 'NO'}</strong></td>
        </tr>
      `;
    });
    
    // 4. Render Conflicts Table
    var conflictsTableBody = document.getElementById("conflicts-table-body");
    conflictsTableBody.innerHTML = "";
    conflicts.forEach(function(c) {
      var badgeClass = "badge-risk-" + c.severity.toLowerCase();
      var chunkIds = Array.from(new Set(c.evidence.map(ev => ev.chunk_id))).join(', ');
      conflictsTableBody.innerHTML += `
        <tr>
          <td style="font-family:monospace; font-weight:bold;">${c.issue_id}</td>
          <td>${c.type}</td>
          <td><span class="badge ${badgeClass}">${c.severity}</span></td>
          <td>${c.description}</td>
          <td style="font-family:monospace;">${chunkIds}</td>
          <td style="color:var(--primary); font-weight:500;">${c.suggested_resolution}</td>
        </tr>
      `;
    });
  </script>
</body>
</html>
"""
        
        # Inject serialized variables
        html_content = html_template \
            .replace("/* INJECT_REASONINGS */", json.dumps(cluster_reasonings, ensure_ascii=False)) \
            .replace("/* INJECT_STATS */", json.dumps(stats_data, ensure_ascii=False)) \
            .replace("/* INJECT_FINDINGS */", json.dumps(findings_list, ensure_ascii=False)) \
            .replace("/* INJECT_CONFLICTS */", json.dumps(conflicts_list, ensure_ascii=False))
            
        with open(reason_dir / "cluster_reasoning_inspector.html", "w", encoding="utf-8") as f:
            f.write(html_content)
            
        logger.info(f"Phase 3 Cluster Inconsistency Reasoning complete. Output folder: {reason_dir}")
        
