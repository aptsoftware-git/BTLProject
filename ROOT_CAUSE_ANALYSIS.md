# ROOT CAUSE INVESTIGATION: bbox Loss in Proofreading Pipeline

## INVESTIGATION SUMMARY

**ROOT CAUSE IDENTIFIED**: bbox loss is **NOT a bug** but a **format limitation**.

- ✓ PDFs: bbox extracted correctly with actual coordinates
- ✗ TXT files: Docling provides no bbox (files have no positional data)
- ✓ ParagraphBuilder: correctly retrieves whatever Docling provides

---

## INVESTIGATION PROCESS

### Step 1: Examine structured_document.json

**Test Case 1: Plain Text File (test_document.txt)**
```json
{
  "file_type": "txt",
  "elements": [
    {
      "id": "b1_#/texts/0",
      "type": "paragraph",
      "text": "Quarterly Report: Proofly Product Update",
      "metadata": {
        "page_number": 1,
        "bbox": null,                    ← EXPLICITLY NULL
        "image_id": null,
        "table_id": null,
        "caption_id": null,
        "caption_text": null,
        "level": 1,
        "parent_id": "b1_#/body",
        "ocr_text": null
      },
      "hierarchy_path": []
    },
    ...
  ]
}
```

**Verification**: ALL 7 text elements in test_document.txt have `"bbox": null`

**Test Case 2: PDF File (LT_Company_Brochure.pdf)**
```json
{
  "file_type": "pdf",
  "elements": [
    {
      "id": "b1_#/texts/0",
      "type": "paragraph",
      "text": "...",
      "metadata": {
        "page_number": 1,
        "bbox": {
          "l": 261.89,                   ← ACTUAL COORDINATES
          "t": 626.38,
          "r": 350.27624,
          "b": 615.34,
          "coord_origin": "BOTTOMLEFT"
        },
        ...
      },
      "hierarchy_path": []
    },
    ...
  ]
}
```

**Verification**: PDFs have actual bbox with left, top, right, bottom coordinates.

---

## DATA FLOW: Where bbox Comes From

### Extraction Chain

```
1. Docling Conversion
   ├─ Input: PDF file
   ├─ Processing: Extracts text + positional info from each element
   └─ Output: DoclingDocument with element.prov[0].bbox = {"l": ..., "t": ..., "r": ..., "b": ...}
   
   OR
   
   ├─ Input: TXT file
   ├─ Processing: Parses text only (no positional data available)
   └─ Output: DoclingDocument with element.prov[0].bbox = None
       └─ NOTE: TXT format has NO positional information whatsoever

2. DocumentBuilder.build() [src/rag/document_builder.py]
   └─ Line 67-71:
   
      if hasattr(element, "prov") and element.prov:
          prov = element.prov[0]
          page_number = getattr(prov, "page_no", 1)
          bbox = convert_bbox(getattr(prov, "bbox", None))
          
      Passes: element.prov[0].bbox (which is None for TXT)
      To: convert_bbox()

3. convert_bbox() [src/rag/utils.py]
   └─ Line 6-10:
   
      if docling_bbox is None:
          return None
          
      ✓ Correctly handles None input
      ✓ Returns None for TXT files (where bbox is not available)
      ✓ Returns BoundingBox object for PDFs (where bbox is available)

4. StructuredDocument JSON [src/rag/document_builder.py]
   └─ Line 166-172:
   
      meta = ElementMetadata(
          page_number=page_number,
          bbox=bbox,                     ← Gets None from convert_bbox() for TXT files
          ...
      )
      
      Serialized to structured_document.json as:
      {
        "metadata": {
          "bbox": null                   ← Correctly stored as null
        }
      }

5. ParagraphBuilder [src/paragraph_builder.py]
   └─ Line 85:
   
      bbox = el_meta.get("bbox")         ← Retrieves None from JSON
      
      lookup[p_idx] = {
          "page": el_meta.get("page_number", 1),
          "bbox": el_meta.get("bbox"),   ← Sets to None
          "element_id": el.get("id")
      }

6. Paragraph Model [src/models.py]
   └─ Line 68:
   
      @dataclass
      class Paragraph:
          ...
          bbox: Optional[Dict[str, Any]] = None  ← None is valid value
      
      paragraph.bbox = None  ✓ Correct assignment

Result: bbox remains None throughout pipeline (as expected for TXT files)
```

---

## SOURCE DATA ANALYSIS

### Evidence: Docling Does NOT Provide bbox for Text Files

**Location**: `src/rag/document_builder.py`, line 67-71

```python
# Get page and bounding box
page_number = 1
bbox = None
if hasattr(element, "prov") and element.prov:
    prov = element.prov[0]
    page_number = getattr(prov, "page_no", 1)
    bbox = convert_bbox(getattr(prov, "bbox", None))  # ← Gets None for TXT
```

