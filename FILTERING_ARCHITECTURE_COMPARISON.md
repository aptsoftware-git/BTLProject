# FILTERING ARCHITECTURE REVIEW: Comparison & Minimal Extension Strategy

## Executive Summary

The codebase contains **TWO DISTINCT FILTERING SYSTEMS** for different domains:

1. **RAG FindingRelevanceFilter** (`src/rag/finding_filter.py`) - Filters document inconsistencies (numerical conflicts, policy violations, missing references)
2. **Main Pipeline** (`src/pipeline.py`) - Currently has only confidence filtering (≤0.50), lacks business relevance filtering

**Recommendation**: DO NOT reuse RAG filter directly. Instead, create a lightweight **ProofreadingFilterer** class with SAME design patterns (method-based filtering + transparency reporting) but tailored for proofreading findings.

---

## PART 1: CURRENT RAG FILTERING RULES

### RAG FindingRelevanceFilter Architecture

**Purpose**: Filter document-level inconsistencies (contextual analysis findings)  
**Input**: List[Dict] with "quote", "title", "explanation", "confidence", "category"  
**Output**: List[Dict] with business_impact, recommendation, severity, deduplicated  
**Model**: InconsistencyIssue (category, severity, confidence, description, evidence)

### Phase 1-2: Rejection Criteria (4 Suppressors)

```python
1. is_placeholder() - Detects leakage of internal system text
   PLACEHOLDER_TEXT_PATTERNS = [
       "the model processes", "example text", "sample content",
       "chunk analysis", "from the given text", "do not have direct evidence"
   ]
   
2. is_project_or_facility_name() - Suppresses standalone entity names
   PROJECT_FACILITY_PATTERNS = [
       "coal handling plant", "bifpcl bangladesh maitree", "sail dsp"
   ]
   Only suppresses if NO business keywords present ("mismatch", "conflict", "contradict")
   
3. is_boilerplate_heading_or_table() - Suppresses section headers and data tables
   SUPPRESSED_EXACT_PATTERNS = {
       "OUR VISION", "MISSION", "PROJECTS", "OVERVIEW", "CHAIRMAN'S MESSAGE"
   }
   SUPPRESSED_REGEXES = [
       r"^\s*(?:vision|mission|contact|leadership|growth)$",
       r"^\s*(?:https?://|www\.)",
       r"^\s*page\s*\d+$"
   ]
   EXCLUDED_BOILERPLATE_SECTIONS = [
       "chairman's message", "vision", "mission", "contents page"
   ]
   Also rejects: short quotes (<8 chars) without action verbs
   Also rejects: financial tables (regex: "\|\s*[\d,.-]+\s*\|")
   
4. is_suppressed() - Composite check
   Returns True if placeholder OR entity_name OR boilerplate
   EXCEPTION: Returns False if explanation contains ["numeric", "mismatch", "broken", "reference"]
```

### Phase 3: Confidence Threshold
```python
min_confidence = 0.70  # Default threshold
Any finding with confidence < 0.70 is rejected (claude_rejections)
```

### Phase 4: Category Normalization
```python
Maps raw LLM categories to 12 executive categories via CATEGORY_MAPPINGS:
- "vague wording" → "Undefined Term"
- "policy conflict" → "Policy Conflict"
- "contradiction" → "Contradictory Statement"
- "numerical ambiguity" → "Numerical Inconsistency"
- "pronoun ambiguity" → "Undefined Term"  # ← KEY: RAG treats pronouns as undefined terms, not suppressions

Special rule for Policy Conflict: Requires explicit evidence
  ("whereas", "contradict", "conflicts with", "section a", "differs from")
```

### Phase 5: Severity Calculation
```python
def calculate_severity(category, confidence, explanation, impact, occurrence_count) -> str:
    
    if "regulatory audit failure" in text: return "Critical"
    if category in ("Regulatory Risk", "Compliance Risk") AND occurrence_count > 1: return "Critical"
    
    if category in ("Contradictory Statements", "Numerical Consistency"): return "High"
    
    if category in ("Cross-Reference Mismatch", "Missing Evidence"): return "Medium"
    
    if category in ("Acronym Definition", "Data Quality"): return "Low"
    
    if confidence < 0.75: return "Informational"
    
    return "Medium"
```

