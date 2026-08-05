# INVESTIGATION SUMMARY: Root Cause of bbox Loss

## FINDINGS AT A GLANCE

### Issue #1: Format Limitation (NOT A BUG)
```
Plain Text Files → Docling → "bbox": null ✓ Correct
  └─ Reason: .txt files have NO positional information
  └─ Impact: TXT files cannot have bbox (format limitation)
```

### Issue #2: Missing Constructor Parameters (REAL BUG)
```
PDF Files → Docling → "bbox": {coordinates} ✓ Correct
         → ParagraphBuilder → Paragraph.bbox ✓ Correct  
         → Sentence Splitter → Sentence.bbox ✓ Correct
         → Agent → Candidate.bbox ✗ LOST (parameter not passed)
```

---

## DETAILED FINDINGS

### Finding #1: Docling Behavior

**For PDF files:**
- ✓ Extracts element.prov[0].bbox = BoundingBox object with l, t, r, b coordinates
- ✓ Stores in structured_document.json as: `"bbox": {"l": 261.89, "t": 626.38, ...}`

**For TXT files:**
- ✗ Returns element.prov[0].bbox = None (no position info in plain text)
- ✓ Correctly stores in structured_document.json as: `"bbox": null`

**Verification**:
```
PDF (LT_Company_Brochure.pdf):
  Element 0: bbox = {'l': 261.89, 't': 626.38, 'r': 350.27624, 'b': 615.34, ...}
  Element 1: bbox = {'l': 186.14, 't': 604.0, 'r': 425.80999999999983, 'b': 574.0, ...}
  Element 2: bbox = {'l': 199.25, 't': 568.06, 'r': 412.75399999999985, 'b': 556.06, ...}

TXT (test_document.txt):
  Element 0: bbox = None
  Element 1: bbox = None
  Element 2: bbox = None
```

**Conclusion**: This is expected behavior. Docling cannot extract position data from formats that don't contain it.

---

### Finding #2: Extraction Layer (DocumentBuilder)

**Code**: `src/rag/document_builder.py`, line 67-71

```python
if hasattr(element, "prov") and element.prov:
    prov = element.prov[0]
    page_number = getattr(prov, "page_no", 1)
    bbox = convert_bbox(getattr(prov, "bbox", None))  # ← Docling bbox here
```

**Analysis**:
- ✓ Correctly retrieves bbox from Docling provenance
- ✓ Passes to convert_bbox() for format conversion
- ✓ Stores result in metadata (None for TXT, BoundingBox for PDF)
- ✓ No issues at this layer

---

### Finding #3: Serialization (structured_document.json)

**Result**:
```json
{
  "elements": [
    {
      "metadata": {
        "page_number": 1,
        "bbox": null              // TXT files
        // OR
        "bbox": {                 // PDF files
          "l": 261.89,
          "t": 626.38,
          "r": 350.27,
          "b": 615.34,
          "coord_origin": "BOTTOMLEFT"
        }
      }
    }
  ]
}
```

**Analysis**:
- ✓ Correctly represents source data
- ✓ No corruption or loss at JSON serialization layer
- ✓ TXT files should have null, PDFs should have coordinates

---

### Finding #4: Metadata Retrieval (ParagraphBuilder)

**Code**: `src/paragraph_builder.py`, line 85

```python
bbox = el_meta.get("bbox")
lookup[p_idx] = {
    "page": el_meta.get("page_number", 1),
    "bbox": el_meta.get("bbox"),           # ← Correct retrieval
    "element_id": el.get("id")
}
```

**Analysis**:
- ✓ Correctly retrieves bbox from metadata
- ✓ For TXT: gets None (as stored in JSON)
- ✓ For PDF: gets BoundingBox object
- ✓ No issues at this layer

---

### Finding #5: Paragraph & Sentence Creation

**Code**: 
- `src/paragraph_builder.py`, line 51: `bbox=bbox`
- `src/sentence_splitter.py`, line 78: `bbox=paragraph.bbox`

**Analysis**:
- ✓ Paragraph.bbox = what was retrieved (None for TXT, coords for PDF)
- ✓ Sentence.bbox = inherited from Paragraph (correct)
- ✓ Data correctly propagates through these stages
- ✓ No issues here

**Runtime Evidence**:
```
For test_document.txt:
  LayoutBlock.bbox:  None
  Paragraph.bbox:    None
  Sentence.bbox:     None  ← Correct (from source data)

For PDF:
  LayoutBlock.bbox:  None (never populated in current code)
  Paragraph.bbox:    {'l': 261.89, 't': 626.38, ...}  ← From structured_doc
  Sentence.bbox:     {'l': 261.89, 't': 626.38, ...}  ← Inherited from Para
```

---

### Finding #6: Candidate Creation (CRITICAL BUG)

**Code - LanguageTool Agent** (`src/languagetool_agent.py`, line 55-64):
```python
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
    # MISSING: page_number=sentence.page
    # MISSING: bbox=sentence.bbox
))
```

