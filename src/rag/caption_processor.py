from typing import Any, List, Optional

class CaptionProcessor:
    """
    Extracts and maps captions for images and tables from the Docling document.
    """

    @staticmethod
    def extract_caption_text(element: Any, doc: Any) -> Optional[str]:
        """
        Retrieves the combined caption text associated with a Docling element (TableItem or PictureItem).
        """
        captions = getattr(element, "captions", []) or []
        if not captions:
            return None
            
        caption_texts = []
        for ref in captions:
            if not hasattr(ref, "cref") or not ref.cref:
                continue
            
            # Resolve the reference in the DoclingDocument
            # In docling, ref.cref is something like '#/texts/109'
            try:
                caption_item = doc.get_ref(ref.cref)
                if caption_item and hasattr(caption_item, "text") and caption_item.text:
                    caption_texts.append(caption_item.text.strip())
            except Exception:
                # Fallback if get_ref fails
                pass
                
        return " ".join(caption_texts) if caption_texts else None

    @staticmethod
    def get_caption_ids(element: Any) -> List[str]:
        """
        Returns a list of element IDs that act as captions for this element.
        """
        captions = getattr(element, "captions", []) or []
        ids = []
        for ref in captions:
            if hasattr(ref, "cref") and ref.cref:
                ids.append(ref.cref)
        return ids
