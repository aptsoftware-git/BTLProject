import logging
import json
import time
import os
import re
import shutil
import base64
from pathlib import Path
from datetime import datetime
from typing import Generator, List, Dict, Any, Optional, Tuple

from PIL import Image

from src.rag.document_schema import StructuredDocument, DocumentElement, BoundingBox
from src.rag.knowledge_objects import KnowledgeObject
from src.rag.config import RagConfig
from src.rag.embedder import Embedder
from src.rag.vector_store import VectorStore
from src.rag.chunk_schema import DocumentChunk, ChunkMetadata
from src.rag.ollama_client import OllamaClient
from src.rag.chunk_utils import estimate_tokens, count_words, format_section_path

logger = logging.getLogger("pipeline")

class KnowledgeExtractionAgent:
    """
    Dedicated agent responsible for converting a structured document representation
    into independent typed Knowledge Objects, running visual understanding via VLM,
    and indexing them in ChromaDB using a memory-optimized batch pipeline.
    """

    def __init__(self, config: Optional[RagConfig] = None):
        self.config = config or RagConfig()
        
        from src.rag.embedding_provider import SentenceTransformersEmbeddingProvider
        provider = SentenceTransformersEmbeddingProvider(
            model_name=self.config.embedding_model,
            device=self.config.embedding_device
        )
        self.embedder = Embedder(provider)
        self.vector_store = VectorStore(
            db_dir=self.config.chroma_db_dir,
            collection_prefix=self.config.collection_prefix
        )
        self.ollama_client = OllamaClient()

        # Debug & Analytics counters
        self.stats = {
            "total_objects": 0,
            "by_type": {},
            "embedding_count": 0,
            "skipped_images": 0,
            "vision_processed_images": 0,
            "ocr_count": 0,
            "table_count": 0,
            "total_embedding_time": 0.0,
            "total_vlm_time": 0.0
        }
        self.all_chunks = []

    def _parse_vlm_output(self, text: str) -> dict:
        """Parses VLM response sections using regex/line rules."""
        lines = text.split('\n')
        img_type = "Diagram"
        description = text
        objects = []
        entities = []
        keywords = []
        
        current_section = None
        desc_parts = []
        for line in lines:
            line_strip = line.strip()
            if not line_strip:
                continue
            
            if any(term in line_strip.lower() for term in ["image type", "type of image", "image_type"]):
                current_section = "type"
                parts = line_strip.split(":")
                if len(parts) > 1:
                    img_type = parts[1].strip().strip("*`\"'")
            elif any(term in line_strip.lower() for term in ["semantic description", "overall description", "meaning"]):
                current_section = "desc"
                parts = line_strip.split(":")
                if len(parts) > 1 and parts[1].strip():
                    desc_parts.append(parts[1].strip())
            elif any(term in line_strip.lower() for term in ["detected objects", "objects"]):
                current_section = "objects"
                parts = line_strip.split(":")
                if len(parts) > 1 and parts[1].strip():
                    objects.extend([o.strip().strip("-* ") for o in parts[1].split(",")])
            elif any(term in line_strip.lower() for term in ["entities", "detected entities", "people", "names"]):
                current_section = "entities"
                parts = line_strip.split(":")
                if len(parts) > 1 and parts[1].strip():
                    entities.extend([e.strip().strip("-* ") for e in parts[1].split(",")])
            elif "keywords" in line_strip.lower():
                current_section = "keywords"
                parts = line_strip.split(":")
                if len(parts) > 1 and parts[1].strip():
                    keywords.extend([k.strip().strip("-* ") for k in parts[1].split(",")])
            else:
                if current_section == "desc":
                    desc_parts.append(line_strip)
                elif current_section == "objects":
                    objects.append(line_strip.strip("-* "))
                elif current_section == "entities":
                    entities.append(line_strip.strip("-* "))
                elif current_section == "keywords":
                    keywords.extend([k.strip().strip("-* ") for k in line_strip.split(",")])
                    
        if desc_parts:
            description = "\n".join(desc_parts)
            
        objects = sorted(list(set([o for o in objects if len(o) > 1])))
        entities = sorted(list(set([e for e in entities if len(e) > 1])))
        keywords = sorted(list(set([k for k in keywords if len(k) > 1])))
        
        return {
            "image_type": img_type or "Diagram",
            "semantic_description": description.strip(),
            "objects": objects,
            "entities": entities,
            "keywords": keywords
        }

    def _generate_objects(
        self, 
        structured_doc: StructuredDocument, 
        doc_id: str, 
        output_dir: Optional[Path] = None
    ) -> Generator[KnowledgeObject, None, None]:
        """
        Generates independent typed Knowledge Objects from the structured document
        layout elements sequentially.
        """
        images_dir = output_dir / "05_images" if output_dir else None
        tables_dir = output_dir / "04_tables" if output_dir else None
        
        # Heading context stacks
        active_headings: Dict[int, str] = {}
        active_heading_ids: Dict[int, str] = {}
        
        # Link context tracking
        last_paragraph_id = None
        last_heading_id = None
        last_image_id = None
        last_table_id = None
        last_caption_id = None
        
        seq_num = 0
        created_time = datetime.utcnow().isoformat() + "Z"
        source_file = structured_doc.file_name + "." + structured_doc.file_type

        # Mapping helper to build section path
        def get_heading_contexts() -> Tuple[Optional[str], Optional[str], Optional[str]]:
            sorted_lvls = sorted(active_headings.keys())
            headings_list = [active_headings[k] for k in sorted_lvls]
            heading = headings_list[-1] if headings_list else None
            parent_heading = headings_list[-2] if len(headings_list) > 1 else None
            section = format_section_path(headings_list) if headings_list else "Root"
            return heading, parent_heading, section

        def make_metadata(txt: str, ref_id: str, element_bbox: Optional[dict], custom_meta: dict) -> dict:
            meta_dict = {
                "word_count": count_words(txt),
                "token_estimate": estimate_tokens(txt),
                "hierarchy_path": list(active_heading_ids.values()),
                "source_element_ids": [ref_id],
                "bounding_boxes": [element_bbox] if element_bbox else []
            }
            meta_dict.update(custom_meta)
            return meta_dict

        for element in structured_doc.elements:
            el_type = element.type
            self_ref = element.id
            text_content = element.text
            page = element.metadata.page_number
            bbox = element.metadata.bbox.model_dump() if hasattr(element.metadata.bbox, "model_dump") else (element.metadata.bbox.dict() if element.metadata.bbox else None)
            
            # --- Heading Context Tracking ---
            if el_type == "heading":
                lvl = element.metadata.level or 1
                levels_to_remove = [k for k in active_headings.keys() if k > lvl]
                for k in levels_to_remove:
                    active_headings.pop(k, None)
                    active_heading_ids.pop(k, None)
                active_headings[lvl] = element.text
                active_heading_ids[lvl] = self_ref
            
            heading, parent_heading, section_path = get_heading_contexts()

            # Map to Typed Knowledge Object
            typed_name = "Paragraph"
            if el_type == "heading":
                typed_name = "Heading"
            elif el_type == "list_item":
                # Bullet list check
                typed_name = "Bullet List" if "*" in text_content or "-" in text_content else "List"
            elif el_type == "code":
                typed_name = "Code Block"
            elif el_type == "footnote":
                typed_name = "Footnote"
            elif el_type == "formula":
                typed_name = "Formula"
            elif el_type == "caption":
                typed_name = "Caption"
            elif el_type == "table":
                typed_name = "Table"
            elif el_type == "image":
                typed_name = "Image"

            # 1. Processing Tables
            if el_type == "table" and tables_dir:
                self.stats["table_count"] += 1
                table_struct = structured_doc.tables.get(self_ref)
                if table_struct:
                    tbl_idx = self.stats["table_count"]
                    tbl_name = f"table_{tbl_idx:03d}"
                    
                    # Reconstruct grid
                    grid = [["" for _ in range(table_struct.cols_count)] for _ in range(table_struct.rows_count)]
                    for cell in table_struct.cells:
                        r, c = cell.row_index, cell.col_index
                        if r < len(grid) and c < len(grid[0]):
                            grid[r][c] = cell.text
                            
                    # Save formats (CSV, JSON, MD, HTML)
                    import csv
                    import io
                    csv_io = io.StringIO()
                    writer = csv.writer(csv_io)
                    writer.writerows(grid)
                    (tables_dir / f"{tbl_name}.csv").write_text(csv_io.getvalue(), encoding="utf-8")
                    
                    tbl_json = {
                        "table_id": table_struct.table_id,
                        "rows_count": table_struct.rows_count,
                        "cols_count": table_struct.cols_count,
                        "caption": table_struct.caption,
                        "markdown": table_struct.markdown,
                        "html": table_struct.html,
                        "grid": grid
                    }
                    with open(tables_dir / f"{tbl_name}.json", "w", encoding="utf-8") as f:
                        json.dump(tbl_json, f, indent=2, ensure_ascii=False)
                        
                    md_str = table_struct.markdown or ""
                    (tables_dir / f"{tbl_name}.md").write_text(md_str, encoding="utf-8")
                    
                    html_str = table_struct.html or ""
                    html_content = (
                        f"<html><head><style>body{{font-family:sans-serif;padding:20px;}} table{{border-collapse:collapse;width:100%;}} th,td{{border:1px solid #ccc;padding:8px;text-align:left;}} th{{background:#eee;}}</style></head><body>"
                        f"<h2>Table: {tbl_name}</h2>"
                        f"<p><strong>Caption</strong>: {table_struct.caption or 'None'}</p>"
                        f"{html_str}"
                        f"</body></html>"
                    )
                    (tables_dir / f"{tbl_name}.html").write_text(html_content, encoding="utf-8")

                    # Yield main table object
                    t_relationships = {
                        "belongs_to": last_heading_id,
                        "related_text": last_paragraph_id
                    }
                    if last_caption_id:
                        t_relationships["has_caption"] = last_caption_id

                    t_meta = make_metadata(
                        txt=md_str or text_content,
                        ref_id=self_ref,
                        element_bbox=bbox,
                        custom_meta={
                            "rows_count": table_struct.rows_count,
                            "cols_count": table_struct.cols_count,
                            "caption": table_struct.caption,
                            "table_id": self_ref,
                            "keywords": ["table", tbl_name]
                        }
                    )
                    
                    t_obj_id = f"{doc_id}_chunk_{seq_num:04d}"
                    last_table_id = t_obj_id
                    seq_num += 1

                    if tables_dir:
                        tables_dir.mkdir(parents=True, exist_ok=True)
                        t_count = len(list(tables_dir.glob("table_*.json"))) + 1
                        t_json_path = tables_dir / f"table_{t_count:03d}.json"
                        t_md_path = tables_dir / f"table_{t_count:03d}.md"
                        try:
                            with open(t_json_path, "w", encoding="utf-8") as tf:
                                json.dump({
                                    "table_id": self_ref,
                                    "page_number": page,
                                    "rows_count": table_struct.rows_count,
                                    "cols_count": table_struct.cols_count,
                                    "caption": table_struct.caption,
                                    "markdown": md_str or text_content
                                }, tf, indent=2, ensure_ascii=False)
                            if md_str:
                                with open(t_md_path, "w", encoding="utf-8") as mf:
                                    mf.write(md_str)
                        except Exception as t_err:
                            logger.error(f"Failed to write table output file: {t_err}")
                    
                    yield KnowledgeObject(
                        knowledge_id=t_obj_id,
                        document_id=doc_id,
                        page_number=page,
                        chunk_type="Table",
                        heading=heading,
                        parent_heading=parent_heading,
                        section_path=section_path,
                        sequence_number=seq_num - 1,
                        text=md_str or text_content,
                        metadata=t_meta,
                        relationships=t_relationships,
                        source_file=source_file,
                        bounding_box=bbox,
                        created_time=created_time
                    )
                    
                    # Yield Table Cells
                    for c_idx, cell in enumerate(table_struct.cells):
                        cell_obj_id = f"{doc_id}_chunk_{seq_num:04d}"
                        seq_num += 1
                        cell_bbox = cell.bbox.dict() if cell.bbox else None
                        
                        cell_text = f"Table Cell [{cell.row_index},{cell.col_index}]: {cell.text}"
                        cell_meta = make_metadata(
                            txt=cell_text,
                            ref_id=f"{self_ref}_cell_{c_idx}",
                            element_bbox=cell_bbox,
                            custom_meta={
                                "table_id": t_obj_id,
                                "row": cell.row_index,
                                "col": cell.col_index,
                                "row_span": cell.row_span,
                                "col_span": cell.col_span
                            }
                        )
                        
                        yield KnowledgeObject(
                            knowledge_id=cell_obj_id,
                            document_id=doc_id,
                            page_number=page,
                            chunk_type="Table Cell",
                            heading=heading,
                            parent_heading=parent_heading,
                            section_path=section_path,
                            sequence_number=seq_num - 1,
                            text=cell_text,
                            metadata=cell_meta,
                            relationships={"belongs_to": t_obj_id},
                            source_file=source_file,
                            bounding_box=cell_bbox,
                            created_time=created_time
                        )
                    continue

            # 2. Processing Images
            elif el_type == "image" and images_dir:
                img_meta = structured_doc.images.get(self_ref)
                if img_meta:
                    img_idx = len(structured_doc.images)  # estimate index
                    # Check if actual png crop was moved
                    orig_path = Path(img_meta.image_path) if img_meta.image_path else None
                    seq_name = f"image_{idx_img(img_id=self_ref, images_dict=structured_doc.images):03d}"
                    new_png_path = images_dir / f"{seq_name}.png"
                    
                    if orig_path and orig_path.exists():
                        try:
                            shutil.move(str(orig_path), str(new_png_path))
                            img_meta.image_path = str(new_png_path)
                        except Exception as move_err:
                            logger.error(f"Failed to move image crop: {move_err}")
                            
                    # Smart filtering: skip VLM for decorative, small icons, logos, or minor graphics
                    is_decorative = False
                    if new_png_path.exists():
                        try:
                            file_size_kb = new_png_path.stat().st_size / 1024.0
                            with Image.open(new_png_path) as pil_img:
                                w, h = pil_img.size
                                if w < 120 or h < 120 or (w * h) < 15000 or file_size_kb < 8.0:
                                    is_decorative = True
                        except Exception:
                            pass
                            
                    caption = img_meta.caption or ""
                    ocr_text = img_meta.ocr_text or ""
                    
                    vlm_description = ""
                    image_type = "Diagram"
                    detected_objects = []
                    keywords = []
                    detected_entities = []
                    
                    if is_decorative:
                        self.stats["skipped_images"] += 1
                        image_type = "Decorative"
                        vlm_description = "Decorative icon, logo, or separator skipped by smart VLM filter."
                        keywords = ["decorative"]
                    else:
                        # Call VLM
                        if new_png_path.exists():
                            try:
                                vlm_start = time.time()
                                with open(new_png_path, "rb") as image_file:
                                    img_b64 = base64.b64encode(image_file.read()).decode("utf-8")
                                
                                prompt = (
                                    f"Describe this image extracted from a document.\n"
                                    f"Caption associated with it: {caption}\n"
                                    f"OCR text: {ocr_text}\n"
                                    "Please provide a structured response in natural language describing:\n"
                                    "1. Image Type (e.g. Graph, Chart, Map, Photo, Diagram, Flowchart, Logo, Screenshot)\n"
                                    "2. Semantic Description (a detailed explanation of the overall meaning)\n"
                                    "3. Detected Objects (list of main objects/elements)\n"
                                    "4. Detected Entities (people, names, or organizations if any)\n"
                                    "5. Keywords (a list of comma-separated keywords)\n"
                                    "\nAnswer clearly and directly."
                                )
                                from src.model_router import MODEL_ROUTER
                                vlm_model = os.environ.get("MODEL_VISION_ANALYSIS", MODEL_ROUTER.get_model("vision_analysis"))
                                vlm_text = self.ollama_client.generate_vision(
                                    model=vlm_model,
                                    prompt=prompt,
                                    image_bytes_b64=img_b64
                                )
                                parsed = self._parse_vlm_output(vlm_text)
                                image_type = parsed["image_type"]
                                vlm_description = parsed["semantic_description"]
                                detected_objects = parsed["objects"]
                                detected_entities = parsed["entities"]
                                keywords = parsed["keywords"]
                                
                                self.stats["vision_processed_images"] += 1
                                self.stats["total_vlm_time"] += (time.time() - vlm_start)
                            except Exception as vlm_err:
                                logger.warning(f"VLM analysis failed for {seq_name}: {vlm_err}")
                                vlm_description = "Image description generation failed."
                        else:
                            vlm_description = "Image crop not found on disk."

                    # Save formats (JSON, MD, HTML)
                    img_json_data = {
                        "image_id": self_ref,
                        "page": page,
                        "caption": caption,
                        "ocr_text": ocr_text,
                        "bounding_box": bbox,
                        "image_path": f"05_images/{seq_name}.png",
                        "image_type": image_type,
                        "objects": detected_objects,
                        "keywords": keywords,
                        "semantic_description": vlm_description,
                        "detected_entities": detected_entities,
                        "confidence": 1.0,
                        "future_vlm_metadata_placeholder": {}
                    }
                    with open(images_dir / f"{seq_name}.json", "w", encoding="utf-8") as f:
                        json.dump(img_json_data, f, indent=2, ensure_ascii=False)
                        
                    md_content = (
                        f"# Image {seq_name} (Page {page})\n\n"
                        f"**Type**: {image_type}\n"
                        f"**Caption**: {caption or 'None'}\n"
                        f"**OCR Text**: {ocr_text or 'None'}\n\n"
                        f"## Semantic Description\n{vlm_description}\n\n"
                        f"## Detected Objects\n" + "\n".join(f"- {obj}" for obj in detected_objects) + "\n\n"
                        f"## Keywords\n" + ", ".join(keywords)
                    )
                    (images_dir / f"{seq_name}.md").write_text(md_content, encoding="utf-8")
                    
                    html_content = (
                        f"<html><head><style>body{{font-family:sans-serif;padding:20px;background:#f8fafc;}} .container{{max-width:700px;margin:0 auto;background:#fff;padding:20px;border-radius:8px;border:1px solid #ddd;}} img{{max-width:100%;border:1px solid #eee;margin-bottom:15px;}}</style></head><body>"
                        f"<div class='container'>"
                        f"<h2>Image Reference: {seq_name}</h2>"
                        f"<img src='./{seq_name}.png'/>"
                        f"<p><strong>Page</strong>: {page}</p>"
                        f"<p><strong>Type</strong>: {image_type}</p>"
                        f"<p><strong>Caption</strong>: {caption or 'None'}</p>"
                        f"<h3>Semantic Description</h3><p>{vlm_description}</p>"
                        f"<h3>Objects</h3><ul>" + "".join(f"<li>{obj}</li>" for obj in detected_objects) + "</ul>"
                        f"<h3>Keywords</h3><p>{', '.join(keywords)}</p>"
                        f"</div></body></html>"
                    )
                    (images_dir / f"{seq_name}.html").write_text(html_content, encoding="utf-8")

                    # Yield main Image object
                    img_relationships = {
                        "belongs_to": last_heading_id,
                        "related_text": last_paragraph_id
                    }
                    if last_caption_id:
                        img_relationships["has_caption"] = last_caption_id

                    img_meta_dict = make_metadata(
                        txt=caption or f"Image Element {seq_name}",
                        ref_id=self_ref,
                        element_bbox=bbox,
                        custom_meta={
                            "image_id": self_ref,
                            "caption": caption,
                            "ocr_text": ocr_text,
                            "image_type": image_type,
                            "objects": detected_objects,
                            "keywords": keywords,
                            "entities": detected_entities
                        }
                    )
                    
                    img_obj_id = f"{doc_id}_chunk_{seq_num:04d}"
                    last_image_id = img_obj_id
                    seq_num += 1
                    
                    yield KnowledgeObject(
                        knowledge_id=img_obj_id,
                        document_id=doc_id,
                        page_number=page,
                        chunk_type="Image",
                        heading=heading,
                        parent_heading=parent_heading,
                        section_path=section_path,
                        sequence_number=seq_num - 1,
                        text=caption or f"Image Element {seq_name}",
                        metadata=img_meta_dict,
                        relationships=img_relationships,
                        source_file=source_file,
                        bounding_box=bbox,
                        created_time=created_time
                    )
                    
                    # Yield Image Description (VLM) object
                    if vlm_description:
                        desc_obj_id = f"{doc_id}_chunk_{seq_num:04d}"
                        seq_num += 1
                        
                        vlm_text_content = f"Image Description: {vlm_description}"
                        desc_meta = make_metadata(
                            txt=vlm_text_content,
                            ref_id=f"{self_ref}_vlm",
                            element_bbox=bbox,
                            custom_meta={
                                "image_id": img_obj_id,
                                "image_type": image_type,
                                "keywords": keywords
                            }
                        )
                        
                        yield KnowledgeObject(
                            knowledge_id=desc_obj_id,
                            document_id=doc_id,
                            page_number=page,
                            chunk_type="Image Description (VLM)",
                            heading=heading,
                            parent_heading=parent_heading,
                            section_path=section_path,
                            sequence_number=seq_num - 1,
                            text=vlm_text_content,
                            metadata=desc_meta,
                            relationships={"belongs_to": img_obj_id},
                            source_file=source_file,
                            bounding_box=bbox,
                            created_time=created_time
                        )
                        
                    # Yield OCR Block object
                    if ocr_text:
                        ocr_obj_id = f"{doc_id}_chunk_{seq_num:04d}"
                        seq_num += 1
                        self.stats["ocr_count"] += 1
                        
                        ocr_block_text = f"Image OCR Text: {ocr_text}"
                        ocr_meta = make_metadata(
                            txt=ocr_block_text,
                            ref_id=f"{self_ref}_ocr",
                            element_bbox=bbox,
                            custom_meta={
                                "image_id": img_obj_id
                            }
                        )
                        
                        yield KnowledgeObject(
                            knowledge_id=ocr_obj_id,
                            document_id=doc_id,
                            page_number=page,
                            chunk_type="OCR Block",
                            heading=heading,
                            parent_heading=parent_heading,
                            section_path=section_path,
                            sequence_number=seq_num - 1,
                            text=ocr_block_text,
                            metadata=ocr_meta,
                            relationships={"belongs_to": img_obj_id},
                            source_file=source_file,
                            bounding_box=bbox,
                            created_time=created_time
                        )
                    continue

            # 3. Processing other element types
            relationships = {
                "belongs_to": last_heading_id
            }
            if typed_name == "Paragraph":
                relationships["previous"] = last_paragraph_id
            elif typed_name == "Heading":
                relationships["parent"] = last_heading_id
            elif typed_name == "Caption":
                relationships["related_to"] = last_table_id or last_image_id
                
            k_obj_id = f"{doc_id}_chunk_{seq_num:04d}"
            
            # Update IDs
            if typed_name == "Paragraph":
                last_paragraph_id = k_obj_id
            elif typed_name == "Heading":
                last_heading_id = k_obj_id
            elif typed_name == "Caption":
                last_caption_id = k_obj_id
                
            seq_num += 1
            
            obj_meta = make_metadata(
                txt=text_content,
                ref_id=self_ref,
                element_bbox=bbox,
                custom_meta={}
            )
            
            yield KnowledgeObject(
                knowledge_id=k_obj_id,
                document_id=doc_id,
                page_number=page,
                chunk_type=typed_name,
                heading=heading,
                parent_heading=parent_heading,
                section_path=section_path,
                sequence_number=seq_num - 1,
                text=text_content,
                metadata=obj_meta,
                relationships=relationships,
                source_file=source_file,
                bounding_box=bbox,
                created_time=created_time
            )

    def _process_chunks_batch(
        self, 
        chunks: List[DocumentChunk], 
        doc_id: str, 
        output_dir: Optional[Path] = None
    ) -> None:
        """
        Processes a batch of semantic chunks: estimates embeddings, indexes in ChromaDB,
        and saves them.
        """
        if not chunks:
            return
            
        logger.info(f"Processing batch of {len(chunks)} semantic chunk(s)...")
        
        # Accumulate in memory for serialization at finalization stage
        self.all_chunks.extend(chunks)
        
        existing_ids = getattr(self, "existing_ids", None)
        if existing_ids is None:
            existing_ids = self.vector_store.get_existing_chunk_ids(doc_id)
            self.existing_ids = existing_ids
            
        chunks_to_index = [c for c in chunks if c.metadata.chunk_id not in existing_ids]
        
        if not chunks_to_index:
            logger.info("All chunks in this batch are already indexed. Skipping embedding and vector DB updates.")
            # Still update stats
            for chunk in chunks:
                t = chunk.metadata.chunk_type
                self.stats["by_type"][t] = self.stats["by_type"].get(t, 0) + 1
            # Update backend status if running in services
            try:
                from backend.services import JOBS, save_job_metadata
                if doc_id in JOBS:
                    job = JOBS[doc_id]
                    job["knowledge_objects_generated"] = len(self.all_chunks)
                    job["embeddings_completed"] = self.stats["embedding_count"]
                    job["index_progress"] = int((self.stats["embedding_count"] / max(1, len(self.all_chunks))) * 100)
                    save_job_metadata(doc_id)
            except Exception:
                pass
            return

        # Generate Embeddings
        emb_start = time.time()
        embeddings = self.embedder.generate_embeddings(
            chunks_to_index,
            batch_size=len(chunks_to_index)
        )
        self.stats["total_embedding_time"] += (time.time() - emb_start)
        self.stats["embedding_count"] += len(chunks_to_index)

        # Index in ChromaDB
        self.vector_store.index_chunks(doc_id, chunks_to_index, embeddings)
        
        # Update metrics
        for chunk in chunks:
            t = chunk.metadata.chunk_type
            self.stats["by_type"][t] = self.stats["by_type"].get(t, 0) + 1

        # Update backend status if running in services
        try:
            from backend.services import JOBS, save_job_metadata
            if doc_id in JOBS:
                job = JOBS[doc_id]
                job["knowledge_objects_generated"] = len(self.all_chunks)
                job["embeddings_completed"] = self.stats["embedding_count"]
                job["index_progress"] = int((self.stats["embedding_count"] / max(1, len(self.all_chunks))) * 100)
                save_job_metadata(doc_id)
        except Exception:
            pass

    def _process_batch(
        self, 
        batch: List[KnowledgeObject], 
        doc_id: str, 
        output_dir: Optional[Path] = None
    ) -> None:
        """
        Deprecated. Converting KnowledgeObjects to DocumentChunks directly is bypassed.
        """
        logger.warning("_process_batch called with raw KnowledgeObjects. Use _process_chunks_batch instead.")

    def extract_and_index(
        self, 
        structured_doc: StructuredDocument, 
        doc_id: str, 
        file_path: Optional[Path] = None,
        output_dir: Optional[Path] = None
    ) -> None:
        """
        Orchestrates Knowledge Object extraction, VLM image vision parsing,
        semantic chunking, and batch vector indexing.
        """
        # Ensure directories exist
        if output_dir:
            for folder in ["01_document", "02_docling", "03_knowledge_objects", "04_tables", "05_images", "06_embeddings", "07_vectordb", "08_retrieval", "09_reports"]:
                (output_dir / folder).mkdir(parents=True, exist_ok=True)
                
            # Copy raw document (01_document/uploaded.pdf)
            if file_path:
                suffix = file_path.suffix.lower()
                try:
                    shutil.copy2(file_path, output_dir / "01_document" / f"uploaded{suffix}")
                    logger.info(f"Saved raw document copy inside 01_document")
                except Exception as e:
                    logger.error(f"Failed to save raw copy: {e}")
            # Clean old jsonl if exists
            jsonl_path = output_dir / "03_knowledge_objects" / "knowledge_objects.jsonl"
            if jsonl_path.exists():
                jsonl_path.unlink()

        # 1. Generate and save raw KnowledgeObjects for structural tracking
        batch_objects = []
        for obj in self._generate_objects(structured_doc, doc_id, output_dir):
            batch_objects.append(obj)
            t = obj.chunk_type
            self.stats["by_type"][t] = self.stats["by_type"].get(t, 0) + 1
            self.stats["total_objects"] += 1
            
        if batch_objects and output_dir:
            jsonl_path = output_dir / "03_knowledge_objects" / "knowledge_objects.jsonl"
            with open(jsonl_path, "a", encoding="utf-8") as f:
                for obj in batch_objects:
                    obj.embedding_status = "Pending"
                    obj_dict = obj.dict() if hasattr(obj, "dict") else obj.model_dump()
                    f.write(json.dumps(obj_dict, ensure_ascii=False) + "\n")

        # 2. Build semantic and context-aware chunks using ChunkBuilder (Task 1)
        from src.rag.chunk_builder import ChunkBuilder
        overlap_size = getattr(self.config, "chunk_overlap_tokens", 50)
        chunk_builder = ChunkBuilder(
            target_tokens_min=250, 
            target_tokens_max=500, 
            overlap_tokens=overlap_size
        )
        
        chunks = chunk_builder.build_chunks(structured_doc, doc_id)
        
        # 3. Index these semantic chunks (Task 1)
        if chunks:
            self._process_chunks_batch(chunks, doc_id, output_dir)

        # Post-processing: Convert JSONL to final JSON list, HTML and Markdown
        if output_dir:
            self._finalize_outputs(doc_id, output_dir, structured_doc)

    def _finalize_outputs(self, doc_id: str, output_dir: Path, structured_doc: StructuredDocument) -> None:
        jsonl_path = output_dir / "03_knowledge_objects" / "knowledge_objects.jsonl"
        json_path = output_dir / "03_knowledge_objects" / "knowledge_objects.json"
        compat_chunks_path = output_dir / "document_chunks.json"
        
        objects_list = []
        if jsonl_path.exists():
            with open(jsonl_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        objects_list.append(json.loads(line))
            # Delete temp jsonl
            try:
                jsonl_path.unlink()
            except Exception:
                pass

        # Write final JSON list
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(objects_list, f, indent=2, ensure_ascii=False)
            
        # Recreate compat document_chunks.json from self.all_chunks (Task 1)
        compat_chunks = []
        for chunk in self.all_chunks:
            meta = chunk.metadata
            bboxes = []
            for b in meta.bounding_boxes:
                # BoundingBox can be Pydantic BaseModel or dict
                if hasattr(b, "l"):
                    bboxes.append({
                        "l": b.l,
                        "t": b.t,
                        "r": b.r,
                        "b": b.b,
                        "coord_origin": getattr(b, "coord_origin", "BOTTOMLEFT")
                    })
                elif isinstance(b, dict):
                    bboxes.append(b)
            
            meta_dict = {
                "chunk_id": meta.chunk_id,
                "document_id": meta.document_id,
                "page_number": meta.page_number,
                "chunk_type": meta.chunk_type,
                "heading": meta.heading,
                "section": meta.section,
                "hierarchy_path": meta.hierarchy_path,
                "source_element_ids": meta.source_element_ids,
                "word_count": meta.word_count,
                "token_estimate": meta.token_estimate,
                "bounding_boxes": bboxes,
                "element_types": getattr(meta, "element_types", []),
                "relationships": getattr(meta, "relationships", {})
            }
            if meta.image_id:
                meta_dict["image_id"] = meta.image_id
            if meta.table_id:
                meta_dict["table_id"] = meta.table_id
                
            # Enriched metadata (NER etc.) (Task 8)
            for extra in ["report_number", "state", "region", "district", "people", "organizations", "groups", "dates", "weapons", "locations", "keywords"]:
                val = getattr(meta, extra, None)
                if val is not None:
                    meta_dict[extra] = val
                    
            compat_chunks.append({
                "content": chunk.content,
                "metadata": meta_dict
            })
            
        with open(compat_chunks_path, "w", encoding="utf-8") as f:
            json.dump({
                "document_id": doc_id, 
                "file_name": f"{structured_doc.file_name}.{structured_doc.file_type}",
                "chunks": compat_chunks
            }, f, indent=2, ensure_ascii=False)
            
        # Save document_chunks.json in compat folder if needed (06_chunks/)
        (output_dir / "06_chunks").mkdir(parents=True, exist_ok=True)
        with open(output_dir / "06_chunks" / "document_chunks.json", "w", encoding="utf-8") as f:
            json.dump({
                "document_id": doc_id, 
                "file_name": f"{structured_doc.file_name}.{structured_doc.file_type}",
                "chunks": compat_chunks
            }, f, indent=2, ensure_ascii=False)

        # Write Markdown representation
        md_path = output_dir / "03_knowledge_objects" / "knowledge_objects.md"
        md_parts = [f"# Knowledge Objects for Document {doc_id}\n\n"]
        for obj in objects_list:
            md_parts.append(
                f"## Object {obj.get('knowledge_id')} ({obj.get('chunk_type')})\n"
                f"- **Page**: {obj.get('page_number')}\n"
                f"- **Section Path**: {obj.get('section_path') or 'Root'}\n"
                f"- **Relationships**: {json.dumps(obj.get('relationships'))}\n\n"
                f"### Content\n```\n{obj.get('text')}\n```\n"
                f"-----------------------------------------\n\n"
            )
        md_path.write_text("".join(md_parts), encoding="utf-8")

        # Generate Embedding summary (06_embeddings/)
        emb_summary = {
            "collection_name": self.vector_store._get_collection_name(doc_id),
            "embedding_model": self.config.embedding_model,
            "total_embeddings": self.stats["embedding_count"],
            "embedding_count_by_type": self.stats["by_type"],
            "average_embedding_time_seconds": self.stats["total_embedding_time"] / max(1, self.stats["embedding_count"]),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        }
        with open(output_dir / "06_embeddings" / "embedding_summary.json", "w", encoding="utf-8") as f:
            json.dump(emb_summary, f, indent=2)
        (output_dir / "07_embeddings").mkdir(parents=True, exist_ok=True)
        with open(output_dir / "07_embeddings" / "embedding_summary.json", "w", encoding="utf-8") as f:
            json.dump(emb_summary, f, indent=2)

        # Generate Vector DB metadata (07_vectordb/)
        vdb_meta = {
            "collection_name": self.vector_store._get_collection_name(doc_id),
            "total_objects": self.stats["total_objects"],
            "objects_by_type": self.stats["by_type"],
            "vision_processed_images": self.stats["vision_processed_images"],
            "skipped_images": self.stats["skipped_images"],
            "ocr_count": self.stats["ocr_count"],
            "table_count": self.stats["table_count"],
            "average_vlm_time_seconds": self.stats["total_vlm_time"] / max(1, self.stats["vision_processed_images"]),
            "average_embedding_time_seconds": self.stats["total_embedding_time"] / max(1, self.stats["embedding_count"])
        }
        with open(output_dir / "07_vectordb" / "vectordb_metadata.json", "w", encoding="utf-8") as f:
            json.dump(vdb_meta, f, indent=2)

        # Generate HTML inspect report (inspection_report.html)
        self._generate_html_inspector(output_dir, doc_id, objects_list, structured_doc, self.all_chunks)

    def _generate_html_inspector(self, output_dir: Path, doc_id: str, objects_list: List[dict], structured_doc: StructuredDocument, chunks_list: List[DocumentChunk]) -> None:
        """Upgraded inspect report supporting filtering by type, displaying metadata, VLM details, and relationships."""
        cards_html = []
        for obj in objects_list:
            c_id = obj.get("knowledge_id")
            c_type = obj.get("chunk_type")
            page = obj.get("page_number")
            section = obj.get("section_path") or "Root"
            text = obj.get("text")
            status = obj.get("embedding_status")
            rels = obj.get("relationships", {})
            meta = obj.get("metadata", {})
            
            # Safe class mapping for CSS filter
            filter_cls = "text"
            if c_type in ("Heading", "Paragraph", "Formula", "Reference", "Quote", "Section Summary"):
                filter_cls = "text"
            elif c_type == "Table":
                filter_cls = "table"
            elif c_type == "Table Cell":
                filter_cls = "table"
            elif c_type == "Image":
                filter_cls = "image"
            elif c_type == "Image Description (VLM)":
                filter_cls = "image"
            elif c_type == "OCR Block":
                filter_cls = "ocr"
            elif c_type == "Caption":
                filter_cls = "caption"
            elif c_type in ("List", "Bullet List"):
                filter_cls = "list"
            elif c_type == "Code Block":
                filter_cls = "list"
            elif c_type == "Footnote":
                filter_cls = "list"
                
            badge_cls = f"badge-{filter_cls}"
            
            # Format relationships string
            rels_str = ", ".join(f"<strong>{k}</strong>: {v}" for k, v in rels.items()) if rels else "None"
            meta_str = ", ".join(f"{k}: {v}" for k, v in meta.items() if k not in ("table_id", "image_id")) if meta else "None"
            
            # Image visual injection
            extra_content = ""
            if c_type == "Image":
                # Find corresponding crop file
                img_idx = idx_img_id(c_id, objects_list)
                seq_name = f"image_{img_idx:03d}"
                extra_content = f"<br/><img src='./05_images/{seq_name}.png' style='max-width:280px; border:1px solid #ddd; border-radius:6px; background:#fff; display:block; margin:8px 0;' onerror='this.style.display=\"none\"'/>"

            cards_html.append(
                f"<div class='card raw-item filter-{filter_cls}' style='margin-bottom:12px; padding:15px; border:1px solid #e2e8f0; text-align:left; background:#fff;'>"
                f"  <div style='display:flex; justify-content:space-between; font-size:11.5px; color:#64748b; margin-bottom:8px;'>"
                f"    <span><strong>Knowledge ID</strong>: {c_id} | <span class='badge {badge_cls}'>{c_type}</span></span>"
                f"    <span>Page {page} | {section}</span>"
                f"  </div>"
                f"  <pre style='background:#f1f5f9; padding:10px; border-radius:6px; font-size:12.5px; overflow-x:auto; white-space:pre-wrap; font-family:monospace; margin:0;'>{text}</pre>"
                f"  {extra_content}"
                f"  <div style='font-size:11px; color:#64748b; margin-top:8px; border-top:1px dotted #e2e8f0; padding-top:6px;'>"
                f"    <strong>Relationships</strong>: {rels_str} <br/>"
                f"    <strong>Metadata</strong>: {meta_str} | <strong>Status</strong>: {status}"
                f"  </div>"
                f"</div>"
            )

        chunks_html = []
        for chunk in chunks_list:
            meta = chunk.metadata
            c_id = meta.chunk_id
            c_type = meta.chunk_type
            page = meta.page_number
            section = meta.section or "Root"
            text = chunk.content
            tokens = meta.token_estimate
            source_ids = meta.source_element_ids or []
            
            # Extract metadata dict safely
            meta_dict = meta.model_dump() if hasattr(meta, "model_dump") else meta.dict()
            
            flat_meta = {
                k: v for k, v in meta_dict.items() 
                if k not in (
                    "chunk_id", "document_id", "page_number", "chunk_type", "heading", "section", 
                    "hierarchy_path", "source_element_ids", "word_count", "token_estimate", 
                    "bounding_boxes", "element_types", "relationships", "image_id", "table_id"
                ) and v
            }
            meta_str = ", ".join(f"<strong>{k}</strong>: {v}" for k, v in flat_meta.items()) if flat_meta else "None"
            
            hierarchy_str = " -> ".join(meta.hierarchy_path) if meta.hierarchy_path else "None"
            source_ids_str = ", ".join(source_ids)
            
            # Image visual injection
            extra_content = ""
            if c_type == "image" and meta.image_id:
                img_idx = idx_img(meta.image_id, structured_doc.images)
                seq_name = f"image_{img_idx:03d}"
                extra_content = f"<br/><img src='./05_images/{seq_name}.png' style='max-width:280px; border:1px solid #ddd; border-radius:6px; background:#fff; display:block; margin:8px 0;' onerror='this.style.display=\"none\"'/>"

            sem_filter_cls = "text"
            if c_type in ("text", "heading", "table", "image", "list", "code", "footnote"):
                sem_filter_cls = c_type
                
            chunks_html.append(
                f"<div class='card semantic-item filter-{sem_filter_cls}' style='margin-bottom:12px; padding:15px; border:1px solid #c7d2fe; border-left: 5px solid #4f46e5; text-align:left; background:#fff;'>"
                f"  <div style='display:flex; justify-content:space-between; font-size:11.5px; color:#64748b; margin-bottom:8px;'>"
                f"    <span><strong>Chunk ID</strong>: {c_id} | <span class='badge' style='background:#4f46e5;'>{c_type.upper()}</span></span>"
                f"    <span>Page {page} | {section}</span>"
                f"  </div>"
                f"  <pre style='background:#f8fafc; padding:10px; border-radius:6px; font-size:12.5px; overflow-x:auto; white-space:pre-wrap; font-family:monospace; margin:0; border: 1px solid #e2e8f0;'>{text}</pre>"
                f"  {extra_content}"
                f"  <div style='font-size:11px; color:#475569; margin-top:8px; border-top:1px dotted #cbd5e1; padding-top:6px; line-height: 1.5;'>"
                f"    <strong>Heading Path</strong>: {hierarchy_str} <br/>"
                f"    <strong>Source Element IDs</strong>: {source_ids_str} | <strong>Tokens</strong>: {tokens} <br/>"
                f"    <strong>Enriched Metadata</strong>: {meta_str}"
                f"  </div>"
                f"</div>"
            )

        html_template = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Knowledge Objects Inspection Report - {doc_id}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif; background: #f8fafc; margin: 0; padding: 25px; color: #1e293b; }}
    .container {{ max-width: 1100px; margin: 0 auto; background: #fff; border-radius: 12px; border: 1px solid #e2e8f0; padding: 30px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); }}
    h1 {{ margin-top: 0; font-size: 24px; color: #0f172a; border-bottom: 1px solid #e2e8f0; padding-bottom: 10px; }}
    .tabs {{ display: flex; gap: 8px; border-bottom: 2px solid #e2e8f0; margin-bottom: 20px; }}
    .tab-btn {{ padding: 10px 18px; border: none; background: transparent; font-size: 14px; font-weight: 600; cursor: pointer; color: #64748b; border-bottom: 2px solid transparent; transition: all 0.2s; }}
    .tab-btn.active {{ color: #4f46e5; border-bottom: 2px solid #4f46e5; }}
    .tab-content {{ display: none; }}
    .tab-content.active {{ display: block; }}
    .card {{ background: #fff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin-bottom: 15px; box-shadow: 0 1px 2px rgba(0,0,0,0.02); }}
    .badge {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 700; color: #fff; text-transform: uppercase; }}
    .badge-text {{ background: #10b981; }}
    .badge-table {{ background: #06b6d4; }}
    .badge-image {{ background: #8b5cf6; }}
    .badge-list {{ background: #fd7e14; }}
    .badge-ocr {{ background: #ef4444; }}
    .badge-caption {{ background: #f59e0b; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 13px; }}
    th, td {{ border: 1px solid #cbd5e1; padding: 8px 12px; text-align: left; }}
    th {{ background: #f1f5f9; font-weight: 600; }}
    .stat-row {{ display: flex; gap: 15px; margin-bottom: 20px; }}
    .stat-card {{ flex: 1; background: #f1f5f9; padding: 12px; border-radius: 8px; text-align: center; }}
    .stat-num {{ font-size: 18px; font-weight: 700; color: #4f46e5; }}
    .stat-lbl {{ font-size: 11px; color: #64748b; text-transform: uppercase; margin-top: 4px; }}
    .search-box {{ width: 100%; padding: 11px 16px; border: 1px solid #cbd5e1; border-radius: 8px; margin-bottom: 15px; font-size: 14px; outline: none; box-sizing: border-box; }}
    .filters-bar {{ display: flex; gap: 10px; margin-bottom: 15px; flex-wrap: wrap; }}
    .filter-btn {{ padding: 6px 12px; border: 1px solid #cbd5e1; border-radius: 6px; background: #fff; font-size: 12.5px; cursor: pointer; color: #334155; }}
    .filter-btn.active {{ background: #4f46e5; color: #fff; border-color: #4f46e5; }}
  </style>
  <script>
    function openTab(evt, tabName) {{
      var i, tabcontent, tablinks;
      tabcontent = document.getElementsByClassName("tab-content");
      for (i = 0; i < tabcontent.length; i++) {{
        tabcontent[i].style.display = "none";
      }}
      tablinks = document.getElementsByClassName("tab-btn");
      for (i = 0; i < tablinks.length; i++) {{
        tablinks[i].className = tablinks[i].className.replace(" active", "");
      }}
      document.getElementById(tabName).style.display = "block";
      evt.currentTarget.className += " active";
    }}
    
    var currentRawFilter = "all";
    function filterTypeRaw(type) {{
      currentRawFilter = type;
      var buttons = document.getElementsByClassName("filter-raw-btn");
      for (var i=0; i < buttons.length; i++) {{
        buttons[i].classList.remove("active");
      }}
      document.getElementById("btn-raw-" + type).classList.add("active");
      runFilterRaw();
    }}
    
    function runFilterRaw() {{
      var items = document.getElementsByClassName("raw-item");
      var searchVal = document.getElementById("search-raw").value.toLowerCase();
      for (var i=0; i < items.length; i++) {{
        var matchesSearch = items[i].innerText.toLowerCase().indexOf(searchVal) > -1;
        var matchesType = currentRawFilter === "all" || items[i].classList.contains("filter-" + currentRawFilter);
        if (matchesSearch && matchesType) {{
          items[i].style.display = "block";
        }} else {{
          items[i].style.display = "none";
        }}
      }}
    }}
    
    var currentSemanticFilter = "all";
    function filterTypeSemantic(type) {{
      currentSemanticFilter = type;
      var buttons = document.getElementsByClassName("filter-semantic-btn");
      for (var i=0; i < buttons.length; i++) {{
        buttons[i].classList.remove("active");
      }}
      document.getElementById("btn-sem-" + type).classList.add("active");
      runFilterSemantic();
    }}
    
    function runFilterSemantic() {{
      var items = document.getElementsByClassName("semantic-item");
      var searchVal = document.getElementById("search-semantic").value.toLowerCase();
      for (var i=0; i < items.length; i++) {{
        var matchesSearch = items[i].innerText.toLowerCase().indexOf(searchVal) > -1;
        var matchesType = currentSemanticFilter === "all" || items[i].classList.contains("filter-" + currentSemanticFilter);
        if (matchesSearch && matchesType) {{
          items[i].style.display = "block";
        }} else {{
          items[i].style.display = "none";
        }}
      }}
    }}
  </script>
</head>
<body>
  <div class="container">
    <h1>Knowledge Objects Inspection Report</h1>
    <p style="color:#64748b; margin-top: -5px; font-size:14px;">Document Job ID: {doc_id} · File: {structured_doc.file_name}.{structured_doc.file_type}</p>
    
    <div class="stat-row">
      <div class="stat-card"><div class="stat-num">{structured_doc.page_count}</div><div class="stat-lbl">Pages</div></div>
      <div class="stat-card"><div class="stat-num">{self.stats["total_objects"]}</div><div class="stat-lbl">Raw Objects</div></div>
      <div class="stat-card"><div class="stat-num">{len(chunks_list)}</div><div class="stat-lbl">Semantic Chunks</div></div>
      <div class="stat-card"><div class="stat-num">{self.stats["table_count"]}</div><div class="stat-lbl">Tables</div></div>
      <div class="stat-card"><div class="stat-num">{len(structured_doc.images)}</div><div class="stat-lbl">Images</div></div>
      <div class="stat-card"><div class="stat-num">{(self.stats["total_embedding_time"]):.1f}s</div><div class="stat-lbl">Emb Time</div></div>
    </div>
    
    <div class="tabs">
      <button class="tab-btn active" onclick="openTab(event, 'Structure')">Document Tree</button>
      <button class="tab-btn" onclick="openTab(event, 'SemanticChunks')">Semantic Chunks (ChromaDB)</button>
      <button class="tab-btn" onclick="openTab(event, 'RawObjects')">Raw Knowledge Objects</button>
    </div>
    
    <div id="Structure" class="tab-content active">
      <div class="card" style="padding:0; overflow:hidden; border:1px solid #e2e8f0;">
        <iframe src="./10_final/annotated_original.html" style="width:100%; height:550px; border:none; margin:0;" onerror="this.style.display='none'"></iframe>
      </div>
    </div>
    
    <div id="SemanticChunks" class="tab-content" style="display:none;">
      <input type="text" id="search-semantic" class="search-box" placeholder="Search final semantic chunks..." oninput="runFilterSemantic()"/>
      <div class="filters-bar">
        <button id="btn-sem-all" class="filter-btn filter-semantic-btn active" onclick="filterTypeSemantic('all')">All</button>
        <button id="btn-sem-text" class="filter-btn filter-semantic-btn" onclick="filterTypeSemantic('text')">Text (Paragraphs)</button>
        <button id="btn-sem-heading" class="filter-btn filter-semantic-btn" onclick="filterTypeSemantic('heading')">Headings</button>
        <button id="btn-sem-table" class="filter-btn filter-semantic-btn" onclick="filterTypeSemantic('table')">Tables</button>
        <button id="btn-sem-image" class="filter-btn filter-semantic-btn" onclick="filterTypeSemantic('image')">Images</button>
        <button id="btn-sem-list" class="filter-btn filter-semantic-btn" onclick="filterTypeSemantic('list')">Lists</button>
        <button id="btn-sem-code" class="filter-btn filter-semantic-btn" onclick="filterTypeSemantic('code')">Codes</button>
        <button id="btn-sem-footnote" class="filter-btn filter-semantic-btn" onclick="filterTypeSemantic('footnote')">Footnotes</button>
      </div>
      <div style="max-height:550px; overflow-y:auto; border: 1px solid #cbd5e1; border-radius: 8px; padding: 10px; background: #f8fafc;">
        {"".join(chunks_html)}
      </div>
    </div>
    
    <div id="RawObjects" class="tab-content" style="display:none;">
      <input type="text" id="search-raw" class="search-box" placeholder="Search raw knowledge objects..." oninput="runFilterRaw()"/>
      <div class="filters-bar">
        <button id="btn-raw-all" class="filter-btn filter-raw-btn active" onclick="filterTypeRaw('all')">All</button>
        <button id="btn-raw-text" class="filter-btn filter-raw-btn" onclick="filterTypeRaw('text')">Text</button>
        <button id="btn-raw-table" class="filter-btn filter-raw-btn" onclick="filterTypeRaw('table')">Tables & Cells</button>
        <button id="btn-raw-image" class="filter-btn filter-raw-btn" onclick="filterTypeRaw('image')">Images</button>
        <button id="btn-raw-ocr" class="filter-btn filter-raw-btn" onclick="filterTypeRaw('ocr')">OCR Blocks</button>
        <button id="btn-raw-caption" class="filter-btn filter-raw-btn" onclick="filterTypeRaw('caption')">Captions</button>
        <button id="btn-raw-list" class="filter-btn filter-raw-btn" onclick="filterTypeRaw('list')">Lists & Codes</button>
      </div>
      <div style="max-height:550px; overflow-y:auto; border: 1px solid #e2e8f0; border-radius: 8px; padding: 10px; background: #f8fafc;">
        {"".join(cards_html)}
      </div>
    </div>
  </div>
</body>
</html>
"""
        inspection_path = output_dir / "inspection_report.html"
        inspection_path.write_text(html_template, encoding="utf-8")
        logger.info(f"Generated inspection report at {inspection_path}")

def idx_img(img_id: str, images_dict: dict) -> int:
    try:
        keys = list(images_dict.keys())
        return keys.index(img_id) + 1
    except Exception:
        return 1

def idx_img_id(chunk_id: str, objects_list: List[dict]) -> int:
    try:
        # Find which index this chunk has among all image chunks
        img_chunks = [o for o in objects_list if o.get("chunk_type") == "Image"]
        ids = [o.get("knowledge_id") for o in img_chunks]
        return ids.index(chunk_id) + 1
    except Exception:
        return 1