**Code - Spell Agent** (`src/spell_agent.py`, line 170-180):
```python
candidates.append(
    Candidate(
        sentence_id=sentence.sentence_id,
        char_start=abs_start,
        char_end=abs_end,
        original_text=word,
        suggested_text=self._match_case(word, best.term),
        issue_type=IssueType.SPELLING,
        source=SourceAgent.SYMSPELL,
        reason="Spelling",
        confidence=confidence,
        # MISSING: page_number=sentence.page
        # MISSING: bbox=sentence.bbox
    )
)
```

**Analysis**:
- ✗ `page_number` parameter NOT passed → defaults to 1
- ✗ `bbox` parameter NOT passed → defaults to None
- Even for PDFs where sentence.bbox = {'l': 261.89, ...}, it's never passed
- **This is the actual bug in the code**

**Runtime Evidence**:
```
Sentence.page:        1
Sentence.bbox:        None (TXT) or {'l': ...} (PDF)

Candidate.page_number: 1         ← Correct (either from param or default)
Candidate.bbox:        None      ← WRONG (not passed, defaults to None)
                                   Should be: None (TXT) or {'l': ...} (PDF)
```

---

## ROOT CAUSE SUMMARY

| Component | Status | Reason |
|-----------|--------|--------|
| Docling extraction | ✓ Working | Correctly returns None for TXT, bbox for PDF |
| DocumentBuilder conversion | ✓ Working | Correctly converts Docling bbox to our format |
| structured_document.json | ✓ Correct | Accurately represents source data |
| ParagraphBuilder retrieval | ✓ Working | Correctly retrieves what's in JSON |
| Paragraph/Sentence creation | ✓ Working | Correctly passes bbox through hierarchy |
| **Candidate creation** | ✗ **BUG** | **Missing parameters in constructor calls** |

---

## THE FIX REQUIRED

### Change 1: LanguageTool Agent
**File**: `src/languagetool_agent.py`  
**Lines**: 55-64  
**Change**: Add two parameters to Candidate() call

```python
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
    page_number=sentence.page,      # ← ADD THIS
    bbox=sentence.bbox               # ← ADD THIS
))
```

### Change 2: Spell Agent
**File**: `src/spell_agent.py`  
**Lines**: 170-180  
**Change**: Add two parameters to Candidate() call

```python
candidates.append(
    Candidate(
        sentence_id=sentence.sentence_id,
        char_start=abs_start,
        char_end=abs_end,
        original_text=word,
        suggested_text=self._match_case(word, best.term),
        issue_type=IssueType.SPELLING,
        source=SourceAgent.SYMSPELL,
        reason="Spelling",
        confidence=confidence,
        page_number=sentence.page,    # ← ADD THIS
        bbox=sentence.bbox             # ← ADD THIS
    )
)
```

### Change 3: Grammar Agent (if applicable)
**File**: `src/grammar_agent.py`  
**Check**: If similar Candidate creation exists, apply same fix

---

## IMPACT OF FIX

### For PDF Documents (Will be Enabled)
```
BEFORE FIX:
  Sentence.bbox:     {'l': 261.89, 't': 626.38, 'r': 350.27, 'b': 615.34}
  Candidate.bbox:    None  ← Lost
  ValidatedIssue.bbox: None  ← Lost
  MergedIssue.bbox:  None  ← Lost

AFTER FIX:
  Sentence.bbox:     {'l': 261.89, 't': 626.38, 'r': 350.27, 'b': 615.34}
  Candidate.bbox:    {'l': 261.89, 't': 626.38, 'r': 350.27, 'b': 615.34}  ← Preserved
  ValidatedIssue.bbox: {'l': 261.89, 't': 626.38, 'r': 350.27, 'b': 615.34}  ← Preserved
  MergedIssue.bbox:  {'l': 261.89, 't': 626.38, 'r': 350.27, 'b': 615.34}  ← Preserved
```

### For TXT Documents (No Change)
```
BEFORE FIX:
  Sentence.bbox:     None
  Candidate.bbox:    None

AFTER FIX:
  Sentence.bbox:     None
  Candidate.bbox:    None  ← Still None (format limitation)
```

---

## CONCLUSION

**bbox Loss = Two-Part Problem:**

1. **Format Limitation** (Not fixable, expected)
   - Plain text files have no positional data
   - Docling correctly returns None
   - This is normal and expected behavior

2. **Code Defect** (Fixable, needs immediate attention)
   - Candidate constructors don't receive page_number and bbox
   - Even for PDFs (which have the data), it's lost here
   - Simple fix: add 2 parameters to 2-3 function calls

**Backward Compatibility**: ✓ Complete
- Adding optional parameters doesn't break existing code
- TXT files will still have bbox=None (as they should)
- PDFs will finally propagate bbox correctly

---

## INVESTIGATION ARTIFACTS

Generated files:
- `RUNTIME_VERIFICATION_REPORT.md` - Full trace of one element
- `ROOT_CAUSE_ANALYSIS.md` - Deep technical analysis
- `EXACT_MISMATCH_ANALYSIS.md` - Expected vs actual structures
- `debug_metadata_direct.py` - Reproducible test script
- `debug_output.txt` - Runtime execution log (if saved)