**For .txt files**:
- `element.prov[0].bbox` is None (text files have no positional metadata)
- `convert_bbox(None)` returns None (line 6-10 in utils.py)
- Metadata stored as `"bbox": null` in JSON (correct)

**For PDF files**:
- `element.prov[0].bbox` is a Docling bbox object with l, t, r, b attributes
- `convert_bbox(bbox_obj)` returns BoundingBox with coordinates
- Metadata stored as `"bbox": {"l": 261.89, "t": 626.38, ...}` in JSON (correct)

---

## CODE VERIFICATION: Extraction Logic

### ParagraphBuilder._build_layout_meta_lookup() [Line 60-104]

```python
def _build_layout_meta_lookup(self, document: Document, job_dir: Optional[Path] = None):
    """Maps paragraph index -> {page, bbox, element_id}"""
    lookup = {}
    
    # Primary path: structured_document.json
    if doc_json_path and doc_json_path.exists():
        with open(doc_json_path, "r", encoding="utf-8") as f:
            struct_doc = json.load(f)
        elements = struct_doc.get("elements", [])
        
        for p_idx, p_text in enumerate(raw_paragraphs):
            # Match element to paragraph
            el_meta = el.get("metadata", {})
            
            lookup[p_idx] = {
                "page": el_meta.get("page_number", 1),     # ✓ Returns 1 for TXT
                "bbox": el_meta.get("bbox"),               # ✗ Returns None for TXT
                "element_id": el.get("id")                 # ✓ Returns element ID
            }
            
    # Fallback path: layout_blocks
    for block in document.layout_blocks:
        lookup[idx] = {
            "page": block.page,
            "bbox": getattr(block, "bbox", None),         # ✗ Also None (never populated)
            "element_id": getattr(block, "element_id", None)
        }
```

**Finding**: The code is **working correctly**. It retrieves whatever Docling provides.

---

## EXPECTED vs ACTUAL METADATA STRUCTURE

### EXPECTED (Desired State)
```json
{
  "metadata": {
    "page_number": 1,
    "bbox": {
      "l": 50.0,
      "t": 100.0,
      "r": 500.0,
      "b": 150.0,
      "coord_origin": "BOTTOMLEFT"
    },
    "element_id": "b1_#/texts/0"
  }
}
```

### ACTUAL (Current for .txt files)
```json
{
  "metadata": {
    "page_number": 1,
    "bbox": null,              ← NULL because TXT has no positional data
    "element_id": "b1_#/texts/0"
  }
}
```

### ACTUAL (Current for PDFs)
```json
{
  "metadata": {
    "page_number": 1,
    "bbox": {
      "l": 261.89,
      "t": 626.38,
      "r": 350.27624,
      "b": 615.34,
      "coord_origin": "BOTTOMLEFT"
    },
    "element_id": "b1_#/texts/0"
  }
}
```

---

## ROOT CAUSE: Format Limitation, Not a Bug

### Why bbox is None for .txt Files

Plain text files (`.txt`) contain **only text content**. They have:
- ✓ Text (what is written)
- ✓ Encoding (UTF-8, ASCII, etc.)
- ✗ Layout information (no columns, no positioning)
- ✗ Page breaks (or implicit single page)
- ✗ Font/formatting (all text is uniform)
- ✗ **Bounding boxes (what we need for positional metadata)**

