# BUSINESS RELEVANCE FILTER: EXACT FILES & SERVICES TO MODIFY

## Summary Table

| # | File | Service | Method | Current Lines | Change | Priority |
|---|------|---------|--------|---------------|--------|----------|
| 1 | `src/finding_business_filter.py` | BusinessRelevanceFilter | NEW | - | Create new class | HIGH |
| 2 | `src/pipeline.py` | ProofreadingPipeline | run() | ~310-330 | Add filtering stage | HIGH |
| 3 | `src/report_generator.py` | ReportGenerator | build() | ~28-38 | Add metadata | MEDIUM |
| 4 | `src/config.py` | PipelineConfig | N/A | TBD | Add config | MEDIUM |

---

## FILE 1: CREATE NEW SERVICE
### Path: `src/finding_business_filter.py`

**Status**: ⚠️ DOES NOT EXIST - MUST CREATE

**Purpose**: Filters MergedIssue objects to identify business-relevant findings

**Class Definition**:
```python
class BusinessRelevanceFilter:
    """
    Filters proofreading findings to surface only business-relevant issues.
    Suppresses noise like pronouns, generic adjectives, approximate numbers.
    """
    
    def __init__(
        self,
        min_relevance_score: float = 0.60,
        max_findings: int = 50,
        track_suppressed: bool = True
    ):
        """Initialize filter with thresholds."""
        
    def is_business_relevant(
        self,
        original_text: str,
        reason: str,
        issue_type: IssueType,
        suggested_text: str,
        confidence: float,
        paragraph_context: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Returns (is_relevant, suppression_reason)
        
        Args:
            original_text: The text flagged by agent (e.g., "it")
            reason: Why the issue was detected (e.g., "Ambiguous pronoun")
            issue_type: Grammar/Spelling/Punctuation/etc
            suggested_text: The replacement (e.g., "the issue")
            confidence: Confidence score 0.0-1.0
            paragraph_context: Surrounding text for context
            
        Returns:
            (True, "") if business-relevant
            (False, reason) if suppressed as noise
        """
        
    def get_filter_statistics(self) -> dict:
        """Returns transparency report of what was filtered."""
```

**Required Methods**:
```python
def is_low_value_pronoun(self, text: str, reason: str, context: str = "") -> bool:
    """Check if this is a low-value pronoun mention."""
    
def is_low_value_adjective(self, text: str) -> bool:
    """Check if this is a generic/vague adjective."""
    
def is_approximate_number(self, text: str, reason: str) -> bool:
    """Check if this is an approximate number (around 500, ~200, etc)."""
    
def is_generic_filler(self, text: str) -> bool:
    """Check if text is filler like 'etc', 'and so on'."""
    
def has_business_context(self, reason: str, issue_type: IssueType) -> bool:
    """Check if reason/type indicates business relevance."""
    
def compute_relevance_score(
        self, 
        original_text: str, 
        reason: str, 
        issue_type: IssueType, 
        confidence: float
    ) -> float:
    """Compute business relevance score 0.0-1.0."""
```

---

## FILE 2: MODIFY PIPELINE ORCHESTRATOR
### Path: `src/pipeline.py`

**Current Implementation** (lines ~310-330):
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
self.logger.info("Confidence filtering: %d accepted, %d rejected", len(high_confidence_issues), len(low_confidence_issues))
```

**Required Changes**:

### Change 2.1: Add Import
**Location**: Top of file (around line 40)
```python
from src.finding_business_filter import BusinessRelevanceFilter
```

### Change 2.2: Add Helper Method to Class
**Location**: Add new method to ProofreadingPipeline class (around line 250)
```python
def _get_paragraph_context(self, issue: MergedIssue, document: StructuredDocument) -> Optional[str]:
    """
    Retrieve paragraph text surrounding the issue for context.
    
    Args:
        issue: MergedIssue with sentence_id and char_start/char_end
        document: StructuredDocument with normalized_text and paragraph info
        
    Returns:
        Paragraph text or surrounding 50 words
    """
    try:
        # Find paragraph containing this issue
        for para in document.paragraphs:
            if para.paragraph_id == issue.paragraph_id or (
                para.doc_char_start and para.doc_char_end and
                para.doc_char_start <= issue.char_start <= para.doc_char_end
            ):
                return para.text
        
        # Fallback: surrounding text
        start = max(0, issue.char_start - 100)
        end = min(len(document.normalized_text), issue.char_end + 100)
        return document.normalized_text[start:end]
    except Exception as e:
        self.logger.debug(f"Failed to get context for issue: {e}")
        return None
