import logging
import re
from pathlib import Path
from typing import List, Dict, Optional, Any
from src.rag.document_schema import StructuredDocument, DocumentElement, ElementMetadata, BoundingBox
from src.rag.chunk_schema import DocumentChunk, ChunkMetadata
from src.rag.chunk_utils import estimate_tokens, count_words, format_section_path

logger = logging.getLogger("pipeline")

def split_paragraph_recursively(text: str, max_tokens: int) -> List[str]:
    """
    If a paragraph exceeds the maximum token budget, split it recursively,
    preferring sentence boundaries, then clause boundaries. Never split mid-sentence.
    """
    if estimate_tokens(text) <= max_tokens:
        return [text]
    
    # Try splitting by sentence boundaries first
    sentences = re.split(r'(?<=[.!?])\s+', text)
    if len(sentences) <= 1:
        # If we cannot split into sentences, try splitting by punctuation (commas, semicolons)
        sub_clauses = re.split(r'(?<=[,;])\s+', text)
        if len(sub_clauses) <= 1:
            # Fallback to word-level splitting if no punctuation is found
            words = text.split()
            chunks_words = []
            curr_words = []
            for w in words:
                curr_words.append(w)
                if int(len(curr_words) * 1.3) + 1 >= max_tokens:
                    chunks_words.append(" ".join(curr_words))
                    curr_words = []
            if curr_words:
                chunks_words.append(" ".join(curr_words))
            return chunks_words
        else:
            sentences = sub_clauses
            
    # Group sentences into sub-paragraphs under max_tokens limit
    sub_paras = []
    current_para = []
    current_tokens = 0
    for sentence in sentences:
        s_tokens = estimate_tokens(sentence)
        if current_tokens + s_tokens > max_tokens:
            if current_para:
                sub_paras.append(" ".join(current_para))
                current_para = [sentence]
                current_tokens = s_tokens
            else:
                # Single sentence itself exceeds max_tokens, keep it intact to obey 'never split mid sentence'
                sub_paras.append(sentence)
                current_para = []
                current_tokens = 0
        else:
            current_para.append(sentence)
            current_tokens += s_tokens
    if current_para:
        sub_paras.append(" ".join(current_para))
        
    return sub_paras

def get_overlap_text(text: str, target_overlap_tokens: int = 50) -> str:
    """
    Retrieves a sentence-aligned overlap text from the end of the text.
    Ensures semantic continuity without duplicating entire chunks.
    """
    if not text or target_overlap_tokens <= 0:
        return ""
        
    sentences = re.split(r'(?<=[.!?])\s+', text)
    if len(sentences) <= 1:
        # Fallback to word splitting
        words = text.split()
        if len(words) <= target_overlap_tokens:
            return text
        return " ".join(words[-target_overlap_tokens:])
        
    overlap_sentences = []
    current_tokens = 0
    # Iterate from the end of sentences list backwards
    for sentence in reversed(sentences):
        s_tokens = estimate_tokens(sentence)
        if current_tokens + s_tokens > target_overlap_tokens:
            # Ensure at least one sentence is included if empty
            if not overlap_sentences:
                overlap_sentences.insert(0, sentence)
            break
        overlap_sentences.insert(0, sentence)
        current_tokens += s_tokens
        
    return " ".join(overlap_sentences)

def is_semantic_content(text: str) -> bool:
    """
    Identifies if a block contains actual semantic information.
    Filters out empty text, whitespace, only decorative bullets, or divider lines.
    """
    cleaned = text.strip()
    if not cleaned:
        return False
    # Remove common bullets and numbering patterns (e.g., *, -, 1., (a))
    no_bullets = re.sub(r'^[\s\*\-\•\+\.\d\)\(]+\s*$', '', cleaned)
    if not no_bullets:
        return False
    # Check if only line separators (e.g. ---, ===, ___, ***)
    if re.match(r'^[\s\-\=\_\*]+$', cleaned) and len(cleaned) > 2:
        return False
    return True