When Docling processes a `.txt` file:
1. It reads the text content
2. It creates logical elements (paragraphs, headings)
3. It attempts to extract position information from `element.prov[0].bbox`
4. **Result**: `element.prov[0].bbox = None` (position info doesn't exist in TXT format)

This is **correct behavior** - you cannot extract positional data from a format that doesn't contain it.

---

## CONFIRMATION: PDF vs TXT Behavior

### Command: Check bbox in different formats

```bash
python -c "
import json
print('=== TXT File (test_document.txt) ===')
f = open('data/output/test_document_20260805_135703/structured_document.json')
doc = json.load(f)
print('File type:', doc['file_type'])
print('First 3 elements bbox:', [doc['elements'][i]['metadata']['bbox'] for i in range(3)])

print('\n=== PDF File (LT_Company_Brochure.pdf) ===')
f = open('data/output/9b580a49750843d68ba1ae78c6a67538/structured_document.json')
doc = json.load(f)
print('File type:', doc['file_type'])
print('First 3 elements bbox:', [doc['elements'][i]['metadata']['bbox'] for i in range(3)])
"
```

**Output**:
```
=== TXT File (test_document.txt) ===
File type: txt
First 3 elements bbox: [None, None, None]

=== PDF File (LT_Company_Brochure.pdf) ===
File type: pdf
First 3 elements bbox: [
  {'l': 261.89, 't': 626.38, 'r': 350.27624, 'b': 615.34, 'coord_origin': 'BOTTOMLEFT'},
  {'l': 186.14, 't': 604.0, 'r': 425.80999999999983, 'b': 574.0, 'coord_origin': 'BOTTOMLEFT'},
  {'l': 199.25, 't': 568.06, 'r': 412.75399999999985, 'b': 556.06, 'coord_origin': 'BOTTOMLEFT'}
]
```

**Conclusion**: This is **expected and correct behavior**, not a bug.

---

## CODE PATH VERIFICATION

### Chain of Responsibility

```
Docling
└─ DoclingDocument
   └─ element.prov[0].bbox = None (for TXT) or BoundingBox (for PDF)
      │
      └─► DocumentBuilder.build()
          │  Line 71: bbox = convert_bbox(getattr(prov, "bbox", None))
          │
          └─► convert_bbox() in utils.py
              │  Line 6-10: if docling_bbox is None: return None
              │
              └─► StructuredDocument.metadata.bbox = None (for TXT)
                  │
                  └─► JSON serialization
                      │  "bbox": null
                      │
                      └─► ParagraphBuilder._build_layout_meta_lookup()
                          │  Line 85: bbox = el_meta.get("bbox")
                          │
                          └─► Paragraph.bbox = None (correct - format has no data)
```

Every step is working correctly. The None value is propagating as intended.

---

## REQUIRED FIX FOR FULL IMPLEMENTATION

Since bbox is a **format limitation** (not available in .txt), here are the options:

### Option 1: Accept Format Limitation (Recommended for TXT)
- ✓ Keep bbox=None for text files (current behavior)
- ✓ bbox will work correctly for PDFs
- ✓ No code changes needed
- ✗ Text-only documents will lack positional metadata

### Option 2: Compute Approximate bbox (Advanced)
- ✓ Works with text-only documents
- ✓ Provides approximate positioning
- ✗ Requires complex layout inference
- ✗ Would add ~50-100 lines of code
- **Example**: Use character counts and line numbers to estimate page position

### Option 3: Force bbox Population from Page Margins
- ✓ Every element gets some bbox
- ✗ All bbox values would be identical (full page)
- ✗ Not useful for highlighting/annotation

### Option 4: Accept bbox=None and Document in UI
- ✓ Simple to implement
- ✓ Clear to users which formats have positional support
- ✗ Text files won't have highlighting

---

## CANDIDATE PROPAGATION (Secondary Issue)

**Current Issue**: Candidate constructor NOT receiving page_number and bbox

**Location**: 
- `src/languagetool_agent.py`, line 55-64
- `src/spell_agent.py`, line 170-180

**Fix Required**: Pass sentence metadata to Candidate

```python
# Current (WRONG):
Candidate(
    sentence_id=sentence.sentence_id,
    char_start=...,
    char_end=...,
    original_text=...,
    suggested_text=...,
    issue_type=...,
    source=...,
    reason=...,
    confidence=...,
)

# Should be (FIXED):
Candidate(
    sentence_id=sentence.sentence_id,
    char_start=...,
    char_end=...,
    original_text=...,
    suggested_text=...,
    issue_type=...,
    source=...,
    reason=...,
    confidence=...,
    page_number=sentence.page,      # ADD THIS
    bbox=sentence.bbox               # ADD THIS
)
```

**Impact**: This is a separate issue from bbox source availability. Even when bbox is available (PDFs), it's not being passed to Candidates.

---

## SUMMARY OF FINDINGS

| Finding | Location | Status | Impact |
|---------|----------|--------|--------|
| Docling doesn't extract bbox from .txt files | `document_builder.py:71` | Normal behavior | TXT files have no positional data |
| convert_bbox() correctly handles None | `utils.py:6-10` | Working as designed | Returns None when bbox unavailable |
| structured_document.json stores null for TXT | JSON structure | Correct | Reflects source data |
| ParagraphBuilder retrieves None from JSON | `paragraph_builder.py:85` | Working correctly | Gets what was stored |
| Sentence.bbox inherited from Paragraph | `sentence_splitter.py:78` | Correct | Maintains consistency |
| Candidate NOT RECEIVING bbox from Sentence | `languagetool_agent.py:55-64` | **BUG** | bbox lost at agent creation |

---

## CONCLUSION

**bbox Loss Root Cause**: Two-part issue:

1. **Format Limitation** (Expected, Not a Bug)
   - Plain text files have no positional information
   - Docling correctly returns None for `.txt` files
   - This is not a bug in extraction logic

2. **Propagation Issue** (Real Bug, Needs Fixing)
   - Candidate constructor doesn't receive `page_number` and `bbox` from Sentence
   - Even when bbox is available (PDFs), it's not passed through the agent stage
   - This is a missing parameter issue that must be fixed

**Next Step**: Fix the Candidate constructor calls to pass Sentence metadata.
