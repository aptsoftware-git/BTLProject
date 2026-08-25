import logging
import re
from typing import List, Set, Tuple, Dict, Any, Optional
from src.rag.retrieval_models import ScoredChunk

logger = logging.getLogger("pipeline")

class ContextBuilder:
    """
    Builds RAG context strings from retrieved document chunks.
    Ensures token limits are respected, original document order is preserved,
    duplicate chunks are removed, and formatting is retained.
    """
    def __init__(self, max_tokens: int = 4000):
        self.max_tokens = max_tokens

    @staticmethod
    def _parse_chunk_index(chunk_id: str) -> int:
        """
        Extracts the numeric index from a chunk ID formatted like '{doc_id}_chunk_{idx:04d}'.
        """
        try:
            match = re.search(r"_chunk_(\d+)", chunk_id)
            if match:
                return int(match.group(1))
        except Exception:
            pass
        return 0

    def extract_image_references(self, chunks: List[ScoredChunk]) -> List[Dict[str, Any]]:
        """
        Extracts structured image reference metadata from chunks for UI and citation.
        """
        from pathlib import Path
        image_refs = []
        seen_keys = set()
        for chunk in chunks:
            meta = chunk.metadata
            if meta.chunk_type == "image" or meta.image_id or getattr(meta, "image_path", None):
                img_id = meta.image_id or meta.chunk_id
                doc_id = meta.document_id
                img_path = getattr(meta, "image_path", None) or ""
                img_url = getattr(meta, "image_url", None) or ""

                # Extract clean filename (e.g. image_090.png)
                img_filename = ""
                for candidate in [img_url, img_path]:
                    if candidate:
                        clean_c = str(candidate).replace("\\", "/")
                        base = Path(clean_c).name
                        if base and ("." in base or base.startswith("image_")):
                            img_filename = base
                            break
                if not img_filename and img_id:
                    clean_id = img_id.replace("#/", "").replace("/", "_")
                    img_filename = f"{clean_id}.png"

                # Construct standard browser-accessible static URL
                resolved_img_url = f"/outputs/{doc_id}/05_images/{img_filename}"
                
                # Validate that the physical image asset actually exists on disk
                from src.config import ROOT_DIR
                exists_on_disk = False
                if img_path and Path(img_path).exists():
                    exists_on_disk = True
                elif img_path and (ROOT_DIR / img_path).exists():
                    exists_on_disk = True
                elif doc_id and img_filename:
                    target_disk_path = ROOT_DIR / "data" / "output" / doc_id / "05_images" / img_filename
                    if target_disk_path.exists():
                        exists_on_disk = True

                if not exists_on_disk:
                    logger.warning(f"Image asset {img_filename} for chunk {meta.chunk_id} does not physically exist on disk. Skipping.")
                    continue

                # Gating: filter out non-retrievable / LOW importance decorative elements
                if hasattr(meta, "retrievable") and meta.retrievable is False:
                    continue
                if getattr(meta, "importance_score", None) == "LOW":
                    continue
                if (getattr(meta, "image_type", None) or "").lower() == "decorative":
                    continue

                # Deduplicate by (resolved_img_url, page_number)
                dedup_key = (resolved_img_url, meta.page_number)
                if dedup_key not in seen_keys:
                    seen_keys.add(dedup_key)

                    bboxes_list = []
                    for b in meta.bounding_boxes:
                        if hasattr(b, "model_dump"):
                            bboxes_list.append(b.model_dump())
                        elif hasattr(b, "dict"):
                            bboxes_list.append(b.dict())
                        elif isinstance(b, dict):
                            bboxes_list.append(b)

                    image_refs.append({
                        "image_id": img_id,
                        "page_number": meta.page_number,
                        "title": getattr(meta, "title", None) or getattr(meta, "caption", None) or meta.heading or f"Figure on Page {meta.page_number}",
                        "subtitle": getattr(meta, "subtitle", None),
                        "caption": getattr(meta, "caption", None) or meta.heading or f"Figure on Page {meta.page_number}",
                        "caption_text": getattr(meta, "caption_text", None) or getattr(meta, "caption", None),
                        "explicit_caption": getattr(meta, "explicit_caption", None),
                        "entity_name": getattr(meta, "entity_name", None),
                        "designation": getattr(meta, "designation", None),
                        "section_heading": getattr(meta, "section_heading", None),
                        "layout_context": getattr(meta, "layout_context", None),
                        "importance_score": getattr(meta, "importance_score", "MEDIUM"),
                        "retrievable": getattr(meta, "retrievable", True),
                        "association_method": getattr(meta, "association_method", "none"),
                        "association_confidence": float(getattr(meta, "association_confidence", getattr(meta, "confidence", 1.0)) or 1.0),
                        "confidence": float(getattr(meta, "confidence", 1.0) or 1.0),
                        "text_before": getattr(meta, "text_before", None),
                        "text_after": getattr(meta, "text_after", None),
                        "semantic_description": getattr(meta, "semantic_description", None),
                        "keywords": getattr(meta, "keywords", []) or [],
                        "image_url": resolved_img_url,
                        "image_path": img_path,
                        "image_type": getattr(meta, "image_type", None) or "Figure",
                        "bounding_boxes": bboxes_list,
                        "objects": getattr(meta, "objects", []) or [],
                        "detected_entities": getattr(meta, "detected_entities", []) or []
                    })
        return image_refs

    def build_context(self, retrieved_chunks: List[ScoredChunk]) -> Tuple[str, List[str], List[int], List[Dict[str, Any]]]:
        """
        Selects chunks based on relevance/reranker scores up to max_tokens, 
        de-duplicates them, sorts them by original document order, and formats the context.
        
        Returns:
            Tuple[context_str, used_chunk_ids, page_references, image_references]
        """
        logger.info("Building context from retrieved chunks...")
        
        # 1. De-duplicate chunks based on chunk_id while preserving retrieval order
        seen_chunk_ids: Set[str] = set()
        deduplicated_chunks: List[ScoredChunk] = []
        for chunk in retrieved_chunks:
            chunk_id = chunk.metadata.chunk_id
            if chunk_id not in seen_chunk_ids:
                seen_chunk_ids.add(chunk_id)
                deduplicated_chunks.append(chunk)

        # 2. Select chunks up to max_tokens (respecting reranker ordering as input is sorted by reranker score)
        selected_chunks: List[ScoredChunk] = []
        current_tokens = 0
        
        for chunk in deduplicated_chunks:
            # Estimate tokens: use metadata estimate, fallback to character count estimation if 0 or None
            token_est = chunk.metadata.token_estimate or (len(chunk.content) // 4)
            # Add some token overhead for formatting (headings, page number labels)
            formatted_overhead_est = 50 
            
            if current_tokens + token_est + formatted_overhead_est <= self.max_tokens:
                selected_chunks.append(chunk)
                current_tokens += (token_est + formatted_overhead_est)
            else:
                logger.info(f"Skipping chunk {chunk.metadata.chunk_id} to avoid exceeding context window limit of {self.max_tokens} tokens.")
        
        # 3. Extract image references from selected chunks
        image_references = self.extract_image_references(selected_chunks)

        # 4. Sort selected chunks to preserve original document order (by page number, then chunk index)
        selected_chunks.sort(key=lambda c: (c.metadata.page_number, self._parse_chunk_index(c.metadata.chunk_id)))

        # 4.5 Dynamic adjacent chunk merging (Phase 6 Optimization - only for text chunks)
        merged_chunks = []
        for chunk in selected_chunks:
            if not merged_chunks:
                merged_chunks.append(chunk)
            else:
                prev = merged_chunks[-1]
                prev_idx = self._parse_chunk_index(prev.metadata.chunk_id)
                curr_idx = self._parse_chunk_index(chunk.metadata.chunk_id)
                
                if (curr_idx == prev_idx + 1 and 
                    prev.metadata.document_id == chunk.metadata.document_id and
                    prev.metadata.page_number == chunk.metadata.page_number and
                    prev.metadata.section == chunk.metadata.section and
                    prev.metadata.chunk_type == "text" and chunk.metadata.chunk_type == "text"):
                    
                    prev.content += "\n\n" + chunk.content
                    logger.info(f"Dynamically merged adjacent chunks {prev.metadata.chunk_id} and {chunk.metadata.chunk_id}")
                else:
                    merged_chunks.append(chunk)
        selected_chunks = merged_chunks

        # 5. Section-level Context Assembly & Merging
        sections_dict = {}
        used_chunk_ids = []
        
        # Track page references prioritized by reranker relevance (avoiding noisy pages)
        top_relevant_pages = []
        for chunk in deduplicated_chunks[:6]:
            p = chunk.metadata.page_number
            if p and p not in top_relevant_pages:
                top_relevant_pages.append(p)
        
        for chunk in selected_chunks:
            used_chunk_ids.append(chunk.metadata.chunk_id)
            sec_key = getattr(chunk.metadata, "section_heading", None) or chunk.metadata.section or "General Context"
            if sec_key not in sections_dict:
                sections_dict[sec_key] = []
            sections_dict[sec_key].append(chunk)

        context_parts = []
        for sec_key, sec_chunks in sections_dict.items():
            first_page = min(c.metadata.page_number for c in sec_chunks)
            last_page = max(c.metadata.page_number for c in sec_chunks)
            page_label = f"Page {first_page}" if first_page == last_page else f"Pages {first_page}-{last_page}"
            
            combined_section_body = "\n\n".join(c.content for c in sec_chunks)
            
            context_part = (
                f"=== SECTION CONTEXT: {sec_key.upper()} [{page_label}] ===\n"
                f"{combined_section_body}\n"
                f"=== END SECTION CONTEXT: {sec_key.upper()} ==="
            )
            context_parts.append(context_part)

        context_str = "\n\n".join(context_parts)
        
        # Sorted concise page references (capped to the most relevant pages)
        sorted_pages = sorted(top_relevant_pages) if top_relevant_pages else sorted(list(set(c.metadata.page_number for c in selected_chunks)))
        
        logger.info(f"Context constructed using {len(used_chunk_ids)} chunks across pages {sorted_pages} with {len(image_references)} visual assets in {len(sections_dict)} section blocks.")
        return context_str, used_chunk_ids, sorted_pages, image_references