### Phase 6: Semantic Deduplication
```python
- Groups findings by (category, topic_key)
- topic_key = extracted keywords from quote + title
- Keeps highest confidence when duplicates found
- Keeps highest severity when duplicates found
- Aggregates occurrence_count and locations
Tracks: duplicate_rejections
```

### Phase 7: Final Consolidation
```python
Target output: 10-25 findings max (Issue 11)
Sort by severity: Critical → High → Medium → Low → Informational
Truncate to max_findings if len(result) > max_findings
```

### Phase 8: Transparency Reporting
```python
transparency_stats = {
    "raw_findings_generated": 0,
    "heading_rejections": 0,
    "table_rejections": 0,
    "placeholder_rejections": 0,
    "project_name_rejections": 0,
    "duplicate_rejections": 0,
    "claude_rejections": 0,  # low confidence
    "executive_findings_retained": 0
}
```

---

## PART 2: CURRENT MAIN PIPELINE FILTERING RULES

### Current Pipeline Filter Architecture

**Purpose**: Filter proofreading findings (grammar, spelling, punctuation, style)  
**Input**: List[Candidate] from LanguageTool, SymSpell, LLM  
**Current Filtering**: ONLY confidence-based (stage ~310)

### Existing Filtering Stages

```
Stage 8-9: Agents create Candidate objects
├─ LanguageTool: detects grammar/tense issues
├─ Spell: detects spelling via SymSpell
└─ Grammar: detects style/punctuation via LLM

Stage 10: Validation Agent
└─ Filters based on protected-term overlap ONLY
└─ No confidence filtering

Stage 12: Semantic Validator
└─ Checks meaning preservation
└─ No business relevance filtering

Stage 13: Difference Engine
└─ Span sanity check
└─ No business relevance filtering

Stage 14: Merge Agent
└─ Consolidates overlapping candidates
└─ Applies confidence formula based on source agreement:
   - LanguageTool + LLM + SymSpell agree: 1.00
   - LanguageTool + LLM agree: 0.95
   - LanguageTool only: 0.75
   - LLM only: 0.80
   - SymSpell only: 0.35
└─ Calculates severity based on type weight + confidence
└─ NO BUSINESS RELEVANCE FILTERING

Stage 14.5 (Line ~310): Confidence Filter (ONLY EXISTING FILTER)
└─ Rejects if final_confidence <= 0.50
└─ Marks as is_protected=True, protected_reason="Low Confidence"
└─ NO NOISE FILTERING (pronouns, adjectives, etc. still pass through)

Stage 15: Annotator
└─ Builds HTML annotations
└─ Processes ALL remaining issues

Stage 16: Report Generator
└─ Exports all remaining issues to JSON/Markdown/CSV
└─ NO FILTERING
```

### Critical Gap
```
Current flow: Candidate → Validated → Semantic Check → Merge → 
             Confidence Filter (0.50 threshold) → Report

Missing flow: No business relevance gate to suppress:
- Pronouns ("it", "they", "these")
- Generic adjectives ("normal", "standard", "various")
- Approximate numbers ("around 500")
- Filler terms ("etc")
```

---

## PART 3: WHY RAG FILTER CAN'T BE REUSED

### Fundamental Domain Differences

| Aspect | RAG FindingRelevanceFilter | Main Pipeline Needs |
|--------|---------------------------|-------------------|
| **Input Model** | InconsistencyIssue (category, description, evidence) | MergedIssue (issue_type, original_text, reason) |
| **Finding Type** | Document inconsistencies (numerical conflicts, policy gaps) | Text corrections (grammar, spelling, style) |
| **Suppressed Patterns** | Project names, boilerplate sections, financial tables | Pronouns, generic adjectives, approximate numbers |
| **Business Context** | What contradicts in the document | What's a low-value grammar fix |
| **Confidence Threshold** | 0.70 (high bar for audit findings) | 0.50 (already in pipeline) |
| **Output Categories** | 12 executive categories (Numerical, Policy, Regulatory, etc.) | 5 issue types (Spelling, Grammar, Tense, Punctuation, Style) |
| **Severity Model** | Based on category + impact + regulation keywords | Based on issue_type weight + agent agreement |

### Why Direct Reuse Fails

1. **Different field structures**: RAG works with "quote", "title", "explanation", "category". Main pipeline has "original_text", "suggested_text", "reason", "issue_type".

