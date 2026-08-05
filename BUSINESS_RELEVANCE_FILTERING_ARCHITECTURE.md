# PRODUCTION HARDENING: Business-Relevance Filtering Architecture

## CURRENT STATE: Why Low-Value Findings Slip Through

### Current Pipeline Flow
```
Stage 8-9: Agents Generate Candidates
  ├─ LanguageTool Agent → Candidate(reason="Uses pronoun 'it'", confidence=0.75)
  ├─ Spell Agent → Candidate(reason="Spelling check", confidence=0.75)
  └─ Grammar Agent → Candidate(reason="Vague number 'around 500'", confidence=0.7)

Stage 10: Validation Agent
  └─ ValidatedIssue (passes through, minimal filtering)

Stage 12: Semantic Validator
  └─ Checks if meaning is preserved (not business relevance)

Stage 13: Difference Engine
  └─ Span sanity check (not business relevance)

Stage 14: Merge Agent
  └─ Consolidates similar issues, no business filtering

Stage 14.5: Confidence Filter (ONLY EXISTING FILTER)
  └─ Removes issues with final_confidence <= 0.50
  └─ Does NOT filter based on business value

Stage 16: Report Generator
  └─ Exports ALL remaining issues
  └─ No business-relevance gate
```

### Gap Identified
**No filtering layer exists to remove:**
- Pronoun-only findings ("it", "they", "these")
- Generic adjective findings ("normal", "standard", "various", "multiple")
- Approximate number findings ("around 500", "around 200")
- Short low-value findings ("etc")

**Current state**: ~100% of passing issues reach the report

---

## REQUIRED MODIFICATIONS

### File 1: Create New Business Relevance Filter
**Path**: `src/finding_business_filter.py`  
**Purpose**: Proofreading-specific business relevance filtering (distinct from RAG finding filter)

**Should contain**:
- `BusinessRelevanceFilter` class
- Low-value term detection patterns
- Business impact scoring
- Finding suppression logic

**Patterns to suppress**:
```python
LOW_VALUE_PRONOUNS = {
    "it", "its", "itself",
    "they", "them", "their", "theirs", "themselves",
    "these", "those", "this", "that",
    "we", "us", "our", "ours", "ourselves",
    "i", "me", "my", "mine", "myself",
    "he", "him", "his", "himself",
    "she", "her", "hers", "herself"
}

LOW_VALUE_ADJECTIVES = {
    "normal", "standard", "regular", "typical",
    "various", "multiple", "several", "many",
    "different", "similar", "same",
    "general", "specific", "particular"
}

APPROXIMATE_NUMBER_PATTERNS = [
    r"around\s+\d+",
    r"approximately\s+\d+",
    r"about\s+\d+",
    r"roughly\s+\d+",
    r"~\s*\d+",
    r"\d+\s*(?:or more|or so|ish)"
]

GENERIC_TERMS = {
    "etc", "et cetera", "and so on", "and so forth"
}
```

---

### File 2: Modify Main Pipeline
**Path**: `src/pipeline.py`

**Current state (line ~310)**:
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
        issue.reason = "Low Confidence"
        low_confidence_issues.append(issue)
    else:
        high_confidence_issues.append(issue)

save_json(low_confidence_issues, stage_dirs["10_final"] / "rejected.json")
```

**Required modification**:
- Add import: `from src.finding_business_filter import BusinessRelevanceFilter`
- Add new filter stage after line 310
- Apply business relevance filtering
- Track filtering statistics for transparency

**New code segment**:
```python
# --- Stage 14b: Business Relevance Filter (NEW) ---------------------
self.logger.stage("Business relevance filtering")
business_filter = BusinessRelevanceFilter()

# First pass: confidence filter (existing)
high_confidence_issues = []
low_confidence_issues = []
for issue in merged_issues:
    if issue.final_confidence <= 0.50:
        issue.is_protected = True
        issue.protected_reason = "Low Confidence"
        issue.reason = "Low Confidence"
        low_confidence_issues.append(issue)
    else:
        high_confidence_issues.append(issue)

# Second pass: business relevance filter (NEW)
business_relevant_issues = []
business_noise_issues = []
for issue in high_confidence_issues:
    if business_filter.is_business_relevant(
        original_text=issue.original_text,
        reason=issue.reason,
        issue_type=issue.issue_type,
        paragraph_context=self._get_paragraph_context(issue, document)
    ):
        business_relevant_issues.append(issue)
    else:
        business_noise_issues.append(issue)

# Update tracking
high_confidence_issues = business_relevant_issues
save_json(business_noise_issues, stage_dirs["10_final"] / "noise_filtered.json")
self.logger.info("Business relevance: %d retained, %d filtered as noise", 
                 len(business_relevant_issues), len(business_noise_issues))
