from typing import List, Optional
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
    table_id: Optional[str] = Field(None, description="Referenced table ID if chunk is a table")
    
    # Enriched Metadata Fields (Phase 6 Optimization)
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
