import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from collections import Counter

from src.rag.config import RagConfig

logger = logging.getLogger("pipeline")

class FinalReportGenerator:
    """
    Phase 15: Final Business Report Generator.
    Consumes the verified Claude responses and generates customer-facing
    business reports in JSON, Markdown, and print-friendly HTML formats.
    Uses professional consulting terminology (e.g. Finding ID, Document Location, Related Sections).
    Writes outputs to 15_final_report/.
    """

    def __init__(self, config: Optional[RagConfig] = None):
        self.config = config or RagConfig()

    def run_generation(self, job_dir: Path, doc_id: str) -> None:
        logger.info(f"Starting Phase 15 Final Business Report Generation for job: {doc_id}")
        
        # Load claude_response.json
        claude_json_path = job_dir / "14_claude_verification" / "claude_response.json"
        if not claude_json_path.exists():
            logger.error(f"claude_response.json not found in {job_dir}/14_claude_verification/")
            return
            
        with open(claude_json_path, "r", encoding="utf-8") as f:
            claude_data = json.load(f)
            
        verified_findings = claude_data.get("verified_findings", [])
        confirmed_findings = [f for f in verified_findings if f.get("status") == "confirmed"]
        rejected_findings = [f for f in verified_findings if f.get("status") == "rejected"]
        
        overall_risk = claude_data.get("overall_document_risk", "Low")
        
        # Terminology translation mappings
        category_mappings = {
            "Lexical Ambiguity": "Writing Quality Issue",
            "Grammar Errors": "Writing Quality Issue",
            "Spelling Errors": "Writing Quality Issue",
            "Writing Style Issues": "Writing Quality Issue",
            "Terminology Inconsistency": "Terminology Inconsistency",
            "Policy Conflict": "Policy Alignment Conflict",
            "Numerical Conflict": "Numerical Conflict",
            "Temporal Conflict": "Temporal Conflict",
            "Broken Reference": "Broken Reference",
            "Duplicate Guidance": "Duplicate Guidance"
        }
        
        # Re-compile stats
        severity_counts = Counter(f.get("severity", "Low") for f in confirmed_findings)
        category_counts = Counter(
            category_mappings.get(f.get("business_category"), f.get("business_category", "Writing Quality Issue")) 
            for f in confirmed_findings
        )
        
        # Map findings to professional business structure
        business_findings = []
        for idx, f in enumerate(confirmed_findings, start=1):
            issue_id = f.get("issue_id", f"finding_{idx:03d}")
            raw_cat = f.get("business_category", "Writing Quality Issue")
            category = category_mappings.get(raw_cat, raw_cat)
            severity = f.get("severity", "Medium")
            evidence = f.get("evidence", [])
            source_sections = list(set(ev.get("chunk_id") for ev in evidence))
            
            # Formulate business title
            title = f"{category} in Document Locations {', '.join(source_sections)}"
            if len(source_sections) > 2:
                title = f"{category} Conflict (Multi-Section)"
                
            # Consulting-grade Business Impact statements
            impact = "OPERATIONAL IMPACT: Minor syntax or clarity issues increase document review cycle times and introduce slight comprehension variances."
            if severity == "Critical":
                impact = "CRITICAL COMPLIANCE RISK: Structural contradictions in regulatory mandates introduce immediate legal exposure, risk audits failures, or halt project certifications."
            elif severity == "High":
                impact = "HIGH STRATEGIC RISK: Terminology divergences or policy discrepancies will cause engineering execution errors, vendor contract disputes, or developer speed bottlenecks."
            elif severity == "Medium":
                impact = "MEDIUM OPERATIONAL RISK: Vague qualifiers or missing prerequisites create execution deviations, increasing task rework rates across operations teams."
                
            business_findings.append({
                "finding_id": issue_id.replace("_amb_", "_finding_").replace("_issue_", "_finding_"),
                "title": title,
                "severity": severity,
                "category": category,
                "explanation": f.get("reason", "No reason provided."),
                "business_impact": impact,
                "evidence": evidence,
                "document_locations": source_sections,
                "suggested_resolution": f.get("recommendation", "Review source requirements documents for reconciliation."),
                "verification_status": "verified"
            })
            
        # Structure final JSON
        final_report_data = {
            "document_job_id": doc_id,
            "overall_document_health": "Poor" if overall_risk == "High" else ("Fair" if overall_risk == "Medium" else "Good"),
            "overall_risk_score": overall_risk,
            "consistency_score": round(100 - (len(confirmed_findings) * 3), 1),
            "quality_score": round(100 - (len(confirmed_findings) * 2), 1),
            "readability_score": "High" if len(confirmed_findings) < 10 else ("Medium" if len(confirmed_findings) < 25 else "Low"),
            "executive_summary": {
                "summary_text": f"This Business Quality Audit Report evaluates the consistency, structural alignment, and compliance profile of document {doc_id}. The analysis verified {len(confirmed_findings)} findings across related sections. The document demonstrates a {overall_risk.upper()} risk exposure and holds a consistency index of {100 - (len(confirmed_findings) * 3)}%.",
                "total_findings_confirmed": len(confirmed_findings),
                "total_findings_rejected": len(rejected_findings),
                "severity_breakdown": dict(severity_counts),
                "category_breakdown": dict(category_counts)
            },
            "findings": business_findings,
            "recommendations": claude_data.get("recommendations", [])
        }
        
        # Ensure output folder exists
        report_dir = job_dir / "15_final_report"
        report_dir.mkdir(parents=True, exist_ok=True)
        
        # Output 1: final_report.json
        with open(report_dir / "final_report.json", "w", encoding="utf-8") as f:
            json.dump(final_report_data, f, indent=2, ensure_ascii=False)

        # Output 2: executive_summary.md
        exec_md = f"""# Executive Compliance Audit Summary
**Document Job ID**: `{doc_id}`  
**Overall Document Health**: **{final_report_data['overall_document_health'].upper()}**  
**Overall Risk Profile**: **{final_report_data['overall_risk_score'].upper()}**  
**Consistency Score**: **{final_report_data['consistency_score']}%**  
**Quality Score**: **{final_report_data['quality_score']}%**  
**Readability Rating**: **{final_report_data['readability_score']}**  

---

## Audit Dashboard Metrics
- **Confirmed Ambiguities / Contradictions**: {final_report_data['executive_summary']['total_findings_confirmed']}
- **Filtered False Positives (Rejected)**: {final_report_data['executive_summary']['total_findings_rejected']}

### Mapped Severities
- Critical issues: {severity_counts.get('Critical', 0)}
- High Severity: {severity_counts.get('High', 0)}
- Medium Severity: {severity_counts.get('Medium', 0)}
- Low Severity: {severity_counts.get('Low', 0)}

### Core Recommendation Resolution
{chr(10).join(f"- {r}" for r in final_report_data['recommendations'])}
"""
        with open(report_dir / "executive_summary.md", "w", encoding="utf-8") as f:
            f.write(exec_md)

        # Output 3: final_report.md
        md_lines = [
            f"# Business Compliance Audit Report\n",
            f"**Job ID**: `{doc_id}`  \n",
            f"**Document Health**: **{final_report_data['overall_document_health'].upper()}**  \n",
            f"**Risk Level**: **{final_report_data['overall_risk_score'].upper()}**  \n\n",
            f"---",
            f"\n## 1. Executive Summary\n",
            final_report_data['executive_summary']['summary_text'],
            f"\n## 2. Overall Document Health & Metrics\n",
            f"- **Consistency Score**: {final_report_data['consistency_score']}%",
            f"- **Quality Score**: {final_report_data['quality_score']}%",
            f"- **Readability Rating**: {final_report_data['readability_score']}",
            f"\n## 3. Risk Overview\n",
            f"- **Critical**: {severity_counts.get('Critical', 0)}",
            f"- **High**: {severity_counts.get('High', 0)}",
            f"- **Medium**: {severity_counts.get('Medium', 0)}",
            f"- **Low**: {severity_counts.get('Low', 0)}"
        ]
        
        # Findings by priority
        for priority in ["Critical", "High", "Medium", "Low"]:
            md_lines.append(f"\n## {priority} Priority Findings\n")
            p_findings = [bf for bf in business_findings if bf["severity"] == priority]
            for bf in p_findings:
                md_lines.append(
                    f"### {bf['title']}\n"
                    f"- **Finding ID**: `{bf['finding_id']}`\n"
                    f"- **Category**: {bf['category']}\n"
                    f"- **Explanation**: {bf['explanation']}\n"
                    f"- **Business Impact**: {bf['business_impact']}\n"
                    f"- **Resolution**: {bf['suggested_resolution']}\n"
                )
                md_lines.append("- **Supporting Evidence Quotes**:\n")
                for ev in bf["evidence"]:
                    md_lines.append(f"  - Document Location `{ev.get('chunk_id')}`: \"{ev.get('quote')}\"\n")
            if not p_findings:
                md_lines.append(f"*No {priority.lower()} findings identified.*\n")
                
        md_lines.append(f"\n## 8. Business Categories Breakdown\n")
        for cat, count in category_counts.items():
            md_lines.append(f"- **{cat}**: {count} instances")
            
        md_lines.append(f"\n## 9. Recommendations\n")
        for r in final_report_data['recommendations']:
            md_lines.append(f"- {r}")
            
        md_lines.append(f"\n## 10. Appendix\n")
        md_lines.append(f"- Mapped verification source arrays stored in `final_report.json`.")
        
        with open(report_dir / "final_report.md", "w", encoding="utf-8") as f:
            f.write("\n".join(md_lines))

        # Output 4: final_report.html (Interactive Debugger Report)
        html_template = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Business Compliance Audit Report</title>
  <style>
    :root {
      --primary: #1e3a8a;
      --primary-light: #eff6ff;
      --bg: #f8fafc;
      --card-bg: #ffffff;
      --text: #0f172a;
      --text-muted: #475569;
      --border: #cbd5e1;
      --shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1);
    }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: var(--bg);
      margin: 0;
      padding: 0;
      color: var(--text);
      display: flex;
      flex-direction: column;
      min-height: 100vh;
    }
    header {
      background: var(--primary);
      color: #fff;
      padding: 30px 40px;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    header h1 {
      margin: 0;
      font-size: 24px;
      font-weight: 800;
      letter-spacing: -0.02em;
    }
    .badge {
      background: var(--primary-light);
      color: var(--primary);
      padding: 4px 10px;
      border-radius: 6px;
      font-size: 11px;
      font-weight: bold;
      text-transform: uppercase;
      display: inline-block;
    }
    .badge-health {
      font-size: 14px;
      padding: 6px 14px;
    }
    .badge-health-good { background: #d1fae5; color: #065f46; }
    .badge-health-fair { background: #fef3c7; color: #92400e; }
    .badge-health-poor { background: #fee2e2; color: #991b1b; }
    
    .badge-severity-critical { background: #fca5a5; color: #b91c1c; }
    .badge-severity-high { background: #fee2e2; color: #ef4444; }
    .badge-severity-medium { background: #fef3c7; color: #d97706; }
    .badge-severity-low { background: #d1fae5; color: #10b981; }

    .main-container {
      max-width: 1200px;
      width: 100%;
      margin: 30px auto;
      padding: 0 20px;
      box-sizing: border-box;
    }
    .dashboard-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 20px;
      margin-bottom: 40px;
    }
    .stat-card {
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 24px;
      box-shadow: var(--shadow);
    }
    .stat-title {
      font-size: 12px;
      font-weight: 700;
      color: var(--text-muted);
      text-transform: uppercase;
      margin-bottom: 8px;
    }
    .stat-value {
      font-size: 28px;
      font-weight: 800;
      color: var(--primary);
    }
    
    .findings-section {
      margin-top: 40px;
    }
    .findings-section h2 {
      border-bottom: 2px solid var(--primary);
      padding-bottom: 10px;
      margin-bottom: 20px;
      color: var(--primary);
    }
    .finding-card {
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 8px;
      margin-bottom: 20px;
      box-shadow: var(--shadow);
      overflow: hidden;
    }
    .finding-header {
      padding: 20px;
      background: #f8fafc;
      cursor: pointer;
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-bottom: 1px solid var(--border);
    }
    .finding-header h4 {
      margin: 0;
      font-size: 16px;
      font-weight: 700;
    }
    .finding-body {
      padding: 25px;
      display: none;
    }
    .finding-body.active {
      display: block;
    }
    
    .evidence-box {
      font-family: monospace;
      font-size: 12px;
      background: #f1f5f9;
      padding: 15px;
      border-radius: 6px;
      margin-top: 10px;
      border-left: 4px solid var(--border);
    }
    
    @media print {
      body {
        background: #fff;
        color: #000;
      }
      header {
        background: none;
        color: #000;
        border-bottom: 2px solid #000;
        padding: 10px 0;
      }
      .stat-card {
        border: 1px solid #000;
        box-shadow: none;
      }
      .finding-card {
        border: 1px solid #000;
        box-shadow: none;
        page-break-inside: avoid;
      }
      .finding-body {
        display: block !important;
      }
      .finding-header {
        background: none;
        border-bottom: 1px solid #000;
      }
      .main-container {
        max-width: 100%;
        margin: 0;
        padding: 0;
      }
    }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>Compliance Business Audit Report</h1>
      <div style="font-size:12px; margin-top:5px; color:#bfdbfe;">Job ID: <span id="header-job-id"></span></div>
    </div>
    <span class="badge badge-health" id="header-health">Good</span>
  </header>
  
  <div class="main-container">
    
    <!-- Executive Dashboard -->
    <div class="dashboard-grid">
      <div class="stat-card">
        <div class="stat-title">Overall Risk Score</div>
        <div class="stat-value" id="stats-risk">LOW</div>
      </div>
      <div class="stat-card">
        <div class="stat-title">Consistency Index</div>
        <div class="stat-value" id="stats-consistency">100%</div>
      </div>
      <div class="stat-card">
        <div class="stat-title">Quality Score</div>
        <div class="stat-value" id="stats-quality">100%</div>
      </div>
      <div class="stat-card">
        <div class="stat-title">Readability Rating</div>
        <div class="stat-value" id="stats-readability">HIGH</div>
      </div>
    </div>
    
    <!-- Summary -->
    <div class="detail-card" style="margin-bottom:40px;">
      <h2>Executive Summary</h2>
      <p id="executive-summary-text" style="font-size:15px; line-height:1.6;"></p>
    </div>
    
    <!-- Findings -->
    <div class="findings-section">
      <h2>Audit Findings List</h2>
      <div id="findings-list-container"></div>
    </div>
    
    <!-- Recommendations -->
    <div class="findings-section" style="margin-bottom:60px;">
      <h2>Action Recommendations</h2>
      <ul id="recommendations-list" style="font-size:15px; line-height:1.6; padding-left:20px;"></ul>
    </div>
    
  </div>

  <script>
    // Injected Data
    var report = /* INJECT_REPORT */;
    
    // Set Header
    document.getElementById("header-job-id").innerText = report.document_job_id;
    var healthBadge = document.getElementById("header-health");
    healthBadge.innerText = "Health: " + report.overall_document_health;
    healthBadge.classList.add("badge-health-" + report.overall_document_health.toLowerCase());
    
    // Set Stats
    document.getElementById("stats-risk").innerText = report.overall_risk_score.toUpperCase();
    document.getElementById("stats-consistency").innerText = report.consistency_score + "%";
    document.getElementById("stats-quality").innerText = report.quality_score + "%";
    document.getElementById("stats-readability").innerText = report.readability_score.toUpperCase();
    
    // Set Executive Text
    document.getElementById("executive-summary-text").innerText = report.executive_summary.summary_text;
    
    // Set Recommendations
    var recList = document.getElementById("recommendations-list");
    recList.innerHTML = "";
    (report.recommendations || []).forEach(function(r) {
      recList.innerHTML += `<li>${r}</li>`;
    });
    
    // Set Findings
    var findingsDiv = document.getElementById("findings-list-container");
    findingsDiv.innerHTML = "";
    (report.findings || []).forEach(function(f, idx) {
      var badgeClass = "badge-severity-" + f.severity.toLowerCase();
      var evHtml = "";
      (f.evidence || []).forEach(function(ev) {
        evHtml += `<li>Document Location <strong>${ev.chunk_id}</strong>: "${ev.quote}"</li>`;
      });
      
      findingsDiv.innerHTML += `
        <div class="finding-card">
          <div class="finding-header" onclick="toggleFinding(${idx})">
            <h4>${f.title}</h4>
            <div>
              <span class="badge ${badgeClass}">${f.severity}</span>
            </div>
          </div>
          <div class="finding-body" id="finding-body-${idx}">
            <p><strong>Finding ID:</strong> ${f.finding_id}</p>
            <p><strong>Category:</strong> ${f.category}</p>
            <p><strong>Explanation:</strong> ${f.explanation}</p>
            <p><strong>Business Impact:</strong> ${f.business_impact}</p>
            <p><strong>Suggested Resolution:</strong> ${f.suggested_resolution}</p>
            <div class="evidence-box">
              <strong>Evidence Mapped Document Sections:</strong>
              <ul style="margin:5px 0 0 15px; padding:0;">${evHtml}</ul>
            </div>
          </div>
        </div>
      `;
    });
    
    window.toggleFinding = function(idx) {
      var body = document.getElementById("finding-body-" + idx);
      body.classList.toggle("active");
    };
  </script>
</body>
</html>
"""
        
        # Inject serialized variables
        html_content = html_template \
            .replace("/* INJECT_REPORT */", json.dumps(final_report_data, ensure_ascii=False))
            
        with open(report_dir / "final_report.html", "w", encoding="utf-8") as f:
            f.write(html_content)
            
        logger.info(f"Phase 15 Business Report generation complete. Outputs in {report_dir}")