```

---

### File 3: Update Report Generator
**Path**: `src/report_generator.py`

**Current state**:
```python
def build(self, issues: List[MergedIssue]) -> Tuple[dict, str, str]:
    """Returns (report_dict, changes_markdown, summary_csv)."""
    report = {
        "total_issues": len(issues),
        "by_type": self._count_by_type(issues),
        "issues": issues,
    }
```

**Required modification**:
- Add filtering metadata to report JSON
- Track what was filtered and why
- Add transparency section showing filter decisions

**New structure**:
```python
def build(self, issues: List[MergedIssue], 
          filtering_stats: Optional[dict] = None) -> Tuple[dict, str, str]:
    """Returns (report_dict, changes_markdown, summary_csv)."""
    report = {
        "total_issues": len(issues),
        "by_type": self._count_by_type(issues),
        "issues": issues,
        "filtering_transparency": filtering_stats or {},  # NEW
    }
```

---

### File 4: Configuration
**Path**: `src/config.py` (or new `src/finding_filter_config.py`)

**Should define**:
- Minimum business relevance score (default: 0.60)
- Categories that are always business-relevant
- Terms/patterns that automatically suppress findings
- Categories that always surface despite low scores

---

## FILTERING LOGIC FLOW

### For Each Finding:

```
Start: MergedIssue from merge_agent

↓

Question 1: Is original_text in LOW_VALUE_PRONOUNS?
  YES → Check Question 2
  NO → Go to Question 3

↓

Question 2: Does reason/evidence suggest HIGH business impact?
  YES → KEEP finding (pronoun but with business context)
  NO → SUPPRESS (low-value pronoun)

↓

Question 3: Is original_text in LOW_VALUE_ADJECTIVES?
  YES → Check Question 4
  NO → Go to Question 5

↓

Question 4: Is this describing a critical difference between versions?
  YES → KEEP finding (adjective matters in comparison)
  NO → SUPPRESS (low-value adjective)

↓

Question 5: Does original_text match APPROXIMATE_NUMBER_PATTERNS?
  YES → Check Question 6
  NO → Go to Question 7

↓

Question 6: Is this a numerical inconsistency (e.g., "around 500" vs "around 200")?
  YES → KEEP finding (numerical inconsistency)
  NO → SUPPRESS (approximate number is intentional)

↓

Question 7: Is original_text in GENERIC_TERMS?
  YES → SUPPRESS (e.g., "etc")
  NO → Go to Question 8

↓

Question 8: Is issue_type in ALWAYS_BUSINESS_RELEVANT?
  YES → KEEP finding
  NO → Go to Question 9

↓

Question 9: Does reason match BUSINESS_IMPACT_KEYWORDS?
  YES → KEEP finding
  NO → SUPPRESS (low business value)

↓

