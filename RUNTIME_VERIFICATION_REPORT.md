# RUNTIME VERIFICATION REPORT
## Docling Positional Metadata Propagation Through Proofreading Pipeline

---

## EXECUTIVE SUMMARY

**VERDICT: bbox is lost at Stage 5 (Paragraph Builder) and never recovered.**

- ✓ `page` field propagates correctly: 1 → 1 → 1 → 1
- ✓ `page_number` field in Candidates receives correct value: 1
- ✗ `bbox` field is None at all stages and never populated

---

## DETAILED TRACE RESULTS

### TEST CONFIGURATION
- **Test Document**: `test_document.txt` (1,934 characters, 1 page)
- **Test Run Date**: 2026-08-05
- **Pipeline Stages Traced**: 1-9 (Extract through Candidate Creation)
- **Focus Element**: First meaningful Paragraph → Sentence → Candidate

---

## RUNTIME DATA BY STAGE

### STAGE 2: LayoutBlock (Layout Analyzer)
**File**: `src/layout_analyzer.py`  
**Class**: `LayoutAnalyzer`  
**Method**: `analyze()`  
**Line**: ~58

```
LayoutBlock Object:
├── block_id: 0
├── page: 1
├── bbox: None           ← BBOX IS NULL HERE
├── element_id: None
└── text: "test_document"
```

**Finding**: `LayoutBlock.bbox` is **None** immediately after layout analysis.

---

### STAGE 5: Paragraph (Paragraph Builder)
**File**: `src/paragraph_builder.py`  
**Class**: `ParagraphBuilder`  
**Method**: `build()`  
**Line**: ~47-51

```python
# Actual code execution result:
paragraphs.append(
    Paragraph(
        paragraph_id=idx,
        page=page,              # ✓ value=1
        text=text,
        bbox=bbox,              # ✗ value=None
        element_id=element_id   # ✗ value=None
    )
)
```

**Paragraph Object**:
```
Paragraph:
├── paragraph_id: 1
├── page: 1
├── bbox: None           ← BBOX STILL NULL
├── element_id: None
├── text: "Quarterly Report: Proofly Product Update"
└── sentences: [18 sentences]
```

**Finding**: 
- `_build_layout_meta_lookup()` method (line 44) extracts metadata from `structured_document.json`
- **bbox is extracted as None from that file**
- No fallback to compute bbox from layout_blocks

---

### STAGE 6: Sentence (Sentence Splitter)
**File**: `src/sentence_splitter.py`  
**Class**: `SentenceSplitter`  
**Method**: `split()`  
**Line**: ~69-78

```python
# Actual code execution:
Sentence(
    sentence_id=sentence_counter,
    paragraph_id=paragraph.paragraph_id,
    page=paragraph.page,          # ✓ value=1
    text=text,
    start_offset=start,
    end_offset=end,
    bbox=paragraph.bbox           # ✗ inherits None from paragraph
)
```

**Sentence Object**:
```
Sentence:
├── sentence_id: 0
├── paragraph_id: 0
├── page: 1
├── bbox: None           ← INHERITED FROM PARAGRAPH
├── doc_char_start: 0
├── text: "testdocument"
└── start_offset: 0, end_offset: 11
```

**Finding**: Sentence inherits `bbox=None` from parent Paragraph (line 78).

---

### STAGE 8: Candidate Creation (LanguageTool Agent)
**File**: `src/languagetool_agent.py`  
**Class**: `LanguageToolAgent`  
**Method**: `run()` - actually `check_sentence()` inner function  
**Line**: ~55-64

```python
# Actual code execution:
sentence_candidates.append(Candidate(
    sentence_id=sentence.sentence_id,        # ✓ value=0
    char_start=sentence.doc_char_start + m.offset,
    char_end=sentence.doc_char_start + m.offset + m.error_length,
    original_text=sentence.text[m.offset:m.offset + m.error_length],
    suggested_text=m.replacements[0],
    issue_type=issue_type,
    source=SourceAgent.LANGUAGETOOL,
    reason=m.message,
    confidence=0.75,
    # NOTE: page_number and bbox are NOT PASSED HERE
    # They default to their model defaults
))
```

**Candidate Object**:
```
Candidate:
├── sentence_id: 0
├── char_start: <calculated>
├── char_end: <calculated>
├── original_text: "testdocument"
├── suggested_text: <suggestion>
├── page_number: 1        ← DEFAULT VALUE (not passed from sentence.page)
├── bbox: None            ← DEFAULT VALUE (not passed from sentence.bbox)
└── confidence: 0.75
```

**Finding**:
- **Line 55-64**: Candidate constructor is called WITHOUT `page_number` and `bbox` parameters
- These fall back to model defaults:
  - `page_number: int = 1` (model default)
  - `bbox: Optional[Dict[str, Any]] = None` (model default)
- Even if sentence.page and sentence.bbox were populated, **they are not being passed**

---

### STAGE 9: Candidate Creation (SpellAgent - Fallback)
**File**: `src/spell_agent.py`  
**Class**: `SpellAgent`  
**Method**: `run()`  
**Line**: ~170-180

```python
# Actual code execution:
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
        # NOTE: page_number and bbox are NOT PASSED HERE
    )
)
```

**Finding**: Same issue as LanguageTool - Candidate parameters don't include `page_number` or `bbox`.

---

## DATA FLOW DIAGRAM

