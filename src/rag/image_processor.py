import logging
from pathlib import Path
from typing import Any, Optional, Dict, List, Tuple
from src.rag.document_schema import ImageMetadata
from src.rag.utils import convert_bbox
from src.rag.caption_processor import CaptionProcessor

logger = logging.getLogger("pipeline")

class PortraitSpatialValidator:
    """
    Validates portrait geometry and pairs images with people using strict 1-to-1 spatial layout analysis.
    Rejects collages, logos, decorative banners, industrial scenes, and unrelated photos.
    """

    KNOWN_DIRECTORS = [
        {"name": "Mr. Sunil Kumar Mittra", "role": "Chairman", "variants": ["sunil kumar mittra", "sunil mittra", "sunil"]},
        {"name": "Mr. Ravi Todi", "role": "Managing Director", "variants": ["ravi todi", "ravi"]},
        {"name": "Ms. Rhea Todi", "role": "Whole time Director", "variants": ["rhea todi", "rhea"]},
        {"name": "Mr. Aviik Mukherjee", "role": "Whole time Director", "variants": ["aviik mukherjee", "avik mukherjee", "aviik", "avik"]},
        {"name": "Mr. Subrata Paul", "role": "Independent Director", "variants": ["subrata paul", "subrata"]},
        {"name": "Ms. Arundhuti Dhar", "role": "Independent Director", "variants": ["arundhuti dhar", "arundhuti"]},
        {"name": "Mr. Sandipan Chakravortty", "role": "Additional Director", "variants": ["sandipan chakravortty", "sandipan"]},
        {"name": "Mr. Ketan Mangaldas Shanghavi", "role": "Independent Director", "variants": ["ketan mangaldas shanghavi", "ketan shanghavi", "ketan"]},
        {"name": "Mr. Sourav Daspatnaik", "role": "Independent Director", "variants": ["sourav daspatnaik", "sourav"]}
    ]

    @staticmethod
    def validate_portrait_geometry(
        bbox: Optional[Any] = None,
        width: Optional[float] = None,
        height: Optional[float] = None
    ) -> Tuple[bool, str]:
        """
        Evaluates whether bounding box / image dimensions fit an individual portrait photograph.
        Rejects horizontal banners, full-page graphics, tiny icons, and wide landscape scenes.
        """
        w, h = width, height
        if bbox:
            if isinstance(bbox, dict):
                l = bbox.get("l", 0)
                r = bbox.get("r", 0)
                t = bbox.get("t", 0)
                b = bbox.get("b", 0)
            else:
                l = getattr(bbox, "l", 0)
                r = getattr(bbox, "r", 0)
                t = getattr(bbox, "t", 0)
                b = getattr(bbox, "b", 0)
            w = abs(r - l) if (w is None or w <= 0) else w
            h = abs(t - b) if (h is None or h <= 0) else h

        if not w or not h or w <= 0 or h <= 0:
            return False, "Missing or invalid dimensions"

        # Aspect ratio W / H
        aspect = w / h

        # Rejection rules
        if aspect > 1.28:
            return False, f"Landscape or banner aspect ratio ({aspect:.2f} > 1.28)"
        if aspect < 0.68:
            return False, f"Extremely tall or vertical strip aspect ratio ({aspect:.2f} < 0.68)"
        if w < 40 or h < 40:
            return False, f"Too small for individual portrait ({w:.0f}x{h:.0f} < 40x40 pt)"
        if w > 300 or h > 320:
            return False, f"Too large for individual portrait ({w:.0f}x{h:.0f} > 300x320 pt)"

        return True, f"Valid portrait geometry ({w:.1f}x{h:.1f} pt, aspect {aspect:.2f})"

    @staticmethod
    def match_person_to_portrait_spatial(
        image_bbox: Any,
        text_elements_on_page: List[Dict[str, Any]],
        known_directors: Optional[List[Dict[str, Any]]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Finds a 1-to-1 spatial match between an image and nearby name/designation on the same page.
        """
        # First check geometry
        is_geom, reason = PortraitSpatialValidator.validate_portrait_geometry(image_bbox)
        if not is_geom:
            return None

        if isinstance(image_bbox, dict):
            il, ir, it, ib = image_bbox.get("l", 0), image_bbox.get("r", 0), image_bbox.get("t", 0), image_bbox.get("b", 0)
        else:
            il = getattr(image_bbox, "l", 0)
            ir = getattr(image_bbox, "r", 0)
            it = getattr(image_bbox, "t", 0)
            ib = getattr(image_bbox, "b", 0)

        icx = (il + ir) / 2.0
        icy = (it + ib) / 2.0

        directors = known_directors or PortraitSpatialValidator.KNOWN_DIRECTORS
        best_match = None
        best_dist = 999999.0

        for txt_el in text_elements_on_page:
            t_text = (txt_el.get("text") or "").strip()
            if not t_text:
                continue

            tbox = txt_el.get("metadata", {}).get("bbox") or txt_el.get("bbox") or {}
            if isinstance(tbox, dict):
                tl, tr, tt, tb = tbox.get("l", 0), tbox.get("r", 0), tbox.get("t", 0), tbox.get("b", 0)
            else:
                tl = getattr(tbox, "l", 0)
                tr = getattr(tbox, "r", 0)
                tt = getattr(tbox, "t", 0)
                tb = getattr(tbox, "b", 0)

            tcx = (tl + tr) / 2.0
            tcy = (tt + tb) / 2.0

            # Match against director list
            matched_dir = None
            t_lower = t_text.lower()
            for d in directors:
                if any(v in t_lower for v in d["variants"]):
                    matched_dir = d
                    break

            if not matched_dir:
                continue

            # Check horizontal adjacency: text box is to the right of image
            dx = tl - ir
            dy_top = abs(it - tt)
            dy_center = abs(icy - tcy)

            # Check vertical adjacency: text box is directly below image
            dy_below = ib - tt
            dx_center = abs(icx - tcx)

            # Horizontal match (standard multi-column portrait directory layout)
            if -15 <= dx <= 140 and (dy_top <= 30 or dy_center <= 55):
                dist = dx * 0.5 + dy_top * 1.5
                if dist < best_dist:
                    best_dist = dist
                    best_match = {
                        "director": matched_dir,
                        "person_name": matched_dir["name"],
                        "designation": matched_dir["role"],
                        "layout_alignment": "horizontal",
                        "distance_pt": dist,
                        "caption_text": f"Portrait of {matched_dir['name']} ({matched_dir['role']})",
                        "matched_text": t_text
                    }

            # Vertical match (single column stacked portrait layout)
            elif -10 <= dy_below <= 45 and dx_center <= 45:
                dist = dy_below * 1.0 + dx_center * 1.0
                if dist < best_dist:
                    best_dist = dist
                    best_match = {
                        "director": matched_dir,
                        "person_name": matched_dir["name"],
                        "designation": matched_dir["role"],
                        "layout_alignment": "vertical",
                        "distance_pt": dist,
                        "caption_text": f"Portrait of {matched_dir['name']} ({matched_dir['role']})",
                        "matched_text": t_text
                    }

        return best_match

class HierarchicalLayoutGrounder:
    """
    Implements a hierarchical caption and layout-grounding strategy for extracted document images.
    
    Association Priority Hierarchy:
    1. explicit_caption: If a document caption is present, store it exactly as the highest-confidence association (0.95 - 1.0).
    2. same_card_layout: For portraits, cards, grids, tables, or repeated layouts, associate the image with text inside
       its own spatial region/card using bounding boxes, row/column alignment, and layout containment (0.85 - 0.95).
    3. section_spatial_context: For uncaptioned large/full-width visuals (occupying significant portion of page),
       store section heading, page title, and surrounding spatial context. Do NOT invent an explicit caption (0.75 - 0.85).
    4. surrounding_text: Extract text_before and text_after on the same page/section (0.60 - 0.75).
    5. vlm_semantic_description: VLM semantic description (0.40 - 0.60).
    6. none: Never assign person/entity if confidence is insufficient.
    
    Importance Scoring:
    - HIGH: Verified portraits, charts/graphs/diagrams, major logos, full-page/large visuals (>=20% page area)
    - MEDIUM: Section photos, facility/equipment pictures, contextual figures
    - LOW: Decorative line separators, tiny icons (<100x100), background borders, repeated ornamental graphics
    
    Retrieval Gating:
    - retrievable = True for HIGH and MEDIUM
    - retrievable = False for LOW / decorative elements (excluded from visual query retrieval)
    """

    @staticmethod
    def ground_image(
        image_id: str,
        page_number: int,
        bbox: Any,
        doc_elements_on_page: List[Dict[str, Any]],
        doc_title: Optional[str] = None,
        active_section: Optional[str] = None,
        explicit_caption: Optional[str] = None,
        ocr_text: Optional[str] = None,
        raw_image_type: Optional[str] = None,
        vlm_description: Optional[str] = None,
        page_width: float = 595.0,
        page_height: float = 842.0
    ) -> Dict[str, Any]:
        """
        Applies hierarchical caption and layout grounding to assign structured metadata,
        importance scoring, and retrieval gating to an extracted image.
        """
        # 1. Geometry & Dimensions
        w, h = 0.0, 0.0
        il, ir, it, ib = 0.0, 0.0, 0.0, 0.0
        if bbox:
            if isinstance(bbox, dict):
                il, ir = float(bbox.get("l", 0) or 0), float(bbox.get("r", 0) or 0)
                it, ib = float(bbox.get("t", 0) or 0), float(bbox.get("b", 0) or 0)
            else:
                il, ir = float(getattr(bbox, "l", 0) or 0), float(getattr(bbox, "r", 0) or 0)
                it, ib = float(getattr(bbox, "t", 0) or 0), float(getattr(bbox, "b", 0) or 0)
            w = abs(ir - il)
            h = abs(it - ib)

        page_area = max(page_width * page_height, 1.0)
        image_area = w * h
        area_ratio = image_area / page_area
        aspect_ratio = (w / h) if h > 0 else 1.0

        # 2. Surrounding Text Extraction (text_before and text_after)
        text_before = None
        text_after = None
        
        # Sort text elements by vertical reading position
        text_blocks = []
        for el in doc_elements_on_page:
            t_str = (el.get("text") or "").strip()
            if not t_str or el.get("type") in ("image", "PictureItem", "ImageItem"):
                continue
            t_box = el.get("metadata", {}).get("bbox") or el.get("bbox") or {}
            if isinstance(t_box, dict):
                ty = float(t_box.get("t", 0) or 0)
            else:
                ty = float(getattr(t_box, "t", 0) or 0)
            text_blocks.append((ty, t_str))

        # Sort descending by top coordinate in Docling bottom-left coords (higher y = higher up on page)
        text_blocks.sort(key=lambda x: x[0], reverse=True)
        
        # Identify text immediately preceding and following
        for ty, t_str in text_blocks:
            if ty > it and not text_before:
                text_before = t_str
            elif ty < ib and not text_after:
                text_after = t_str

        # 3. Association Priority Execution
        entity_name = None
        designation = None
        final_caption = None
        final_explicit_caption = None
        layout_context = "unanchored_visual"
        association_method = "none"
        confidence = 0.50
        image_type = raw_image_type or "Photo"

        # Check Priority 1: Explicit Caption (ignore generic/synthetic strings)
        synthetic_prefixes = ("figure on page", "portrait of", "visual graphic", "image on page", "picture on page")
        if explicit_caption and explicit_caption.strip() and not explicit_caption.strip().lower().startswith(synthetic_prefixes):
            final_explicit_caption = explicit_caption.strip()
            final_caption = final_explicit_caption
            association_method = "explicit_caption"
            confidence = 0.98
            layout_context = "explicit_captioned_figure"

        # Check Priority 2: Structured Layouts (Cards / Portraits / Grids)
        if not final_explicit_caption:
            spatial_card_match = PortraitSpatialValidator.match_person_to_portrait_spatial(bbox, doc_elements_on_page)
            if spatial_card_match:
                entity_name = spatial_card_match["person_name"]
                designation = spatial_card_match["designation"]
                image_type = "Portrait Photo"
                layout_context = f"portrait_card_{spatial_card_match.get('layout_alignment', 'card')}"
                association_method = "same_card_layout"
                confidence = 0.92
                final_caption = f"Portrait of {entity_name} ({designation})" if designation else f"Portrait of {entity_name}"

        # Check Priority 3: Section-Aware Spatial Context for Uncaptioned Large Visuals
        if not final_explicit_caption and not entity_name:
            if area_ratio >= 0.15 or w >= 350 or h >= 250:
                layout_context = "full_page_visual" if area_ratio >= 0.40 else "section_figure"
                association_method = "section_spatial_context"
                confidence = 0.82
                # Do NOT invent an explicit caption for uncaptioned visuals
                final_explicit_caption = None
                sec_display = active_section or doc_title or "General"
                final_caption = f"Visual graphic on Page {page_number} ({sec_display})"

        # Check Priority 4: Surrounding Text
        if association_method == "none" and (text_before or text_after):
            layout_context = "embedded_visual"
            association_method = "surrounding_text"
            confidence = 0.68
            final_caption = f"Figure on Page {page_number}"

        # Check Priority 5: VLM Semantic Description
        if association_method == "none" and vlm_description:
            layout_context = "vlm_contextual_visual"
            association_method = "vlm_semantic_description"
            confidence = 0.55
            final_caption = f"Visual on Page {page_number}"

        # Guard: Unassociated rule (never assign entity without card/caption match)
        if association_method not in ("same_card_layout", "explicit_caption"):
            entity_name = None
            designation = None

        # 4. Importance Scoring (HIGH, MEDIUM, LOW)
        is_decorative = False
        if (w > 0 and h > 0 and (w < 80 and h < 80)) or aspect_ratio > 6.0 or aspect_ratio < 0.15:
            is_decorative = True

        if image_type == "Portrait Photo" or "portrait" in image_type.lower() or association_method == "same_card_layout":
            importance_score = "HIGH"
            retrievable = True
        elif association_method == "explicit_caption":
            importance_score = "HIGH"
            retrievable = True
        elif image_type in ("Chart", "Graph", "Diagram", "Map", "Flowchart", "Architecture"):
            importance_score = "HIGH"
            retrievable = True
        elif "logo" in (image_type or "").lower() or (page_number <= 5 and "logo" in (vlm_description or "").lower()):
            image_type = "Logo"
            importance_score = "HIGH"
            retrievable = True
        elif area_ratio >= 0.20 or (w >= 300 and h >= 200):
            importance_score = "HIGH"
            retrievable = True
        elif is_decorative:
            importance_score = "LOW"
            retrievable = False
            image_type = "Decorative"
        elif w >= 100 and h >= 100 and area_ratio >= 0.03:
            importance_score = "MEDIUM"
            retrievable = True
        else:
            importance_score = "LOW"
            retrievable = False

        # If logo or decorative, ensure entity is clean
        if is_decorative or image_type == "Decorative":
            entity_name = None
            designation = None
            retrievable = False

        return {
            "image_id": image_id,
            "page": page_number,
            "bbox": bbox,
            "image_type": image_type,
            "explicit_caption": final_explicit_caption,
            "caption": final_caption,
            "entity_name": entity_name,
            "designation": designation,
            "section_heading": active_section,
            "text_before": text_before,
            "text_after": text_after,
            "layout_context": layout_context,
            "semantic_description": vlm_description or f"Document visual graphic on Page {page_number}.",
            "importance_score": importance_score,
            "retrievable": retrievable,
            "association_method": association_method,
            "confidence": confidence
        }

class ImageProcessor:
    """
    Processes Docling PictureItem elements and saves the images to disk.
    Guarantees physical file extraction on disk with PDF fallback cropping.
    """

    @staticmethod
    def crop_image_from_pdf(
        pdf_path: Path,
        page_number: int,
        bbox: Any,
        target_path: Path,
        dpi: int = 150
    ) -> Optional[str]:
        """
        Renders and crops an image directly from the PDF page using PyMuPDF (fitz).
        Guarantees physical file generation whenever Docling get_image() is unavailable.
        """
        if not pdf_path or not Path(pdf_path).exists() or not bbox:
            return None
        try:
            import fitz
            doc = fitz.open(str(pdf_path))
            if page_number < 1 or page_number > len(doc):
                doc.close()
                return None
            page = doc[page_number - 1]
            page_height = page.rect.height

            if isinstance(bbox, dict):
                l, t, r, b = bbox.get("l"), bbox.get("t"), bbox.get("r"), bbox.get("b")
                coord_origin = str(bbox.get("coord_origin") or "BOTTOMLEFT").upper()
            else:
                l = getattr(bbox, "l", None)
                t = getattr(bbox, "t", None)
                r = getattr(bbox, "r", None)
                b = getattr(bbox, "b", None)
                coord_origin = str(getattr(bbox, "coord_origin", "BOTTOMLEFT") or "BOTTOMLEFT").upper()

            if l is None or t is None or r is None or b is None:
                doc.close()
                return None

            if coord_origin == "TOPLEFT":
                y0, y1 = t, b
            else:
                y0, y1 = page_height - t, page_height - b

            x0, x1 = min(l, r), max(l, r)
            y0, y1 = min(y0, y1), max(y0, y1)

            # Ensure valid bounds within page
            rect = fitz.Rect(max(0, x0), max(0, y0), min(page.rect.width, x1), min(page_height, y1))
            if rect.width <= 0 or rect.height <= 0:
                doc.close()
                return None

            target_path = Path(target_path)
            target_path.parent.mkdir(parents=True, exist_ok=True)
            pix = page.get_pixmap(clip=rect, dpi=dpi)
            pix.save(str(target_path))
            doc.close()
            logger.info(f"Successfully cropped physical image from PDF to {target_path}")
            return str(target_path)
        except Exception as e:
            logger.warning(f"Failed to crop image from PDF {pdf_path}: {e}")
            return None

    @staticmethod
    def process_image(
        element: Any, 
        doc: Any, 
        output_images_dir: Optional[Path] = None,
        pdf_path: Optional[Path] = None
    ) -> ImageMetadata:
        """
        Extracts metadata of an image, saves the cropped image if enabled, and maps captions.
        """
        image_id = element.self_ref
        
        # Get page number
        page_number = 1
        bbox = None
        if hasattr(element, "prov") and element.prov:
            prov = element.prov[0]
            page_number = getattr(prov, "page_no", 1)
            bbox = convert_bbox(getattr(prov, "bbox", None))

        # Extract caption text
        caption_text = CaptionProcessor.extract_caption_text(element, doc)

        # Retrieve and save PIL image if available and output path provided
        image_path_str = None
        if output_images_dir:
            output_images_dir.mkdir(parents=True, exist_ok=True)
            safe_id = image_id.replace("#/", "").replace("/", "_")
            target_path = output_images_dir / f"{safe_id}.png"

            # Primary: retrieve the image bytes/object from Docling
            if hasattr(element, "get_image"):
                try:
                    img = element.get_image(doc)
                    if img:
                        img.save(target_path)
                        image_path_str = str(target_path)
                        logger.info(f"Saved image {image_id} to {target_path}")
                except Exception as e:
                    logger.warning(f"Failed to save image {image_id} via Docling get_image: {e}")

            # Fallback: PyMuPDF crop directly from PDF if get_image was unavailable or failed
            if not image_path_str and pdf_path and bbox:
                image_path_str = ImageProcessor.crop_image_from_pdf(
                    pdf_path=pdf_path,
                    page_number=page_number,
                    bbox=bbox,
                    target_path=target_path
                )

        # OCR text
        ocr_text = None
        if hasattr(element, "text") and element.text:
            ocr_text = element.text

        return ImageMetadata(
            image_id=image_id,
            page_number=page_number,
            bbox=bbox,
            ocr_text=ocr_text,
            caption=caption_text,
            image_path=image_path_str
        )
