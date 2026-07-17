import logging
from typing import List, Dict, Optional, Any
from src.rag.document_schema import StructuredDocument, DocumentElement, BoundingBox
from src.rag.chunk_schema import DocumentChunk, ChunkMetadata
from src.rag.chunk_utils import estimate_tokens, count_words, format_section_path

logger = logging.getLogger("pipeline")

class ChunkBuilder:
    """
    Builds semantic chunks from a StructuredDocument.
    Preserves document structure, headings, lists, tables, and images without breaking semantic units.
    """

    def __init__(self, target_tokens_min: int = 250, target_tokens_max: int = 500) -> None:
        self.target_tokens_min = target_tokens_min
        self.target_tokens_max = target_tokens_max
        self._nlp = None

    def build_chunks(self, doc: StructuredDocument, document_id: str) -> List[DocumentChunk]:
        """
        Processes all document elements sequentially and aggregates them into semantic chunks.
        """
        chunks: List[DocumentChunk] = []
        
        # Heading context tracking: level -> heading text
        active_headings: Dict[int, str] = {}
        active_heading_ids: Dict[int, str] = {}
        
        # Accumulators for grouping elements
        current_text_elements: List[DocumentElement] = []
        current_list_elements: List[DocumentElement] = []
        current_footnote_elements: List[DocumentElement] = []
        
        def finalize_text_chunk():
            if not current_text_elements:
                return
            chunk = self._create_text_chunk(current_text_elements, document_id, dict(active_headings), dict(active_heading_ids), len(chunks))
            chunks.append(chunk)
            current_text_elements.clear()

        def finalize_list_chunk():
            if not current_list_elements:
                return
            chunk = self._create_list_chunk(current_list_elements, document_id, dict(active_headings), dict(active_heading_ids), len(chunks))
            chunks.append(chunk)
            current_list_elements.clear()

        def finalize_footnote_chunk():
            if not current_footnote_elements:
                return
            chunk = self._create_footnote_chunk(current_footnote_elements, document_id, dict(active_headings), dict(active_heading_ids), len(chunks))
            chunks.append(chunk)
            current_footnote_elements.clear()

        for element in doc.elements:
            el_type = element.type
            
            # --- Finalize other accumulators if element type changes ---
            # If we see a table, image, code block, or a list, finalize running texts
            if el_type in ("table", "image", "code"):
                finalize_text_chunk()
                finalize_list_chunk()
                finalize_footnote_chunk()
            elif el_type == "list_item":
                finalize_text_chunk()
                finalize_footnote_chunk()
            elif el_type == "footnote":
                finalize_text_chunk()
                finalize_list_chunk()
            elif el_type in ("paragraph", "heading"):
                finalize_list_chunk()
                finalize_footnote_chunk()

            # --- Check if we should split text chunk on new heading ---
            if el_type in ("paragraph", "heading"):
                if el_type == "heading" and current_text_elements:
                    # If we hit a new heading and already have accumulated paragraphs,
                    # finalize the previous chunk first to avoid orphans or multi-topic chunks.
                    has_paragraphs = any(e.type == "paragraph" for e in current_text_elements)
                    if has_paragraphs:
                        finalize_text_chunk()

            # --- Heading Context Tracking ---
            # Update context AFTER finalization check so the finalized chunk gets the old context
            if el_type == "heading":
                lvl = element.metadata.level or 1
                
                # A new heading at level L resets all subheadings at level > L
                levels_to_remove = [k for k in active_headings.keys() if k > lvl]
                for k in levels_to_remove:
                    active_headings.pop(k, None)
                    active_heading_ids.pop(k, None)
                    
                active_headings[lvl] = element.text
                active_heading_ids[lvl] = element.id

            # --- Process Elements based on type ---
            if el_type in ("paragraph", "heading"):
                # Add to accumulator
                current_text_elements.append(element)
                
                # Check if size exceeds target max
                acc_text = "\n\n".join(e.text for e in current_text_elements)
                if estimate_tokens(acc_text) >= self.target_tokens_max:
                    finalize_text_chunk()

            elif el_type == "list_item":
                current_list_elements.append(element)
                # Check if list size exceeds target max
                acc_text = "\n".join(f"- {e.text}" for e in current_list_elements)
                if estimate_tokens(acc_text) >= self.target_tokens_max:
                    finalize_list_chunk()

            elif el_type == "footnote":
                current_footnote_elements.append(element)
                # Check size
                acc_text = "\n".join(e.text for e in current_footnote_elements)
                if estimate_tokens(acc_text) >= self.target_tokens_max:
                    finalize_footnote_chunk()

            elif el_type == "code":
                # Code blocks remain intact in their own chunk
                chunk = self._create_code_chunk(element, document_id, active_headings, active_heading_ids, len(chunks))
                chunks.append(chunk)

            elif el_type == "table":
                # Standalone table chunk
                # Resolve detailed structure from doc
                table_struct = doc.tables.get(element.id)
                chunk = self._create_table_chunk(element, table_struct, document_id, active_headings, active_heading_ids, len(chunks))
                chunks.append(chunk)

            elif el_type == "image":
                # Standalone image chunk
                image_meta = doc.images.get(element.id)
                chunk = self._create_image_chunk(element, image_meta, document_id, active_headings, active_heading_ids, len(chunks))
                chunks.append(chunk)

        # Finalize any remaining accumulators
        finalize_text_chunk()
        finalize_list_chunk()
        finalize_footnote_chunk()

        return chunks


    def _enrich_chunk_metadata(self, content: str, page_number: int, section_path: Optional[str] = None) -> dict:
        import re
        
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
        
        # 6. Extract Keywords
        stopwords = {"about", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are", "aren't", "as", "at", "be", "because", "been", "before", "being", "below", "between", "both", "but", "by", "can't", "cannot", "could", "couldn't", "did", "didn't", "do", "does", "doesn't", "doing", "don't", "down", "during", "each", "few", "for", "from", "further", "had", "hadn't", "has", "hasn't", "have", "haven't", "having", "he", "he'd", "he'll", "he's", "her", "here", "here's", "hers", "herself", "him", "himself", "his", "how", "how's", "i", "i'd", "i'll", "i'm", "i've", "if", "in", "into", "is", "isn't", "it", "it's", "its", "itself", "let's", "me", "more", "most", "mustn't", "my", "myself", "no", "nor", "not", "of", "off", "on", "once", "only", "or", "other", "ought", "our", "ours", "ourselves", "out", "over", "own", "same", "shan't", "she", "she'd", "she'll", "she's", "should", "shouldn't", "so", "some", "such", "than", "that", "that's", "the", "their", "theirs", "them", "themselves", "then", "there", "there's", "these", "they", "they'd", "they'll", "they're", "they've", "this", "those", "through", "to", "too", "under", "until", "up", "very", "was", "wasn't", "we", "we'd", "we'll", "we're", "we've", "were", "weren't", "what", "what's", "when", "when's", "where", "where's", "which", "while", "who", "who's", "whom", "why", "why's", "with", "won't", "would", "wouldn't", "you", "you'd", "you'll", "you're", "you've", "your", "yours", "yourself", "yourselves"}
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

    def _get_heading_contexts(
        self, 
        active_headings: Dict[int, str], 
        active_heading_ids: Dict[int, str]
    ) -> tuple[Optional[str], Optional[str], List[str]]:
        """
        Helper to construct immediate heading, section path, and hierarchy path.
        """
        sorted_lvls = sorted(active_headings.keys())
        headings_list = [active_headings[k] for k in sorted_lvls]
        heading_ids_list = [active_heading_ids[k] for k in sorted_lvls]
        
        heading = headings_list[-1] if headings_list else None
        section = format_section_path(headings_list) if headings_list else "Root"
        
        return heading, section, heading_ids_list

    def _create_text_chunk(
        self, 
        elements: List[DocumentElement], 
        doc_id: str, 
        active_headings: Dict[int, str],
        active_heading_ids: Dict[int, str],
        chunk_idx: int
    ) -> DocumentChunk:
        content = "\n\n".join(e.text for e in elements)
        heading, section, hierarchy_path = self._get_heading_contexts(active_headings, active_heading_ids)
        
        page_number = elements[0].metadata.page_number
        source_ids = [e.id for e in elements]
        bboxes = [e.metadata.bbox for e in elements if e.metadata.bbox is not None]
        
        enriched = self._enrich_chunk_metadata(content, page_number, section)
        metadata = ChunkMetadata(
            chunk_id=f"{doc_id}_chunk_{chunk_idx:04d}",
            document_id=doc_id,
            page_number=page_number,
            chunk_type="text",
            heading=heading,
            section=section,
            hierarchy_path=hierarchy_path,
            source_element_ids=source_ids,
            word_count=count_words(content),
            token_estimate=estimate_tokens(content),
            bounding_boxes=bboxes,
            **enriched
        )
        return DocumentChunk(content=content, metadata=metadata)

    def _create_list_chunk(
        self, 
        elements: List[DocumentElement], 
        doc_id: str, 
        active_headings: Dict[int, str],
        active_heading_ids: Dict[int, str],
        chunk_idx: int
    ) -> DocumentChunk:
        content = "\n".join(f"* {e.text}" for e in elements)
        heading, section, hierarchy_path = self._get_heading_contexts(active_headings, active_heading_ids)
        
        page_number = elements[0].metadata.page_number
        source_ids = [e.id for e in elements]
        bboxes = [e.metadata.bbox for e in elements if e.metadata.bbox is not None]
        
        enriched = self._enrich_chunk_metadata(content, page_number, section)
        metadata = ChunkMetadata(
            chunk_id=f"{doc_id}_chunk_{chunk_idx:04d}",
            document_id=doc_id,
            page_number=page_number,
            chunk_type="list",
            heading=heading,
            section=section,
            hierarchy_path=hierarchy_path,
            source_element_ids=source_ids,
            word_count=count_words(content),
            token_estimate=estimate_tokens(content),
            bounding_boxes=bboxes,
            **enriched
        )
        return DocumentChunk(content=content, metadata=metadata)

    def _create_footnote_chunk(
        self, 
        elements: List[DocumentElement], 
        doc_id: str, 
        active_headings: Dict[int, str],
        active_heading_ids: Dict[int, str],
        chunk_idx: int
    ) -> DocumentChunk:
        content = "\n".join(e.text for e in elements)
        heading, section, hierarchy_path = self._get_heading_contexts(active_headings, active_heading_ids)
        
        page_number = elements[0].metadata.page_number
        source_ids = [e.id for e in elements]
        bboxes = [e.metadata.bbox for e in elements if e.metadata.bbox is not None]
        
        enriched = self._enrich_chunk_metadata(content, page_number, section)
        metadata = ChunkMetadata(
            chunk_id=f"{doc_id}_chunk_{chunk_idx:04d}",
            document_id=doc_id,
            page_number=page_number,
            chunk_type="footnote",
            heading=heading,
            section=section,
            hierarchy_path=hierarchy_path,
            source_element_ids=source_ids,
            word_count=count_words(content),
            token_estimate=estimate_tokens(content),
            bounding_boxes=bboxes,
            **enriched
        )
        return DocumentChunk(content=content, metadata=metadata)

    def _create_code_chunk(
        self, 
        element: DocumentElement, 
        doc_id: str, 
        active_headings: Dict[int, str],
        active_heading_ids: Dict[int, str],
        chunk_idx: int
    ) -> DocumentChunk:
        content = element.text
        heading, section, hierarchy_path = self._get_heading_contexts(active_headings, active_heading_ids)
        
        page_number = element.metadata.page_number
        bboxes = [element.metadata.bbox] if element.metadata.bbox else []
        
        enriched = self._enrich_chunk_metadata(content, page_number, section)
        metadata = ChunkMetadata(
            chunk_id=f"{doc_id}_chunk_{chunk_idx:04d}",
            document_id=doc_id,
            page_number=page_number,
            chunk_type="code",
            heading=heading,
            section=section,
            hierarchy_path=hierarchy_path,
            source_element_ids=[element.id],
            word_count=count_words(content),
            token_estimate=estimate_tokens(content),
            bounding_boxes=bboxes,
            **enriched
        )
        return DocumentChunk(content=content, metadata=metadata)

    def _create_table_chunk(
        self, 
        element: DocumentElement, 
        table_struct: Optional[Any],
        doc_id: str, 
        active_headings: Dict[int, str],
        active_heading_ids: Dict[int, str],
        chunk_idx: int
    ) -> DocumentChunk:
        caption_text = getattr(table_struct, "caption", None)
        markdown_str = getattr(table_struct, "markdown", None) or element.text
        
        content_parts = []
        if caption_text:
            content_parts.append(f"Table Caption: {caption_text}")
        content_parts.append(markdown_str)
        content = "\n\n".join(content_parts)
        
        heading, section, hierarchy_path = self._get_heading_contexts(active_headings, active_heading_ids)
        page_number = element.metadata.page_number
        bboxes = [element.metadata.bbox] if element.metadata.bbox else []
        
        enriched = self._enrich_chunk_metadata(content, page_number, section)
        metadata = ChunkMetadata(
            chunk_id=f"{doc_id}_chunk_{chunk_idx:04d}",
            document_id=doc_id,
            page_number=page_number,
            chunk_type="table",
            heading=heading,
            section=section,
            hierarchy_path=hierarchy_path,
            source_element_ids=[element.id],
            word_count=count_words(content),
            token_estimate=estimate_tokens(content),
            bounding_boxes=bboxes,
            **enriched
        )
        return DocumentChunk(content=content, metadata=metadata)

    def _create_image_chunk(
        self, 
        element: DocumentElement, 
        image_meta: Optional[Any],
        doc_id: str, 
        active_headings: Dict[int, str],
        active_heading_ids: Dict[int, str],
        chunk_idx: int
    ) -> DocumentChunk:
        caption_text = getattr(image_meta, "caption", None) or element.metadata.caption_text
        ocr_text = getattr(image_meta, "ocr_text", None) or element.metadata.ocr_text
        vlm_desc = getattr(image_meta, "semantic_description", None)
        img_type = getattr(image_meta, "image_type", None)
        
        content_parts = []
        if img_type:
            content_parts.append(f"Image Type: {img_type}")
        if caption_text:
            content_parts.append(f"Image Caption: {caption_text}")
        if ocr_text:
            content_parts.append(f"Image OCR Text: {ocr_text}")
        if vlm_desc:
            content_parts.append(f"Image VLM Description: {vlm_desc}")
            
        if not content_parts:
            content_parts.append("Image Element")
            
        content = "\n\n".join(content_parts)
        
        heading, section, hierarchy_path = self._get_heading_contexts(active_headings, active_heading_ids)
        page_number = element.metadata.page_number
        bboxes = [element.metadata.bbox] if element.metadata.bbox else []
        
        enriched = self._enrich_chunk_metadata(content, page_number, section)
        metadata = ChunkMetadata(
            chunk_id=f"{doc_id}_chunk_{chunk_idx:04d}",
            document_id=doc_id,
            page_number=page_number,
            chunk_type="image",
            heading=heading,
            section=section,
            hierarchy_path=hierarchy_path,
            source_element_ids=[element.id],
            word_count=count_words(content),
            token_estimate=estimate_tokens(content),
            bounding_boxes=bboxes,
            **enriched
        )
        return DocumentChunk(content=content, metadata=metadata)

