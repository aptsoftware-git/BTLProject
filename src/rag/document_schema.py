from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

class BoundingBox(BaseModel):
    """Bounding box coordinates for a document element."""
    l: float = Field(..., description="Left coordinate")
    t: float = Field(..., description="Top coordinate")
    r: float = Field(..., description="Right coordinate")
    b: float = Field(..., description="Bottom coordinate")
    coord_origin: str = Field("BOTTOMLEFT", description="Coordinate origin (e.g. BOTTOMLEFT, TOPLEFT)")

class ElementMetadata(BaseModel):
    """Metadata associated with a single document element."""
    page_number: int = Field(..., description="1-indexed page number of the element")
    bbox: Optional[BoundingBox] = Field(None, description="Coordinates bounding box on the page")
    image_id: Optional[str] = Field(None, description="Referenced image ID if element is an image")
    table_id: Optional[str] = Field(None, description="Referenced table ID if element is a table")
    caption_id: Optional[str] = Field(None, description="Referenced caption element ID if associated with one")
    caption_text: Optional[str] = Field(None, description="Caption text if associated with a caption")
    level: Optional[int] = Field(None, description="Nesting level (e.g. heading depth, list depth)")
    parent_id: Optional[str] = Field(None, description="ID of parent element in the document tree")
    ocr_text: Optional[str] = Field(None, description="OCR extracted text if applicable")

class DocumentElement(BaseModel):
    """A single logical element in the document hierarchy (e.g. paragraph, heading, list item, image, table, formula, code, footnote)."""
    id: str = Field(..., description="Unique element identifier (typically Docling self_ref)")
    type: str = Field(..., description="Element type (heading, paragraph, list_item, table, image, caption, formula, code, footnote)")
    text: str = Field(..., description="Raw text content of the element")
    metadata: ElementMetadata = Field(..., description="Element metadata including layout details")
    hierarchy_path: List[str] = Field(default_factory=list, description="Ordered ancestor IDs from root down to parent")

class TableCell(BaseModel):
    """A cell in an extracted table."""
    text: str = Field(..., description="Cell text content")
    row_index: int = Field(..., description="0-indexed row index of cell")
    col_index: int = Field(..., description="0-indexed column index of cell")
    row_span: int = Field(1, description="Number of rows spanned by this cell")
    col_span: int = Field(1, description="Number of columns spanned by this cell")
    is_header: bool = Field(False, description="Whether this cell is part of row/column headers")
    bbox: Optional[BoundingBox] = Field(None, description="Coordinates of cell on the page")

class TableStructure(BaseModel):
    """Detailed structure of an extracted table."""
    table_id: str = Field(..., description="Unique ID of the table (matching element ID)")
    rows_count: int = Field(..., description="Total number of rows")
    cols_count: int = Field(..., description="Total number of columns")
    cells: List[TableCell] = Field(default_factory=list, description="Flat list of cell structures")
    markdown: Optional[str] = Field(None, description="Markdown serialization of the table")
    html: Optional[str] = Field(None, description="HTML serialization of the table")
    caption: Optional[str] = Field(None, description="Associated table caption text")

class ImageMetadata(BaseModel):
    """Detailed metadata for an extracted image."""
    image_id: str = Field(..., description="Unique ID of the image (matching element ID)")
    page_number: int = Field(..., description="1-indexed page number where the image appears")
    bbox: Optional[BoundingBox] = Field(None, description="Image bounding box")
    ocr_text: Optional[str] = Field(None, description="OCR text extracted from image area")
    caption: Optional[str] = Field(None, description="Associated figure caption text")
    image_path: Optional[str] = Field(None, description="Local path to saved image file, if saved")
    
    # Vision metadata fields (Phase 6 Final & Hierarchical Layout Grounding)
    image_type: Optional[str] = Field(None, description="Detected image type (e.g. Chart, Graph, Map)")
    title: Optional[str] = Field(None, description="Primary title or exact caption of the image")
    subtitle: Optional[str] = Field(None, description="Secondary contextual text, role, or description")
    explicit_caption: Optional[str] = Field(None, description="Exact document caption if explicitly present")
    caption_text: Optional[str] = Field(None, description="Full caption text associated with the image")
    entity_name: Optional[str] = Field(None, description="Name of person or entity associated via layout grounding")
    designation: Optional[str] = Field(None, description="Designation or role of person associated via layout grounding")
    entity_id: Optional[str] = Field(None, description="Stable document-scoped entity/person key, shared with the text chunks that discuss this same person")
    linked_text_chunk_ids: List[str] = Field(default_factory=list, description="Chunk IDs of the text chunks (biography/qualifications/experience) that discuss this image's grounded entity")
    section_heading: Optional[str] = Field(None, description="Immediate section heading covering the image")
    text_before: Optional[str] = Field(None, description="Immediate textual context preceding the image")
    text_after: Optional[str] = Field(None, description="Immediate textual context succeeding the image")
    nearby_text: Optional[str] = Field(None, description="Selected adjacent profile/text block content used for spatial grounding")
    layout_context: Optional[str] = Field(None, description="Layout spatial context (e.g. portrait_card_horizontal, full_page_visual, section_figure)")
    importance_score: str = Field("MEDIUM", description="Image importance level: HIGH, MEDIUM, LOW")
    retrievable: bool = Field(True, description="Whether image is meaningful and retrievable (False for decorative/separators)")
    association_method: str = Field("none", description="Method used for context association: explicit_caption, same_card_layout, spatial_document_context, spatially_nearest_text, section_spatial_context, surrounding_text, vlm_semantic_description, none")
    association_confidence: Optional[float] = Field(1.0, description="Confidence score of context association (0.0 to 1.0)")
    objects: List[str] = Field(default_factory=list, description="List of detected objects in the image")
    keywords: List[str] = Field(default_factory=list, description="Keywords summarizing the image content")
    semantic_description: Optional[str] = Field(None, description="Generated semantic description of the image content")
    detected_entities: List[str] = Field(default_factory=list, description="Entities detected inside the image")
    related_section: Optional[str] = Field(None, description="Heading/section path where the image was found")
    confidence: float = Field(1.0, description="Confidence of the extraction/understanding")
    future_vlm_metadata_placeholder: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Placeholder for future VLM metadata")


class StructuredDocument(BaseModel):
    """Unified structured representation of the entire document hierarchy."""
    title: str = Field(..., description="Document title or root header")
    file_name: str = Field(..., description="Name of original source file")
    file_type: str = Field(..., description="File extension without dot")
    page_count: int = Field(..., description="Total pages in document")
    elements: List[DocumentElement] = Field(default_factory=list, description="Sequential list of all document elements in layout order")
    tables: Dict[str, TableStructure] = Field(default_factory=dict, description="Detailed table structures keyed by table ID")
    images: Dict[str, ImageMetadata] = Field(default_factory=dict, description="Detailed image metadata keyed by image ID")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Generic metadata parsed from the document")
