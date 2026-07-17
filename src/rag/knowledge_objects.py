from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class KnowledgeObject(BaseModel):
    """
    Represents an independent Knowledge Object in the Knowledge-Centric Multimodal RAG system.
    """
    knowledge_id: str = Field(..., description="Unique ID of this knowledge object (e.g., {doc_id}_chunk_{seq:04d})")
    document_id: str = Field(..., description="Identifier of the source document")
    page_number: int = Field(..., description="Page number where the knowledge element resides (1-indexed)")
    chunk_type: str = Field(..., description="Type of knowledge object (e.g., Heading, Paragraph, Table Cell, etc.)")
    heading: Optional[str] = Field(None, description="Immediate heading context")
    parent_heading: Optional[str] = Field(None, description="Parent heading context")
    section_path: Optional[str] = Field(None, description="Concatenated heading hierarchy path")
    sequence_number: int = Field(..., description="Ingestion sequence order number")
    text: str = Field(..., description="Raw textual content of this knowledge object")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Generic metadata details")
    relationships: Dict[str, Any] = Field(default_factory=dict, description="Relationships to other knowledge objects")
    embedding_status: str = Field("Pending", description="Status of embedding: Pending or Embedded")
    source_file: str = Field(..., description="Name of the source file")
    bounding_box: Optional[Dict[str, Any]] = Field(None, description="Bounding box details")
    created_time: str = Field(..., description="ISO 8601 created timestamp")
    confidence: float = Field(1.0, description="Extraction/understanding confidence score")