```

### Change 2.3: Replace Confidence Filter with Two-Stage Filter
**Location**: Lines ~310-330 (replace entire section)

**NEW CODE**:
```python
# --- Stage 14: Merge Agent ----------------------------------------
merged_issues: List[MergedIssue] = self.merge_agent.merge(confirmed_issues)
self.logger.info("Merged issues: %d total", len(merged_issues))

# --- Stage 14b: Quality Gates (Confidence + Business Relevance) ----
self.logger.stage("Applying quality gates")
business_filter = BusinessRelevanceFilter()

# Gate 1: Confidence filtering
high_confidence_issues = []
low_confidence_issues = []
for issue in merged_issues:
    if issue.final_confidence <= 0.50:
        issue.is_protected = True
        issue.protected_reason = "Low Confidence"
        low_confidence_issues.append(issue)
    else:
        high_confidence_issues.append(issue)

save_json(low_confidence_issues, stage_dirs["10_final"] / "rejected_confidence.json")
self.logger.info("Confidence gate: %d passed, %d failed", 
                 len(high_confidence_issues), len(low_confidence_issues))

# Gate 2: Business relevance filtering (NEW)
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
        # Mark as suppressed noise
        issue.is_protected = True
        issue.protected_reason = suppression_reason or "Low business value"
        business_noise_issues.append(issue)

# Save transparency artifacts
save_json(business_noise_issues, stage_dirs["10_final"] / "noise_filtered.json")
filter_stats = business_filter.get_filter_statistics()
save_json(filter_stats, stage_dirs["10_final"] / "filter_statistics.json")

self.logger.info("Business relevance gate: %d retained, %d filtered as noise",
                 len(business_relevant_issues), len(business_noise_issues))
self.logger.info("Filter statistics: %s", filter_stats)

# Update issues list for downstream stages
high_confidence_issues = business_relevant_issues
```

### Change 2.4: Update Report Generator Call
**Location**: Lines ~336-340 (modify existing call)

**Current**:
```python
report_generator = ReportGenerator(document.normalized_text, all_sentences)
report_json, changes_md, summary_csv = report_generator.build(high_confidence_issues)
```

**New**:
```python
report_generator = ReportGenerator(document.normalized_text, all_sentences)
report_json, changes_md, summary_csv = report_generator.build(
    high_confidence_issues,
    filtering_stats=filter_stats
)
```

### Change 2.5: Update Return Statistics
**Location**: Lines ~350-360 (return dict)

**Add to return statement**:
```python
return {
    "run_dir": str(run_dir),
    "total_issues": len(high_confidence_issues),
    "accepted": len(accepted),
    "rejected_protected": len(rejected),
    "rejected_semantic": len(semantically_failed),
    "rejected_confidence": len(low_confidence_issues),
    "rejected_noise": len(business_noise_issues),  # NEW
    "filtering_stats": filter_stats,  # NEW
    # ... rest of return dict
}
```

---

## FILE 3: MODIFY REPORT GENERATOR
### Path: `src/report_generator.py`

**Current Implementation** (lines ~20-40):
```python
class ReportGenerator:
    def __init__(self, full_text: str, sentences: List[Sentence]) -> None:
        self.full_text = full_text
        self.sentences = sentences
        self._sentence_by_id: Dict[int, Sentence] = {s.sentence_id: s for s in sentences}

    def build(self, issues: List[MergedIssue]) -> Tuple[dict, str, str]:
        """Returns (report_dict, changes_markdown, summary_csv)."""
        report = {
            "total_issues": len(issues),
            "by_type": self._count_by_type(issues),
            "issues": issues,
        }
        return report, self._build_changes_md(issues), self._build_summary_csv(issues)