class ChunkBuilder:
    """
    Builds semantic, layout-aware, and hierarchy-aware chunks from a StructuredDocument.
    Merges paragraphs, consolidates tables and images, and performs context conditioning.
    """

    def __init__(self, target_tokens_min: int = 250, target_tokens_max: int = 500, overlap_tokens: int = 50) -> None:
        self.target_tokens_min = target_tokens_min
        self.target_tokens_max = target_tokens_max
        self.overlap_tokens = overlap_tokens
        self._nlp = None

    def build_chunks(self, doc: StructuredDocument, document_id: str) -> List[DocumentChunk]:
        """
        Processes all document elements sequentially and aggregates them into semantic,
        context-conditioned, and layout-aware chunks with sliding window overlap.
        """
        chunks: List[DocumentChunk] = []
        
        # Heading context tracking
        active_headings: Dict[int, str] = {}
        active_heading_ids: Dict[int, str] = {}
        
        # Accumulators
        accumulators = {
            "text": {"texts": [], "elements": [], "tokens": 0, "overlap": ""},
            "list": {"texts": [], "elements": [], "tokens": 0, "overlap": ""},
            "code": {"texts": [], "elements": [], "tokens": 0, "overlap": ""},
            "footnote": {"texts": [], "elements": [], "tokens": 0, "overlap": ""}
        }
        
        def finalize_accumulator(acc_type: str):
            acc = accumulators[acc_type]
            if not acc["elements"]:
                return
            
            # Combine body text
            if acc_type == "list":
                actual_text = "\n".join(f"* {t}" for t in acc["texts"])
            else:
                actual_text = "\n\n".join(acc["texts"])
                
            # Filter non-semantic chunks (Task 1)
            if not is_semantic_content(actual_text):
                acc["texts"].clear()
                acc["elements"].clear()
                acc["tokens"] = 0
                return

            chunk_idx = len(chunks)
            page_number = acc["elements"][0].metadata.page_number
            heading, section, hierarchy_path, sec_heading, subsec_heading, sec_id = self._get_heading_contexts(active_headings, active_heading_ids)
            
            # Prepend Context Conditioning (Task 5)
            header = f"Document Section: {section}\nContent:\n"
            if acc["overlap"]:
                content = header + acc["overlap"] + "\n" + actual_text
            else:
                content = header + actual_text
                
            bboxes = [el.metadata.bbox for el in acc["elements"] if el.metadata.bbox]
            source_ids = [el.id for el in acc["elements"]]
            element_types = [el.type for el in acc["elements"]]
            
            relationships = {
                "belongs_to": hierarchy_path[-1] if hierarchy_path else "body"
            }
            if chunk_idx > 0:
                relationships["previous"] = chunks[-1].metadata.chunk_id
                
            # Clean metadata enrichment (Task 3) - Run on actual_text instead of content
            enriched = self._enrich_chunk_metadata(actual_text, page_number, section)
            
            metadata = ChunkMetadata(
                chunk_id=f"{document_id}_chunk_{chunk_idx:04d}",
                document_id=document_id,
                page_number=page_number,
                chunk_type=acc_type,
                heading=heading,
                section=section,
                section_id=sec_id,
                section_heading=sec_heading,
                subsection_heading=subsec_heading,
                hierarchy_path=hierarchy_path,
                source_element_ids=source_ids,
                word_count=count_words(content),
                token_estimate=estimate_tokens(content),
                bounding_boxes=bboxes,
                element_types=element_types,
                relationships=relationships,
                **enriched
            )
            
            chunks.append(DocumentChunk(content=content, metadata=metadata))
            
            # Save overlap text for next chunk of same type (Task 6)
            acc["overlap"] = get_overlap_text(actual_text, self.overlap_tokens)
            
            # Reset
            acc["texts"].clear()
            acc["elements"].clear()
            acc["tokens"] = 0

        def finalize_all_except(keep_type: Optional[str] = None):
            for t in list(accumulators.keys()):
                if t != keep_type:
                    finalize_accumulator(t)
                    # Reset overlap when switching structure type
                    accumulators[t]["overlap"] = ""

        # Loop through document elements sequentially
        for element in doc.elements:
            el_type = element.type
            
            # --- Boundary checks ---
            # Tables & images finalize all accumulators and reset overlap context
            if el_type in ("table", "image"):
                finalize_all_except(None)
                
            # Headings finalize all accumulators, reset overlap context, and create explicit heading chunk (Task 2)
            if el_type == "heading":
                finalize_all_except(None)
                
                # Update Heading Context
                lvl = element.metadata.level or 1
                levels_to_remove = [k for k in active_headings.keys() if k > lvl]
                for k in levels_to_remove:
                    active_headings.pop(k, None)
                    active_heading_ids.pop(k, None)
                active_headings[lvl] = element.text
                active_heading_ids[lvl] = element.id
                
                if is_semantic_content(element.text):
                    heading, section, hierarchy_path, sec_heading, subsec_heading, sec_id = self._get_heading_contexts(active_headings, active_heading_ids)
                    content = f"Document Section: {section}\nContent:\n{element.text}"
                    
                    chunk_idx = len(chunks)
                    relationships = {
                        "belongs_to": hierarchy_path[-2] if len(hierarchy_path) > 1 else "body"
                    }
                    if chunk_idx > 0:
                        relationships["previous"] = chunks[-1].metadata.chunk_id
                        
                    # Clean metadata enrichment (Task 3) - Run on element.text instead of content
                    enriched = self._enrich_chunk_metadata(element.text, element.metadata.page_number, section)
                    
                    metadata = ChunkMetadata(
                        chunk_id=f"{document_id}_chunk_{chunk_idx:04d}",
                        document_id=document_id,
                        page_number=element.metadata.page_number,
                        chunk_type="heading",
                        heading=heading,
                        section=section,
                        section_id=sec_id,
                        section_heading=sec_heading,
                        subsection_heading=subsec_heading,
                        hierarchy_path=hierarchy_path,
                        source_element_ids=[element.id],
                        word_count=count_words(content),
                        token_estimate=estimate_tokens(content),
                        bounding_boxes=[element.metadata.bbox] if element.metadata.bbox else [],
                        element_types=["heading"],
                        relationships=relationships,
                        **enriched
                    )
                    chunks.append(DocumentChunk(content=content, metadata=metadata))
                continue

            # Process Tables (Task 3)
            if el_type == "table":
                table_struct = doc.tables.get(element.id)
                tbl_chunk = self._create_semantic_table_chunk(
                    element, table_struct, document_id, active_headings, active_heading_ids, len(chunks)
                )
                if tbl_chunk:
                    chunks.append(tbl_chunk)
                continue
                
            # Process Images (Task 4)
            if el_type == "image":
                image_meta = doc.images.get(element.id)
                if not image_meta and hasattr(doc, "images") and doc.images:
                    target_id = getattr(element.metadata, "image_id", None) or element.id
                    for k, v in doc.images.items():
                        if k == target_id or k.endswith(target_id) or target_id.endswith(k):
                            image_meta = v
                            break
                img_chunk = self._create_semantic_image_chunk(
                    element, image_meta, document_id, active_headings, active_heading_ids, len(chunks)
                )
                if img_chunk:
                    chunks.append(img_chunk)
                continue
                
            # Process text-like elements: paragraphs, lists, code, footnotes, formulas, and standalone captions
            # Map element type to accumulator key
            if el_type == "list_item":
                acc_type = "list"
            elif el_type == "code":
                acc_type = "code"
            elif el_type == "footnote":
                acc_type = "footnote"
            else:
                acc_type = "text"
                
            finalize_all_except(acc_type)
            acc = accumulators[acc_type]
            el_tokens = estimate_tokens(element.text)
            
            # Large Paragraph Handling (Task 7)
            if el_tokens > self.target_tokens_max:
                split_texts = split_paragraph_recursively(element.text, self.target_tokens_max)
                for st in split_texts:
                    st_tokens = estimate_tokens(st)
                    if acc["tokens"] + st_tokens > self.target_tokens_max:
                        finalize_accumulator(acc_type)
                    acc["texts"].append(st)
                    acc["elements"].append(element)
                    acc["tokens"] += st_tokens
            else:
                if acc["tokens"] + el_tokens > self.target_tokens_max:
                    finalize_accumulator(acc_type)
                acc["texts"].append(element.text)
                acc["elements"].append(element)
                acc["tokens"] += el_tokens

        # Finalize any leftover elements in accumulators
        finalize_all_except(None)
        
        # Process any images in doc.images that were not encountered in doc.elements
        processed_image_ids = {c.metadata.image_id for c in chunks if c.metadata.image_id}
        processed_image_paths = {c.metadata.image_path for c in chunks if c.metadata.image_path}
        if doc.images:
            for img_id, img_meta in doc.images.items():
                if img_id not in processed_image_ids:
                    p_num = getattr(img_meta, "page_number", None) or (img_meta.get("page") if isinstance(img_meta, dict) else 1) or 1
                    b_box = getattr(img_meta, "bbox", None) or (img_meta.get("bounding_box") if isinstance(img_meta, dict) else None)
                    virtual_el = DocumentElement(
                        id=img_id,
                        type="image",
                        text=getattr(img_meta, "caption", "") or getattr(img_meta, "title", "") or "Image",
                        metadata=ElementMetadata(
                            page_number=p_num,
                            bbox=b_box,
                            image_id=img_id
                        )
                    )
                    img_chunk = self._create_semantic_image_chunk(
                        virtual_el, img_meta, document_id, active_headings, active_heading_ids, len(chunks)
                    )
                    if img_chunk:
                        chunks.append(img_chunk)
                        processed_image_ids.add(img_id)
                        if img_chunk.metadata.image_path:
                            processed_image_paths.add(img_chunk.metadata.image_path)

        # Process any image metadata JSONs in 05_images not yet represented
        if document_id:
            try:
                import json
                from src.config import ROOT_DIR
                images_dir = ROOT_DIR / "data" / "output" / document_id / "05_images"
                if images_dir.exists():
                    for jf in sorted(list(images_dir.glob("image_*.json"))):
                        stem = jf.stem
                        rel_path = f"05_images/{stem}.png"
                        try:
                            with open(jf, "r", encoding="utf-8") as f:
                                jdata = json.load(f)
                            im_id = jdata.get("image_id") or stem
                            if im_id not in processed_image_ids and rel_path not in processed_image_paths:
                                p_num = int(jdata.get("page", 1))
                                b_box = None
                                if jdata.get("bounding_box"):
                                    b_raw = jdata["bounding_box"]
                                    if isinstance(b_raw, dict):
                                        b_box = BoundingBox(**b_raw)
                                    elif isinstance(b_raw, BoundingBox):
                                        b_box = b_raw
                                virtual_el = DocumentElement(
                                    id=im_id,
                                    type="image",
                                    text=jdata.get("caption_text") or jdata.get("title") or "Image",
                                    metadata=ElementMetadata(
                                        page_number=p_num,
                                        bbox=b_box,
                                        image_id=im_id
                                    )
                                )
                                img_chunk = self._create_semantic_image_chunk(
                                    virtual_el, jdata, document_id, active_headings, active_heading_ids, len(chunks)
                                )
                                if img_chunk:
                                    chunks.append(img_chunk)
                                    processed_image_ids.add(im_id)
                                    processed_image_paths.add(rel_path)
                        except Exception as j_err:
                            logger.warning(f"Failed to chunk image JSON {jf.name}: {j_err}")
            except Exception as dir_err:
                logger.debug(f"05_images scan skipped: {dir_err}")

        return chunks

    def _create_semantic_table_chunk(
        self, 
        element: DocumentElement, 
        table_struct: Optional[Any], 
        doc_id: str, 
        active_headings: Dict[int, str],
        active_heading_ids: Dict[int, str],
        chunk_idx: int
    ) -> Optional[DocumentChunk]:
        """
        Creates one semantic table chunk consolidating caption, row/column headers,
        and markdown grid coordinates. Returns None if it is not semantic.
        """
        page_number = element.metadata.page_number
        heading, section, hierarchy_path, sec_heading, subsec_heading, sec_id = self._get_heading_contexts(active_headings, active_heading_ids)
        
        caption_text = ""
        markdown_str = element.text
        col_headers = []
        row_headers = []
        
        if table_struct:
            caption_text = getattr(table_struct, "caption", None) or element.metadata.caption_text or ""
            markdown_str = getattr(table_struct, "markdown", None) or element.text
            
            # Extract headers
            cells = getattr(table_struct, "cells", []) or []
            for cell in cells:
                # Row 0 cells represent column headers
                if cell.row_index == 0:
                    col_headers.append(cell.text)
                # Column 0 cells represent row headers
                if cell.col_index == 0:
                    row_headers.append(cell.text)
                    
        col_headers_str = ", ".join(col_headers) if col_headers else "None"
        row_headers_str = ", ".join(row_headers) if row_headers else "None"
        
        table_content_parts = []
        if caption_text:
            table_content_parts.append(f"Table Caption: {caption_text}")
        table_content_parts.append(f"Column Headers: {col_headers_str}")
        table_content_parts.append(f"Row Headers: {row_headers_str}")
        table_content_parts.append("Markdown Table:")
        table_content_parts.append(markdown_str)
        
        actual_table_text = "\n".join(table_content_parts)
        
        # Filter empty table chunks (Task 1)
        if not is_semantic_content(actual_table_text):
            return None

        # Apply Context Conditioning (Task 5)
        content = f"Document Section: {section}\nContent:\n{actual_table_text}"
        
        # Collect cell bboxes
        bboxes = [element.metadata.bbox] if element.metadata.bbox else []
        if table_struct and hasattr(table_struct, "cells"):
            for cell in table_struct.cells:
                if cell.bbox:
                    bboxes.append(cell.bbox)
                    
        # Clean metadata enrichment (Task 3) - Run on actual_table_text instead of content
        enriched = self._enrich_chunk_metadata(actual_table_text, page_number, section)
        
        metadata = ChunkMetadata(
            chunk_id=f"{doc_id}_chunk_{chunk_idx:04d}",
            document_id=doc_id,
            page_number=page_number,
            chunk_type="table",
            heading=heading,
            section=section,
            section_id=sec_id,
            section_heading=sec_heading,
            subsection_heading=subsec_heading,
            hierarchy_path=hierarchy_path,
            source_element_ids=[element.id],
            word_count=count_words(content),
            token_estimate=estimate_tokens(content),
            bounding_boxes=bboxes,
            table_id=element.id,
            element_types=["table"],
            relationships={"belongs_to": hierarchy_path[-1] if hierarchy_path else "body"},
            **enriched
        )
        
        return DocumentChunk(content=content, metadata=metadata)

    def _create_semantic_image_chunk(
        self, 
        element: DocumentElement, 
        image_meta: Optional[Any], 
        doc_id: str, 
        active_headings: Dict[int, str],
        active_heading_ids: Dict[int, str],
        chunk_idx: int
    ) -> Optional[DocumentChunk]:
        """
        Creates a dedicated semantic image representation combining semantic_description,
        caption, ocr_text, objects, keywords, and detected_entities as a first-class retrievable knowledge object.
        """
        page_number = element.metadata.page_number
        heading, section, hierarchy_path, sec_heading, subsec_heading, sec_id = self._get_heading_contexts(active_headings, active_heading_ids)
        
        caption_text = element.metadata.caption_text or ""
        ocr_text = element.metadata.ocr_text or ""
        vlm_desc = ""
        image_type = "Image"
        title = None
        subtitle = None
        objects = []
        keywords = []
        detected_entities = []
        img_path = None
        img_url = None
        explicit_caption = None
        entity_name = None
        designation = None
        text_before = None
        text_after = None
        layout_context = None
        importance_score = "MEDIUM"
        retrievable = True
        association_method = "none"
        confidence = 1.0
        association_confidence = 1.0
        
        if image_meta:
            if isinstance(image_meta, dict):
                title = image_meta.get("title")
                subtitle = image_meta.get("subtitle")
                caption_text = image_meta.get("caption_text") or image_meta.get("caption") or caption_text
                ocr_text = image_meta.get("ocr_text") or ocr_text
                vlm_desc = image_meta.get("semantic_description") or ""
                image_type = image_meta.get("image_type") or "Image"
                objects = image_meta.get("objects") or []
                keywords = image_meta.get("keywords") or []
                detected_entities = image_meta.get("detected_entities") or []
                img_path = image_meta.get("image_path")
                explicit_caption = image_meta.get("explicit_caption")
                entity_name = image_meta.get("entity_name")
                designation = image_meta.get("designation")
                text_before = image_meta.get("text_before")
                text_after = image_meta.get("text_after")
                layout_context = image_meta.get("layout_context")
                importance_score = image_meta.get("importance_score") or "MEDIUM"
                retrievable = image_meta.get("retrievable", True)
                association_method = image_meta.get("association_method") or "none"
                association_confidence = float(image_meta.get("association_confidence", image_meta.get("confidence", 1.0)) or 1.0)
                confidence = float(image_meta.get("confidence", 1.0) or 1.0)
            else:
                title = getattr(image_meta, "title", None)
                subtitle = getattr(image_meta, "subtitle", None)
                caption_text = getattr(image_meta, "caption_text", None) or getattr(image_meta, "caption", None) or caption_text
                ocr_text = getattr(image_meta, "ocr_text", None) or ocr_text
                vlm_desc = getattr(image_meta, "semantic_description", None) or ""
                image_type = getattr(image_meta, "image_type", None) or "Image"
                objects = getattr(image_meta, "objects", []) or []
                keywords = getattr(image_meta, "keywords", []) or []
                detected_entities = getattr(image_meta, "detected_entities", []) or []
                img_path = getattr(image_meta, "image_path", None)
                explicit_caption = getattr(image_meta, "explicit_caption", None)
                entity_name = getattr(image_meta, "entity_name", None)
                designation = getattr(image_meta, "designation", None)
                text_before = getattr(image_meta, "text_before", None)
                text_after = getattr(image_meta, "text_after", None)
                layout_context = getattr(image_meta, "layout_context", None)
                importance_score = getattr(image_meta, "importance_score", "MEDIUM") or "MEDIUM"
                retrievable = getattr(image_meta, "retrievable", True)
                association_method = getattr(image_meta, "association_method", "none") or "none"
                association_confidence = float(getattr(image_meta, "association_confidence", getattr(image_meta, "confidence", 1.0)) or 1.0)
                confidence = float(getattr(image_meta, "confidence", 1.0) or 1.0)

        if not img_path and element.metadata and hasattr(element.metadata, "image_path"):
            img_path = element.metadata.image_path

        # Check if corresponding 05_images JSON exists on disk to enrich metadata if missing
        if doc_id:
            try:
                import json
                from src.config import ROOT_DIR
                images_dir = ROOT_DIR / "data" / "output" / doc_id / "05_images"
                if images_dir.exists():
                    target_json = None
                    if img_path:
                        stem = Path(str(img_path).replace("\\", "/")).stem
                        cand = images_dir / f"{stem}.json"
                        if cand.exists():
                            target_json = cand
                    if not target_json and element.id:
                        clean_stem = element.id.replace("#/", "").replace("/", "_")
                        cand = images_dir / f"{clean_stem}.json"
                        if cand.exists():
                            target_json = cand
                    if not target_json:
                        for jf in images_dir.glob("image_*.json"):
                            try:
                                with open(jf, "r", encoding="utf-8") as f:
                                    jd = json.load(f)
                                if jd.get("image_id") == element.id:
                                    target_json = jf
                                    break
                            except Exception:
                                pass
                    if target_json and target_json.exists():
                        with open(target_json, "r", encoding="utf-8") as f:
                            jd = json.load(f)
                        title = title or jd.get("title")
                        subtitle = subtitle or jd.get("subtitle")
                        explicit_caption = explicit_caption or jd.get("explicit_caption")
                        caption_text = caption_text or jd.get("caption_text") or jd.get("caption")
                        entity_name = entity_name or jd.get("entity_name")
                        designation = designation or jd.get("designation")
                        sec_heading = sec_heading or jd.get("section_heading")
                        text_before = text_before or jd.get("text_before")
                        text_after = text_after or jd.get("text_after")
                        layout_context = layout_context or jd.get("layout_context")
                        importance_score = jd.get("importance_score") or importance_score
                        retrievable = jd.get("retrievable", retrievable)
                        vlm_desc = vlm_desc or jd.get("semantic_description") or ""
                        ocr_text = ocr_text or jd.get("ocr_text") or ""
                        image_type = jd.get("image_type") or image_type
                        img_path = img_path or jd.get("image_path")
                        img_url = img_url or jd.get("image_url")
                        if jd.get("keywords"):
                            keywords = list(set((keywords or []) + jd.get("keywords", [])))
                        if jd.get("objects"):
                            objects = list(set((objects or []) + jd.get("objects", [])))
                        if jd.get("detected_entities"):
                            detected_entities = list(set((detected_entities or []) + jd.get("detected_entities", [])))
            except Exception as j_err:
                logger.debug(f"Disk JSON metadata lookup skipped for image {element.id}: {j_err}")

        # Resolve clean filename for static browser URL
        img_filename = ""
        if img_path:
            clean_p = str(img_path).replace("\\", "/")
            base = Path(clean_p).name
            if base and ("." in base or base.startswith("image_")):
                img_filename = base
        if not img_filename and element.id:
            clean_id = element.id.replace("#/", "").replace("/", "_")
            img_filename = f"{clean_id}.png"

        if not img_url:
            img_url = f"/outputs/{doc_id}/05_images/{img_filename}"

        if not title:
            if explicit_caption:
                title = explicit_caption
            elif entity_name:
                title = entity_name
            elif caption_text:
                title = caption_text
            else:
                clean_name = element.id.replace("#/", "").replace("/", " ").replace("_", " ").title()
                title = f"Figure on Page {page_number} ({heading or clean_name})"

        if not caption_text.strip():
            caption_text = title

        if not vlm_desc.strip():
            vlm_desc = f"Visual graphic / {image_type.lower()} on Page {page_number} under section '{section}'."

        # Dedicated image representation combining all multimodal modalities
        image_parts = [
            f"Image ID: {element.id}",
            f"Image Type: {image_type}",
            f"Page: {page_number}",
            f"Image Title: {title}",
        ]
        if subtitle:
            image_parts.append(f"Image Subtitle: {subtitle}")
        if explicit_caption:
            image_parts.append(f"Explicit Document Caption: {explicit_caption}")
        if caption_text and caption_text != title:
            image_parts.append(f"Image Caption: {caption_text}")
        if entity_name:
            role_part = f" ({designation})" if designation else ""
            image_parts.append(f"Associated Person/Entity: {entity_name}{role_part}")
        if sec_heading:
            image_parts.append(f"Section Heading: {sec_heading}")
        if layout_context:
            image_parts.append(f"Layout Context: {layout_context}")
        if association_method and association_method != "none":
            image_parts.append(f"Association Method: {association_method}")
        if importance_score:
            image_parts.append(f"Importance: {importance_score}")
        if img_url:
            image_parts.append(f"Image URL: {img_url}")
        if vlm_desc:
            image_parts.append(f"Image Semantic Description: {vlm_desc}")
        if ocr_text:
            image_parts.append(f"Image OCR Text: {ocr_text}")
        if text_before:
            image_parts.append(f"Preceding Text Context: {text_before[:150]}")
        if text_after:
            image_parts.append(f"Succeeding Text Context: {text_after[:150]}")
        if objects:
            objs_str = ", ".join(objects) if isinstance(objects, list) else str(objects)
            image_parts.append(f"Detected Visual Objects: {objs_str}")
        if detected_entities:
            ents_str = ", ".join(detected_entities) if isinstance(detected_entities, list) else str(detected_entities)
            image_parts.append(f"Detected Entities: {ents_str}")
        if keywords:
            kws_str = ", ".join(keywords) if isinstance(keywords, list) else str(keywords)
            image_parts.append(f"Keywords: {kws_str}")
            
        actual_image_text = "\n".join(image_parts)

        # Apply Context Conditioning
        content = f"Document Section: {section}\nContent:\n{actual_image_text}"
        
        bboxes = [element.metadata.bbox] if element.metadata.bbox else []
        
        # Clean metadata enrichment
        enriched = self._enrich_chunk_metadata(actual_image_text, page_number, section)
        
        # Merge detected entities/keywords with enriched metadata if not already present
        if entity_name:
            if entity_name not in enriched.get("people", []):
                enriched.setdefault("people", []).append(entity_name)
        if detected_entities:
            for ent in detected_entities:
                if ent not in enriched.get("people", []) and ent not in enriched.get("organizations", []):
                    enriched.setdefault("organizations", []).append(ent)
        if keywords:
            for kw in keywords:
                if kw not in enriched.get("keywords", []):
                    enriched.setdefault("keywords", []).append(kw)

        metadata = ChunkMetadata(
            chunk_id=f"{doc_id}_chunk_{chunk_idx:04d}",
            document_id=doc_id,
            page_number=page_number,
            chunk_type="image",
            heading=heading,
            section=section,
            section_id=sec_id,
            section_heading=sec_heading,
            subsection_heading=subsec_heading,
            hierarchy_path=hierarchy_path,
            source_element_ids=[element.id],
            word_count=count_words(content),
            token_estimate=estimate_tokens(content),
            bounding_boxes=bboxes,
            image_id=element.id,
            image_path=img_path,
            image_url=img_url,
            image_type=image_type,
            title=title,
            subtitle=subtitle,
            explicit_caption=explicit_caption,
            caption_text=caption_text,
            entity_name=entity_name,
            designation=designation,
            text_before=text_before,
            text_after=text_after,
            layout_context=layout_context,
            importance_score=importance_score,
            retrievable=retrievable,
            association_method=association_method,
            association_confidence=association_confidence,
            confidence=confidence,
            caption=caption_text,
            ocr_text=ocr_text,
            semantic_description=vlm_desc,
            objects=objects if isinstance(objects, list) else [objects],
            detected_entities=detected_entities if isinstance(detected_entities, list) else [detected_entities],
            element_types=["image"],
            relationships={"belongs_to": hierarchy_path[-1] if hierarchy_path else "body"},
            **enriched
        )
        
        return DocumentChunk(content=content, metadata=metadata)

    def _get_heading_contexts(
        self, 
        active_headings: Dict[int, str], 
        active_heading_ids: Dict[int, str]
    ) -> tuple[Optional[str], Optional[str], List[str], Optional[str], Optional[str], Optional[str]]:
        """
        Helper to construct immediate heading, section path, hierarchy path, section_heading, subsection_heading, section_id.
        """
        sorted_lvls = sorted(active_headings.keys())
        headings_list = [active_headings[k] for k in sorted_lvls]
        heading_ids_list = [active_heading_ids[k] for k in sorted_lvls]
        
        heading = headings_list[-1] if headings_list else None
        section = format_section_path(headings_list) if headings_list else "Root"
        
        sec_heading = headings_list[0] if headings_list else "Root"
        subsec_heading = headings_list[1] if len(headings_list) > 1 else (heading if len(headings_list) > 1 else None)
        
        import re
        slug = re.sub(r'[^a-zA-Z0-9]+', '_', sec_heading.lower()).strip('_')
        sec_id = f"sec_{slug}" if slug else "sec_root"
        
        return heading, section, heading_ids_list, sec_heading, subsec_heading, sec_id

    def _enrich_chunk_metadata(self, content: str, page_number: int, section_path: Optional[str] = None) -> dict:
        """
        Enriches chunk metadata with contextual reports, states, regions, weapons, groups, NER, and keywords.
        """
        # 1. Report Number Context
        report_number = None
        report_match = re.search(r'(?i)(?:report|case|bulletin|no)\.?\s*#?\s*(\d+)', content)
        if not report_match and section_path:
            report_match = re.search(r'(?i)(?:report|case|bulletin|no)\.?\s*#?\s*(\d+)', section_path)
        if report_match:
            report_number = f"Report {report_match.group(1)}"

        # 2. States / Regions / Districts keyword parsing
        states_list = ["Assam", "Nagaland", "Manipur", "Meghalaya", "Tripura", "Mizoram", "Arunachal Pradesh", "Sikkim"]
        regions_list = ["Northeast", "Barak Valley", "Brahmaputra Valley"]
        districts_list = ["Kamrup", "Cachar", "Karbi Anglong", "Dimapur", "Kohima", "Imphal"]
        
        state = next((s for s in states_list if re.search(rf'\b{s}\b', content, re.IGNORECASE)), None)
        region = next((r for r in regions_list if re.search(rf'\b{r}\b', content, re.IGNORECASE)), None)
        district = next((d for d in districts_list if re.search(rf'\b{d}\b', content, re.IGNORECASE)), None)

        # 3. Weapons & Groups terms
        weapons_list = ["rifle", "pistol", "carbine", "ammunition", "grenade", "explosive", "weapon", "arms", "mortar", "bullet", "ak-47", "insurgent"]
        groups_list = ["insurgents", "militants", "police", "army", "security forces", "civilian", "authority"]
        
        weapons_found = sorted(list({w for w in weapons_list if re.search(rf'\b{w}s?\b', content, re.IGNORECASE)}))
        groups_found = sorted(list({g for g in groups_list if re.search(rf'\b{g}s?\b', content, re.IGNORECASE)}))

        # 4. Dates & Entities extraction (spaCy + regex hybrid)
        dates_found = re.findall(r'\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b|\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.? \d{1,2},? \d{4}\b|\b(?:19|20)\d{2}\b', content)
        
        people_found = []
        orgs_found = []
        locs_found = []

        # Run spaCy NER if available
        if self._nlp is None:
            import spacy
            try:
                self._nlp = spacy.load("en_core_web_sm")
            except Exception:
                self._nlp = "failed"
                
        if self._nlp != "failed":
            try:
                doc = self._nlp(content)
                for ent in doc.ents:
                    ent_text = ent.text.strip()
                    if ent.label_ == "PERSON" and len(ent_text) > 2:
                        people_found.append(ent_text)
                    elif ent.label_ == "ORG" and len(ent_text) > 2:
                        orgs_found.append(ent_text)
                    elif ent.label_ in ("GPE", "LOC") and len(ent_text) > 2:
                        locs_found.append(ent_text)
                    elif ent.label_ == "DATE":
                        dates_found.append(ent_text)
            except Exception:
                pass

        # 5. Fallback regex entity extraction (if spaCy failed)
        if not people_found:
            capitalized_seqs = re.findall(r'\b[A-Z][a-zA-Z]+\s+[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?\b', content)
            for seq in capitalized_seqs:
                if "page" not in seq.lower() and "figure" not in seq.lower() and "table" not in seq.lower():
                    if any(term in seq.lower() for term in ["inc", "corp", "org", "dept", "force", "police", "army", "committee", "group"]):
                        orgs_found.append(seq)
                    elif any(term in seq.lower() for term in ["valley", "district", "state", "india", "river", "town"]):
                        locs_found.append(seq)
                    else:
                        people_found.append(seq)

        # De-duplicate lists
        people = sorted(list(set(people_found)))
        organizations = sorted(list(set(orgs_found)))
        locations = sorted(list(set(locs_found)))
        dates = sorted(list(set(dates_found)))
        
        # 6. Extract Keywords (Task 4 Stopword Improvements)
        stopwords = {
            "about", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are", "aren't", "as", "at", 
            "be", "because", "been", "before", "being", "below", "between", "both", "but", "by", "can't", "cannot", 
            "could", "couldn't", "did", "didn't", "do", "does", "doesn't", "doing", "don't", "down", "during", "each", 
            "few", "for", "from", "further", "had", "hadn't", "has", "hasn't", "have", "haven't", "having", "he", "he'd", 
            "he'll", "he's", "her", "here", "here's", "hers", "herself", "him", "himself", "his", "how", "how's", "i", 
            "i'd", "i'll", "i'm", "i've", "if", "in", "into", "is", "isn't", "it", "it's", "its", "itself", "let's", 
            "me", "more", "most", "mustn't", "my", "myself", "no", "nor", "not", "of", "off", "on", "once", "only", 
            "or", "other", "ought", "our", "ours", "ourselves", "out", "over", "own", "same", "shan't", "she", "she'd", 
            "she'll", "she's", "should", "shouldn't", "so", "some", "such", "than", "that", "that's", "the", "their", 
            "theirs", "them", "themselves", "then", "there", "there's", "these", "they", "they'd", "they'll", "they're", 
            "they've", "this", "those", "through", "to", "too", "under", "until", "up", "very", "was", "wasn't", "we", 
            "we'd", "we'll", "we're", "we've", "were", "weren't", "what", "what's", "when", "when's", "where", "where's", 
            "which", "while", "who", "who's", "whom", "why", "why's", "with", "won't", "would", "wouldn't", "you", 
            "you'd", "you'll", "you're", "you've", "your", "yours", "yourself", "yourselves",
            # Structural/contextual words to ignore
            "document", "section", "content", "root", "page", "image", "table", "figure", "caption", "header", "footer"
        }
        words = re.findall(r'\b[a-zA-Z]{5,}\b', content.lower())
        word_freq = {}
        for w in words:
            if w not in stopwords:
                word_freq[w] = word_freq.get(w, 0) + 1
        sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
        keywords = [w for w, freq in sorted_words[:10]]

        return {
            "report_number": report_number,
            "state": state,
            "region": region,
            "district": district,
            "people": people,
            "organizations": organizations,
            "groups": groups_found,
            "dates": dates,
            "weapons": weapons_found,
            "locations": locations,
            "keywords": keywords
        }
