from typing import Any, Optional
from src.rag.document_schema import BoundingBox

def convert_bbox(docling_bbox: Any) -> Optional[BoundingBox]:
    """
    Converts a Docling bounding box to our schema's BoundingBox model.
    """
    if docling_bbox is None:
        return None
    
    # Docling bounding box has attributes l, t, r, b
    # Check if they exist
    if not (hasattr(docling_bbox, "l") and hasattr(docling_bbox, "t") and 
            hasattr(docling_bbox, "r") and hasattr(docling_bbox, "b")):
        return None
        
    coord_origin = "BOTTOMLEFT"
    if hasattr(docling_bbox, "coord_origin"):
        coord_origin = str(docling_bbox.coord_origin)
        # Often it's an enum, get name if possible
        if hasattr(docling_bbox.coord_origin, "name"):
            coord_origin = docling_bbox.coord_origin.name

    return BoundingBox(
        l=float(docling_bbox.l),
        t=float(docling_bbox.t),
        r=float(docling_bbox.r),
        b=float(docling_bbox.b),
        coord_origin=coord_origin
    )
