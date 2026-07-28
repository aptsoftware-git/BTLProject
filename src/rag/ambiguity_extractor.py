import re
import json
import logging
import os
from pathlib import Path
from typing import List, Dict, Any, Optional

from src.rag.config import RagConfig
from src.rag.ollama_client import OllamaClient

logger = logging.getLogger("pipeline")

class AmbiguityExtractor:
    """
    Phase 2A: Local LLM Claims & Structural Metadata Extractor.
    Extracts atomic factual claims, entities, dates, policies, modal obligations,
    permissions, conditional constraints, definitions, and cross-references
    from semantic chunks, writing structured indexes to 10_claim_extraction/.
    """

    def __init__(self, config: Optional[RagConfig] = None):
        self.config = config or RagConfig()
        self.model_name = getattr(self.config, "ollama_model", os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:32b"))
        
        # Instantiate OllamaClient using host from configuration
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

    def _extract_fallback_knowledge(self, chunk_id: str, text: str) -> dict:
        """Regex-based fallback metadata extractor in case Ollama is offline."""
        claims = []
        entities = []
        dates = []
        numbers = []
        policies = []
        obligations = []
        permissions = []
        conditions = []
        definitions = []
        references = []
        
        # Factual Claims (split sentences)
        sentences = [s.strip() for s in re.split(r'[.!?]+', text) if len(s.strip()) > 12]
        for idx, s in enumerate(sentences):
            claims.append({
                "claim_id": f"{chunk_id}_claim_{idx:03d}",
                "text": s.replace("Document Section: Root Content: ", ""),
                "type": "fact"
            })
            
        # Capitalized Words as Entities
        words = re.findall(r'\b[A-Z][a-z]+\b', text)
        unique_words = sorted(list(set(words)))
        for idx, w in enumerate(unique_words[:4]):
            entities.append({
                "entity_id": f"{chunk_id}_ent_{idx:03d}",
                "text": w,
                "type": "Organization" if "company" in text.lower() or "department" in text.lower() else "Person"
            })
            
        # Numerical Values
        percentages = re.findall(r'\b\d+(?:\.\d+)?%\b', text)
        money = re.findall(r'\$\d+(?:\.\d+)?\b', text)
        durations = re.findall(r'\b\d+\s+(?:minutes?|hours?|days?|months?|years?)\b', text, re.IGNORECASE)
        for idx, p in enumerate(percentages):
            numbers.append({
                "number_id": f"{chunk_id}_num_{idx:03d}",
                "text": p,
                "type": "percentage"
            })
        for idx, m in enumerate(money):
            numbers.append({
                "number_id": f"{chunk_id}_num_{len(percentages)+idx:03d}",
                "text": m,
                "type": "money"
            })
        for idx, d in enumerate(durations):
            numbers.append({
                "number_id": f"{chunk_id}_num_{len(percentages)+len(money)+idx:03d}",
                "text": d,
                "type": "duration"
            })

        # Dates
        dates_found = re.findall(r'\b(?:yesterday|today|tomorrow|next\s+month|last\s+year)\b', text, re.IGNORECASE)
        for idx, dt in enumerate(dates_found):
            dates.append({
                "date_id": f"{chunk_id}_date_{idx:03d}",
                "text": dt,
                "type": "relative"
            })

        # Modal statements
        if any(m in text.lower() for m in ["must", "shall", "required", "mandatory"]):
            obligations.append({
                "obligation_id": f"{chunk_id}_ob_000",
                "text": text
            })
        if any(m in text.lower() for m in ["may", "can", "optional", "allowed"]):
            permissions.append({
                "permission_id": f"{chunk_id}_perm_000",
                "text": text
            })
        if any(c in text.lower() for c in ["if", "unless", "except", "provided that"]):
            conditions.append({
                "condition_id": f"{chunk_id}_cond_000",
                "text": text
            })

        # References
        refs = re.findall(r'\b(?:Figure \d+|Table \d+|Section \d+)\b', text)
        for idx, r in enumerate(refs):
            references.append({
                "reference_id": f"{chunk_id}_ref_{idx:03d}",
                "target": r,
                "type": "figure" if "Figure" in r else ("table" if "Table" in r else "section")
            })
            
        return {
            "chunk_id": chunk_id,
            "claims": claims,
            "entities": entities,
            "dates": dates,
            "numbers": numbers,
            "policies": policies,
            "obligations": obligations,
            "permissions": permissions,
            "conditions": conditions,
            "definitions": definitions,
            "references": references,
            "confidence": 0.50
        }

    def run_extraction(self, job_dir: Path, doc_id: str) -> None:
        logger.info(f"Starting Phase 2A Claim Extraction for job: {doc_id}")
        
        # Cache hit check
        cache_claims_path = job_dir / "10_claim_extraction" / "chunk_claims.json"
        if cache_claims_path.exists() and cache_claims_path.stat().st_size > 0:
            logger.info(f"[CACHE HIT] Claim extractions already exist for job {doc_id}. Skipping re-extraction.")
            return

        # 1. Load document chunks (Master list containing all chunks)
        chunks_json_path = job_dir / "06_chunks" / "document_chunks.json"
        if not chunks_json_path.exists():
            chunks_json_path = job_dir / "document_chunks.json"
            
        chunks_master = []
        if chunks_json_path.exists():
            try:
                with open(chunks_json_path, "r", encoding="utf-8") as f:
                    chunks_data = json.load(f)
                    chunks_master = chunks_data.get("chunks", [])
            except Exception as e:
                logger.error(f"Failed to load document chunks master list: {e}")
                
        if not chunks_master:
            logger.error("No semantic chunks found to extract claims from.")
            return
            
        # Check connection to Ollama server
        ollama_active = False
        try:
            ollama_active = self.ollama_client.check_connection()
        except Exception:
            pass
            
        if not ollama_active:
            logger.warning("Ollama connection failed. Falling back to deterministic regex-based claim extractor.")
            
        extractions = {}
        
        system_prompt = (
            "You are a precise semantic knowledge extraction engine.\n"
            "You extract structural elements from document chunks and return ONLY a valid JSON object matching the requested schema.\n"
            "Do not output any markdown formatting (like ```json), explanations, or conversational text.\n"
            "Your response must be parseable directly by `json.loads` in Python."
        )
        
        def _process_single_chunk(ch):
            meta = ch.get("metadata", {})
            chunk_id = meta.get("chunk_id")
            text = ch.get("content", "")
            if not chunk_id:
                return None, None
            
            # Fast-path fallback for short / structural chunks (< 20 words) or when Ollama is inactive
            if len(text.split()) < 20 or not ollama_active:
                return chunk_id, self._extract_fallback_knowledge(chunk_id, text)
            
            prompt = f"""Extract structural metadata from this document chunk.
Chunk ID: {chunk_id}
Text:
{text}

Return the extracted values STRICTLY as a single JSON object.
Do NOT wrap the output in markdown fences (like ```json), do not include comments, do not include explanations.

Requested JSON Schema:
{{
    "chunk_id": "{chunk_id}",
    "claims": [
        {{
            "claim_id": "{chunk_id}_claim_000",
            "text": "claim text",
            "type": "fact"
        }}
    ],
    "entities": [
        {{
            "entity_id": "{chunk_id}_ent_000",
            "text": "entity name",
            "type": "Person|Organization|Department|Product|Location|System|Team|Project|Policy|Application"
        }}
    ],
    "dates": [
        {{
            "date_id": "{chunk_id}_date_000",
            "text": "date text",
            "type": "explicit|relative"
        }}
    ],
    "numbers": [
        {{
            "number_id": "{chunk_id}_num_000",
            "text": "number text",
            "type": "percentage|money|quantity|duration|limit"
        }}
    ],
    "policies": [
        {{
            "policy_id": "{chunk_id}_pol_000",
            "text": "policy statement"
        }}
    ],
    "obligations": [
        {{
            "obligation_id": "{chunk_id}_ob_000",
            "text": "obligation statement containing must|shall|required|mandatory"
        }}
    ],
    "permissions": [
        {{
            "permission_id": "{chunk_id}_perm_000",
            "text": "permission statement containing may|can|optional|allowed"
        }}
    ],
    "conditions": [
        {{
            "condition_id": "{chunk_id}_cond_000",
            "text": "conditional statement containing if|unless|except|provided that"
        }}
    ],
    "definitions": [
        {{
            "definition_id": "{chunk_id}_def_000",
            "term": "defined term",
            "definition": "concept definition"
        }}
    ],
    "references": [
        {{
            "reference_id": "{chunk_id}_ref_000",
            "target": "reference target text",
            "type": "section|appendix|figure|table"
        }}
    ],
    "confidence": 0.95
}}
"""
            try:
                logger.info(f"Running LLM Claim Extraction for chunk: {chunk_id}")
                resp = self.ollama_client.generate(
                    model=self.model_name,
                    prompt=prompt,
                    system=system_prompt
                )
                parsed = self._clean_and_parse_json(resp)
                return chunk_id, parsed
            except Exception as e:
                logger.error(f"Failed LLM extraction for {chunk_id}: {e}. Falling back to regex.")
                return chunk_id, self._extract_fallback_knowledge(chunk_id, text)

        from concurrent.futures import ThreadPoolExecutor, as_completed
        max_workers = 4 if ollama_active else 8
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_chunk = {executor.submit(_process_single_chunk, ch): ch for ch in chunks_master}
            for future in as_completed(future_to_chunk):
                cid, ext = future.result()
                if cid:
                    extractions[cid] = ext

        # Ensure directory exists
        claim_dir = job_dir / "10_claim_extraction"
        claim_dir.mkdir(parents=True, exist_ok=True)

        # 2. Build Claim Index (claim_index.json)
        claims_list = []
        for cid, ext in extractions.items():
            for c in ext.get("claims", []):
                claims_list.append({
                    "claim_id": c.get("claim_id"),
                    "chunk_id": cid,
                    "text": c.get("text"),
                    "type": c.get("type", "fact")
                })
        with open(claim_dir / "claim_index.json", "w", encoding="utf-8") as f:
            json.dump({"claims": claims_list}, f, indent=2, ensure_ascii=False)

        # 3. Build Chunk Claims (chunk_claims.json)
        chunk_claims_list = []
        for ch in chunks_master:
            meta = ch.get("metadata", {})
            cid = meta.get("chunk_id")
            if not cid:
                continue
            
            hierarchy = meta.get("hierarchy_path", [])
            heading_path = " -> ".join(hierarchy) if hierarchy else (meta.get("heading") or "Root")
            
            chunk_claims_list.append({
                "chunk_id": cid,
                "page": meta.get("page_number", 1),
                "heading_path": heading_path,
                "text": ch.get("content", ""),
                "extraction": extractions.get(cid, {})
            })
        with open(claim_dir / "chunk_claims.json", "w", encoding="utf-8") as f:
            json.dump({"chunks": chunk_claims_list}, f, indent=2, ensure_ascii=False)

        # 4. Build Entity Index (entity_index.json)
        entities_list = []
        for cid, ext in extractions.items():
            claims = ext.get("claims", [])
            for ent in ext.get("entities", []):
                # Map to originating claim
                match_claim = None
                ent_text = ent.get("text", "").lower()
                for c in claims:
                    if ent_text in c.get("text", "").lower():
                        match_claim = c.get("claim_id")
                        break
                if not match_claim and claims:
                    match_claim = claims[0].get("claim_id")
                    
                entities_list.append({
                    "entity_id": ent.get("entity_id"),
                    "text": ent.get("text"),
                    "type": ent.get("type"),
                    "chunk_id": cid,
                    "claim_id": match_claim
                })
        with open(claim_dir / "entity_index.json", "w", encoding="utf-8") as f:
            json.dump({"entities": sorted(entities_list, key=lambda x: x["text"])}, f, indent=2, ensure_ascii=False)

        # 5. Build Policy Index (policy_index.json)
        policies_list = []
        for cid, ext in extractions.items():
            for p in ext.get("policies", []):
                policies_list.append({
                    "policy_id": p.get("policy_id"),
                    "text": p.get("text"),
                    "type": "policy",
                    "chunk_id": cid
                })
            for ob in ext.get("obligations", []):
                policies_list.append({
                    "policy_id": ob.get("obligation_id"),
                    "text": ob.get("text"),
                    "type": "obligation",
                    "chunk_id": cid
                })
            for perm in ext.get("permissions", []):
                policies_list.append({
                    "policy_id": perm.get("permission_id"),
                    "text": perm.get("text"),
                    "type": "permission",
                    "chunk_id": cid
                })
        with open(claim_dir / "policy_index.json", "w", encoding="utf-8") as f:
            json.dump({"policies": policies_list}, f, indent=2, ensure_ascii=False)

        # 6. Build Reference Index (reference_index.json)
        references_list = []
        for cid, ext in extractions.items():
            for r in ext.get("references", []):
                references_list.append({
                    "reference_id": r.get("reference_id"),
                    "target": r.get("target"),
                    "type": r.get("type"),
                    "chunk_id": cid
                })
        with open(claim_dir / "reference_index.json", "w", encoding="utf-8") as f:
            json.dump({"references": references_list}, f, indent=2, ensure_ascii=False)

        # Calculate statistics
        total_chunks = len(extractions)
        total_claims = len(claims_list)
        total_entities = len(entities_list)
        total_policies = len(policies_list)
        total_references = len(references_list)
        avg_conf = sum(ext.get("confidence", 0.0) for ext in extractions.values()) / max(1, total_chunks)

        # 7. Write claim_statistics.json
        stats_data = {
            "total_chunks": total_chunks,
            "total_claims": total_claims,
            "total_entities": total_entities,
            "total_policies": total_policies,
            "total_references": total_references,
            "average_confidence": round(avg_conf, 4)
        }
        with open(claim_dir / "claim_statistics.json", "w", encoding="utf-8") as f:
            json.dump(stats_data, f, indent=2)

        # 8. Write Markdown Reports
        # claim_index.md
        md_claims = ["# Factual Claims Index\n\n"]
        for ch in chunk_claims_list:
            md_claims.append(f"## Chunk `{ch['chunk_id']}` (Page {ch['page']})\n")
            ext = ch["extraction"]
            for c in ext.get("claims", []):
                md_claims.append(f"- **{c.get('claim_id')}**: {c.get('text')} *(type: {c.get('type')})*\n")
            if not ext.get("claims"):
                md_claims.append("- *No claims extracted.*\n")
            md_claims.append("\n---\n")
        with open(claim_dir / "claim_index.md", "w", encoding="utf-8") as f:
            f.write("".join(md_claims))

        # chunk_claims.md
        md_chunk_claims = ["# Detailed Chunk Claims Extracted\n\n"]
        for ch in chunk_claims_list:
            ext = ch["extraction"]
            md_chunk_claims.append(f"## Chunk {ch['chunk_id']}\n")
            md_chunk_claims.append(f"- **Page**: {ch['page']}\n")
            md_chunk_claims.append(f"- **Heading Path**: {ch['heading_path']}\n")
            md_chunk_claims.append(f"- **Extraction Confidence**: {ext.get('confidence', 0.0):.2f}\n")
            md_chunk_claims.append(f"\n### Original Text\n```\n{ch['text'].strip()}\n```\n")
            
            md_chunk_claims.append("\n### Claims\n")
            for c in ext.get("claims", []):
                md_chunk_claims.append(f"- **{c.get('claim_id')}**: {c.get('text')}\n")
                
            md_chunk_claims.append("\n### Entities\n")
            for e in ext.get("entities", []):
                md_chunk_claims.append(f"- `{e.get('text')}` ({e.get('type')})\n")
                
            md_chunk_claims.append("\n### Policies/Obligations\n")
            for ob in ext.get("obligations", []):
                md_chunk_claims.append(f"- **Obligation**: {ob.get('text')}\n")
            for perm in ext.get("permissions", []):
                md_chunk_claims.append(f"- **Permission**: {perm.get('text')}\n")
                
            md_chunk_claims.append("\n---\n")
        with open(claim_dir / "chunk_claims.md", "w", encoding="utf-8") as f:
            f.write("".join(md_chunk_claims))

        # entity_index.md
        md_entities = ["# Extracted Entity Index\n\n| Entity | Type | Originating Chunk | Originating Claim |\n|:-------|:-----|:------------------|:------------------|\n"]
        for e in entities_list:
            md_entities.append(f"| {e['text']} | {e['type']} | `{e['chunk_id']}` | `{e['claim_id'] or 'N/A'}` |\n")
        with open(claim_dir / "entity_index.md", "w", encoding="utf-8") as f:
            f.write("".join(md_entities))

        # policy_index.md
        md_policies = ["# Policy, Obligation, and Permission Index\n\n| ID | Type | Statement | Chunk ID |\n|:---|:-----|:----------|:---------|\n"]
        for p in policies_list:
            md_policies.append(f"| `{p['policy_id']}` | {p['type']} | {p['text'].strip()} | `{p['chunk_id']}` |\n")
        with open(claim_dir / "policy_index.md", "w", encoding="utf-8") as f:
            f.write("".join(md_policies))

        # reference_index.md
        md_refs = ["# Document References Index\n\n| ID | Target | Type | Chunk ID |\n|:---|:-------|:-----|:---------|\n"]
        for r in references_list:
            md_refs.append(f"| `{r['reference_id']}` | {r['target']} | {r['type']} | `{r['chunk_id']}` |\n")
        with open(claim_dir / "reference_index.md", "w", encoding="utf-8") as f:
            f.write("".join(md_refs))

        # claim_summary.md (Executive overview)
        summary_md = f"""# Structured Knowledge & Claim Extraction Summary

## Executive Overview
- **Total Processed Chunks**: {total_chunks}
- **Total Factual Claims**: {total_claims}
- **Total Extracted Entities**: {total_entities}
- **Total Policies & Obligations**: {total_policies}
- **Total References**: {total_references}
- **Average Extraction Confidence**: {avg_conf * 100:.2f}%

## Extraction Statistics
| Metric | Count |
|:-------|:-----:|
| Processed Semantic Chunks | {total_chunks} |
| Atomic Factual Claims | {total_claims} |
| Extracted Entities | {total_entities} |
| Policy/Obligation Statements | {total_policies} |
| Cross-References | {total_references} |
"""
        with open(claim_dir / "claim_summary.md", "w", encoding="utf-8") as f:
            f.write(summary_md)

        # 9. Generate Interactive Debugger HTML
        html_template = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Claim Inspector Dashboard</title>
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
    
    /* Inputs */
    .controls-panel {
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 20px;
      margin-bottom: 20px;
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
      gap: 15px;
    }
    .control-input {
      padding: 8px 12px;
      border: 1px solid var(--border);
      border-radius: 6px;
      font-size: 13px;
      outline: none;
      width: 100%;
      box-sizing: border-box;
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
      <h2>Claim Inspector</h2>
    </div>
    <ul class="nav-list">
      <li class="nav-item active" onclick="switchTab('tab-overview')">🏠 Overview Dashboard</li>
      <li class="nav-item" onclick="switchTab('tab-chunks')">📦 Chunk Browser</li>
      <li class="nav-item" onclick="switchTab('tab-claims')">📄 Claim Browser</li>
      <li class="nav-item" onclick="switchTab('tab-entities')">👥 Entity Browser</li>
      <li class="nav-item" onclick="switchTab('tab-policies')">⚖️ Policy Browser</li>
      <li class="nav-item" onclick="switchTab('tab-references')">🔗 Reference Browser</li>
      <li class="nav-item" onclick="switchTab('tab-search')">🔎 Search & Filters</li>
    </ul>
  </div>
  
  <div class="main-content">
    
    <!-- 1. Overview Dashboard -->
    <div id="tab-overview" class="content-tab active">
      <h1 style="margin-top:0;">Claim Extraction Dashboard</h1>
      <div class="dashboard-grid">
        <div class="stat-card">
          <div class="stat-title">Total Chunks Processed</div>
          <div class="stat-value" id="d-total-chunks">0</div>
        </div>
        <div class="stat-card">
          <div class="stat-title">Total Factual Claims</div>
          <div class="stat-value" id="d-total-claims">0</div>
        </div>
        <div class="stat-card">
          <div class="stat-title">Total Entities</div>
          <div class="stat-value" id="d-total-entities">0</div>
        </div>
        <div class="stat-card">
          <div class="stat-title">Total Policies & Obligations</div>
          <div class="stat-value" id="d-total-policies">0</div>
        </div>
        <div class="stat-card">
          <div class="stat-title">Total References</div>
          <div class="stat-value" id="d-total-references">0</div>
        </div>
        <div class="stat-card">
          <div class="stat-title">Average LLM Confidence</div>
          <div class="stat-value" id="d-avg-confidence">0%</div>
        </div>
      </div>
    </div>
    
    <!-- 2. Chunk Browser -->
    <div id="tab-chunks" class="content-tab">
      <h1 style="margin-top:0;">Chunk Browser</h1>
      <div class="browser-container">
        <div class="browser-list" id="chunks-list-element"></div>
        <div class="browser-detail" id="chunks-detail-element">
          <div style="color:var(--text-muted); text-align:center; margin:auto;">Select a chunk on the left to inspect its extracted claims</div>
        </div>
      </div>
    </div>
    
    <!-- 3. Claim Browser -->
    <div id="tab-claims" class="content-tab">
      <h1 style="margin-top:0;">Claim Browser</h1>
      <table class="index-table">
        <thead>
          <tr>
            <th>Claim ID</th>
            <th>Source Chunk</th>
            <th>Type</th>
            <th>Statement</th>
          </tr>
        </thead>
        <tbody id="claims-table-body"></tbody>
      </table>
    </div>
    
    <!-- 4. Entity Browser -->
    <div id="tab-entities" class="content-tab">
      <h1 style="margin-top:0;">Entity Browser</h1>
      <table class="index-table">
        <thead>
          <tr>
            <th>Entity</th>
            <th>Type</th>
            <th>Originating Chunk</th>
            <th>Originating Claim ID</th>
          </tr>
        </thead>
        <tbody id="entities-table-body"></tbody>
      </table>
    </div>
    
    <!-- 5. Policy Browser -->
    <div id="tab-policies" class="content-tab">
      <h1 style="margin-top:0;">Policy Browser</h1>
      <table class="index-table">
        <thead>
          <tr>
            <th>Policy ID</th>
            <th>Type</th>
            <th>Statement</th>
            <th>Source Chunk ID</th>
          </tr>
        </thead>
        <tbody id="policies-table-body"></tbody>
      </table>
    </div>
    
    <!-- 6. Reference Browser -->
    <div id="tab-references" class="content-tab">
      <h1 style="margin-top:0;">Reference Browser</h1>
      <table class="index-table">
        <thead>
          <tr>
            <th>Reference ID</th>
            <th>Target</th>
            <th>Type</th>
            <th>Source Chunk ID</th>
          </tr>
        </thead>
        <tbody id="references-table-body"></tbody>
      </table>
    </div>
    
    <!-- 7. Advanced Search & Filters -->
    <div id="tab-search" class="content-tab">
      <h1 style="margin-top:0;">Search & Filters</h1>
      <div class="controls-panel">
        <div>
          <label style="font-size:12px; font-weight:600; color:var(--text-muted);">Text Search (Claims, Entities, Policies)</label>
          <input type="text" id="search-input" class="control-input" placeholder="Type query..." oninput="applySearch()"/>
        </div>
      </div>
      <div id="search-results-container" style="display:flex; flex-direction:column; gap:15px;"></div>
    </div>
    
  </div>

  <script>
    // Injected Data
    var chunks = /* INJECT_CHUNKS */;
    var stats = /* INJECT_STATS */;
    var claims = /* INJECT_CLAIMS */;
    var entities = /* INJECT_ENTITIES */;
    var policies = /* INJECT_POLICIES */;
    var references = /* INJECT_REFERENCES */;
    
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
      else if (tabId === "tab-chunks") targetIdx = 1;
      else if (tabId === "tab-claims") targetIdx = 2;
      else if (tabId === "tab-entities") targetIdx = 3;
      else if (tabId === "tab-policies") targetIdx = 4;
      else if (tabId === "tab-references") targetIdx = 5;
      else if (tabId === "tab-search") targetIdx = 6;
      navItems[targetIdx].classList.add("active");
    };
    
    // 1. Render Dashboard
    document.getElementById("d-total-chunks").innerText = stats.total_chunks;
    document.getElementById("d-total-claims").innerText = stats.total_claims;
    document.getElementById("d-total-entities").innerText = stats.total_entities;
    document.getElementById("d-total-policies").innerText = stats.total_policies;
    document.getElementById("d-total-references").innerText = stats.total_references;
    document.getElementById("d-avg-confidence").innerText = (stats.average_confidence * 100).toFixed(1) + "%";
    
    // 2. Render Chunks Browser
    var chunksListDiv = document.getElementById("chunks-list-element");
    chunksListDiv.innerHTML = "";
    chunks.forEach(function(ch, idx) {
      var item = document.createElement("div");
      item.className = "browser-item";
      item.onclick = function() { selectChunk(idx); };
      item.innerHTML = `
        <div style="font-weight:bold; font-family:monospace;">${ch.chunk_id}</div>
        <div style="font-size:11px; color:var(--text-muted); margin-top:4px;">Page: ${ch.page} | Claims: ${ch.extraction.claims ? ch.extraction.claims.length : 0}</div>
      `;
      chunksListDiv.appendChild(item);
    });
    
    function selectChunk(idx) {
      var items = document.getElementsByClassName("browser-item");
      for (var i = 0; i < items.length; i++) {
        items[i].classList.remove("active");
      }
      items[idx].classList.add("active");
      
      var ch = chunks[idx];
      var ext = ch.extraction || {};
      var detailDiv = document.getElementById("chunks-detail-element");
      
      var claimsHtml = "";
      (ext.claims || []).forEach(function(c) {
        claimsHtml += `<li><strong>${c.claim_id}</strong>: ${c.text}</li>`;
      });
      
      var entsHtml = "";
      (ext.entities || []).forEach(function(e) {
        entsHtml += `<span class="badge" style="margin-right:5px; margin-bottom:5px;">${e.text} (${e.type})</span>`;
      });
      
      var policiesHtml = "";
      (ext.policies || []).forEach(function(p) {
        policiesHtml += `<li><strong>Policy</strong>: ${p.text}</li>`;
      });
      (ext.obligations || []).forEach(function(ob) {
        policiesHtml += `<li><strong>Obligation</strong>: ${ob.text}</li>`;
      });
      
      var condsHtml = "";
      (ext.conditions || []).forEach(function(cond) {
        condsHtml += `<li>${cond.text}</li>`;
      });
      
      detailDiv.innerHTML = `
        <h2 style="margin-top:0; color:var(--primary);">${ch.chunk_id}</h2>
        <div style="font-size:13px; color:var(--text-muted); margin-bottom:12px;">
          <strong>Page:</strong> ${ch.page} | <strong>Heading Path:</strong> ${ch.heading_path} | <strong>LLM Confidence:</strong> ${(ext.confidence * 100).toFixed(1)}%
        </div>
        
        <div class="detail-card">
          <h3>Original Text</h3>
          <div class="text-box">${escapeHtml(ch.text)}</div>
        </div>
        
        <div class="detail-card">
          <h3>Extracted Factual Claims</h3>
          <ul>${claimsHtml || '<li><em>No claims extracted</em></li>'}</ul>
        </div>
        
        <div class="detail-card">
          <h3>Extracted Entities</h3>
          <div>${entsHtml || '<em>No entities extracted</em>'}</div>
        </div>
        
        <div class="detail-card">
          <h3>Policies & Obligations</h3>
          <ul>${policiesHtml || '<li><em>No policies extracted</em></li>'}</ul>
        </div>
        
        <div class="detail-card">
          <h3>Conditions</h3>
          <ul>${condsHtml || '<li><em>No conditions extracted</em></li>'}</ul>
        </div>
      `;
    }
    
    // 3. Render Claims Table
    var claimsTableBody = document.getElementById("claims-table-body");
    claimsTableBody.innerHTML = "";
    claims.forEach(function(c) {
      claimsTableBody.innerHTML += `
        <tr>
          <td style="font-family:monospace; font-weight:bold;">${c.claim_id}</td>
          <td style="font-family:monospace;">${c.chunk_id}</td>
          <td><span class="badge">${c.type}</span></td>
          <td>${c.text}</td>
        </tr>
      `;
    });
    
    // 4. Render Entities Table
    var entitiesTableBody = document.getElementById("entities-table-body");
    entitiesTableBody.innerHTML = "";
    entities.forEach(function(e) {
      entitiesTableBody.innerHTML += `
        <tr>
          <td style="font-weight:bold;">${e.text}</td>
          <td><span class="badge">${e.type}</span></td>
          <td style="font-family:monospace;">${e.chunk_id}</td>
          <td style="font-family:monospace;">${e.claim_id || 'N/A'}</td>
        </tr>
      `;
    });
    
    // 5. Render Policies Table
    var policiesTableBody = document.getElementById("policies-table-body");
    policiesTableBody.innerHTML = "";
    policies.forEach(function(p) {
      policiesTableBody.innerHTML += `
        <tr>
          <td style="font-family:monospace; font-weight:bold;">${p.policy_id}</td>
          <td><span class="badge">${p.type}</span></td>
          <td>${p.text}</td>
          <td style="font-family:monospace;">${p.chunk_id}</td>
        </tr>
      `;
    });
    
    // 6. Render References Table
    var referencesTableBody = document.getElementById("references-table-body");
    referencesTableBody.innerHTML = "";
    references.forEach(function(r) {
      referencesTableBody.innerHTML += `
        <tr>
          <td style="font-family:monospace; font-weight:bold;">${r.reference_id}</td>
          <td><strong>${r.target}</strong></td>
          <td><span class="badge">${r.type}</span></td>
          <td style="font-family:monospace;">${r.chunk_id}</td>
        </tr>
      `;
    });
    
    // 7. Render Search Results
    window.applySearch = function() {
      var query = document.getElementById("search-input").value.toLowerCase();
      var resultsContainer = document.getElementById("search-results-container");
      resultsContainer.innerHTML = "";
      
      if (!query) {
        resultsContainer.innerHTML = '<div style="color:var(--text-muted); text-align:center; padding:20px;">Type a query to search across chunks and claims</div>';
        return;
      }
      
      var matched = [];
      chunks.forEach(function(ch) {
        var idMatch = ch.chunk_id.toLowerCase().indexOf(query) > -1;
        var textMatch = ch.text.toLowerCase().indexOf(query) > -1;
        
        var ext = ch.extraction || {};
        var claimMatch = (ext.claims || []).some(function(c) { return c.text.toLowerCase().indexOf(query) > -1; });
        var entMatch = (ext.entities || []).some(function(e) { return e.text.toLowerCase().indexOf(query) > -1; });
        var polMatch = (ext.policies || []).some(function(p) { return p.text.toLowerCase().indexOf(query) > -1; });
        
        if (idMatch || textMatch || claimMatch || entMatch || polMatch) {
          matched.push(ch);
        }
      });
      
      matched.forEach(function(ch) {
        resultsContainer.innerHTML += `
          <div class="detail-card">
            <h4 style="margin:0; color:var(--primary); font-family:monospace;">${ch.chunk_id} (Page ${ch.page})</h4>
            <div class="text-box" style="margin-top:10px;">${escapeHtml(ch.text)}</div>
          </div>
        `;
      });
      
      if (matched.length === 0) {
        resultsContainer.innerHTML = '<div style="color:var(--text-muted); text-align:center; padding:20px;">No matching semantic chunks found.</div>';
      }
    };
    
    function escapeHtml(text) {
      return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
    }
    
    applySearch();
  </script>
</body>
</html>
"""
        # Inject serialized indices into HTML
        html_content = html_template \
            .replace("/* INJECT_CHUNKS */", json.dumps(chunk_claims_list, ensure_ascii=False)) \
            .replace("/* INJECT_STATS */", json.dumps(stats_data, ensure_ascii=False)) \
            .replace("/* INJECT_CLAIMS */", json.dumps(claims_list, ensure_ascii=False)) \
            .replace("/* INJECT_ENTITIES */", json.dumps(entities_list, ensure_ascii=False)) \
            .replace("/* INJECT_POLICIES */", json.dumps(policies_list, ensure_ascii=False)) \
            .replace("/* INJECT_REFERENCES */", json.dumps(references_list, ensure_ascii=False))
            
        with open(claim_dir / "claim_inspector.html", "w", encoding="utf-8") as f:
            f.write(html_content)
            
        logger.info(f"Phase 2A Structured Ingestion complete. Output folder: {claim_dir}")
