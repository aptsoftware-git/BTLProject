import re
from typing import List

def estimate_tokens(text: str) -> int:
    """
    Estimates the number of tokens in a text block.
    Uses tiktoken if installed, falling back to a word-based heuristic (words * 1.3).
    """
    if not text:
        return 0
        
    try:
        import tiktoken
        # Use cl100k_base (standard for GPT models)
        encoding = tiktoken.get_encoding("cl100k_base")
        return len(encoding.encode(text))
    except (ImportError, Exception):
        # Fallback to word-count based estimation (1 word is approx 1.3 tokens)
        words = len(text.split())
        return int(words * 1.3) + 1

def count_words(text: str) -> int:
    """
    Counts the number of words in a text block.
    """
    if not text:
        return 0
    # Split by whitespace, ignoring punctuation
    words = re.findall(r'\b\w+\b', text)
    return len(words)

def format_section_path(headings: List[str]) -> str:
    """
    Formats a list of headings into a section hierarchy string.
    Example: ['Chapter 1', 'Section A'] -> 'Chapter 1 > Section A'
    """
    if not headings:
        return "Root"
    return " > ".join(headings)


import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger("pipeline")

def load_stage6_chunks(job_dir: Path, doc_id: Optional[str] = None, materialize_cache: bool = True) -> Dict[str, Any]:
    """
    Shared robust chunk loader for Stage 6 Ambiguity Analysis.
    Loads semantic chunks in strict priority order:
      1. 06_chunks/document_chunks.json
      2. document_chunks.json
      3. 03_knowledge_objects/knowledge_objects.json (or root knowledge_objects.json)
      4. 03_knowledge_objects/knowledge_objects.jsonl (or root knowledge_objects.jsonl)

    When document_chunks.json is absent, converts knowledge objects into standard document chunks
    and optionally materializes canonical 06_chunks/document_chunks.json cache.
    """
    job_dir = Path(job_dir)
    if not doc_id:
        doc_id = job_dir.name

    def _validate_chunks_dict(data: Any) -> Optional[Dict[str, Any]]:
        if isinstance(data, dict) and "chunks" in data and isinstance(data["chunks"], list) and len(data["chunks"]) > 0:
            return data
        return None

    # Priority 1: 06_chunks/document_chunks.json
    p1 = job_dir / "06_chunks" / "document_chunks.json"
    if p1.exists():
        try:
            with open(p1, "r", encoding="utf-8") as f:
                data = json.load(f)
                val = _validate_chunks_dict(data)
                if val:
                    return val
        except Exception as exc:
            logger.warning(f"Error reading {p1}: {exc}")

    # Priority 2: document_chunks.json
    p2 = job_dir / "document_chunks.json"
    if p2.exists():
        try:
            with open(p2, "r", encoding="utf-8") as f:
                data = json.load(f)
                val = _validate_chunks_dict(data)
                if val:
                    if materialize_cache:
                        try:
                            p1.parent.mkdir(parents=True, exist_ok=True)
                            with open(p1, "w", encoding="utf-8") as f_out:
                                json.dump(val, f_out, indent=2, ensure_ascii=False)
                        except Exception as mat_err:
                            logger.warning(f"Failed to materialize {p1}: {mat_err}")
                    return val
        except Exception as exc:
            logger.warning(f"Error reading {p2}: {exc}")

    # Converter helper for KO items list -> standard chunk dict
    def _convert_ko_objs_to_chunks(ko_objs: list) -> Dict[str, Any]:
        file_name = f"{doc_id}.pdf"
        meta_file = job_dir / "metadata.json"
        if meta_file.exists():
            try:
                with open(meta_file, "r", encoding="utf-8") as fm:
                    mdata = json.load(fm)
                    file_name = mdata.get("filename") or mdata.get("original_filename") or file_name
            except Exception:
                pass

        chunks = []
        seen_ids = set()

        for idx, item in enumerate(ko_objs):
            if not isinstance(item, dict):
                continue
            meta = dict(item.get("metadata", {}))
            cid = meta.get("chunk_id") or item.get("knowledge_id") or f"{doc_id}_chunk_{idx:04d}"
            if cid in seen_ids:
                continue
            seen_ids.add(cid)

            content = item.get("content") or item.get("text") or ""
            if item.get("source_file"):
                file_name = item["source_file"]

            meta["chunk_id"] = cid
            meta["document_id"] = item.get("document_id") or doc_id
            meta["page_number"] = item.get("page_number") or meta.get("page_number", 1)
            meta["chunk_type"] = item.get("chunk_type") or meta.get("chunk_type", "Paragraph")
            meta["heading"] = item.get("heading") or meta.get("heading")
            meta["section"] = item.get("section_path") or item.get("section") or meta.get("section", "Root")
            meta["hierarchy_path"] = meta.get("hierarchy_path", [])
            meta["source_element_ids"] = meta.get("source_element_ids", [])
            meta["word_count"] = meta.get("word_count") or (len(content.split()) if content else 0)
            meta["token_estimate"] = meta.get("token_estimate") or (int(len(content.split()) * 1.3) if content else 0)

            if "bounding_box" in item and item["bounding_box"] and "bounding_boxes" not in meta:
                meta["bounding_boxes"] = [item["bounding_box"]]
            elif "bounding_boxes" not in meta:
                meta["bounding_boxes"] = []

            chunks.append({
                "content": content,
                "text": content,
                "metadata": meta
            })

        result = {
            "document_id": doc_id,
            "file_name": file_name,
            "chunks": chunks
        }

        if materialize_cache and chunks:
            try:
                p1.parent.mkdir(parents=True, exist_ok=True)
                with open(p1, "w", encoding="utf-8") as f_out:
                    json.dump(result, f_out, indent=2, ensure_ascii=False)
                logger.info(f"Materialized canonical chunk cache to {p1} with {len(chunks)} chunks.")
            except Exception as mat_err:
                logger.warning(f"Could not materialize chunk cache to {p1}: {mat_err}")

        return result

    # Priority 3: 03_knowledge_objects/knowledge_objects.json or knowledge_objects.json
    p3 = job_dir / "03_knowledge_objects" / "knowledge_objects.json"
    if not p3.exists():
        p3 = job_dir / "knowledge_objects.json"
    if p3.exists():
        try:
            with open(p3, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list) and len(data) > 0:
                    return _convert_ko_objs_to_chunks(data)
                elif isinstance(data, dict):
                    val = _validate_chunks_dict(data)
                    if val:
                        return val
        except Exception as exc:
            logger.warning(f"Error reading {p3}: {exc}")

    # Priority 4: 03_knowledge_objects/knowledge_objects.jsonl or knowledge_objects.jsonl
    p4 = job_dir / "03_knowledge_objects" / "knowledge_objects.jsonl"
    if not p4.exists():
        p4 = job_dir / "knowledge_objects.jsonl"
    if p4.exists():
        try:
            ko_objs = []
            with open(p4, "r", encoding="utf-8") as f:
                for line in f:
                    line_str = line.strip()
                    if line_str:
                        ko_objs.append(json.loads(line_str))
            if ko_objs:
                return _convert_ko_objs_to_chunks(ko_objs)
        except Exception as exc:
            logger.warning(f"Error reading {p4}: {exc}")

    # Priority 5: 03_page_text/page_text.json or page_text.json
    p5 = job_dir / "03_page_text" / "page_text.json"
    if not p5.exists():
        p5 = job_dir / "page_text.json"
    if p5.exists():
        try:
            with open(p5, "r", encoding="utf-8") as f:
                pt_data = json.load(f)
                if isinstance(pt_data, list) and len(pt_data) > 0:
                    return _convert_ko_objs_to_chunks(pt_data)
                elif isinstance(pt_data, dict):
                    page_objs = [{"page_number": int(k), "text": v} for k, v in pt_data.items() if isinstance(v, str)]
                    if page_objs:
                        return _convert_ko_objs_to_chunks(page_objs)
        except Exception as exc:
            logger.warning(f"Error reading {p5}: {exc}")

    return {"document_id": doc_id, "file_name": f"{doc_id}.pdf", "chunks": []}

