import json
from pathlib import Path
from src.rag.multimodal_extractor import MultimodalExtractor
from src.rag.chunk_builder import ChunkBuilder
from src.rag.document_schema import StructuredDocument
from src.rag.chunk_schema import DocumentChunksOutput

def test_chunk_builder_on_txt():
    # Construct a dummy StructuredDocument directly to isolate ChunkBuilder
    # containing headings, paragraphs, lists, tables, images, captions
    from src.rag.document_schema import DocumentElement, ElementMetadata, TableStructure, ImageMetadata, TableCell
    
    doc = StructuredDocument(
        title="Test Document",
        file_name="test_doc",
        file_type="txt",
        page_count=1,
        elements=[
            # Heading 1
            DocumentElement(
                id="#/texts/0", type="heading", text="1. Introduction",
                metadata=ElementMetadata(page_number=1, level=1, parent_id="body"),
                hierarchy_path=[]
            ),
            # Paragraph 1
            DocumentElement(
                id="#/texts/1", type="paragraph", text="This is paragraph one under the first heading.",
                metadata=ElementMetadata(page_number=1, parent_id="#/texts/0"),
                hierarchy_path=["#/texts/0"]
            ),
            # Heading 2
            DocumentElement(
                id="#/texts/2", type="heading", text="2. Details",
                metadata=ElementMetadata(page_number=1, level=1, parent_id="body"),
                hierarchy_path=[]
            ),
            # Paragraph 2
            DocumentElement(
                id="#/texts/3", type="paragraph", text="This is paragraph two under the second heading.",
                metadata=ElementMetadata(page_number=1, parent_id="#/texts/2"),
                hierarchy_path=["#/texts/2"]
            ),
            # List items
            DocumentElement(
                id="#/texts/4", type="list_item", text="First point",
                metadata=ElementMetadata(page_number=1, parent_id="body"),
                hierarchy_path=[]
            ),
            DocumentElement(
                id="#/texts/5", type="list_item", text="Second point",
                metadata=ElementMetadata(page_number=1, parent_id="body"),
                hierarchy_path=[]
            ),
            # Standalone Table Element
            DocumentElement(
                id="#/tables/0", type="table", text="Markdown Table Representation",
                metadata=ElementMetadata(page_number=1, parent_id="body", caption_text="Table 1: Data Details"),
                hierarchy_path=[]
            ),
            # Standalone Image Element
            DocumentElement(
                id="#/pictures/0", type="image", text="Image Element",
                metadata=ElementMetadata(page_number=1, parent_id="body", caption_text="Figure 1: Diagram", ocr_text="TEXT IN IMAGE"),
                hierarchy_path=[]
            ),
        ],
        tables={
            "#/tables/0": TableStructure(
                table_id="#/tables/0", rows_count=2, cols_count=2,
                cells=[
                    TableCell(text="A1", row_index=0, col_index=0),
                    TableCell(text="B1", row_index=0, col_index=1),
                ],
                markdown="| A1 | B1 |",
                caption="Table 1: Data Details"
            )
        },
        images={
            "#/pictures/0": ImageMetadata(
                image_id="#/pictures/0", page_number=1,
                ocr_text="TEXT IN IMAGE",
                caption="Figure 1: Diagram"
            )
        }
    )

    builder = ChunkBuilder(target_tokens_max=100)
    chunks = builder.build_chunks(doc, "test_doc_id")
    
    assert len(chunks) > 0
    
    # Verify Heading + Paragraph is attached
    # Heading "1. Introduction" and "This is paragraph one..." should be grouped
    text_chunks = [c for c in chunks if c.metadata.chunk_type == "text"]
    assert len(text_chunks) >= 2
    
    chunk_1 = text_chunks[0]
    assert "1. Introduction" in chunk_1.content
    assert "This is paragraph one" in chunk_1.content
    assert chunk_1.metadata.heading == "1. Introduction"
    assert chunk_1.metadata.section == "1. Introduction"
    
    chunk_2 = text_chunks[1]
    assert "2. Details" in chunk_2.content
    assert "This is paragraph two" in chunk_2.content
    assert chunk_2.metadata.heading == "2. Details"
    
    # Verify Table Chunk is complete and not split
    table_chunks = [c for c in chunks if c.metadata.chunk_type == "table"]
    assert len(table_chunks) == 1
    assert "Table 1: Data Details" in table_chunks[0].content
    assert "| A1 | B1 |" in table_chunks[0].content
    assert table_chunks[0].metadata.page_number == 1
    
    # Verify Image Chunk keeps caption & OCR together
    image_chunks = [c for c in chunks if c.metadata.chunk_type == "image"]
    assert len(image_chunks) == 1
    assert "Figure 1: Diagram" in image_chunks[0].content
    assert "TEXT IN IMAGE" in image_chunks[0].content
    
    # Verify List chunk
    list_chunks = [c for c in chunks if c.metadata.chunk_type == "list"]
    assert len(list_chunks) == 1
    assert "First point" in list_chunks[0].content
    assert "Second point" in list_chunks[0].content

    # Verify metadata fields exist
    for chunk in chunks:
        meta = chunk.metadata
        assert meta.chunk_id is not None
        assert meta.document_id == "test_doc_id"
        assert meta.page_number == 1
        assert meta.chunk_type in ("text", "list", "table", "image")
        assert meta.word_count > 0
        assert meta.token_estimate > 0
        assert isinstance(meta.source_element_ids, list)
        assert len(meta.source_element_ids) > 0


def test_chunking_end_to_end_on_pdf():
    # Run the MultimodalExtractor on nsmail.pdf with output_dir provided
    # which will trigger ChunkBuilder and save document_chunks.json
    pdf_path = Path("C:/Users/sanju/INTERNSHIP-APT/DocumentProofreadingSystem/data/input/nsmail.pdf")
    if not pdf_path.exists():
        return
        
    temp_output_dir = Path("C:/Users/sanju/INTERNSHIP-APT/DocumentProofreadingSystem/data/output/temp_chunk_test")
    temp_output_dir.mkdir(parents=True, exist_ok=True)
    
    extractor = MultimodalExtractor(
        enable_ocr=False,
        enable_table_extraction=True,
        enable_image_extraction=True
    )
    
    # Extract will save both structured_document.json and document_chunks.json
    raw_text, structured_doc, page_count = extractor.extract(pdf_path, temp_output_dir)
    
    chunks_json_path = temp_output_dir / "document_chunks.json"
    assert chunks_json_path.exists()
    
    with open(chunks_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    assert "document_id" in data
    assert "file_name" in data
    assert "chunks" in data
    assert len(data["chunks"]) > 0
    
    # Verify structure of saved chunks
    for chunk in data["chunks"]:
        assert "content" in chunk
        assert "metadata" in chunk
        meta = chunk["metadata"]
        assert "chunk_id" in meta
        assert "document_id" in meta
        assert "page_number" in meta
        assert "chunk_type" in meta
        assert "heading" in meta
        assert "section" in meta
        assert "hierarchy_path" in meta
        assert "source_element_ids" in meta
        assert "word_count" in meta
        assert "token_estimate" in meta
        assert "bounding_boxes" in meta

    # Clean up
    try:
        import shutil
        shutil.rmtree(temp_output_dir)
    except Exception:
        pass
