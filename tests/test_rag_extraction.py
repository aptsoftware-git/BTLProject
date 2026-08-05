import json
from pathlib import Path
from src.rag.multimodal_extractor import MultimodalExtractor
from src.rag.document_schema import StructuredDocument

from src.config import ROOT_DIR

def test_rag_extraction_on_txt():
    # Test on a simple text file
    txt_path = ROOT_DIR / "data" / "input" / "test_document.txt"
    if not txt_path.exists():
        # Create a dummy file if not exists
        txt_path.parent.mkdir(parents=True, exist_ok=True)
        txt_path.write_text("Heading 1\n\nThis is paragraph one.\n\nThis is paragraph two.", encoding="utf-8")

    extractor = MultimodalExtractor(
        enable_ocr=False,
        enable_table_extraction=True,
        enable_image_extraction=True
    )
    
    raw_text, structured_doc, page_count = extractor.extract(txt_path)
    
    assert isinstance(structured_doc, StructuredDocument)
    assert page_count >= 1
    assert len(structured_doc.elements) >= 2
    
    # Check elements
    types = [el.type for el in structured_doc.elements]
    assert "heading" in types or "paragraph" in types
    
    for el in structured_doc.elements:
        assert el.id is not None
        assert el.type is not None
        assert el.text is not None
        assert el.metadata.page_number >= 1

def test_rag_extraction_on_pdf():
    # Test on a PDF file
    pdf_path = ROOT_DIR / "data" / "input" / "nsmail.pdf"
    if not pdf_path.exists():
        return # Skip if file not found in test environment
        
    extractor = MultimodalExtractor(
        enable_ocr=False,
        enable_table_extraction=True,
        enable_image_extraction=True
    )
    
    # Extract
    raw_text, structured_doc, page_count = extractor.extract(pdf_path)
    
    assert isinstance(structured_doc, StructuredDocument)
    assert page_count >= 1
    assert len(structured_doc.elements) > 0
    
    # Verify some elements have hierarchy path, parents, and page number
    for el in structured_doc.elements:
        assert el.id is not None
        assert el.metadata.page_number >= 1
        assert el.metadata.parent_id is not None
        assert isinstance(el.hierarchy_path, list)

def test_rag_extraction_on_pdf_attention():
    # Test on attention_is_all_you_need.pdf which contains tables and images
    pdf_path = ROOT_DIR / "data" / "input" / "attention_is_all_you_need.pdf"
    if not pdf_path.exists():
        return # Skip if file not found in test environment
        
    extractor = MultimodalExtractor(
        enable_ocr=False,
        enable_table_extraction=True,
        enable_image_extraction=True
    )
    
    # Run extractor and save structured_document.json to a temp dir
    temp_output_dir = ROOT_DIR / "data" / "output" / "temp_rag_test"
    temp_output_dir.mkdir(parents=True, exist_ok=True)
    
    raw_text, structured_doc, page_count = extractor.extract(pdf_path, temp_output_dir)
    
    # Check that structured_document.json was saved
    json_path = temp_output_dir / "structured_document.json"
    assert json_path.exists()
    
    # Load and verify JSON contents
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    assert "title" in data
    assert "elements" in data
    assert "tables" in data
    assert "images" in data
    
    # Check for elements containing expected metadata
    elements = data["elements"]
    assert len(elements) > 0
    
    element_types = [el["type"] for el in elements]
    assert "heading" in element_types
    assert "paragraph" in element_types
    
    # Check tables detailed structure
    assert len(data["tables"]) > 0
    for table_id, table in data["tables"].items():
        assert "rows_count" in table
        assert "cols_count" in table
        assert "cells" in table
        assert len(table["cells"]) > 0
        cell = table["cells"][0]
        assert "text" in cell
        assert "row_index" in cell
        assert "col_index" in cell

    # Clean up temp dir
    try:
        import shutil
        shutil.rmtree(temp_output_dir)
    except Exception:
        pass
