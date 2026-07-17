import json
import time
import logging
import re
from pathlib import Path
from typing import List, Dict, Any, Tuple

from src.rag.contextual_analysis.models import InconsistencyIssue, AnalysisReport, ExecutiveSummary

logger = logging.getLogger("pipeline")

def clean_technical_jargon(text: str) -> str:
    if not text:
        return text
    replacements = {
        "knowledge object": "document segment",
        "Knowledge Object": "Document Segment",
        "knowledge objects": "document segments",
        "Knowledge Objects": "Document Segments",
        "chunk": "segment",
        "Chunk": "Segment",
        "chunks": "segments",
        "Chunks": "Segments",
        "metadata": "document properties",
        "Metadata": "Document Properties",
        "embedding": "index status",
        "Embedding": "Index Status",
        "embeddings": "index status",
        "Embeddings": "Index Status",
        "inference": "analysis",
        "Inference": "Analysis",
        "llm": "audit engine",
        "LLM": "Audit Engine",
        "candidate group": "comparison group",
        "Candidate Group": "Comparison Group",
        "candidate groups": "comparison groups",
        "Candidate Groups": "Comparison Groups",
        "vector database": "document index",
        "Vector Database": "Document Index",
        "vector db": "document index",
        "Vector DB": "Document Index",
        "internal id": "segment reference",
        "Internal ID": "Segment Reference",
        "internal ids": "segment references",
        "Internal IDs": "Segment References",
        "confidence %": "audit certainty",
        "Confidence %": "Audit Certainty",
        "confidence percentage": "audit certainty",
        "Confidence Percentage": "Audit Certainty",
        "error": "potential inconsistency",
        "Error": "Potential Inconsistency",
        "wrong": "appears inconsistent",
        "Wrong": "Appears Inconsistent",
        "incorrect": "possible contradiction",
        "Incorrect": "Possible Contradiction"
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    return text

def map_to_enterprise_category(cat: str) -> str:
    c = cat.lower()
    if "numeric" in c or "number" in c or "mismatch" in c:
        return "Numeric Inconsistencies"
    if "date" in c or "time" in c or "chronology" in c:
        return "Date Conflicts"
    if "policy" in c or "rule" in c or "expiry" in c:
        return "Policy Conflicts"
    if "entity" in c or "person" in c or "org" in c:
        return "Entity Inconsistencies"
    if "contradiction" in c or "conflict" in c or "clash" in c:
        return "Cross-section Contradictions"
    if "missing" in c:
        return "Missing References"
    if "broken" in c:
        return "Broken References"
    if "duplicate" in c:
        return "Duplicate Information"
    if "reference" in c:
        return "Reference Conflicts"
    if "terminology" in c or "naming" in c:
        return "Terminology Conflicts"
    return "Cross-section Contradictions"

class ReportGenerator:
    """
    Compiles InconsistencyIssues into a standardized JSON report and
    a business-friendly, professional HTML audit dashboard.
    """

    @staticmethod
    def generate_report(
        document_id: str, 
        source_file: str, 
        issues: List[InconsistencyIssue], 
        output_dir: Path
    ) -> Tuple[Path, Path]:
        
        # Mapped categories configuration
        standard_categories = [
            "Numeric Inconsistencies",
            "Reference Conflicts",
            "Terminology Conflicts",
            "Policy Conflicts",
            "Entity Inconsistencies",
            "Date Conflicts",
            "Cross-section Contradictions",
            "Missing References",
            "Broken References",
            "Duplicate Information"
        ]
        
        # Mapped issues list
        mapped_issues = []
        for issue in issues:
            mapped_cat = map_to_enterprise_category(issue.category)
            mapped_issues.append(InconsistencyIssue(
                category=mapped_cat,
                severity=issue.severity,
                confidence=issue.confidence,
                description=clean_technical_jargon(issue.description),
                evidence=clean_technical_jargon(issue.evidence),
                object_ids=issue.object_ids,
                page_numbers=issue.page_numbers,
                section_path=issue.section_path,
                quoted_text=clean_technical_jargon(issue.quoted_text),
                metadata=issue.metadata
            ))

        total = len(mapped_issues)
        high = sum(1 for i in mapped_issues if i.severity == "High")
        med = sum(1 for i in mapped_issues if i.severity == "Medium")
        low = sum(1 for i in mapped_issues if i.severity == "Low")
        
        categories_distribution = {cat: 0 for cat in standard_categories}
        for i in mapped_issues:
            categories_distribution[i.category] = categories_distribution.get(i.category, 0) + 1
            
        avg_conf = (sum(i.confidence for i in mapped_issues) / total) if total > 0 else 0.0
        
        summary = ExecutiveSummary(
            total_issues=total,
            high_severity=high,
            medium_severity=med,
            low_severity=low,
            categories_distribution=categories_distribution,
            average_confidence=avg_conf
        )
        
        report = AnalysisReport(
            document_id=document_id,
            source_file=source_file,
            created_time=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            summary=summary,
            issues=mapped_issues
        )
        
        # Load knowledge objects metadata to compute page counts and segments
        page_count = 1
        objects_by_id = {}
        total_segments = 0
        ko_path = output_dir / "03_knowledge_objects" / "knowledge_objects.json"
        if not ko_path.exists():
            ko_path = output_dir / "knowledge_objects.json"
        if ko_path.exists():
            try:
                with open(ko_path, "r", encoding="utf-8") as f:
                    objects = json.load(f)
                    total_segments = len(objects)
                    page_count = max([o.get("page_number", 1) for o in objects]) if objects else 1
                    objects_by_id = {o.get("knowledge_id"): o for o in objects if o.get("knowledge_id")}
            except Exception as e:
                logger.error(f"Error loading knowledge_objects.json: {e}")

        # Parse processing time from README.md
        processing_time = "N/A"
        readme_path = output_dir / "README.md"
        if readme_path.exists():
            try:
                readme_text = readme_path.read_text(encoding="utf-8")
                m = re.search(r"processing time:\s*([\d\.\s\w\-]+)", readme_text, re.IGNORECASE)
                if m:
                    processing_time = m.group(1).strip()
            except Exception:
                pass

        # Determine overall document health
        if high > 0:
            health = "Critical"
            health_color = "#ef4444"
            health_desc = "This document contains potential high-priority conflicts that require review."
        elif med > 0:
            health = "Needs Review"
            health_color = "#f59e0b"
            health_desc = "Some potential inconsistencies found. Please review the flagged items."
        elif low > 0:
            health = "Good"
            health_color = "#2563eb"
            health_desc = "Only minor low-priority issues flagged. Overall document quality is good."
        else:
            health = "Excellent"
            health_color = "#16a34a"
            health_desc = "No contextual inconsistencies or contradictions detected in this document."

        # Document type mapping
        doc_type = "Document"
        if "." in source_file:
            doc_type = source_file.split(".")[-1].upper() + " Document"

        # Build JSON Output
        issues_json_list = []
        for idx, i in enumerate(report.issues):
            # Resolve side-by-side locations
            side_by_side = None
            if len(i.object_ids) >= 2:
                obj_a = objects_by_id.get(i.object_ids[0])
                obj_b = objects_by_id.get(i.object_ids[1])
                if obj_a and obj_b:
                    side_by_side = {
                        "location_a": {
                            "page": obj_a.get("page_number", 1),
                            "section": obj_a.get("section_path") or obj_a.get("heading") or "N/A",
                            "text": clean_technical_jargon(obj_a.get("text", "")).strip()
                        },
                        "location_b": {
                            "page": obj_b.get("page_number", 1),
                            "section": obj_b.get("section_path") or obj_b.get("heading") or "N/A",
                            "text": clean_technical_jargon(obj_b.get("text", "")).strip()
                        }
                    }
            elif len(i.object_ids) == 1:
                obj_a = objects_by_id.get(i.object_ids[0])
                if obj_a:
                    side_by_side = {
                        "location_a": {
                            "page": obj_a.get("page_number", 1),
                            "section": obj_a.get("section_path") or obj_a.get("heading") or "N/A",
                            "text": clean_technical_jargon(i.evidence or obj_a.get("text", "")).strip()
                        }
                    }
            
            # Map description polite rules
            desc_val = i.description
            if not desc_val.endswith(".") and desc_val:
                desc_val += "."

            reason_val = f"Potential discrepancy in mapped statements across document sections."
            if "numeric" in i.category.lower():
                reason_val = "Different numerical values are cited for the same metric."
            elif "reference" in i.category.lower():
                reason_val = "Cross-reference link points to a non-existent heading or page number."
            elif "terminology" in i.category.lower():
                reason_val = "Different naming terms appear to represent the same concept."

            # Polite business manual verification instructions
            manual_ver = "Please verify the correct value."
            if "numeric" in i.category.lower():
                manual_ver = "Please verify which number is accurate."
            elif "contradiction" in i.category.lower():
                manual_ver = "Please verify which statement represents the correct fact."
            elif "terminology" in i.category.lower():
                manual_ver = "Please verify the preferred naming convention."
            elif "reference" in i.category.lower():
                manual_ver = "Please verify the section outlines and page sequences."

            issues_json_list.append({
                "id": f"ISSUE-{idx+1:03d}",
                "category": i.category,
                "severity": i.severity,
                "description": desc_val,
                "evidence": i.evidence,
                "page_numbers": i.page_numbers,
                "section_path": i.section_path or "Root Document",
                "reason": reason_val,
                "manual_verification": manual_ver,
                "side_by_side": side_by_side,
                "object_ids": i.object_ids
            })

        json_data = {
            "document_id": report.document_id,
            "source_file": report.source_file,
            "created_time": report.created_time,
            "summary": {
                "document_name": source_file,
                "document_type": doc_type,
                "pages_analysed": page_count,
                "total_segments": total_segments,
                "processing_time": processing_time,
                "analysis_completed_on": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
                "total_issues": total,
                "high_severity": high,
                "medium_severity": med,
                "low_severity": low,
                "overall_health": health,
                "health_description": health_desc,
                "categories_distribution": categories_distribution,
                "status": "Completed Successfully"
            },
            "issues": issues_json_list
        }
        
        json_path = output_dir / "report.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(json_data, f, indent=2, ensure_ascii=False)
            
        # Save Developer HTML Report
        html_path = output_dir / "report.html"
        html_content = ReportGenerator._build_developer_html(json_data)
        html_path.write_text(html_content, encoding="utf-8")

        # Save Business HTML Report
        business_html_path = output_dir / "business_report.html"
        business_html_content = ReportGenerator._build_business_html(json_data)
        business_html_path.write_text(business_html_content, encoding="utf-8")
        
        return json_path, html_path

    @staticmethod
    def _build_developer_html(data: dict) -> str:
        """Simple HTML output containing full technical developer details."""
        summary = data["summary"]
        issues = data["issues"]
        
        issues_html = []
        for idx, i in enumerate(issues):
            sev_class = f"priority-{i['severity'].lower()}"
            badge_cls = "badge-danger" if i['severity'] == "High" else "badge-warning" if i['severity'] == "Medium" else "badge-secondary"
            
            issues_html.append(
                f"<div class='card issue-card {sev_class}' data-category='{i['category']}'>"
                f"  <div class='issue-header'>"
                f"    <div class='issue-idx'>{i['id']}</div>"
                f"    <span class='badge {badge_cls}'>{i['severity']} Priority</span>"
                f"  </div>"
                f"  <div class='issue-grid'>"
                f"    <div class='issue-row'><strong>Category</strong><span>{i['category']}</span></div>"
                f"    <div class='issue-row'><strong>Description</strong><span>{i['description']}</span></div>"
                f"    <div class='issue-row'><strong>Location</strong><span>Page {', '.join(map(str, i['page_numbers']))} | Section: {i['section_path']}</span></div>"
                f"    <div class='issue-row'><strong>Evidence</strong><pre style='white-space:pre-wrap;'>{i['evidence']}</pre></div>"
                f"    <div class='issue-row'><strong>Object IDs</strong><span>{', '.join(i['object_ids'])}</span></div>"
                f"  </div>"
                f"</div>"
            )
            
        issues_list_str = "".join(issues_html) if issues_html else "<div class='card' style='text-align:center;'>No issues found.</div>"

        return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Developer Audit Report - {data['document_id']}</title>
  <style>
    body {{ font-family: sans-serif; background: #fafafa; padding: 20px; color: #333; }}
    .container {{ max-width: 900px; margin: 0 auto; }}
    .card {{ background: #fff; border: 1px solid #ddd; padding: 15px; border-radius: 8px; margin-bottom: 15px; }}
    .issue-card {{ border-left: 5px solid #ccc; }}
    .priority-high {{ border-left-color: #d9534f; }}
    .priority-medium {{ border-left-color: #f0ad4e; }}
    .priority-low {{ border-left-color: #5bc0de; }}
    .issue-header {{ display: flex; justify-content: space-between; }}
    .badge {{ padding: 3px 8px; border-radius: 4px; color: #fff; font-size: 11px; }}
    .badge-danger {{ background: #d9534f; }}
    .badge-warning {{ background: #f0ad4e; }}
    .badge-secondary {{ background: #777; }}
    .issue-row {{ display: grid; grid-template-columns: 150px 1fr; margin-top: 8px; }}
  </style>
</head>
<body>
  <div class="container">
    <h2>Developer Consistency Report</h2>
    <div class="card">
      <p>Source file: {data['source_file']}</p>
      <p>Total issues: {summary['total_issues']}</p>
    </div>
    <div id="issues">
      {issues_list_str}
    </div>
  </div>
</body>
</html>
"""

    @staticmethod
    def _build_business_html(data: dict) -> str:
        """EY/Deloitte-style Consulting Enterprise Audit Report."""
        sum_data = data["summary"]
        issues = data["issues"]
        
        health_color = "#16a34a"
        if sum_data["overall_health"] == "Critical":
            health_color = "#ef4444"
        elif sum_data["overall_health"] == "Needs Review":
            health_color = "#d97706"
        elif sum_data["overall_health"] == "Good":
            health_color = "#2563eb"
            
        # Category Dashboard Grid
        categories_html = []
        for cat, cnt in sum_data["categories_distribution"].items():
            active_class = "category-has-issues" if cnt > 0 else ""
            badge_color = "#ef4444" if cnt > 3 else "#d97706" if cnt > 0 else "#64748b"
            categories_html.append(
                f"<div class='category-card {active_class}'>"
                f"  <div class='category-header'>"
                f"    <span class='category-name'>{cat}</span>"
                f"    <span class='category-count' style='background-color: {badge_color}'>{cnt}</span>"
                f"  </div>"
                f"</div>"
            )
        categories_str = "".join(categories_html)

        # Issues Cards HTML
        issues_html = []
        for idx, i in enumerate(issues):
            sev_class = f"priority-{i['severity'].lower()}"
            badge_cls = "badge-critical" if i['severity'] == "High" else "badge-review" if i['severity'] == "Medium" else "badge-info"
            priority_label = "High Priority" if i['severity'] == "High" else "Medium Priority" if i['severity'] == "Medium" else "Low Priority"
            
            # Format comparison visual
            comparison_html = ""
            sbs = i.get("side_by_side")
            if sbs and "location_b" in sbs:
                loc_a = sbs["location_a"]
                loc_b = sbs["location_b"]
                comparison_html = (
                    f"<div class='comparison-grid'>"
                    f"  <div class='comparison-col'>"
                    f"    <div class='comp-header'>LOCATION A</div>"
                    f"    <div class='comp-meta'>Page {loc_a['page']} | Section: {loc_a['section']}</div>"
                    f"    <div class='comp-content'>\"{loc_a['text']}\"</div>"
                    f"  </div>"
                    f"  <div class='comparison-arrow'>➔</div>"
                    f"  <div class='comparison-col'>"
                    f"    <div class='comp-header'>LOCATION B</div>"
                    f"    <div class='comp-meta'>Page {loc_b['page']} | Section: {loc_b['section']}</div>"
                    f"    <div class='comp-content'>\"{loc_b['text']}\"</div>"
                    f"  </div>"
                    f"</div>"
                )
            elif sbs and "location_a" in sbs:
                loc_a = sbs["location_a"]
                comparison_html = (
                    f"<div class='comparison-grid single-location'>"
                    f"  <div class='comparison-col'>"
                    f"    <div class='comp-header'>LOCATION CITATION</div>"
                    f"    <div class='comp-meta'>Page {loc_a['page']} | Section: {loc_a['section']}</div>"
                    f"    <div class='comp-content'>\"{loc_a['text']}\"</div>"
                    f"  </div>"
                    f"</div>"
                )
            else:
                quote_val = i.get("evidence", "").strip().replace('"', '')
                comparison_html = f"<div class='evidence-quote'>\"{quote_val}\"</div>"

            issues_html.append(
                f"<div class='issue-item {sev_class}' data-category='{i['category']}' data-priority='{i['severity']}'>"
                f"  <div class='issue-item-header'>"
                f"    <div class='issue-id-cat'>"
                f"      <span class='issue-id-label'>{i['id']}</span>"
                f"      <span class='issue-category-label'>{i['category']}</span>"
                f"    </div>"
                f"    <span class='badge {badge_cls}'>{priority_label}</span>"
                f"  </div>"
                f"  <div class='issue-body-grid'>"
                f"    <div class='issue-field-row'>"
                f"      <span class='issue-field-title'>Observation</span>"
                f"      <span class='issue-field-desc'>{i['description']}</span>"
                f"    </div>"
                f"    <div class='issue-field-row'>"
                f"      <span class='issue-field-title'>References</span>"
                f"      <span class='issue-field-desc'>Page(s): {', '.join(map(str, i['page_numbers']))} | Section Path: {i['section_path']}</span>"
                f"    </div>"
                f"    <div class='issue-field-row'>"
                f"      <span class='issue-field-title'>Document Evidence</span>"
                f"      <div class='issue-field-desc'>{comparison_html}</div>"
                f"    </div>"
                f"    <div class='issue-field-row'>"
                f"      <span class='issue-field-title'>Reasoning</span>"
                f"      <span class='issue-field-desc'>{i['reason']}</span>"
                f"    </div>"
                f"    <div class='issue-field-row'>"
                f"      <span class='issue-field-title'>Manual Action Recommended</span>"
                f"      <span class='issue-field-desc action-recommended-text'>{i['manual_verification']}</span>"
                f"    </div>"
                f"  </div>"
                f"</div>"
            )
            
        issues_str = "".join(issues_html) if issues_html else "<div class='no-issues-found'>No inconsistencies or potential contradictions detected in this document.</div>"

        # Unique categories for JS filters
        filter_buttons = ["<button class='filter-btn active' onclick='setCategoryFilter(\"all\")'>All Categories</button>"]
        for cat in sum_data["categories_distribution"].keys():
            filter_buttons.append(f"<button class='filter-btn' onclick='setCategoryFilter(\"{cat}\")'>{cat}</button>")
        filter_buttons_str = "".join(filter_buttons)

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Document Quality & Consistency Audit</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&display=swap');
    
    :root {{
      --primary: #0a192f;
      --secondary: #cca43b;
      --bg: #f8fafc;
      --text: #1e293b;
      --border: #e2e8f0;
      --card-bg: #ffffff;
      --critical: #ef4444;
      --warning: #f59e0b;
      --info: #2563eb;
      --success: #16a34a;
    }}

    body {{
      font-family: 'Outfit', sans-serif;
      background-color: var(--bg);
      color: var(--text);
      margin: 0;
      padding: 0;
      line-height: 1.5;
    }}

    .audit-container {{
      max-width: 1100px;
      margin: 0 auto;
      padding: 40px 20px;
    }}

    /* Title Block */
    .audit-title-block {{
      background: linear-gradient(135deg, var(--primary) 0%, #112240 100%);
      color: #fff;
      border-radius: 16px;
      padding: 40px;
      margin-bottom: 30px;
      box-shadow: 0 10px 25px -5px rgba(0,0,0,0.1);
      border-bottom: 5px solid var(--secondary);
    }}

    .audit-title-block h1 {{
      margin: 0 0 10px 0;
      font-size: 32px;
      font-weight: 700;
      letter-spacing: -0.5px;
    }}

    .audit-title-block p {{
      margin: 0;
      color: #94a3b8;
      font-size: 15px;
    }}

    /* Stats Grid */
    .summary-stats-grid {{
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 20px;
      margin-bottom: 30px;
    }}

    .summary-card {{
      background-color: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 20px;
      text-align: center;
      box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
      transition: transform 0.2s;
    }}
    .summary-card:hover {{
      transform: translateY(-2px);
    }}

    .summary-val {{
      font-size: 32px;
      font-weight: 700;
      color: var(--primary);
      margin-bottom: 4px;
    }}

    .summary-lbl {{
      font-size: 11px;
      font-weight: 600;
      color: #64748b;
      text-transform: uppercase;
      letter-spacing: 1px;
    }}

    /* Audit Details */
    .details-box {{
      background-color: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 24px;
      margin-bottom: 35px;
      box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
      display: grid;
      grid-template-columns: 1.5fr 1fr;
      gap: 30px;
    }}

    .details-list {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 15px;
    }}

    .details-item {{
      border-bottom: 1px solid #f1f5f9;
      padding-bottom: 8px;
    }}

    .details-label {{
      display: block;
      font-size: 11px;
      color: #64748b;
      font-weight: 600;
      text-transform: uppercase;
    }}

    .details-val {{
      font-size: 14.5px;
      color: var(--text);
      font-weight: 500;
      margin-top: 2px;
    }}

    .health-status-box {{
      border-left: 6px solid {health_color};
      padding-left: 20px;
      display: flex;
      flex-direction: column;
      justify-content: center;
    }}

    .health-title {{
      font-size: 18px;
      font-weight: 700;
      color: var(--primary);
      margin: 0 0 5px 0;
    }}

    .health-badge {{
      display: inline-block;
      align-self: flex-start;
      background-color: {health_color};
      color: #fff;
      font-weight: 700;
      font-size: 12px;
      padding: 4px 12px;
      border-radius: 6px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      margin-bottom: 8px;
    }}

    .health-desc {{
      margin: 0;
      font-size: 13.5px;
      color: #475569;
    }}

    /* Categories Dashboard */
    .dashboard-title {{
      font-size: 20px;
      font-weight: 700;
      color: var(--primary);
      margin-bottom: 18px;
      border-bottom: 2px solid var(--border);
      padding-bottom: 8px;
    }}

    .categories-grid {{
      display: grid;
      grid-template-columns: repeat(5, 1fr);
      gap: 12px;
      margin-bottom: 35px;
    }}

    .category-card {{
      background-color: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 15px;
      box-shadow: 0 2px 4px -1px rgba(0,0,0,0.03);
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      transition: all 0.2s;
    }}
    
    .category-card.category-has-issues {{
      border-color: #cbd5e1;
      background-color: #f8fafc;
    }}

    .category-header {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 6px;
    }}

    .category-name {{
      font-size: 12.5px;
      font-weight: 600;
      color: #475569;
      line-height: 1.3;
    }}

    .category-count {{
      font-size: 11px;
      font-weight: 700;
      color: #fff;
      width: 20px;
      height: 20px;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
    }}

    /* Filters Bar */
    .filters-bar {{
      display: flex;
      flex-direction: column;
      gap: 12px;
      margin-bottom: 24px;
      background-color: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 16px;
      box-shadow: 0 2px 4px -1px rgba(0,0,0,0.03);
    }}

    .filter-section {{
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
    }}

    .filter-section-title {{
      font-size: 12px;
      font-weight: 700;
      color: #64748b;
      text-transform: uppercase;
      margin-right: 5px;
    }}

    .filter-btn {{
      background: #fff;
      border: 1px solid #cbd5e1;
      border-radius: 6px;
      padding: 5px 12px;
      font-size: 12.5px;
      font-weight: 500;
      cursor: pointer;
      transition: all 0.2s;
      font-family: inherit;
    }}
    .filter-btn:hover {{
      background-color: #f1f5f9;
    }}
    .filter-btn.active {{
      background-color: var(--primary);
      color: #fff;
      border-color: var(--primary);
    }}

    .search-input {{
      border: 1px solid #cbd5e1;
      border-radius: 6px;
      padding: 6px 12px;
      font-size: 13px;
      font-family: inherit;
      flex-grow: 1;
      min-width: 250px;
    }}

    /* Issues Cards styling */
    .issue-item {{
      background-color: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 24px;
      margin-bottom: 24px;
      box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);
      border-left: 6px solid #94a3b8;
      transition: transform 0.2s;
    }}
    .issue-item:hover {{
      transform: translateY(-1px);
    }}

    .issue-item.priority-high {{
      border-left-color: var(--critical);
    }}
    .issue-item.priority-medium {{
      border-left-color: var(--warning);
    }}
    .issue-item.priority-low {{
      border-left-color: #64748b;
    }}

    .issue-item-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-bottom: 1px solid #f1f5f9;
      padding-bottom: 12px;
      margin-bottom: 18px;
    }}

    .issue-id-cat {{
      display: flex;
      align-items: center;
      gap: 12px;
    }}

    .issue-id-label {{
      font-size: 15px;
      font-weight: 700;
      color: var(--primary);
    }}

    .issue-category-label {{
      font-size: 12.5px;
      font-weight: 600;
      color: #475569;
      background-color: #f1f5f9;
      padding: 2px 8px;
      border-radius: 4px;
    }}

    .badge {{
      font-size: 11px;
      font-weight: 700;
      padding: 4px 10px;
      border-radius: 5px;
      text-transform: uppercase;
      color: #fff;
    }}
    .badge-critical {{ background-color: var(--critical); }}
    .badge-review {{ background-color: var(--warning); }}
    .badge-info {{ background-color: #64748b; }}

    .issue-body-grid {{
      display: flex;
      flex-direction: column;
      gap: 16px;
    }}

    .issue-field-row {{
      display: grid;
      grid-template-columns: 200px 1fr;
      gap: 20px;
      font-size: 14px;
    }}

    .issue-field-title {{
      font-weight: 600;
      color: #475569;
    }}

    .issue-field-desc {{
      color: var(--text);
    }}

    .action-recommended-text {{
      color: var(--info);
      font-weight: 500;
    }}

    /* Side-by-side location view */
    .comparison-grid {{
      display: grid;
      grid-template-columns: 1fr auto 1fr;
      gap: 15px;
      align-items: stretch;
      margin-top: 4px;
    }}

    .comparison-grid.single-location {{
      grid-template-columns: 1fr;
    }}

    .comparison-col {{
      background-color: #f8fafc;
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 14px 16px;
    }}

    .comp-header {{
      font-size: 10px;
      font-weight: 700;
      color: #64748b;
      letter-spacing: 1px;
      margin-bottom: 4px;
    }}

    .comp-meta {{
      font-size: 12px;
      font-weight: 500;
      color: var(--primary);
      margin-bottom: 8px;
    }}

    .comp-content {{
      font-size: 13.5px;
      color: var(--text);
      font-style: italic;
      background-color: #fff;
      border: 1px solid #f1f5f9;
      padding: 8px 12px;
      border-radius: 6px;
      border-left: 3px solid var(--secondary);
      line-height: 1.45;
    }}

    .comparison-arrow {{
      font-size: 20px;
      color: #94a3b8;
      display: flex;
      align-items: center;
      justify-content: center;
    }}

    .evidence-quote {{
      font-size: 13.5px;
      font-style: italic;
      background-color: #f8fafc;
      border-left: 3px solid var(--secondary);
      padding: 10px 14px;
      border-radius: 6px;
      line-height: 1.45;
    }}

    .no-issues-found {{
      background-color: #fff;
      border: 1px dashed var(--border);
      border-radius: 12px;
      padding: 50px;
      text-align: center;
      color: #64748b;
      font-size: 15px;
    }}
  </style>
</head>
<body>

  <div class="audit-container">
    
    <!-- Title block -->
    <div class="audit-title-block">
      <h1>Document Integrity & Consistency Audit</h1>
      <p>Quality assurance review for factual coordination and section sequence consistency.</p>
    </div>

    <!-- Details Box & Document Health -->
    <div class="details-box">
      <div class="details-list">
        <div class="details-item">
          <span class="details-label">Document Name</span>
          <span class="details-val">{sum_data['document_name']}</span>
        </div>
        <div class="details-item">
          <span class="details-label">Document Type</span>
          <span class="details-val">{sum_data['document_type']}</span>
        </div>
        <div class="details-item">
          <span class="details-label">Pages Analysed</span>
          <span class="details-val">{sum_data['pages_analysed']}</span>
        </div>
        <div class="details-item">
          <span class="details-label">Processing Time</span>
          <span class="details-val">{sum_data['processing_time']}</span>
        </div>
        <div class="details-item" style="grid-column: span 2;">
          <span class="details-label">Audit Completed On</span>
          <span class="details-val">{sum_data['analysis_completed_on']}</span>
        </div>
      </div>
      
      <div class="health-status-box">
        <span class="health-badge">Health Status: {sum_data['overall_health']}</span>
        <div class="health-title">{sum_data['overall_health']} Rating</div>
        <p class="health-desc">{sum_data['health_description']}</p>
      </div>
    </div>

    <!-- Stats summary grid -->
    <div class="summary-stats-grid">
      <div class="summary-card">
        <div class="summary-val">{sum_data['total_issues']}</div>
        <div class="summary-lbl">Potential Discrepancies</div>
      </div>
      <div class="summary-card" style="border-top: 4px solid var(--critical)">
        <div class="summary-val" style="color: var(--critical)">{sum_data['high_severity']}</div>
        <div class="summary-lbl">High Priority</div>
      </div>
      <div class="summary-card" style="border-top: 4px solid var(--warning)">
        <div class="summary-val" style="color: var(--warning)">{sum_data['medium_severity']}</div>
        <div class="summary-lbl">Medium Priority</div>
      </div>
      <div class="summary-card" style="border-top: 4px solid #64748b">
        <div class="summary-val" style="color: #64748b">{sum_data['low_severity']}</div>
        <div class="summary-lbl">Low Priority</div>
      </div>
    </div>

    <!-- Category Dashboard Grid -->
    <h3 class="dashboard-title">Audit Categories Summary</h3>
    <div class="categories-grid">
      {categories_str}
    </div>

    <!-- Search & Filter Controls -->
    <h3 class="dashboard-title">Detailed Audit Findings</h3>
    <div class="filters-bar">
      <div class="filter-section">
        <span class="filter-section-title">Search:</span>
        <input type="text" id="audit-search" class="search-input" placeholder="Search observation, reasoning or page numbers..." oninput="triggerSearchFilter()"/>
      </div>
      <div class="filter-section">
        <span class="filter-section-title">Priority:</span>
        <button class="filter-btn active" id="btn-pri-all" onclick="setPriorityFilter('all')">All Priorities</button>
        <button class="filter-btn" id="btn-pri-high" onclick="setPriorityFilter('High')">High</button>
        <button class="filter-btn" id="btn-pri-medium" onclick="setPriorityFilter('Medium')">Medium</button>
        <button class="filter-btn" id="btn-pri-low" onclick="setPriorityFilter('Low')">Low</button>
      </div>
      <div class="filter-section" style="margin-top: 4px;">
        <span class="filter-section-title">Category:</span>
        {filter_buttons_str}
      </div>
    </div>

    <!-- Detailed issue items container -->
    <div id="audit-issues-container">
      {issues_str}
    </div>

  </div>

  <script>
    var currentCategory = "all";
    var currentPriority = "all";
    var currentSearch = "";

    function setCategoryFilter(cat) {{
      currentCategory = cat;
      // Active state button updates
      var btns = document.querySelectorAll(".filters-bar .filter-btn");
      btns.forEach(btn => {{
        if (btn.getAttribute("onclick").includes("setCategoryFilter") && 
            btn.getAttribute("onclick").includes('"' + cat + '"')) {{
          btn.classList.add("active");
        }} else if (btn.getAttribute("onclick").includes("setCategoryFilter")) {{
          btn.classList.remove("active");
        }}
      }});
      applyAllFilters();
    }}

    function setPriorityFilter(pri) {{
      currentPriority = pri;
      var btns = ["all", "High", "Medium", "Low"];
      btns.forEach(b => {{
        var btn = document.getElementById("btn-pri-" + b.toLowerCase());
        if (btn) {{
          if (b === pri) btn.classList.add("active");
          else btn.classList.remove("active");
        }}
      }});
      applyAllFilters();
    }}

    function triggerSearchFilter() {{
      currentSearch = document.getElementById("audit-search").value.toLowerCase();
      applyAllFilters();
    }}

    function applyAllFilters() {{
      var cards = document.getElementsByClassName("issue-item");
      for (var i = 0; i < cards.length; i++) {{
        var cat = cards[i].getAttribute("data-category");
        var pri = cards[i].getAttribute("data-priority");
        var text = cards[i].innerText.toLowerCase();
        
        var matchCat = (currentCategory === "all" || cat === currentCategory);
        var matchPri = (currentPriority === "all" || pri === currentPriority);
        var matchSearch = (currentSearch === "" || text.indexOf(currentSearch) > -1);
        
        if (matchCat && matchPri && matchSearch) {{
          cards[i].style.display = "block";
        }} else {{
          cards[i].style.display = "none";
        }}
      }}
    }}
  </script>
</body>
</html>
"""
