import logging
from pathlib import Path
from typing import Any, Optional
from src.rag.document_schema import ImageMetadata
from src.rag.utils import convert_bbox
from src.rag.caption_processor import CaptionProcessor

logger = logging.getLogger("pipeline")

class ImageProcessor:
    """
    Processes Docling PictureItem elements and saves the images to disk.
    """

    @staticmethod
    def process_image(
        element: Any, 
        doc: Any, 
        output_images_dir: Optional[Path] = None
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
        if output_images_dir and hasattr(element, "get_image"):
            try:
                # Retrieve the image bytes/object from Docling
                img = element.get_image(doc)
                if img:
                    output_images_dir.mkdir(parents=True, exist_ok=True)
                    # Clean the self_ref ID to make a valid filename
                    safe_id = image_id.replace("#/", "").replace("/", "_")
                    target_path = output_images_dir / f"{safe_id}.png"
                    img.save(target_path)
                    image_path_str = str(target_path)
                    logger.info(f"Saved image {image_id} to {target_path}")
            except Exception as e:
                logger.warning(f"Failed to save image {image_id}: {e}")

        # OCR text
        ocr_text = None
        # In Docling, sometimes text overlay or annotations contain OCR text
        # If available, we can grab it, but typically it is None or handled by layout
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