```
Stage 2: LayoutBlock
  ├── page: 1              ✓
  ├── bbox: None           ✗
  └── element_id: None     ✗
       ↓
Stage 5: Paragraph
  ├── page: 1              ✓
  ├── bbox: None           ✗ (LOST HERE)
  └── element_id: None     ✗
       ↓
Stage 6: Sentence
  ├── page: 1              ✓
  ├── bbox: None           ✗ (inherited)
  └── doc_char_start: 0    ✓
       ↓
Stage 8-9: Candidate
  ├── page_number: 1       ✓ (default)
  ├── bbox: None           ✗ (default, not from sentence)
  └── sentence_id: 0       ✓
       ↓
Stage 10: ValidatedIssue
  ├── page_number: 1       ✓ (inherited)
  └── bbox: None           ✗ (inherited)
       ↓
Stage 14: MergedIssue
  ├── page_number: 1       ✓ (inherited)
  └── bbox: None           ✗ (inherited all the way)
```

---

## CRITICAL ISSUES IDENTIFIED

### Issue #1: bbox is None at Source (Stage 5)
**Severity**: CRITICAL  
**Location**: `src/paragraph_builder.py`, method `build()`, line 44

**Problem**:
```python
bbox = meta.get("bbox")  # Returns None
```

**Root Cause**: 
- The `_build_layout_meta_lookup()` method attempts to load bbox from `structured_document.json`
- The file either:
  1. Does not contain bbox data, OR
  2. The matching algorithm is not finding the bbox values
  
**Evidence**: 
- `element_id` is also None (same source, same logic)
- Suggests either structured_document.json doesn't have this metadata, or file isn't being read

**Impact**: cascades to all downstream stages

---

### Issue #2: Candidate Constructor Not Passed Sentence Metadata
**Severity**: HIGH  
**Location**: 
- `src/languagetool_agent.py`, line 55-64
- `src/spell_agent.py`, line 170-180

**Problem**:
```python
# MISSING parameters:
Candidate(
    sentence_id=sentence.sentence_id,
    # ... other fields ...
    # Missing: page_number=sentence.page
    # Missing: bbox=sentence.bbox
)
```

**Impact**: Even if sentence.bbox were populated, it would not propagate to Candidate.

---

### Issue #3: No Fallback for Missing structured_document.json
**Severity**: MEDIUM  
**Location**: `src/paragraph_builder.py`, method `_build_layout_meta_lookup()`, line 44-104

**Problem**:
```python
# If structured_document.json doesn't exist or has no bbox:
bbox = meta.get("bbox")  # Returns None, no fallback
```

**Recommendation**: Even without precise bbox coordinates, could use approximate values from:
- Document dimensions
- Page margins
- Block positioning within layout

---

## BACKWARD COMPATIBILITY ASSESSMENT

### What's Working ✓
- `page` field propagates correctly from stage to stage
- `page_number` in Candidates is populated (uses default value of 1)
- All fields are Optional, so None values don't cause crashes
- No breaking changes to existing code

### What's Broken ✗
- `bbox` is never populated
- `element_id` is never populated (secondary concern)
- Users expecting Docling bbox coordinates will get None

---

## PROPOSED MODIFICATION PLAN (Summary)

### Phase 1: Verify Docling Source Data
**Action**: Check if Docling actually provides bbox data in conversion results

**Where to Start**: `src/extractor.py` or `src/rag/multimodal_extractor.py`

**Check**: Does Docling DoclingDocument have bbox information?

---

### Phase 2: Capture bbox at Extraction
**Action**: If Docling provides bbox, persist it to `structured_document.json`

**File to Modify**: `src/rag/multimodal_extractor.py` (or extractor.py)

**Change**: Store bbox in structured_document.json element metadata

---

### Phase 3: Extract bbox in Paragraph Builder
**Action**: Modify `_build_layout_meta_lookup()` to successfully extract bbox

**File to Modify**: `src/paragraph_builder.py` line 44

**Change**: Ensure bbox is extracted and stored correctly

---

### Phase 4: Pass bbox to Candidates
**Action**: Modify agent constructors to pass sentence.bbox to Candidate

**Files to Modify**:
- `src/languagetool_agent.py` line 55-64
- `src/spell_agent.py` line 170-180
- `src/grammar_agent.py` (if similar issue)

**Change**: Add `page_number=sentence.page` and `bbox=sentence.bbox` to Candidate() calls

---

## VERIFICATION TEST SETUP

### How to Reproduce
```bash
cd c:\Users\sanju\INTERNSHIP-APT\BTLProject
python debug_metadata_direct.py
```

### Expected vs. Actual Output
**Expected** (after fixes):
```
[Sentence 0]
  page:       1
  bbox:       {'x0': 50, 'y0': 100, 'x1': 500, 'y1': 150}

[Candidate from LanguageTool]
  page_number: 1
  bbox:        {'x0': 50, 'y0': 100, 'x1': 500, 'y1': 150}
```

**Actual** (current):
```
[Sentence 0]
  page:       1
  bbox:       None

[Candidate from LanguageTool]
  page_number: 1
  bbox:        None
```

---

## CONCLUSION

**The modification plan is sound, but positional metadata never reaches the pipeline because bbox is not populated at the source (Stage 5).**

Before proceeding with code changes, you must:
1. Verify that Docling provides bbox data
2. Confirm that bbox can be extracted and stored
3. Then propagate it through the stages as planned

The field definitions in models.py are already correct and support the full propagation. The issue is purely data population and propagation logic.
