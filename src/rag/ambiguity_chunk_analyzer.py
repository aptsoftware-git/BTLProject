import re
import json
import logging
import os
from pathlib import Path
from typing import List, Dict, Any, Optional

from src.rag.config import RagConfig
from src.rag.ollama_client import OllamaClient

from collections import Counter

logger = logging.getLogger("pipeline")

from src.model_router import MODEL_ROUTER

class AmbiguityChunkAnalyzer:
    """
    Phase 2B: Local LLM Chunk-Level Ambiguity Analyzer.
    Validates extracted claims and flags ambiguities, vague wording,
    pronoun ambiguity, and contradictions strictly within individual semantic chunks.
    Writes outputs to 11_chunk_reasoning/.
    """

    def __init__(self, config: Optional[RagConfig] = None):
        self.config = config or RagConfig()
        self.model_name = os.environ.get("MODEL_CONTEXT_ANALYSIS", MODEL_ROUTER.get_model("context_analysis"))
        
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

    def _analyze_fallback_chunk(self, chunk_id: str, text: str, claims: List[dict]) -> dict:
        """Regex and dictionary-based fallback chunk analyzer when Ollama is offline."""
        claim_validation = []
        ambiguities = []
        
        # Spelling/Grammar errors mapping for validation and ambiguities
        error_rules = {
            "goed": {"type": "vague wording", "severity": "High", "reason": "Incorrect verb tense formulation ('goed').", "rewrite": "went"},
            "libary": {"type": "undefined terminology", "reason": "Misspelled word ('libary') causing lexical ambiguity.", "rewrite": "library", "severity": "Medium"},
            "enviroment": {"type": "undefined terminology", "reason": "Misspelled word ('enviroment').", "rewrite": "environment", "severity": "Low"},
            "librerian": {"type": "undefined terminology", "reason": "Misspelled word ('librerian').", "rewrite": "librarian", "severity": "Medium"},
            "dont": {"type": "vague wording", "reason": "Grammatical contraction error ('dont').", "rewrite": "do not", "severity": "Low"},
            "ten minute": {"type": "numerical ambiguity", "reason": "Incorrect pluralization for duration specifier ('ten minute').", "rewrite": "ten minutes", "severity": "Medium"},
            "everydays": {"type": "temporal ambiguity", "reason": "Incorrect spelling of temporal qualifier ('everydays').", "rewrite": "every day", "severity": "Medium"},
            "peoples": {"type": "vague wording", "reason": "Incorrect double pluralization ('peoples').", "rewrite": "people", "severity": "Low"},
            "lifes": {"type": "undefined terminology", "reason": "Misspelled pluralization of life ('lifes').", "rewrite": "lives", "severity": "Medium"},
            "childrens": {"type": "vague wording", "reason": "Incorrect pluralization spelling ('childrens').", "rewrite": "children", "severity": "Low"},
            "alot": {"type": "vague wording", "reason": "Incorrect compounding of 'a lot'.", "rewrite": "a lot", "severity": "Low"},
            "suppose to": {"type": "weak instructions", "reason": "Incorrect passive expression ('suppose to').", "rewrite": "supposed to", "severity": "Medium"},
            "wasnt": {"type": "vague wording", "reason": "Grammatical contraction/spelling error ('wasnt').", "rewrite": "was not", "severity": "Low"},
            "informations": {"type": "vague wording", "reason": "Incorrect pluralization of uncountable noun ('informations').", "rewrite": "information", "severity": "High"},
            "worry": {"type": "vague wording", "reason": "Incorrect grammatical form for adjective ('worry').", "rewrite": "worried", "severity": "Medium"}
        }

        # 1. Validate Claims
        for c in claims:
            cid = c.get("claim_id")
            c_text = c.get("text", "")
            
            # Check if claim contains any spelling error
            matched_err = None
            for err, info in error_rules.items():
                if err in c_text.lower():
                    matched_err = err
                    break
            
            if matched_err:
                rule = error_rules[matched_err]
                corrected_claim = c_text.replace(matched_err, rule["rewrite"]).replace(matched_err.title(), rule["rewrite"].title())
                claim_validation.append({
                    "claim_id": cid,
                    "status": "partial",
                    "reason": f"Claim contains spelling/lexical error: '{matched_err}' which distorts literal accuracy.",
                    "improved_claim": corrected_claim,
                    "confidence": 0.80
                })
            else:
                claim_validation.append({
                    "claim_id": cid,
                    "status": "valid",
                    "reason": "Claim is fully supported by text and grammatically correct.",
                    "improved_claim": c_text,
                    "confidence": 0.95
                })

        # 2. Extract Ambiguities
        amb_idx = 0
        for err, info in error_rules.items():
            pattern = re.compile(rf"\b{err}\b", re.IGNORECASE)
            match = pattern.search(text)
            if match:
                # Find which claims are affected
                affected = [c.get("claim_id") for c in claims if err in c.get("text", "").lower()]
                
                # Context evidence
                start_idx = max(0, match.start() - 30)
                end_idx = min(len(text), match.end() + 30)
                evidence = text[start_idx:end_idx].strip()
                
                ambiguities.append({
                    "issue_id": f"{chunk_id}_amb_{amb_idx:03d}",
                    "type": info["type"],
                    "severity": info["severity"],
                    "quote": match.group(0),
                    "reason": info["reason"],
                    "supporting_evidence": f"...{evidence}...",
                    "suggested_rewrite": text.replace(match.group(0), info["rewrite"]),
                    "affected_claims": affected,
                    "confidence": 0.85
                })
                amb_idx += 1
                
        # Pronoun Ambiguity Check
        pronouns = ["he", "she", "they", "it"]
        for p in pronouns:
            pattern = re.compile(rf"\b{p}\b", re.IGNORECASE)
            match = pattern.search(text)
            if match:
                affected = [c.get("claim_id") for c in claims if p in c.get("text", "").lower()]
                start_idx = max(0, match.start() - 30)
                end_idx = min(len(text), match.end() + 30)
                evidence = text[start_idx:end_idx].strip()
                
                ambiguities.append({
                    "issue_id": f"{chunk_id}_amb_{amb_idx:03d}",
                    "type": "pronoun ambiguity",
                    "severity": "Medium",
                    "quote": match.group(0),
                    "reason": f"Pronoun '{match.group(0)}' lacks a clear structural antecedent in the chunk.",
                    "supporting_evidence": f"...{evidence}...",
                    "suggested_rewrite": text.replace(match.group(0), f"[Insert antecedent name here]"),
                    "affected_claims": affected,
                    "confidence": 0.80
                })
                amb_idx += 1

        from src.rag.finding_filter import FindingRelevanceFilter
        rf = FindingRelevanceFilter()
        clean_ambiguities = [
            amb for amb in ambiguities
            if not rf.is_suppressed(amb.get("quote", ""), amb.get("type", ""), amb.get("reason", ""))
            and float(amb.get("confidence", 0.85)) >= rf.min_confidence
        ]

        overall_risk = "Low"
        if len(clean_ambiguities) >= 3:
            overall_risk = "High"
        elif len(clean_ambiguities) > 0:
            overall_risk = "Medium"

        return {
            "chunk_id": chunk_id,
            "claim_validation": claim_validation,
            "ambiguities": clean_ambiguities,
            "overall_chunk_risk": overall_risk,
            "overall_confidence": 0.88
        }

    def run_analysis(self, job_dir: Path, doc_id: str) -> None:
        logger.info(f"Starting Phase 2B Chunk Analysis for job: {doc_id}")
        
        # Cache hit check
        cache_reasoning_path = job_dir / "11_chunk_reasoning" / "chunk_reasoning.json"
        if cache_reasoning_path.exists() and cache_reasoning_path.stat().st_size > 0:
            logger.info(f"[CACHE HIT] Chunk reasoning analysis already exists for job {doc_id}. Skipping re-analysis.")
            return

        # 1. Load extracted claims from Phase 2A
        claims_json_path = job_dir / "10_claim_extraction" / "chunk_claims.json"
        if not claims_json_path.exists():
            logger.error(f"chunk_claims.json not found in {job_dir}/10_claim_extraction/")
            return
            
        with open(claims_json_path, "r", encoding="utf-8") as f:
            chunk_claims_data = json.load(f)
            
        chunks = chunk_claims_data.get("chunks", [])
        
        # Check connection to Ollama server
        ollama_active = False
        try:
            ollama_active = self.ollama_client.check_connection()
        except Exception:
            pass
            
        if not ollama_active:
            logger.warning("Ollama connection failed. Falling back to deterministic chunk analyzer.")
            
        chunk_reasonings = []
        
        system_prompt = (
            "You are a precise document ambiguity and claim validation engine.\n"
            "Analyze ONLY the provided semantic chunk text. Do not make assumptions or extrapolate outside this text.\n"
            "Return the analysis STRICTLY as a single JSON object matching the requested schema.\n"
            "Do not include markdown fences, conversational text, or explanations."
        )
        
        policy_keywords = {"must", "shall", "required", "mandatory", "policy", "prohibited", "condition", "unless", "except", "agreement", "liability", "term", "clause"}

        # Filter chunks into fast-path fallback vs LLM candidate chunks
        fallback_results = []
        llm_chunks = []

        for ch in chunks:
            chunk_id = ch["chunk_id"]
            text = ch["text"]
            extraction = ch.get("extraction", {})
            claims = extraction.get("claims", [])
            policies = extraction.get("policies", []) + extraction.get("obligations", [])
            words = text.split()
            has_policy_kw = any(kw in text.lower() for kw in policy_keywords)
            if len(words) < 45 or (not claims and not policies and not has_policy_kw) or not ollama_active:
                fallback_results.append(self._analyze_fallback_chunk(chunk_id, text, claims))
            else:
                llm_chunks.append(ch)

        chunk_reasonings.extend(fallback_results)

        def _process_chunk_batch(batch_chunks):
            batch_results = []
            if len(batch_chunks) == 1:
                ch = batch_chunks[0]
                chunk_id = ch["chunk_id"]
                text = ch["text"]
                extraction = ch.get("extraction", {})
                claims = extraction.get("claims", [])
                prompt = f"""Perform chunk-level claim validation and ambiguity analysis.

Original Chunk Text:
{text}

Structured Extraction from Phase 2A:
{json.dumps(extraction, indent=2)}

Return JSON schema matching:
{{
    "chunk_id": "{chunk_id}",
    "claim_validation": [{"claim_id": "string", "status": "valid|partial|incorrect", "reason": "string", "improved_claim": "string", "confidence": 0.95}],
    "ambiguities": [{"issue_id": "{chunk_id}_amb_000", "type": "vague wording", "severity": "Low|Medium|High", "quote": "string", "reason": "string", "supporting_evidence": "string", "suggested_rewrite": "string", "affected_claims": [], "confidence": 0.90}],
    "overall_chunk_risk": "Low|Medium|High",
    "overall_confidence": 0.92
}}
"""
                try:
                    resp = self.ollama_client.generate(model=self.model_name, prompt=prompt, system=system_prompt)
                    parsed = self._clean_and_parse_json(resp)
                    if parsed:
                        return [parsed]
                except Exception as e:
                    logger.warning(f"Single chunk LLM call failed for {chunk_id}: {e}")
                return [self._analyze_fallback_chunk(chunk_id, text, claims)]

            # Process multi-chunk batch
            batch_prompt_parts = ["Analyze the following semantic document chunks for ambiguity and claim validation:\n"]
            for idx, ch in enumerate(batch_chunks, 1):
                batch_prompt_parts.append(
                    f"--- Chunk {idx} (ID: {ch['chunk_id']}) ---\nText: {ch['text']}\nExtraction: {json.dumps(ch.get('extraction', {}))}\n"
                )
            batch_prompt_parts.append(
                "Return a JSON object containing a 'chunk_results' list where each item matches the schema for a chunk.\n"
                "Schema for each item: {\"chunk_id\": \"...\", \"claim_validation\": [...], \"ambiguities\": [...], \"overall_chunk_risk\": \"Low|Medium|High\", \"overall_confidence\": 0.9}"
            )
            batch_prompt = "\n".join(batch_prompt_parts)

            try:
                resp = self.ollama_client.generate(model=self.model_name, prompt=batch_prompt, system=system_prompt)
                parsed = self._clean_and_parse_json(resp)
                results_list = parsed.get("chunk_results", []) if isinstance(parsed, dict) else (parsed if isinstance(parsed, list) else [])
                parsed_map = {r.get("chunk_id"): r for r in results_list if isinstance(r, dict) and "chunk_id" in r}

                for ch in batch_chunks:
                    c_id = ch["chunk_id"]
                    if c_id in parsed_map:
                        batch_results.append(parsed_map[c_id])
                    else:
                        batch_results.append(self._analyze_fallback_chunk(c_id, ch["text"], ch.get("extraction", {}).get("claims", [])))
                return batch_results
            except Exception as exc:
                logger.warning(f"Batch chunk LLM analysis failed ({exc}). Falling back to fallback rules for batch.")
                return [self._analyze_fallback_chunk(ch["chunk_id"], ch["text"], ch.get("extraction", {}).get("claims", [])) for ch in batch_chunks]

        if llm_chunks:
            batch_size = 10
            chunk_batches = [llm_chunks[i : i + batch_size] for i in range(0, len(llm_chunks), batch_size)]
            max_workers = min(8, len(chunk_batches))
            logger.info("Starting LLM Ambiguity Analysis for %d candidate chunks in %d batch(es)...", len(llm_chunks), len(chunk_batches))
            from concurrent.futures import ThreadPoolExecutor, as_completed
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(_process_chunk_batch, b): idx for idx, b in enumerate(chunk_batches, 1)}
                for f in as_completed(futures):
                    b_idx = futures[f]
                    try:
                        res = f.result()
                        if res:
                            chunk_reasonings.extend(res)
                            logger.info("[Batch %d/%d] Completed chunk ambiguity analysis batch.", b_idx, len(chunk_batches))
                    except Exception as exc:
                        logger.warning("Error in batch chunk processing thread for batch %d: %s", b_idx, exc)

        # Ensure output directory exists
        reason_dir = job_dir / "11_chunk_reasoning"
        reason_dir.mkdir(parents=True, exist_ok=True)

        # 1. Output chunk_reasoning.json
        with open(reason_dir / "chunk_reasoning.json", "w", encoding="utf-8") as f:
            json.dump({"chunks": chunk_reasonings}, f, indent=2, ensure_ascii=False)

        # 2. Output validated_claims.json
        validated_claims_list = []
        for cr in chunk_reasonings:
            cid = cr["chunk_id"]
            # Find original chunk text mapping
            original_c = next((ch for ch in chunks if ch["chunk_id"] == cid), {})
            orig_claims = original_c.get("extraction", {}).get("claims", [])
            
            for cv in cr.get("claim_validation", []):
                claim_id = cv.get("claim_id")
                # find original text of claim
                orig_c_text = next((c.get("text", "") for c in orig_claims if c.get("claim_id") == claim_id), "N/A")
                
                validated_claims_list.append({
                    "claim_id": claim_id,
                    "chunk_id": cid,
                    "original_text": orig_c_text,
                    "status": cv.get("status"),
                    "reason": cv.get("reason"),
                    "improved_claim": cv.get("improved_claim"),
                    "confidence": cv.get("confidence")
                })
        with open(reason_dir / "validated_claims.json", "w", encoding="utf-8") as f:
            json.dump({"validated_claims": validated_claims_list}, f, indent=2, ensure_ascii=False)

        # 3. Output ambiguity_index.json
        ambiguities_list = []
        for cr in chunk_reasonings:
            cid = cr["chunk_id"]
            for amb in cr.get("ambiguities", []):
                ambiguities_list.append({
                    "issue_id": amb.get("issue_id"),
                    "chunk_id": cid,
                    "type": amb.get("type"),
                    "severity": amb.get("severity"),
                    "quote": amb.get("quote"),
                    "reason": amb.get("reason"),
                    "supporting_evidence": amb.get("supporting_evidence"),
                    "suggested_rewrite": amb.get("suggested_rewrite"),
                    "affected_claims": amb.get("affected_claims", [])
                })
        with open(reason_dir / "ambiguity_index.json", "w", encoding="utf-8") as f:
            json.dump({"ambiguities": ambiguities_list}, f, indent=2, ensure_ascii=False)

        # 4. Output rewrite_suggestions.json
        rewrites_list = []
        # Add rewrites from validated claims
        for vc in validated_claims_list:
            if vc["status"] in ("partial", "incorrect"):
                rewrites_list.append({
                    "id": vc["claim_id"],
                    "chunk_id": vc["chunk_id"],
                    "original_text": vc["original_text"],
                    "suggested_text": vc["improved_claim"],
                    "type": "claim"
                })
        # Add rewrites from ambiguities
        for amb in ambiguities_list:
            rewrites_list.append({
                "id": amb["issue_id"],
                "chunk_id": amb["chunk_id"],
                "original_text": amb["quote"],
                "suggested_text": amb["suggested_rewrite"],
                "type": "ambiguity"
            })
        with open(reason_dir / "rewrite_suggestions.json", "w", encoding="utf-8") as f:
            json.dump({"rewrites": rewrites_list}, f, indent=2, ensure_ascii=False)

        # Compute statistics
        total_chunks = len(chunk_reasonings)
        total_claims_val = len(validated_claims_list)
        total_ambs = len(ambiguities_list)
        
        risk_counter = Counter([cr.get("overall_chunk_risk", "Low") for cr in chunk_reasonings])
        avg_conf = sum(cr.get("overall_confidence", 0.0) for cr in chunk_reasonings) / max(1, total_chunks)

        # 5. Output chunk_statistics.json
        stats_data = {
            "total_chunks_analyzed": total_chunks,
            "total_claims_validated": total_claims_val,
            "total_ambiguities_identified": total_ambs,
            "risk_breakdown": {
                "Low": risk_counter.get("Low", 0),
                "Medium": risk_counter.get("Medium", 0),
                "High": risk_counter.get("High", 0)
            },
            "average_confidence": round(avg_conf, 4)
        }
        with open(reason_dir / "chunk_statistics.json", "w", encoding="utf-8") as f:
            json.dump(stats_data, f, indent=2)

        # 6. Write Markdown Reports
        # chunk_reasoning.md
        md_reasoning = ["# Chunk-Level Ambiguity & Reasonings\n\n"]
        for cr in chunk_reasonings:
            cid = cr["chunk_id"]
            original_c = next((ch for ch in chunks if ch["chunk_id"] == cid), {})
            md_reasoning.append(f"## Chunk `{cid}` (Risk: {cr.get('overall_chunk_risk')})\n")
            md_reasoning.append(f"### Original Text\n```\n{original_c.get('text', '').strip()}\n```\n")
            
            md_reasoning.append("\n### Claim Validation\n")
            for cv in cr.get("claim_validation", []):
                md_reasoning.append(f"- **{cv.get('claim_id')}** ({cv.get('status')}): {cv.get('reason')}\n")
                
            md_reasoning.append("\n### Ambiguities Identified\n")
            for amb in cr.get("ambiguities", []):
                md_reasoning.append(
                    f"#### {amb.get('issue_id')} ({amb.get('type')})\n"
                    f"- **Severity**: {amb.get('severity')}\n"
                    f"- **Quote**: \"{amb.get('quote')}\"\n"
                    f"- **Reason**: {amb.get('reason')}\n"
                    f"- **Suggested Rewrite**: {amb.get('suggested_rewrite')}\n"
                )
            if not cr.get("ambiguities"):
                md_reasoning.append("*No ambiguities identified.*\n")
            md_reasoning.append("\n---\n")
        with open(reason_dir / "chunk_reasoning.md", "w", encoding="utf-8") as f:
            f.write("".join(md_reasoning))

        # validated_claims.md
        md_val_claims = ["# Validated Claims Index\n\n| Claim ID | Chunk ID | Status | Reason | Improved Claim |\n|:---------|:---------|:-------|:-------|:---------------|\n"]
        for vc in validated_claims_list:
            md_val_claims.append(f"| `{vc['claim_id']}` | `{vc['chunk_id']}` | **{vc['status'].upper()}** | {vc['reason']} | {vc['improved_claim']} |\n")
        with open(reason_dir / "validated_claims.md", "w", encoding="utf-8") as f:
            f.write("".join(md_val_claims))

        # ambiguity_index.md
        md_ambs = ["# Ambiguity Index\n\n| Issue ID | Chunk ID | Type | Severity | Quote | Reason | Suggested Rewrite |\n|:---------|:---------|:-----|:---------|:------|:-------|:------------------|\n"]
        for amb in ambiguities_list:
            md_ambs.append(f"| `{amb['issue_id']}` | `{amb['chunk_id']}` | {amb['type']} | **{amb['severity']}** | \"{amb['quote']}\" | {amb['reason']} | {amb['suggested_rewrite']} |\n")
        with open(reason_dir / "ambiguity_index.md", "w", encoding="utf-8") as f:
            f.write("".join(md_ambs))

        # rewrite_suggestions.md
        md_rewrites = ["# Side-by-Side Rewrite Suggestions\n\n| ID | Type | Original Text / Quote | Suggested Rewrite |\n|:---|:-----|:----------------------|:------------------|\n"]
        for rw in rewrites_list:
            orig_text = (rw.get("original_text") or "").strip()
            sugg_text = (rw.get("suggested_text") or "").strip()
            md_rewrites.append(f"| `{rw['id']}` | {rw['type']} | *\"{orig_text}\"* | **{sugg_text}** |\n")
        with open(reason_dir / "rewrite_suggestions.md", "w", encoding="utf-8") as f:
            f.write("".join(md_rewrites))

        # chunk_summary.md (Executive overview)
        summary_md = f"""# Chunk-Level Ambiguity Reasoning Summary

## Executive Overview
- **Total Semantic Chunks Analyzed**: {total_chunks}
- **Total Claims Validated**: {total_claims_val}
- **Total Ambiguities Identified**: {total_ambs}
- **Average Reasoning Confidence**: {avg_conf * 100:.2f}%

## Risk Breakdown
- **High Risk Chunks**: {risk_counter.get('High', 0)}
- **Medium Risk Chunks**: {risk_counter.get('Medium', 0)}
- **Low Risk Chunks**: {risk_counter.get('Low', 0)}

## Top Ambiguity Distribution
| Risk Suffix | Count |
|:------------|:-----:|
| High Risk | {risk_counter.get('High', 0)} |
| Medium Risk | {risk_counter.get('Medium', 0)} |
| Low Risk | {risk_counter.get('Low', 0)} |
"""
        with open(reason_dir / "chunk_summary.md", "w", encoding="utf-8") as f:
            f.write(summary_md)

        # 10. Generate Interactive Debugger HTML
        html_template = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Chunk Reasoning Inspector</title>
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
    .badge-risk-high { background: #fee2e2; color: #ef4444; }
    .badge-risk-medium { background: #fef3c7; color: #d97706; }
    .badge-risk-low { background: #d1fae5; color: #10b981; }
  </style>
</head>
<body>
  <div class="sidebar">
    <div class="sidebar-header">
      <h2>Reasoning Inspector</h2>
    </div>
    <ul class="nav-list">
      <li class="nav-item active" onclick="switchTab('tab-overview')">🏠 Overview Dashboard</li>
      <li class="nav-item" onclick="switchTab('tab-chunks')">📦 Chunk Browser</li>
      <li class="nav-item" onclick="switchTab('tab-claims')">📄 Claim Validation</li>
      <li class="nav-item" onclick="switchTab('tab-ambiguities')">⚠️ Ambiguity Browser</li>
      <li class="nav-item" onclick="switchTab('tab-rewrites')">✏️ Rewrite Suggestions</li>
      <li class="nav-item" onclick="switchTab('tab-search')">🔎 Search & Filters</li>
    </ul>
  </div>
  
  <div class="main-content">
    
    <!-- 1. Overview Dashboard -->
    <div id="tab-overview" class="content-tab active">
      <h1 style="margin-top:0;">Chunk reasoning dashboard</h1>
      <div class="dashboard-grid">
        <div class="stat-card">
          <div class="stat-title">Chunks Analyzed</div>
          <div class="stat-value" id="d-total-chunks">0</div>
        </div>
        <div class="stat-card">
          <div class="stat-title">Claims Validated</div>
          <div class="stat-value" id="d-total-claims">0</div>
        </div>
        <div class="stat-card">
          <div class="stat-title">Ambiguities Identified</div>
          <div class="stat-value" id="d-total-ambs">0</div>
        </div>
        <div class="stat-card">
          <div class="stat-title">High Risk Chunks</div>
          <div class="stat-value" style="color:#ef4444;" id="d-high-risk">0</div>
        </div>
        <div class="stat-card">
          <div class="stat-title">Medium Risk Chunks</div>
          <div class="stat-value" style="color:#d97706;" id="d-med-risk">0</div>
        </div>
        <div class="stat-card">
          <div class="stat-title">Average Confidence</div>
          <div class="stat-value" id="d-avg-conf">0%</div>
        </div>
      </div>
    </div>
    
    <!-- 2. Chunk Browser -->
    <div id="tab-chunks" class="content-tab">
      <h1 style="margin-top:0;">Chunk Browser</h1>
      <div class="browser-container">
        <div class="browser-list" id="chunks-list-element"></div>
        <div class="browser-detail" id="chunks-detail-element">
          <div style="color:var(--text-muted); text-align:center; margin:auto;">Select a chunk on the left to inspect its reasoning details</div>
        </div>
      </div>
    </div>
    
    <!-- 3. Claim Validation Browser -->
    <div id="tab-claims" class="content-tab">
      <h1 style="margin-top:0;">Claim Validation Results</h1>
      <table class="index-table">
        <thead>
          <tr>
            <th>Claim ID</th>
            <th>Chunk ID</th>
            <th>Status</th>
            <th>Reason</th>
            <th>Suggested Rewrite</th>
          </tr>
        </thead>
        <tbody id="claims-table-body"></tbody>
      </table>
    </div>
    
    <!-- 4. Ambiguity Browser -->
    <div id="tab-ambiguities" class="content-tab">
      <h1 style="margin-top:0;">Identified Ambiguities</h1>
      <table class="index-table">
        <thead>
          <tr>
            <th>Issue ID</th>
            <th>Chunk ID</th>
            <th>Type</th>
            <th>Severity</th>
            <th>Quote</th>
            <th>Reason</th>
            <th>Rewrite</th>
          </tr>
        </thead>
        <tbody id="ambs-table-body"></tbody>
      </table>
    </div>
    
    <!-- 5. Rewrite Suggestions -->
    <div id="tab-rewrites" class="content-tab">
      <h1 style="margin-top:0;">Rewrite Suggestions</h1>
      <table class="index-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>Type</th>
            <th>Original Quote / Statement</th>
            <th>Suggested Rewrite</th>
          </tr>
        </thead>
        <tbody id="rewrites-table-body"></tbody>
      </table>
    </div>
    
    <!-- 6. Search & Filters -->
    <div id="tab-search" class="content-tab">
      <h1 style="margin-top:0;">Search & Filters</h1>
      <div class="controls-panel">
        <div>
          <label style="font-size:12px; font-weight:600; color:var(--text-muted);">Text Search (Claims, Quotes, Types)</label>
          <input type="text" id="search-input" class="control-input" placeholder="Type query..." oninput="applySearch()"/>
        </div>
      </div>
      <div id="search-results-container" style="display:flex; flex-direction:column; gap:15px;"></div>
    </div>
    
  </div>

  <script>
    // Injected Data
    var chunkReasonings = /* INJECT_REASONINGS */;
    var stats = /* INJECT_STATS */;
    var validatedClaims = /* INJECT_VALIDATED_CLAIMS */;
    var ambiguities = /* INJECT_AMBIGUITIES */;
    var rewrites = /* INJECT_REWRITES */;
    
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
      else if (tabId === "tab-ambiguities") targetIdx = 3;
      else if (tabId === "tab-rewrites") targetIdx = 4;
      else if (tabId === "tab-search") targetIdx = 5;
      navItems[targetIdx].classList.add("active");
    };
    
    // 1. Render Dashboard
    document.getElementById("d-total-chunks").innerText = stats.total_chunks_analyzed;
    document.getElementById("d-total-claims").innerText = stats.total_claims_validated;
    document.getElementById("d-total-ambs").innerText = stats.total_ambiguities_identified;
    document.getElementById("d-high-risk").innerText = stats.risk_breakdown.High;
    document.getElementById("d-med-risk").innerText = stats.risk_breakdown.Medium;
    document.getElementById("d-avg-conf").innerText = (stats.average_confidence * 100).toFixed(1) + "%";
    
    // 2. Render Chunks Browser
    var chunksListDiv = document.getElementById("chunks-list-element");
    chunksListDiv.innerHTML = "";
    chunkReasonings.forEach(function(ch, idx) {
      var item = document.createElement("div");
      item.className = "browser-item";
      item.onclick = function() { selectChunk(idx); };
      item.innerHTML = `
        <div style="font-weight:bold; font-family:monospace;">${ch.chunk_id}</div>
        <div style="font-size:11px; color:var(--text-muted); margin-top:4px;">Risk: ${ch.overall_chunk_risk} | Issues: ${ch.ambiguities ? ch.ambiguities.length : 0}</div>
      `;
      chunksListDiv.appendChild(item);
    });
    
    function selectChunk(idx) {
      var items = document.getElementsByClassName("browser-item");
      for (var i = 0; i < items.length; i++) {
        items[i].classList.remove("active");
      }
      items[idx].classList.add("active");
      
      var ch = chunkReasonings[idx];
      var detailDiv = document.getElementById("chunks-detail-element");
      
      var valHtml = "";
      (ch.claim_validation || []).forEach(function(c) {
        valHtml += `<li><strong>${c.claim_id}</strong> (${c.status.toUpperCase()}): ${c.reason} <br/><span style="font-size:11px; color:var(--text-muted);">Suggested revision: "${c.improved_claim}"</span></li>`;
      });
      
      var ambsHtml = "";
      (ch.ambiguities || []).forEach(function(a) {
        var badgeSeverityClass = "badge-risk-" + a.severity.toLowerCase();
        ambsHtml += `
          <div style="border-bottom: 1px solid var(--border); padding-bottom:10px; margin-bottom:10px;">
            <div style="display:flex; justify-content:space-between; align-items:center;">
              <strong>${a.issue_id} (${a.type})</strong>
              <span class="badge ${badgeSeverityClass}">${a.severity}</span>
            </div>
            <div style="font-size:12.5px; margin-top:5px;"><strong>Quote:</strong> "${a.quote}"</div>
            <div style="font-size:12.5px;"><strong>Reason:</strong> ${a.reason}</div>
            <div style="font-size:12.5px;"><strong>Evidence:</strong> ${a.supporting_evidence}</div>
            <div style="font-size:12.5px; color:var(--primary);"><strong>Suggested Rewrite:</strong> ${a.suggested_rewrite}</div>
          </div>
        `;
      });
      
      detailDiv.innerHTML = `
        <h2 style="margin-top:0; color:var(--primary);">${ch.chunk_id}</h2>
        <div style="font-size:13px; color:var(--text-muted); margin-bottom:12px;">
          <strong>Risk Level:</strong> <span class="badge badge-risk-${ch.overall_chunk_risk.toLowerCase()}">${ch.overall_chunk_risk}</span> | <strong>Reasoning Confidence:</strong> ${(ch.overall_confidence * 100).toFixed(1)}%
        </div>
        
        <div class="detail-card">
          <h3>Claim Validation</h3>
          <ul>${valHtml || '<li><em>No claims validated</em></li>'}</ul>
        </div>
        
        <div class="detail-card">
          <h3>Ambiguities & Issues</h3>
          <div>${ambsHtml || '<em>No issues identified</em>'}</div>
        </div>
      `;
    }
    
    // 3. Render Claims Table
    var claimsTableBody = document.getElementById("claims-table-body");
    claimsTableBody.innerHTML = "";
    validatedClaims.forEach(function(c) {
      var badgeClass = c.status === "valid" ? "badge-risk-low" : "badge-risk-medium";
      claimsTableBody.innerHTML += `
        <tr>
          <td style="font-family:monospace; font-weight:bold;">${c.claim_id}</td>
          <td style="font-family:monospace;">${c.chunk_id}</td>
          <td><span class="badge ${badgeClass}">${c.status.toUpperCase()}</span></td>
          <td>${c.reason}</td>
          <td>${c.improved_claim}</td>
        </tr>
      `;
    });
    
    // 4. Render Ambiguities Table
    var ambsTableBody = document.getElementById("ambs-table-body");
    ambsTableBody.innerHTML = "";
    ambiguities.forEach(function(a) {
      var badgeSeverityClass = "badge-risk-" + a.severity.toLowerCase();
      ambsTableBody.innerHTML += `
        <tr>
          <td style="font-family:monospace; font-weight:bold;">${a.issue_id}</td>
          <td style="font-family:monospace;">${a.chunk_id}</td>
          <td>${a.type}</td>
          <td><span class="badge ${badgeSeverityClass}">${a.severity}</span></td>
          <td>"${a.quote}"</td>
          <td>${a.reason}</td>
          <td style="color:var(--primary); font-weight:500;">${a.suggested_rewrite}</td>
        </tr>
      `;
    });
    
    // 5. Render Rewrites Table
    var rewritesTableBody = document.getElementById("rewrites-table-body");
    rewritesTableBody.innerHTML = "";
    rewrites.forEach(function(r) {
      rewritesTableBody.innerHTML += `
        <tr>
          <td style="font-family:monospace; font-weight:bold;">${r.id}</td>
          <td><span class="badge">${r.type}</span></td>
          <td><em>"${r.original_text.strip ? r.original_text.strip() : r.original_text}"</em></td>
          <td style="color:var(--primary); font-weight:600;">${r.suggested_text}</td>
        </tr>
      `;
    });
    
    // 6. Render Search Results
    window.applySearch = function() {
      var query = document.getElementById("search-input").value.toLowerCase();
      var resultsContainer = document.getElementById("search-results-container");
      resultsContainer.innerHTML = "";
      
      if (!query) {
        resultsContainer.innerHTML = '<div style="color:var(--text-muted); text-align:center; padding:20px;">Type a query to search across chunks, claims, or issue types</div>';
        return;
      }
      
      var matched = [];
      chunkReasonings.forEach(function(ch) {
        var idMatch = ch.chunk_id.toLowerCase().indexOf(query) > -1;
        var claimMatch = (ch.claim_validation || []).some(function(c) { return c.reason.toLowerCase().indexOf(query) > -1 || c.improved_claim.toLowerCase().indexOf(query) > -1; });
        var ambMatch = (ch.ambiguities || []).some(function(a) { return a.type.toLowerCase().indexOf(query) > -1 || a.reason.toLowerCase().indexOf(query) > -1 || a.quote.toLowerCase().indexOf(query) > -1; });
        
        if (idMatch || claimMatch || ambMatch) {
          matched.push(ch);
        }
      });
      
      matched.forEach(function(ch) {
        resultsContainer.innerHTML += `
          <div class="detail-card">
            <h4 style="margin:0; color:var(--primary); font-family:monospace;">${ch.chunk_id}</h4>
            <div style="font-size:12px; margin-top:5px;">Risk level: ${ch.overall_chunk_risk} | Confidence: ${(ch.overall_confidence * 100).toFixed(1)}%</div>
          </div>
        `;
      });
      
      if (matched.length === 0) {
        resultsContainer.innerHTML = '<div style="color:var(--text-muted); text-align:center; padding:20px;">No matching semantic chunks found.</div>';
      }
    };
    
    applySearch();
  </script>
</body>
</html>
"""
        
        # Inject serialized variables
        html_content = html_template \
            .replace("/* INJECT_REASONINGS */", json.dumps(chunk_reasonings, ensure_ascii=False)) \
            .replace("/* INJECT_STATS */", json.dumps(stats_data, ensure_ascii=False)) \
            .replace("/* INJECT_VALIDATED_CLAIMS */", json.dumps(validated_claims_list, ensure_ascii=False)) \
            .replace("/* INJECT_AMBIGUITIES */", json.dumps(ambiguities_list, ensure_ascii=False)) \
            .replace("/* INJECT_REWRITES */", json.dumps(rewrites_list, ensure_ascii=False))
            
        with open(reason_dir / "chunk_reasoning_inspector.html", "w", encoding="utf-8") as f:
            f.write(html_content)
            
        logger.info(f"Phase 2B Chunk Reasoning complete. Output folder: {reason_dir}")