End: Output KEEP or SUPPRESS decision
```

---

## SUPPRESSION CRITERIA

### Always Suppress (unless explicitly mentioned in reason/context):
```
1. Pronouns: it, its, they, them, these, that, etc.
2. Generic adjectives: normal, standard, various, multiple
3. Approximate numbers: "around X", "approximately X"
4. Filler terms: etc, and so on, etc.
5. Short phrases (<5 chars) without action verbs
6. Standalone company/product names (unless mismatched)
7. Section numbers/references (unless broken)
8. Contact information formatting
9. Date formats (unless conflicting)
10. Measurement units alone (unless conflicting)
```

### Always Keep (unless confidence < 0.50):
```
1. Numerical conflicts (e.g., "500 employees" vs "200 employees")
2. Date conflicts (e.g., "Q2 2023" vs "Q3 2023")
3. Entity mismatches (e.g., "Company A" vs "Company B")
4. Policy contradictions
5. Cross-reference failures (e.g., "See Table 5" but no Table 5)
6. Regulatory compliance gaps
7. Contractual inconsistencies
8. Definition contradictions
```

---

## IMPLEMENTATION CHECKLIST

### Step 1: Create BusinessRelevanceFilter Class
- [ ] File: `src/finding_business_filter.py`
- [ ] Implement `__init__()`
- [ ] Implement `is_business_relevant()`
- [ ] Add pattern definitions
- [ ] Add scoring logic
- [ ] Add transparency reporting

### Step 2: Modify Pipeline
- [ ] File: `src/pipeline.py`
- [ ] Add import for BusinessRelevanceFilter
- [ ] Add filtering stage after merge_agent
- [ ] Pass filtering stats to report_generator
- [ ] Add logging for transparency

### Step 3: Update Report Generator
- [ ] File: `src/report_generator.py`
- [ ] Accept filtering_stats parameter
- [ ] Include in report JSON output
- [ ] Add transparency section to markdown

### Step 4: Configuration
- [ ] File: `src/config.py` or new file
- [ ] Define filter thresholds
- [ ] Define exception patterns
- [ ] Make configurable via environment variables

### Step 5: Testing
- [ ] Unit tests for filter logic
- [ ] Integration tests with pipeline
- [ ] Validation that business findings aren't suppressed
- [ ] Audit that noise findings are suppressed

---

## BEFORE/AFTER EXAMPLE

### Before (Current)
```json
{
  "total_issues": 47,
  "issues": [
    {
      "original_text": "it",
      "suggested_text": "the issue",
      "reason": "Ambiguous pronoun reference",
      "confidence": 0.75
    },
    {
      "original_text": "around 500",
      "suggested_text": "approximately 500",
      "reason": "Approximate number",
      "confidence": 0.65
    },
    {
      "original_text": "normal",
      "suggested_text": "typical",
      "reason": "Generic adjective",
      "confidence": 0.60
    },
    ...47 more low-value findings...
  ]
}
```

### After (With Filtering)
```json
{
  "total_issues": 8,
  "filtering_transparency": {
    "raw_findings_before_filter": 47,
    "confidence_filter_rejected": 5,
    "business_relevance_rejected": 34,
    "final_findings": 8,
    "suppression_rate": 82.9
  },
  "issues": [
    {
      "original_text": "500 employees",
      "suggested_text": "200 employees",
      "reason": "Numerical inconsistency: contradicts statement on page 3",
      "confidence": 0.95
    },
    {
      "original_text": "Q2 2023",
      "suggested_text": "Q3 2023",
      "reason": "Temporal inconsistency: conflicts with fiscal year stated in executive summary",
      "confidence": 0.92
    },
    ...6 more high-value findings...
  ]
}
```

---

## SERVICES REQUIRING MODIFICATION

| File | Service | Method | Lines | Change Type |
|------|---------|--------|-------|------------|
| `src/finding_business_filter.py` | BusinessRelevanceFilter | NEW | - | Create |
| `src/pipeline.py` | ProofreadingPipeline | run() | ~310-350 | Add stage |
| `src/report_generator.py` | ReportGenerator | build() | ~28-38 | Add params |
| `src/config.py` | PipelineConfig | N/A | TBD | Add config |
| `src/models.py` | MergedIssue | N/A | Optional | Add metadata |

---

## QUALITY GATES FOR REPORT OUTPUT

### Pre-Report Filter Checklist
Before a finding reaches the final report, it must satisfy:

```python
def passes_report_quality_gate(issue: MergedIssue) -> bool:
    return (
        # Gate 1: Minimum confidence
        issue.final_confidence >= 0.50
        
        # Gate 2: Business relevance
        AND is_business_relevant(issue)
        
        # Gate 3: Has actionable context
        AND issue.reason is not None
        AND len(issue.reason.strip()) > 10
        
        # Gate 4: Would auditor care?
        AND would_auditor_flag(issue)
        
        # Gate 5: Not noise
        AND not is_noise(issue)
    )
```

---

## EXPECTED OUTPUT

### Report Metrics After Implementation

**For test_document.txt (current)**:
- Total findings (before filter): 22
- Noise filtered: 18 (82%)
- Business relevant: 4 (18%)

**Expected findings to keep**:
1. Grammar: verb tense inconsistency (confidence: 0.92)
2. Vocabulary: repeated phrase pattern (confidence: 0.85)
3. Structure: missing punctuation in list (confidence: 0.80)
4. Style: inconsistent terminology (confidence: 0.78)

**Expected findings to suppress**:
1. "it" (pronoun) ← suppress
2. "they" (pronoun) ← suppress
3. "these" (pronoun) ← suppress
4. "around 500" (approximate number) ← suppress
5. "normal" (generic adjective) ← suppress
6. "standard" (generic adjective) ← suppress
7. "various" (generic adjective) ← suppress
8. "multiple" (generic adjective) ← suppress
9. "etc" (filler) ← suppress

---

## TRANSPARENCY & AUDIT TRAIL

### Each Finding Stores
- Original business relevance score
- Filter decision and reason
- LLM confidence score
- Agreement count from agents
- Contributing sources
- All metadata for audit review

### Report Includes
- Total findings before any filtering
- Filtering stage breakdown (confidence → business relevance)
- Suppression statistics
- Sample of suppressed findings (for audit)
- Exception explanations (if any finding bypassed filters)

---

## NEXT STEPS

1. Create `src/finding_business_filter.py` with full filter logic
2. Modify `src/pipeline.py` to apply filter before report generation
3. Update `src/report_generator.py` to include transparency metadata
4. Add configuration options for filtering thresholds
5. Add tests to verify business-value findings are not suppressed
6. Run on test documents and verify noise reduction
