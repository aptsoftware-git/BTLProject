import logging
from pathlib import Path
from typing import Any, List, Dict, Optional

from src.rag.document_schema import (
    StructuredDocument,
    DocumentElement,
    ElementMetadata,
    BoundingBox
)
from src.rag.utils import convert_bbox
from src.rag.table_processor import TableProcessor
from src.rag.image_processor import ImageProcessor
from src.rag.caption_processor import CaptionProcessor

logger = logging.getLogger("pipeline")

class DocumentBuilder:
    """
    Builds a StructuredDocument from a converted Docling document.
    """

    def __init__(
        self,
        output_images_dir: Optional[Path] = None,
        pdf_path: Optional[Path] = None,
        batch_tag: Optional[str] = None
    ) -> None:
        self.output_images_dir = output_images_dir
        self.pdf_path = Path(pdf_path) if pdf_path else None
        # Tags the raw, pre-rename image filenames this batch writes (e.g.
        # "b3") so they can never collide with another batch's Docling
        # picture output in the shared 05_images directory -- see
        # ImageProcessor.process_image's filename_prefix docstring.
        self.batch_tag = batch_tag

    def build(self, docling_doc: Any, file_name: str, file_type: str) -> StructuredDocument:
        """
        Translates a Docling DoclingDocument tree into our StructuredDocument schema.
        """
        elements: List[DocumentElement] = []
        tables_dict = {}
        images_dict = {}
        
        # 1. Parse document pages count
        page_count = len(getattr(docling_doc, "pages", []) or []) or 1
        
        # 2. Track captions so we can link them
        # Captions might be standalone TextItems with a caption label, or referenced by images/tables.
        # We want to identify them and set caption_id in elements.
        caption_refs = {}  # maps cref (e.g. '#/texts/109') to target element ID (image/table ID)
        caption_texts = {} # maps cref to its text content

        # Pre-scan for captions of tables and pictures
        for element, _ in docling_doc.iterate_items():
            el_type = type(element).__name__
            if el_type in ("TableItem", "PictureItem"):
                target_id = element.self_ref
                captions = getattr(element, "captions", []) or []
                for ref in captions:
                    if hasattr(ref, "cref") and ref.cref:
                        caption_refs[ref.cref] = target_id

        # 3. Iterate items to build sequential elements
        for element, level in docling_doc.iterate_items():
            el_type = type(element).__name__
            self_ref = element.self_ref
            
            # Retrieve text representation
            text = getattr(element, "text", "") or ""
            
            # Resolve parent reference & hierarchy path
            parent_id = "body"
            if hasattr(element, "parent") and element.parent:
                parent_id = getattr(element.parent, "cref", "body") or "body"
            
            hierarchy_path = self._trace_hierarchy_path(element, docling_doc)

            # Get page and bounding box
            page_number = 1
            bbox = None
            if hasattr(element, "prov") and element.prov:
                prov = element.prov[0]
                page_number = getattr(prov, "page_no", 1)
                bbox = convert_bbox(getattr(prov, "bbox", None))

            # Determine element type and map specific structures
            mapped_type = "paragraph"
            image_id = None
            table_id = None
            caption_id = None
            ocr_text = None
            heading_level = None
            
            # Map type based on Docling class or label
            label = str(getattr(element, "label", "")).lower()
            
            if el_type == "SectionHeaderItem" or "section_header" in label or "heading" in label:
                mapped_type = "heading"
                heading_level = getattr(element, "level", 1)
            elif el_type == "ListItem" or "list_item" in label:
                mapped_type = "list_item"
            elif el_type == "TableItem" or "table" in label:
                mapped_type = "table"
                table_id = self_ref
                # Process detailed table structure
                try:
                    table_struct = TableProcessor.process_table(element, docling_doc)
                    tables_dict[self_ref] = table_struct
                    # Set text representation to markdown if available, for easier RAG ingestion
                    if table_struct.markdown:
                        text = table_struct.markdown
                except Exception as e:
                    logger.error(f"Error processing table {self_ref}: {e}")
            elif el_type in ("PictureItem", "ImageItem") or "picture" in label or "image" in label:
                mapped_type = "image"
                image_id = self_ref
                # Process detailed image metadata and save crop if configured
                try:
                    img_meta = ImageProcessor.process_image(
                        element,
                        docling_doc,
                        output_images_dir=self.output_images_dir,
                        pdf_path=self.pdf_path,
                        filename_prefix=self.batch_tag or ""
                    )
                    images_dict[self_ref] = img_meta
                    if img_meta.caption:
                        text = f"Image: {img_meta.caption}"
                    else:
                        text = "Image"
                except Exception as e:
                    logger.error(f"Error processing image {self_ref}: {e}")
            elif el_type == "FormulaItem" or "formula" in label:
                mapped_type = "formula"
            elif "footnote" in label:
                mapped_type = "footnote"
            elif "code" in label:
                mapped_type = "code"
            elif "caption" in label or self_ref in caption_refs:
                mapped_type = "caption"
                caption_texts[self_ref] = text
            else:
                # Default to paragraph
                mapped_type = "paragraph"

            # Associate caption reference if this element has a caption
            if self_ref in caption_refs:
                associated_target = caption_refs[self_ref]
                if "table" in associated_target:
                    table_id = associated_target
                elif "picture" in associated_target:
                    image_id = associated_target

            # Or if this element is a table/image, link its caption element ID
            # In docling, element.captions lists the refs
            element_captions = getattr(element, "captions", []) or []
            if element_captions and hasattr(element_captions[0], "cref"):
                caption_id = element_captions[0].cref

            # Build metadata
            meta = ElementMetadata(
                page_number=page_number,
                bbox=bbox,
                image_id=image_id,
                table_id=table_id,
                caption_id=caption_id,
                caption_text=CaptionProcessor.extract_caption_text(element, docling_doc),
                level=heading_level if mapped_type == "heading" else level,
                parent_id=parent_id,
                ocr_text=ocr_text
            )

            # Build element
            doc_element = DocumentElement(
                id=self_ref,
                type=mapped_type,
                text=text,
                metadata=meta,
                hierarchy_path=hierarchy_path
            )
            elements.append(doc_element)

        # 4. Determine Document Title
        title = file_name
        for el in elements:
            if el.type == "heading" and el.metadata.level == 1:
                title = el.text
                break

        return StructuredDocument(
            title=title,
            file_name=file_name,
            file_type=file_type,
            page_count=page_count,
            elements=elements,
            tables=tables_dict,
            images=images_dict,
            metadata=getattr(docling_doc, "meta", {}) or {}
        )

    def _trace_hierarchy_path(self, element: Any, doc: Any) -> List[str]:
        """
        Resolves the chain of parents of the element.
        """
        path = []
        current = element
        # Limit iterations to prevent infinite loop
        visited = set()
        for _ in range(50):
            if not hasattr(current, "parent") or not current.parent:
                break
            cref = getattr(current.parent, "cref", None)
            if not cref or cref == "#/body" or cref in visited:
                break
            visited.add(cref)
            path.append(cref)
            try:
                current = doc.get_ref(cref)
            except Exception:
                break
        path.reverse()
        return path
