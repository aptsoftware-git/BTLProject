# EXACT MISMATCH: Expected vs Actual Metadata

## The Problem in One Picture

### EXPECTED METADATA STRUCTURE (What we want for PDFs)
```
PDF File → Docling → structured_document.json
  ↓
  {
    "elements": [
      {
        "id": "b1_#/texts/0",
        "metadata": {
          "page_number": 1,
          "bbox": {
            "l": 261.89,
            "t": 626.38,
            "r": 350.27,
            "b": 615.34,
            "coord_origin": "BOTTOMLEFT"
          },
          "element_id": "b1_#/texts/0"
        }
      }
    ]
  }
  ↓
  ParagraphBuilder._build_layout_meta_lookup()
    bbox = el_meta.get("bbox")
    → bbox = {"l": 261.89, "t": 626.38, ...}  ✓ POPULATED
  ↓
  Paragraph.bbox = {"l": 261.89, ...}  ✓ POPULATED
  ↓
  Sentence.bbox = {"l": 261.89, ...}  ✓ POPULATED
  ↓
  Candidate.bbox = {"l": 261.89, ...}  ✓ POPULATED (IF PASSED)
```

### ACTUAL METADATA STRUCTURE (What happens with .txt files)
```
TXT File → Docling → structured_document.json
  ↓
  {
    "elements": [
      {
        "id": "b1_#/texts/0",
        "metadata": {
          "page_number": 1,
          "bbox": null,                    ← REASON: .txt has no positional data
          "element_id": "b1_#/texts/0"
        }
      }
    ]
  }
  ↓
  ParagraphBuilder._build_layout_meta_lookup()
    bbox = el_meta.get("bbox")
    → bbox = None  ✗ NOT AVAILABLE
  ↓
  Paragraph.bbox = None  ✗ NOT AVAILABLE
  ↓
  Sentence.bbox = None  ✗ NOT AVAILABLE (inherited from Paragraph)
  ↓
  Candidate.bbox = None  ✗ NOT AVAILABLE (not passed anyway)
```

---

## The TWO Root Causes

### ROOT CAUSE #1: Format Limitation (Not a Bug)
**Where**: Docling → DocumentBuilder.build() → convert_bbox()  
**Why**: Plain text files have NO positional information  
**Code**: `src/rag/document_builder.py` line 67-71

```python
if hasattr(element, "prov") and element.prov:
    prov = element.prov[0]
    bbox = convert_bbox(getattr(prov, "bbox", None))  # ← Gets None for .txt
```

**For .txt files**:
- `element.prov[0].bbox = None` (Docling found no position info in text file)
- `convert_bbox(None)` → returns None (correct handling)
- `structured_document.json` stores `"bbox": null` (correct)

**For PDF files**:
- `element.prov[0].bbox = BoundingBox(l=..., t=..., r=..., b=...)`
- `convert_bbox(bbox)` → returns BoundingBox object
- `structured_document.json` stores `"bbox": {"l": 261.89, ...}` (correct)

**Conclusion**: This is NOT a bug - it's the correct behavior for a format that lacks positional data.

---

### ROOT CAUSE #2: Candidate Constructor Missing Parameters (Actual Bug)
**Where**: Agent creation stages  
**Why**: Developers didn't pass page_number and bbox to Candidate()  
**Code**: 
- `src/languagetool_agent.py` line 55-64
- `src/spell_agent.py` line 170-180

```python
# WRONG - bbox parameter missing:
Candidate(
    sentence_id=sentence.sentence_id,
    char_start=sentence.doc_char_start + m.offset,
    char_end=sentence.doc_char_start + m.offset + m.error_length,
    original_text=sentence.text[...],
    suggested_text=m.replacements[0],
    issue_type=issue_type,
    source=SourceAgent.LANGUAGETOOL,
    reason=m.message,
    confidence=0.75,
    # page_number and bbox NOT PASSED
)
```

**Impact**: Even if sentence.bbox were available (PDFs), it wouldn't be passed to Candidate. The parameter is simply missing from the constructor call.

---

## Why bbox Becomes None - Step By Step

### For .txt Files (Test Document)
```
Stage 1: DocumentBuilder.build()
  ├─ Input: Docling DoclingDocument (from .txt file)
  ├─ Process: element.prov[0].bbox = None (text files have no position info)
  ├─ Function: convert_bbox(None)
  │   └─ Line 6: if docling_bbox is None: return None
  │   └─ OUTPUT: None
  ├─ Store: metadata.bbox = None
  └─ Serialize: structured_document.json → "bbox": null

Stage 2: ParagraphBuilder._build_layout_meta_lookup()
  ├─ Read: structured_document.json
  ├─ Extract: el_meta.get("bbox")
  ├─ Value: None (from JSON)
  ├─ Store: lookup[p_idx]["bbox"] = None
  └─ Result: Paragraph created with bbox=None

Stage 3: Sentence Splitter
  ├─ Read: Paragraph.bbox = None
  ├─ Assign: Sentence(bbox=paragraph.bbox)
  └─ Result: Sentence created with bbox=None

Stage 4: Agent (LanguageTool/Spell)
  ├─ Read: Sentence.bbox = None
  ├─ Pass: NOT PASSED TO CANDIDATE (missing parameter)
  ├─ Create: Candidate(sentence_id=..., page_number=1, bbox=None)
  │          ↑ bbox=None (default, not from sentence)
  └─ Result: Candidate created with bbox=None
```