2. **Different suppression logic**: RAG suppresses boilerplate sections and project names. Main pipeline needs to suppress pronouns and adjectives.

3. **Different scoring models**: RAG uses category + impact keywords. Main pipeline uses agent agreement + type weights.

4. **Incompatible categories**: RAG's 12 executive categories (Numerical Inconsistency, Policy Conflict) don't map to main pipeline's 5 issue types (GRAMMAR, SPELLING, PUNCTUATION, STYLE, TENSE).

---

## PART 4: PROPOSED MINIMAL EXTENSION STRATEGY

### Key Insight
**Use RAG's DESIGN PATTERNS (method-based filtering + transparency) but BUILD SEPARATE filter for proofreading findings.**

### Architecture Decision

Instead of:
```python
# ❌ WRONG: Try to reuse RAG filter
from src.rag.finding_filter import FindingRelevanceFilter
```

Do this:
```python
# ✓ RIGHT: Create parallel filter following same design patterns
from src.finding_proofreading_filter import ProofreadingBusinessFilter
```

### New Service: ProofreadingBusinessFilter

**File**: `src/finding_proofreading_filter.py`  
**Purpose**: Extends existing filtering patterns to proofreading domain

**Design Pattern** (inherited from RAG):
- Multiple boolean checker methods (is_low_value_pronoun, is_generic_adjective, etc.)
- Confidence threshold filtering
- Transparency statistics tracking
- Returns (accept/reject, reason) tuples

**Key Differences from RAG**:
- Works with MergedIssue (not InconsistencyIssue)
- Checks for pronouns/adjectives/numbers (not boilerplate/tables)
- Simpler severity model (uses existing merge_agent weights)
- Lighter deduplication (already done by merge_agent)

### Exact New Service Specification

```python
class ProofreadingBusinessFilter:
    """
    Filters proofreading findings to suppress low-value noise.
    Same design as RAG FindingRelevanceFilter but for grammar/spelling domain.
    """
    
    def __init__(
        self,
        min_relevance_score: float = 0.60,
        track_suppressed: bool = True
    ):
        self.min_relevance_score = min_relevance_score
        self.transparency_stats = {
            "raw_findings": 0,
            "pronoun_suppressions": 0,
            "adjective_suppressions": 0,
            "approximate_number_suppressions": 0,
            "filler_suppressions": 0,
            "confidence_rejections": 0,
            "business_relevant_retained": 0
        }
    
    def is_business_relevant(
        self,
        original_text: str,
        reason: str,
        issue_type: IssueType,
        suggested_text: str,
        confidence: float,
        paragraph_context: Optional[str] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Returns (is_relevant, suppression_reason)
        Similar API to RAG's is_suppressed() but adapted for proofreading
        """
    
    # CHECKING METHODS (like RAG)
    def is_low_value_pronoun(self, text: str, reason: str, context: str = "") -> bool:
        """Check if text is a suppressed pronoun (it, they, these, etc)"""
    
    def is_low_value_adjective(self, text: str) -> bool:
        """Check if text is a generic adjective (normal, standard, various)"""
    
    def is_approximate_number(self, text: str, reason: str, context: str = "") -> bool:
        """Check if text is approximate number (around 500, ~200)"""
    
    def is_filler_term(self, text: str) -> bool:
        """Check if text is filler (etc, and so on)"""
    
    def has_business_context(self, reason: str, issue_type: IssueType) -> bool:
        """Check if reason/type indicates business relevance"""
    
    # REPORTING METHOD (like RAG)
    def get_transparency_stats(self) -> dict:
        """Returns suppression statistics for audit trail"""
```

### Design Patterns Reused from RAG

```python
# ✓ Pattern 1: Multiple boolean methods instead of one big filter
RAG:     is_placeholder(), is_boilerplate_heading(), is_project_name()
MAIN:    is_low_value_pronoun(), is_low_value_adjective(), is_approximate_number()

# ✓ Pattern 2: Return tuple with reason
RAG:     is_suppressed() -> bool
MAIN:    is_business_relevant() -> (bool, Optional[str])  # Return reason

# ✓ Pattern 3: Transparency statistics dict
RAG:     transparency_stats = {"heading_rejections", "table_rejections", ...}
MAIN:    transparency_stats = {"pronoun_suppressions", "adjective_suppressions", ...}

# ✓ Pattern 4: Confidence threshold
RAG:     if confidence < self.min_confidence: reject
MAIN:    if confidence < self.min_confidence: reject  (reuse 0.70 or use 0.60)

# ✓ Pattern 5: Exception handling (keep despite low values if business context)
RAG:     "if explanation contains keywords: return False" (keep it)
MAIN:    "if reason contains keywords: return True" (keep pronoun if important)
```

