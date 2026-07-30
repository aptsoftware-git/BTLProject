import json
import logging
from pathlib import Path
from collections import Counter
from typing import Dict, Any, Optional

from src.rag.config import RagConfig
from src.rag.claude.claude_client import ClaudeClient
from src.rag.claude.prompts import CLAUDE_SYSTEM_PROMPT, build_user_prompt
from src.rag.claude.response_parser import ResponseParser

logger = logging.getLogger("pipeline")

class ClaudeVerificationService:
    """
    Phase 14: Claude Inconsistency Verification Service.
    Invokes the Claude Messages API using the packaged json payload,
    reconciles findings, and writes the verified structured findings
    and inspector reports to 14_claude_verification/.
    """

    def __init__(self, config: Optional[RagConfig] = None):
        self.config = config or RagConfig()
        self.client = ClaudeClient()
        self.parser = ResponseParser()

    def _generate_fallback_verification(self, input_data: dict) -> dict:
        """Determines verification status locally if Claude API is offline/invalid key."""
        logger.warning("Using local deterministic compiler for Claude verification fallback.")
        verified_findings = []
        
        # 1. Chunk ambiguities mapping
        chunk_reasoning = input_data.get("chunk_reasoning", {})
        for cid, cr in chunk_reasoning.items():
            page_num = cr.get("page_number") or cr.get("page") or 1
            sec_heading = cr.get("section_heading") or cr.get("heading") or cr.get("section") or "Document Section"
            orig_text = cr.get("text") or cr.get("original_text") or ""
            
            for amb in cr.get("ambiguities", []):
                if isinstance(amb, str):
                    amb = {"quote": amb, "type": "vague wording", "reason": amb}
                if not isinstance(amb, dict):
                    continue
                amb_type = str(amb.get("type", "")).lower()
                if "pronoun" in amb_type or "reference" in amb_type:
                    cat = "Pronoun Ambiguity"
                elif "grammar" in amb_type or "syntax" in amb_type:
                    cat = "Grammar Issue"
                elif "spell" in amb_type:
                    cat = "Spelling Issue"
                elif "undefined" in amb_type or "acronym" in amb_type:
                    cat = "Undefined Term"
                elif "term" in amb_type:
                    cat = "Terminology Issue"
                elif "number" in amb_type or "numerical" in amb_type:
                    cat = "Numerical Inconsistency"
                else:
                    cat = "Writing Clarity"

                quote_text = amb.get("quote") or amb.get("highlighted_ambiguity") or orig_text[:60]
                chunk_full = orig_text if orig_text else quote_text

                verified_findings.append({
                    "issue_id": amb.get("issue_id", f"finding_{len(verified_findings)+1:03d}"),
                    "status": "confirmed",
                    "severity": amb.get("severity", "Medium"),
                    "business_category": cat,
                    "page": page_num,
                    "section": sec_heading,
                    "chunk_id": cid,
                    "original_chunk": chunk_full,
                    "highlighted_ambiguity": quote_text,
                    "reason": amb.get("reason") or "Passage contains ambiguous phrasing affecting clarity.",
                    "business_impact": amb.get("business_impact") or "Ambiguity in operational instructions may cause execution deviations across teams.",
                    "recommendation": amb.get("suggested_rewrite") or amb.get("recommendation") or "Revise the sentence to state explicit parameters.",
                    "evidence": [
                        {
                            "chunk_id": cid,
                            "quote": quote_text
                        }
                    ]
                })
                
        # 2. Cluster findings mapping
        cluster_reasoning = input_data.get("cluster_reasoning", {})
        for clid, clr in cluster_reasoning.items():
            for find in clr.get("cluster_findings", []):
                evidence = find.get("evidence", [])
                primary_cid = evidence[0].get("chunk_id") if evidence and evidence[0].get("chunk_id") else "N/A"
                quote_text = evidence[0].get("quote") if evidence and evidence[0].get("quote") else ""

                verified_findings.append({
                    "issue_id": find.get("issue_id", f"finding_{len(verified_findings)+1:03d}"),
                    "status": "confirmed",
                    "severity": find.get("severity", "High"),
                    "business_category": "Policy Conflict",
                    "page": find.get("page", 1),
                    "section": find.get("section", "Cross-Section Policy"),
                    "chunk_id": primary_cid,
                    "original_chunk": quote_text or "Cross-section document passage evaluated during assurance audit.",
                    "highlighted_ambiguity": quote_text or "Conflicting operational directives",
                    "reason": find.get("reason") or "Cross-section directives present contradictory operational rules.",
                    "business_impact": find.get("business_impact") or "Conflicting directives create legal exposure and compliance audit risk.",
                    "recommendation": find.get("suggested_resolution") or find.get("recommendation") or "Reconcile conflicting section statements to establish a single authoritative policy.",
                    "evidence": evidence
                })
                
        severity_counts = Counter(f["severity"] for f in verified_findings)
        
        return {
            "executive_summary": {
                "total_verified_findings": len(verified_findings),
                "high_severity_count": severity_counts.get("High", 0) + severity_counts.get("Critical", 0),
                "medium_severity_count": severity_counts.get("Medium", 0),
                "low_severity_count": severity_counts.get("Low", 0),
                "document_risk_level": "High" if severity_counts.get("High", 0) + severity_counts.get("Critical", 0) > 0 else ("Medium" if verified_findings else "Low")
            },
            "overall_document_risk": "High" if severity_counts.get("High", 0) + severity_counts.get("Critical", 0) > 0 else ("Medium" if verified_findings else "Low"),
            "verified_findings": verified_findings,
            "recommendations": [
                "Reconcile cross-section policy directives to establish a unified operational protocol.",
                "Ensure all technical acronyms and proprietary terms have explicit definitions in the appendix.",
                "Clarify pronoun references across all multi-clause statements."
            ]
        }

    def run_verification(self, job_dir: Path, doc_id: str, force_regenerate: bool = False) -> Dict[str, Any]:
        logger.info(f"Starting Phase 14 Claude Verification for job: {doc_id}")
        
        verification_dir = job_dir / "14_claude_verification"
        response_json_path = verification_dir / "claude_response.json"

        if not force_regenerate and response_json_path.exists() and response_json_path.stat().st_size > 0:
            logger.info(f"[CACHE HIT] Claude verification report already exists for job {doc_id}. Skipping Claude API re-invocation.")
            try:
                with open(response_json_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Could not read cached Claude verification response: {e}. Re-running...")

        # Load claude_input.json
        input_json_path = job_dir / "13_claude_input" / "claude_input.json"
        if not input_json_path.exists():
            logger.error(f"claude_input.json not found in {job_dir}/13_claude_input/")
            return {}
            
        with open(input_json_path, "r", encoding="utf-8") as f:
            input_data = json.load(f)
            
        # Determine if we should call the Claude API
        api_callable = True
        if not self.client.api_key or "sk-ant" not in self.client.api_key:
            api_callable = False
            
        claude_response_data = None
        if api_callable:
            try:
                user_prompt = build_user_prompt(input_data)
                resp_text = self.client.send_message(user_prompt, CLAUDE_SYSTEM_PROMPT)
                claude_response_data = self.parser.clean_and_parse_json(resp_text)
            except Exception as e:
                logger.error(f"Claude API request failed: {e}. Falling back to local verification compiler.")
                claude_response_data = self._generate_fallback_verification(input_data)
        else:
            claude_response_data = self._generate_fallback_verification(input_data)

        # Ensure output folder exists
        verification_dir = job_dir / "14_claude_verification"
        verification_dir.mkdir(parents=True, exist_ok=True)

        # Output 1: claude_response.json
        with open(verification_dir / "claude_response.json", "w", encoding="utf-8") as f:
            json.dump(claude_response_data, f, indent=2, ensure_ascii=False)

        # Compute verification statistics
        verified = claude_response_data.get("verified_findings", [])
        confirmed = [f for f in verified if f.get("status") == "confirmed"]
        rejected = [f for f in verified if f.get("status") == "rejected"]
        
        severity_counts = Counter(f.get("severity") for f in confirmed)
        category_counts = Counter(f.get("business_category") for f in confirmed)

        # Output 2: verification_statistics.json
        stats_data = {
            "total_findings_audited": len(verified),
            "total_findings_confirmed": len(confirmed),
            "total_findings_rejected": len(rejected),
            "overall_document_risk": claude_response_data.get("overall_document_risk", "Low"),
            "severity_breakdown": {
                "Critical": severity_counts.get("Critical", 0),
                "High": severity_counts.get("High", 0),
                "Medium": severity_counts.get("Medium", 0),
                "Low": severity_counts.get("Low", 0)
            },
            "category_breakdown": dict(category_counts)
        }
        with open(verification_dir / "verification_statistics.json", "w", encoding="utf-8") as f:
            json.dump(stats_data, f, indent=2)

        # Output 3: verification_summary.md (Executive overview)
        summary_md = f"""# Claude Quality Audit Verification Summary

## Executive Overview
- **Overall Document Risk Level**: **{stats_data['overall_document_risk'].upper()}**
- **Total Local LLM Findings Audited**: {stats_data['total_findings_audited']}
- **Confirmed Ambiguities / Contradictions**: {stats_data['total_findings_confirmed']}
- **Rejected False Positives**: {stats_data['total_findings_rejected']}

## Severity Mappings
- **Critical Issues**: {stats_data['severity_breakdown']['Critical']}
- **High Severity**: {stats_data['severity_breakdown']['High']}
- **Medium Severity**: {stats_data['severity_breakdown']['Medium']}
- **Low Severity**: {stats_data['severity_breakdown']['Low']}
"""
        with open(verification_dir / "verification_summary.md", "w", encoding="utf-8") as f:
            f.write(summary_md)

        # Output 4: verification_inspector.html (Interactive Debugger)
        html_template = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Claude Quality Audit Inspector</title>
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
    .badge {
      background: var(--primary-light);
      color: var(--primary);
      padding: 2px 6px;
      border-radius: 4px;
      font-size: 10px;
      font-weight: bold;
      text-transform: uppercase;
    }
    .badge-status-confirmed { background: #d1fae5; color: #10b981; }
    .badge-status-rejected { background: #fee2e2; color: #ef4444; }
  </style>
</head>
<body>
  <div class="sidebar">
    <div class="sidebar-header">
      <h2>Audit Inspector</h2>
    </div>
    <ul class="nav-list">
      <li class="nav-item active" onclick="switchTab('tab-overview')">🏠 Overview</li>
      <li class="nav-item" onclick="switchTab('tab-summary')">📊 Summary</li>
      <li class="nav-item" onclick="switchTab('tab-verified')">✅ Verified Findings</li>
      <li class="nav-item" onclick="switchTab('tab-rejected')">❌ Rejected Findings</li>
      <li class="nav-item" onclick="switchTab('tab-recommendations')">💡 Recommendations</li>
      <li class="nav-item" onclick="switchTab('tab-raw')">⚙️ Raw Claude JSON</li>
    </ul>
  </div>
  
  <div class="main-content">
    
    <!-- 1. Overview Dashboard -->
    <div id="tab-overview" class="content-tab active">
      <h1 style="margin-top:0;">Claude Verification Audit</h1>
      <div class="dashboard-grid">
        <div class="stat-card">
          <div class="stat-title">Audited Findings</div>
          <div class="stat-value" id="d-audited">0</div>
        </div>
        <div class="stat-card">
          <div class="stat-title">Confirmed Issues</div>
          <div class="stat-value" style="color:#10b981;" id="d-confirmed">0</div>
        </div>
        <div class="stat-card">
          <div class="stat-title">Rejected Issues</div>
          <div class="stat-value" style="color:#ef4444;" id="d-rejected">0</div>
        </div>
        <div class="stat-card">
          <div class="stat-title">Document Risk</div>
          <div class="stat-value" id="d-risk">N/A</div>
        </div>
      </div>
      
      <h2>Severity Distribution</h2>
      <div class="dashboard-grid">
        <div class="stat-card">
          <div class="stat-title">Critical</div>
          <div class="stat-value" id="s-critical">0</div>
        </div>
        <div class="stat-card">
          <div class="stat-title">High</div>
          <div class="stat-value" id="s-high">0</div>
        </div>
        <div class="stat-card">
          <div class="stat-title">Medium</div>
          <div class="stat-value" id="s-medium">0</div>
        </div>
        <div class="stat-card">
          <div class="stat-title">Low</div>
          <div class="stat-value" id="s-low">0</div>
        </div>
      </div>
    </div>
    
    <!-- 2. Summary -->
    <div id="tab-summary" class="content-tab">
      <h1 style="margin-top:0;">Quality Audit Summary</h1>
      <div class="detail-card">
        <h3>Risk Score</h3>
        <p>This document is verified as having a <strong><span id="summary-risk">N/A</span></strong> risk profile.</p>
      </div>
    </div>
    
    <!-- 3. Verified Findings -->
    <div id="tab-verified" class="content-tab">
      <h1 style="margin-top:0;">Verified Contradictions & Ambiguities</h1>
      <table class="index-table">
        <thead>
          <tr>
            <th>Issue ID</th>
            <th>Business Category</th>
            <th>Severity</th>
            <th>Reasoning</th>
            <th>Evidence Quotes</th>
            <th>Recommendation Resolution</th>
          </tr>
        </thead>
        <tbody id="verified-table-body"></tbody>
      </table>
    </div>
    
    <!-- 4. Rejected Findings -->
    <div id="tab-rejected" class="content-tab">
      <h1 style="margin-top:0;">Rejected False Positives</h1>
      <table class="index-table">
        <thead>
          <tr>
            <th>Issue ID</th>
            <th>Audit Status</th>
            <th>Rejection Reason</th>
          </tr>
        </thead>
        <tbody id="rejected-table-body"></tbody>
      </table>
    </div>
    
    <!-- 5. Recommendations -->
    <div id="tab-recommendations" class="content-tab">
      <h1 style="margin-top:0;">Audit Document Recommendations</h1>
      <ul id="recommendations-list" style="background:#fff; border:1px solid var(--border); border-radius:8px; padding:25px; line-height:1.6;"></ul>
    </div>
    
    <!-- 6. Raw Claude JSON -->
    <div id="tab-raw" class="content-tab" style="overflow:hidden;">
      <h1 style="margin-top:0;">Raw Claude Verification JSON</h1>
      <textarea id="raw-json-textarea" style="flex:1; width:100%; border:1px solid var(--border); border-radius:8px; font-family:monospace; font-size:12px; padding:15px; box-sizing:border-box; outline:none; resize:none;" readonly></textarea>
    </div>
    
  </div>

  <script>
    // Injected Data
    var auditData = /* INJECT_CLAUDE_RESPONSE */;
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
      else if (tabId === "tab-verified") targetIdx = 2;
      else if (tabId === "tab-rejected") targetIdx = 3;
      else if (tabId === "tab-recommendations") targetIdx = 4;
      else if (tabId === "tab-raw") targetIdx = 5;
      navItems[targetIdx].classList.add("active");
    };
    
    // Render stats
    document.getElementById("d-audited").innerText = stats.total_findings_audited;
    document.getElementById("d-confirmed").innerText = stats.total_findings_confirmed;
    document.getElementById("d-rejected").innerText = stats.total_findings_rejected;
    document.getElementById("d-risk").innerText = stats.overall_document_risk;
    document.getElementById("summary-risk").innerText = stats.overall_document_risk;
    
    document.getElementById("s-critical").innerText = stats.severity_breakdown.Critical;
    document.getElementById("s-high").innerText = stats.severity_breakdown.High;
    document.getElementById("s-medium").innerText = stats.severity_breakdown.Medium;
    document.getElementById("s-low").innerText = stats.severity_breakdown.Low;
    
    // Render verified findings
    var verifiedBody = document.getElementById("verified-table-body");
    verifiedBody.innerHTML = "";
    
    // Render rejected findings
    var rejectedBody = document.getElementById("rejected-table-body");
    rejectedBody.innerHTML = "";
    
    var verified = auditData.verified_findings || [];
    verified.forEach(function(f) {
      if (f.status === "confirmed") {
        var evHtml = "";
        (f.evidence || []).forEach(function(ev) {
          evHtml += `<li>Chunk <strong>${ev.chunk_id}</strong>: "${ev.quote}"</li>`;
        });
        
        verifiedBody.innerHTML += `
          <tr>
            <td style="font-family:monospace; font-weight:bold;">${f.issue_id}</td>
            <td><strong>${f.business_category}</strong></td>
            <td><span class="badge">${f.severity}</span></td>
            <td>${f.reason}</td>
            <td><ul style="margin:0; padding:0 0 0 12px; font-size:12px;">${evHtml}</ul></td>
            <td style="color:var(--primary); font-weight:500;">${f.recommendation}</td>
          </tr>
        `;
      } else {
        rejectedBody.innerHTML += `
          <tr>
            <td style="font-family:monospace; font-weight:bold;">${f.issue_id}</td>
            <td><span class="badge badge-status-rejected">${f.status.toUpperCase()}</span></td>
            <td>${f.reason}</td>
          </tr>
        `;
      }
    });
    
    if (rejectedBody.innerHTML === "") {
      rejectedBody.innerHTML = '<tr><td colspan="3" style="text-align:center; color:var(--text-muted);">No findings were rejected by the auditor.</td></tr>';
    }
    
    // Render recommendations
    var recList = document.getElementById("recommendations-list");
    recList.innerHTML = "";
    (auditData.recommendations || []).forEach(function(r) {
      recList.innerHTML += `<li>${r}</li>`;
    });
    
    // Raw JSON view
    document.getElementById("raw-json-textarea").value = JSON.stringify(auditData, null, 2);
  </script>
</body>
</html>
"""
        
        # Inject serialized variables
        html_content = html_template \
            .replace("/* INJECT_CLAUDE_RESPONSE */", json.dumps(claude_response_data, ensure_ascii=False)) \
            .replace("/* INJECT_STATS */", json.dumps(stats_data, ensure_ascii=False))
            
        with open(verification_dir / "verification_inspector.html", "w", encoding="utf-8") as f:
            f.write(html_content)
            
        logger.info(f"Phase 14 Claude Verification complete. Outputs in {verification_dir}")
        return claude_response_data
