from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from src.rag.document_schema import BoundingBox

class ChunkMetadata(BaseModel):
    """
    Metadata required for each semantic chunk for retrieval and RAG processing.
    """
    chunk_id: str = Field(..., description="Unique ID of this chunk (e.g., doc_id_chunk_idx)")
    document_id: str = Field(..., description="Identifier of the source document")
    page_number: int = Field(..., description="Page number where the chunk elements reside (1-indexed)")
    chunk_type: str = Field(..., description="Type of chunk: 'text', 'table', 'image', 'list', 'code', 'footnote'")
    heading: Optional[str] = Field(None, description="Immediate heading context for this chunk")
    section: Optional[str] = Field(None, description="Concatenated heading hierarchy path (e.g., 'Chapter 1 > Section 2')")
    hierarchy_path: List[str] = Field(default_factory=list, description="IDs of ancestor headings/sections")
    source_element_ids: List[str] = Field(default_factory=list, description="Docling element IDs composing this chunk")
    word_count: int = Field(..., description="Number of words in this chunk")
    token_estimate: int = Field(..., description="Estimated number of tokens in this chunk")
    bounding_boxes: List[BoundingBox] = Field(default_factory=list, description="Bounding boxes of the source elements")
    image_id: Optional[str] = Field(None, description="Referenced image ID if chunk is an image")
    image_path: Optional[str] = Field(None, description="Local path to saved image file")
    image_url: Optional[str] = Field(None, description="Static URL to access the image")
    image_type: Optional[str] = Field(None, description="Detected or annotated image type (e.g. Chart, Diagram, Graph, Map)")
    title: Optional[str] = Field(None, description="Primary title or exact caption of the image")
    subtitle: Optional[str] = Field(None, description="Secondary contextual text, role, or description")
    explicit_caption: Optional[str] = Field(None, description="Exact document caption if explicitly present")
    caption_text: Optional[str] = Field(None, description="Full caption text associated with the image")
    entity_name: Optional[str] = Field(None, description="Name of person or entity associated via layout grounding")
    designation: Optional[str] = Field(None, description="Designation or role of person associated via layout grounding")
    text_before: Optional[str] = Field(None, description="Immediate textual context preceding the image")
    text_after: Optional[str] = Field(None, description="Immediate textual context succeeding the image")
    nearby_text: Optional[str] = Field(None, description="Selected adjacent profile/text block content used for spatial grounding")
    layout_context: Optional[str] = Field(None, description="Layout spatial context (e.g. portrait_card_horizontal, full_page_visual, section_figure)")
    importance_score: Optional[str] = Field("MEDIUM", description="Image importance level: HIGH, MEDIUM, LOW")
    retrievable: bool = Field(True, description="Whether image is meaningful and retrievable (False for decorative/separators)")
    association_method: Optional[str] = Field("none", description="Method used for context association: explicit_caption, same_card_layout, spatial_document_context, spatially_nearest_text, section_spatial_context, surrounding_text, vlm_semantic_description, none")
    confidence: float = Field(1.0, description="Confidence of the extraction/understanding")
    association_confidence: Optional[float] = Field(1.0, description="Confidence score of context association (0.0 to 1.0)")
    caption: Optional[str] = Field(None, description="Image or table caption")
    ocr_text: Optional[str] = Field(None, description="OCR text extracted from image")
    semantic_description: Optional[str] = Field(None, description="Detailed VLM semantic description of image content")
    objects: List[str] = Field(default_factory=list, description="Detected objects inside the image")
    detected_entities: List[str] = Field(default_factory=list, description="Entities detected inside the image")
    table_id: Optional[str] = Field(None, description="Referenced table ID if chunk is a table")
    element_types: List[str] = Field(default_factory=list, description="Types of source elements composing this chunk")
    relationships: Dict[str, Any] = Field(default_factory=dict, description="Relationships to other chunks or elements")
    
    # Enriched Metadata Fields (Phase 6 Optimization & Section Hierarchy)
    section_id: Optional[str] = Field(None, description="Unique ID of the parent section object")
    section_heading: Optional[str] = Field(None, description="Top-level parent section heading (e.g. 'Our Marquee Clients')")
    subsection_heading: Optional[str] = Field(None, description="Immediate subsection heading if present")
    is_section_root: bool = Field(False, description="True if chunk represents an intact section object")
    child_chunk_ids: List[str] = Field(default_factory=list, description="IDs of sub-chunks within this section")
    
    report_number: Optional[str] = Field(None, description="Extracted report number context")
    state: Optional[str] = Field(None, description="Associated state name")
    region: Optional[str] = Field(None, description="Associated region name")
    district: Optional[str] = Field(None, description="Associated district name")
    people: List[str] = Field(default_factory=list, description="Extracted person names")
    organizations: List[str] = Field(default_factory=list, description="Extracted organization names")
    groups: List[str] = Field(default_factory=list, description="Extracted group names")
    dates: List[str] = Field(default_factory=list, description="Extracted date mentions")
    weapons: List[str] = Field(default_factory=list, description="Extracted weapon terms")
    locations: List[str] = Field(default_factory=list, description="Extracted location/GPE names")
    keywords: List[str] = Field(default_factory=list, description="Extracted text keywords")

class SectionObject(BaseModel):
    """
    Coherent section object preserving entity lists and section-level context.
    """
    section_id: str = Field(..., description="Unique section identifier")
    section_title: str = Field(..., description="Canonical section title")
    page_start: int = Field(..., description="Starting page of section")
    page_end: int = Field(..., description="Ending page of section")
    content: str = Field(..., description="Full consolidated section content")
    child_chunks: List[str] = Field(default_factory=list, description="List of child chunk IDs")



class DocumentChunk(BaseModel):
    """
    A single semantic chunk of the document.
    """
    content: str = Field(..., description="Textual or structured content of the chunk")
    metadata: ChunkMetadata = Field(..., description="Associated metadata")

class DocumentChunksOutput(BaseModel):
    """
    The root structure of the exported document_chunks.json.
    """
    document_id: str = Field(..., description="Source document job/run ID")
    file_name: str = Field(..., description="Source file name")
    chunks: List[DocumentChunk] = Field(default_factory=list, description="List of all extracted semantic chunks")