### For PDF Files (LT_Company_Brochure.pdf)
```
Stage 1: DocumentBuilder.build()
  ├─ Input: Docling DoclingDocument (from PDF)
  ├─ Process: element.prov[0].bbox = BoundingBox(l=261.89, t=626.38, ...)
  ├─ Function: convert_bbox(bbox_obj)
  │   └─ Line 23-28: Create BoundingBox from docling_bbox attributes
  │   └─ OUTPUT: BoundingBox(l=261.89, t=626.38, r=350.27, b=615.34, ...)
  ├─ Store: metadata.bbox = BoundingBox(...)
  └─ Serialize: structured_document.json → "bbox": {"l": 261.89, "t": 626.38, ...}

Stage 2: ParagraphBuilder._build_layout_meta_lookup()
  ├─ Read: structured_document.json
  ├─ Extract: el_meta.get("bbox")
  ├─ Value: {"l": 261.89, "t": 626.38, ...} (from JSON)
  ├─ Store: lookup[p_idx]["bbox"] = {...}
  └─ Result: Paragraph created with bbox={...}

Stage 3: Sentence Splitter
  ├─ Read: Paragraph.bbox = {...}
  ├─ Assign: Sentence(bbox=paragraph.bbox)
  └─ Result: Sentence created with bbox={...}

Stage 4: Agent (LanguageTool/Spell)
  ├─ Read: Sentence.bbox = {...}
  ├─ Pass: NOT PASSED TO CANDIDATE (missing parameter)
  ├─ Create: Candidate(sentence_id=..., page_number=1, bbox=None)
  │          ↑ bbox=None (default, not from sentence)
  └─ Result: Candidate created with bbox=None (LOST!)
```

---

## The Critical Difference

### PDF Scenario (Should Succeed, Currently Fails)
```
PDF bbox flow:
  Docling  ✓
    ↓
  DocumentBuilder  ✓ (bbox extracted correctly)
    ↓
  structured_document.json  ✓ (bbox stored as coordinates)
    ↓
  ParagraphBuilder  ✓ (bbox retrieved from JSON)
    ↓
  Paragraph  ✓ (bbox stored)
    ↓
  Sentence  ✓ (bbox inherited)
    ↓
  Agent  ✗ BROKEN HERE (bbox not passed to Candidate constructor)
    ↓
  Candidate  ✗ (bbox=None because parameter missing)
```

### TXT Scenario (Cannot Succeed - Format Limitation)
```
TXT bbox flow:
  Docling  ✗ (no positional data in .txt format)
    ↓
  DocumentBuilder  ✓ (correctly returns None for unavailable data)
    ↓
  structured_document.json  ✓ (correctly stores "bbox": null)
    ↓
  ParagraphBuilder  ✓ (correctly retrieves None from JSON)
    ↓
  Paragraph  ✓ (correctly stores None)
    ↓
  Sentence  ✓ (correctly inherits None)
    ↓
  Agent  ✗ BROKEN HERE (bbox=None because format has no data)
    ↓
  Candidate  ✗ (bbox=None - unavoidable for .txt files)
```

---

## The Fix Required

### FIX #1: Pass Parameters to Candidate (Required for PDFs)

**File**: `src/languagetool_agent.py`, line 55-64

```python
# BEFORE:
sentence_candidates.append(Candidate(
    sentence_id=sentence.sentence_id,
    char_start=sentence.doc_char_start + m.offset,
    char_end=sentence.doc_char_start + m.offset + m.error_length,
    original_text=sentence.text[m.offset:m.offset + m.error_length],
    suggested_text=m.replacements[0],
    issue_type=issue_type,
    source=SourceAgent.LANGUAGETOOL,
    reason=m.message,
    confidence=0.75,
))

# AFTER:
sentence_candidates.append(Candidate(
    sentence_id=sentence.sentence_id,
    char_start=sentence.doc_char_start + m.offset,
    char_end=sentence.doc_char_start + m.offset + m.error_length,
    original_text=sentence.text[m.offset:m.offset + m.error_length],
    suggested_text=m.replacements[0],
    issue_type=issue_type,
    source=SourceAgent.LANGUAGETOOL,
    reason=m.message,
    confidence=0.75,
    page_number=sentence.page,           # ADD THIS
    bbox=sentence.bbox                    # ADD THIS
))
```

Same fix needed for: `src/spell_agent.py` line 170-180

### FIX #2: Accept TXT Format Limitation (Status Quo)

For `.txt` files: Accept that bbox=None (expected behavior)

---

## Summary Table

| Aspect | .txt Files | PDF Files |
|--------|-----------|-----------|
| Docling provides bbox? | ✗ No (format has no positional data) | ✓ Yes (coordinates extracted) |
| Extraction logic correct? | ✓ Yes (returns None correctly) | ✓ Yes (returns coordinates correctly) |
| structured_document.json correct? | ✓ Yes (stores null) | ✓ Yes (stores coordinates) |
| ParagraphBuilder correct? | ✓ Yes (retrieves null) | ✓ Yes (retrieves coordinates) |
| Sentence.bbox correct? | ✓ Yes (inherits null) | ✓ Yes (inherits coordinates) |
| Candidate.bbox correct? | ✗ No (missing parameter) | ✗ No (missing parameter) |
| Can be fixed? | ✗ No (format limitation) | ✓ Yes (pass parameter to Candidate) |

---

## Files Involved in Root Cause

### Source Data Generation
- **`src/rag/document_builder.py`** (line 67-71): Extracts bbox from Docling
- **`src/rag/utils.py`** (line 4-28): Converts Docling bbox to our format

### Metadata Propagation
- **`src/paragraph_builder.py`** (line 85): Retrieves bbox from JSON
- **`src/sentence_splitter.py`** (line 78): Inherits bbox from Paragraph

### Lost Parameters
- **`src/languagetool_agent.py`** (line 55-64): MISSING bbox parameter
- **`src/spell_agent.py`** (line 170-180): MISSING bbox parameter
