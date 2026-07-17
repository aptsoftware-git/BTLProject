from typing import Any, Optional
from src.rag.document_schema import TableStructure, TableCell
from src.rag.utils import convert_bbox
from src.rag.caption_processor import CaptionProcessor

class TableProcessor:
    """
    Processes Docling TableItem elements and parses them into TableStructure objects.
    """

    @staticmethod
    def process_table(element: Any, doc: Any) -> TableStructure:
        """
        Extracts structural, semantic, and layout details of a table.
        """
        table_id = element.self_ref
        
        # Extract markdown and HTML representations
        markdown_str = None
        html_str = None
        try:
            if hasattr(element, "export_to_markdown"):
                markdown_str = element.export_to_markdown(doc)
        except Exception:
            pass
            
        try:
            if hasattr(element, "export_to_html"):
                html_str = element.export_to_html(doc)
        except Exception:
            pass

        # Extract caption text
        caption_text = CaptionProcessor.extract_caption_text(element, doc)

        # Initialize cells list and counts
        cells = []
        rows_count = 0
        cols_count = 0

        # Retrieve table cell details
        if hasattr(element, "data") and element.data:
            table_data = element.data
            
            # Count rows and columns
            # In docling 2.x, table_data has attributes: table_cells, grid, etc.
            # We can find max indices to calculate rows_count and cols_count
            max_row_idx = -1
            max_col_idx = -1
            
            cells_list = getattr(table_data, "table_cells", []) or []
            for cell in cells_list:
                row_idx = getattr(cell, "start_row_offset_idx", 0)
                col_idx = getattr(cell, "start_col_offset_idx", 0)
                row_span = getattr(cell, "row_span", 1)
                col_span = getattr(cell, "col_span", 1)
                
                max_row_idx = max(max_row_idx, row_idx + row_span - 1)
                max_col_idx = max(max_col_idx, col_idx + col_span - 1)
                
                is_header = bool(getattr(cell, "col_header", False) or getattr(cell, "row_header", False))
                bbox = convert_bbox(getattr(cell, "bbox", None))
                
                cells.append(TableCell(
                    text=getattr(cell, "text", "") or "",
                    row_index=row_idx,
                    col_index=col_idx,
                    row_span=row_span,
                    col_span=col_span,
                    is_header=is_header,
                    bbox=bbox
                ))
                
            rows_count = max_row_idx + 1
            cols_count = max_col_idx + 1

        return TableStructure(
            table_id=table_id,
            rows_count=rows_count,
            cols_count=cols_count,
            cells=cells,
            markdown=markdown_str,
            html=html_str,
            caption=caption_text
        )