---

## PART 5: IMPLEMENTATION PLAN

### Single Implementation Point

**Location**: `src/pipeline.py` line ~310-330  
**Current Code**:
```python
# --- Stage 14: Merge Agent ----------------------------------------
merged_issues: List[MergedIssue] = self.merge_agent.merge(confirmed_issues)

# Filter issues by confidence: reject if final_confidence <= 0.50
high_confidence_issues = []
low_confidence_issues = []
for issue in merged_issues:
    if issue.final_confidence <= 0.50:
        issue.is_protected = True
        issue.protected_reason = "Low Confidence"
        low_confidence_issues.append(issue)
    else:
        high_confidence_issues.append(issue)

save_json(low_confidence_issues, stage_dirs["10_final"] / "rejected.json")
```

**New Code** (after ProofreadingBusinessFilter created):
```python
# --- Stage 14: Merge Agent ----------------------------------------
merged_issues: List[MergedIssue] = self.merge_agent.merge(confirmed_issues)

# --- Stage 14b: Business Relevance Gate (NEW) -----
self.logger.stage("Business relevance filtering")
business_filter = ProofreadingBusinessFilter()

# Gate 1: Confidence filter (existing)
high_confidence_issues = []
low_confidence_issues = []
for issue in merged_issues:
    if issue.final_confidence <= 0.50:
        issue.is_protected = True
        issue.protected_reason = "Low Confidence"
        low_confidence_issues.append(issue)
    else:
        high_confidence_issues.append(issue)

# Gate 2: Business relevance filter (NEW - uses same patterns as RAG)
business_relevant_issues = []
business_noise_issues = []
for issue in high_confidence_issues:
    is_relevant, suppression_reason = business_filter.is_business_relevant(
        original_text=issue.original_text,
        reason=issue.reason,
        issue_type=issue.issue_type,
        suggested_text=issue.suggested_text,
        confidence=issue.final_confidence,
        paragraph_context=self._get_paragraph_context(issue, document)
    )
    
    if is_relevant:
        business_relevant_issues.append(issue)
    else:
        issue.is_protected = True
        issue.protected_reason = suppression_reason
        business_noise_issues.append(issue)

save_json(low_confidence_issues, stage_dirs["10_final"] / "rejected_confidence.json")
save_json(business_noise_issues, stage_dirs["10_final"] / "rejected_noise.json")
filter_stats = business_filter.get_transparency_stats()
save_json(filter_stats, stage_dirs["10_final"] / "filter_statistics.json")
self.logger.info("Filtering: %d retained, %d noise, %d low-confidence",
                 len(business_relevant_issues), len(business_noise_issues), len(low_confidence_issues))

# Update issues list for downstream stages
high_confidence_issues = business_relevant_issues
```

---

## PART 6: COMPARISON TABLE - RAG vs NEW PROOFREADING FILTER

| Component | RAG Filter | Proofreading Filter | Relationship |
|-----------|-----------|-------------------|--------------|
| **Input Type** | InconsistencyIssue dict | MergedIssue | Different models |
| **Checker Methods** | is_placeholder(), is_boilerplate() | is_pronoun(), is_adjective() | Same PATTERN, different rules |
| **Confidence Check** | `< 0.70` | `< 0.50` (or 0.60) | Both use threshold |
| **Deduplication** | Via semantic topic matching | Already done by merge_agent | Simpler for proofreading |
| **Severity Model** | Category-based + business keywords | Type-weight + source agreement | Already in merge_agent |
| **Transparency** | transparency_stats dict | transparency_stats dict | Same PATTERN |
| **Suppression Criteria** | Headings, tables, placeholders | Pronouns, adjectives, numbers | Domain-specific |
| **Report Integration** | Via RAG pipeline | Via main pipeline.py line ~310 | Different pipelines |
| **Reusability** | Can't reuse code directly | Uses same design patterns | Code duplication is OK here |