```

**Required Changes**:

### Change 3.1: Import Dict Type
**Location**: Line ~15
```python
from typing import Dict, List, Tuple, Optional
```

### Change 3.2: Modify build() Signature
**Location**: Line ~28

**Current**:
```python
def build(self, issues: List[MergedIssue]) -> Tuple[dict, str, str]:
```

**New**:
```python
def build(
    self, 
    issues: List[MergedIssue],
    filtering_stats: Optional[Dict[str, any]] = None
) -> Tuple[dict, str, str]:
```

### Change 3.3: Update Report Dictionary
**Location**: Lines ~30-36

**Current**:
```python
report = {
    "total_issues": len(issues),
    "by_type": self._count_by_type(issues),
    "issues": issues,
}
```

**New**:
```python
report = {
    "total_issues": len(issues),
    "by_type": self._count_by_type(issues),
    "issues": issues,
    "filtering_transparency": filtering_stats or {},  # NEW
}
```

---

## FILE 4: OPTIONAL - ADD CONFIGURATION
### Path: `src/config.py`

**If adding configuration support** (optional but recommended):

### Add to Config Class:
```python
class FindingFilterConfig:
    """Configuration for business relevance filtering."""
    
    MIN_RELEVANCE_SCORE: float = 0.60  # Minimum business relevance threshold
    MAX_FINDINGS: int = 50  # Cap on final findings to prevent overwhelm
    MIN_CONFIDENCE: float = 0.50  # Already exists, kept for reference
    
    # Patterns that always suppress (unless business context exists)
    ALWAYS_SUPPRESS_TERMS = {
        "it", "its", "they", "them", "these", "that",
        "normal", "standard", "various", "multiple",
        "etc", "and so on"
    }
    
    # Issue types that are always business-relevant
    ALWAYS_RELEVANT_TYPES = {
        IssueType.NUMERICAL,  # Assuming numerical inconsistencies
        IssueType.CROSS_REFERENCE,
    }
    
    # Keywords that indicate business relevance
    BUSINESS_IMPACT_KEYWORDS = {
        "mismatch", "conflict", "contradiction", "inconsistent",
        "broken", "missing", "undefined", "policy", "compliance",
        "regulatory", "contractual", "liability", "risk",
        "revenue", "employee", "date", "deadline", "deadline",
        "percentage", "percent", "amount", "quantity"
    }
```

---

## IMPLEMENTATION ORDER

### Phase 1: Create Filter Service
1. ✓ Create `src/finding_business_filter.py`
2. ✓ Implement BusinessRelevanceFilter class
3. ✓ Add all pattern detection methods
4. ✓ Add scoring logic

### Phase 2: Integrate into Pipeline
1. ✓ Add import to `src/pipeline.py`
2. ✓ Add helper method `_get_paragraph_context()`
3. ✓ Add filtering stage after merge_agent
4. ✓ Update return statistics

### Phase 3: Update Report Output
1. ✓ Modify `report_generator.py` build() signature
2. ✓ Add filtering_stats to report JSON
3. ✓ Update markdown/CSV if needed

### Phase 4: Optional Configuration
1. ✓ Add config to `src/config.py`
2. ✓ Make thresholds configurable

---

## TESTING CHECKLIST

### Unit Tests for BusinessRelevanceFilter:
```python
def test_suppress_pronoun_without_context():
    # "it" should be suppressed
    
def test_keep_pronoun_with_business_context():
    # "it" with reason="numerical reference conflict" should be kept
    
def test_suppress_generic_adjective():
    # "normal" should be suppressed
    
def test_suppress_approximate_number():
    # "around 500" should be suppressed
    
def test_keep_numerical_mismatch():
    # "500" vs "200" should be kept
```

### Integration Tests for Pipeline:
```python
def test_pipeline_filtering_output():
    # Verify report contains filtered statistics
    
def test_noise_filtered_artifacts():
    # Verify noise_filtered.json contains low-value findings
    
def test_business_findings_retained():
    # Verify business-relevant findings make it to report
```

### Regression Tests:
```python
def test_existing_high_confidence_findings_not_suppressed():
    # Ensure real issues still surface
    
def test_filtering_transparency():
    # Verify all filtering decisions are logged/tracked
```

---

## SUCCESS CRITERIA

✅ **For Each Document**:
1. Noise findings (pronouns, generic adjectives, approx numbers) suppressed by 80%+
2. Business-relevant findings retained at 95%+
3. Filter transparency statistics included in report
4. No regression in detecting real issues

✅ **For Test Suite**:
1. All filter tests passing
2. Pipeline integration tests passing
3. No failures in existing tests
4. Performance impact <5% on pipeline runtime

---

## DEPLOYMENT CHECKLIST

- [ ] Code review of `finding_business_filter.py`
- [ ] Code review of `pipeline.py` modifications
- [ ] Code review of `report_generator.py` modifications
- [ ] All tests passing
- [ ] Integration test on sample documents
- [ ] Verify suppression statistics are correct
- [ ] Merge to main
- [ ] Deploy to production
- [ ] Monitor filter statistics on real documents