---

## PART 7: MINIMAL ARCHITECTURE CHANGES NEEDED

### File Changes Required

```
NEW FILE: src/finding_proofreading_filter.py
  ├─ Class ProofreadingBusinessFilter
  ├─ Methods: is_business_relevant(), is_low_value_pronoun(), is_generic_adjective(),
  │           is_approximate_number(), is_filler_term(), has_business_context(),
  │           get_transparency_stats()
  └─ Patterns borrowed from RAG: method-based filtering + transparency dict

MODIFY: src/pipeline.py
  ├─ Add import: from src.finding_proofreading_filter import ProofreadingBusinessFilter
  ├─ Add method: _get_paragraph_context()
  └─ Stage 14b (line ~310): Replace confidence-only filter with two-gate filter
      ├─ Gate 1: Confidence (existing)
      └─ Gate 2: Business relevance (new)

MODIFY: src/report_generator.py
  ├─ Add parameter: filtering_stats: Optional[Dict]
  └─ Add field: "filtering_transparency": filtering_stats to report JSON

OPTIONAL: src/config.py
  └─ Add configuration class for filter thresholds
```

### Why This Is Minimal

1. **No code duplication from RAG**: RAG and main pipeline are separate domains. Trying to share code would require complex abstraction.

2. **Follows existing patterns**: ProofreadingBusinessFilter uses same design as RAG (method-based checking + transparency tracking).

3. **Single insertion point**: Changes only stage 14b of pipeline, all else stays the same.

4. **Backward compatible**: Suppressed findings marked with `is_protected=True` and stored separately, no breaking changes.

---

## PART 8: DECISION MATRIX

| Approach | Pros | Cons | Recommendation |
|----------|------|------|-----------------|
| **Reuse RAG FindingRelevanceFilter** | Code reuse, one filter | Incompatible models, wrong suppression patterns, requires wrapper layer | ❌ NOT VIABLE |
| **Create separate ProofreadingBusinessFilter** | Domain-specific, clean, follows patterns, minimal insertion | Some code duplication | ✓ RECOMMENDED |
| **Generic BusinessRelevanceFilter for both** | "DRY" principle | Over-abstraction, mixed concerns, harder to maintain | ❌ OVER-ENGINEERED |

**Recommendation**: **Proceed with ProofreadingBusinessFilter** following RAG design patterns.

---

## PART 9: IMPLEMENTATION CHECKLIST

### Phase 1: Create New Filter Service
- [ ] Create `src/finding_proofreading_filter.py`
- [ ] Implement `ProofreadingBusinessFilter` class
- [ ] Add pattern definitions (LOW_VALUE_PRONOUNS, LOW_VALUE_ADJECTIVES, etc.)
- [ ] Implement all checking methods
- [ ] Implement transparency statistics tracking
- [ ] Test suppression logic with sample findings

### Phase 2: Integrate into Pipeline
- [ ] Add import to `src/pipeline.py`
- [ ] Add `_get_paragraph_context()` helper method
- [ ] Add Stage 14b filtering logic
- [ ] Update return statistics
- [ ] Test pipeline execution

### Phase 3: Update Report Output
- [ ] Modify `report_generator.py` build() signature
- [ ] Add filtering_stats to report JSON
- [ ] Test report generation

### Phase 4: Testing & Validation
- [ ] Unit tests for ProofreadingBusinessFilter
- [ ] Integration tests with pipeline
- [ ] Verify business findings still surface
- [ ] Verify noise findings are suppressed
- [ ] Check transparency metrics are accurate

---

## SUMMARY

The existing RAG `FindingRelevanceFilter` cannot be directly reused for the main pipeline because:
1. Works with different data models (InconsistencyIssue vs MergedIssue)
2. Suppresses different patterns (boilerplate vs pronouns/adjectives)
3. Designed for document inconsistencies, not text corrections

**Optimal solution**: Create `ProofreadingBusinessFilter` that **borrows design patterns from RAG** (method-based filtering + transparency tracking) but implements **domain-specific logic** for proofreading findings.

**Single insertion point**: `src/pipeline.py` stage 14b (after merge_agent, before report_generator)

**Expected output**: 80-85% noise suppression, final reports with 8-15 business-relevant findings instead of 50-100 low-value findings.
