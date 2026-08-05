# PROOFREADING FILTER: Detailed Business Relevance Rules

## Overview

**Objective**: Filter MergedIssue findings to suppress low-value proofreading noise while retaining business-relevant corrections.

**Domain**: Grammar, spelling, tense, punctuation, style corrections (IssueType: GRAMMAR, SPELLING, TENSE, PUNCTUATION, STYLE)

**Input**: MergedIssue with (original_text, suggested_text, reason, issue_type, confidence, final_confidence)

**Output**: (is_business_relevant: bool, suppression_reason: Optional[str])

**Design Pattern**: Follows RAG FindingRelevanceFilter method-based filtering architecture

---

## RULE SET 1: LOW-VALUE PRONOUNS

### Suppressed Pronouns
```python
PRONOUNS_TO_SUPPRESS = {
    # 3rd person singular
    "it", "its", "itself",
    
    # 3rd person plural
    "they", "them", "their", "theirs", "themselves",
    
    # Demonstratives
    "this", "that", "these", "those",
    
    # 1st person
    "i", "me", "my", "mine", "myself",
    "we", "us", "our", "ours", "ourselves",
    
    # 3rd person singular other
    "he", "him", "his", "himself",
    "she", "her", "hers", "herself",
    
    # Other low-value
    "one", "ones"
}
```

### Rule: is_low_value_pronoun()
```python
def is_low_value_pronoun(self, text: str, reason: str, context: str = "") -> bool:
    """
    Returns True if this should be suppressed as low-value pronoun.
    
    Algorithm:
    1. Normalize text to lowercase
    2. Check if normalized text in PRONOUNS_TO_SUPPRESS
    3. If Yes:
       a. Check if reason contains business keywords
          BUSINESS_KEYWORDS = [
              "ambiguous", "unclear", "reference", "antecedent",
              "inconsistent", "conflict", "contradiction"
          ]
       b. If business context found → NOT suppressed (return False)
       c. Else → suppress as low-value (return True)
    4. If not pronoun → return False (not our concern)
    
    Examples:
    - "it" with reason="Ambiguous pronoun reference" → return False (keep, has business context)
    - "it" with reason="Pronoun usage" → return True (suppress, no business context)
    - "they" with reason="Grammar" → return True (suppress)
    - "they" with reason="Contradictory references (they vs he)" → return False (keep)
    """
```

### Exception Cases (Keep Despite Being Pronoun)
- Reason contains: "ambiguous pronoun", "unclear reference", "antecedent"
- Reason contains: "contradictory", "conflict", "inconsistent"
- Context shows multiple entities (e.g., "they vs. he")

---

## RULE SET 2: GENERIC ADJECTIVES

### Suppressed Adjectives
```python
GENERIC_ADJECTIVES = {
    # Vagueness indicators
    "normal", "standard", "regular", "typical",
    "general", "common", "ordinary",
    
    # Multiplicity without specificity
    "various", "multiple", "several", "many", "few",
    "some", "other", "another",
    
    # Similarity/Difference without detail
    "different", "similar", "same", "equal",
    
    # Approximation adjectives
    "roughly", "approximately", "about", "around",
    "almost", "nearly", "basically",
    
    # Intensifiers without meaning
    "very", "quite", "rather", "fairly",
    "significantly", "substantially"
}
```

### Rule: is_low_value_adjective()
```python
def is_low_value_adjective(self, text: str) -> bool:
    """
    Returns True if text is a generic adjective that should be suppressed.
    
    Algorithm:
    1. Normalize text to lowercase
    2. Check if text in GENERIC_ADJECTIVES
    3. If Yes → return True (suppress as low-value)
    4. Else → return False
    
    Examples:
    - "normal" → return True (suppress)
    - "various" → return True (suppress)
    - "different" → return True (suppress)
    - "critical" → return False (not generic)
    - "specific" → return False (not generic)
    """
```

### No Exceptions
- Generic adjectives are always low-value when used in text corrections
- They don't carry business meaning on their own
- If an adjective is business-relevant, it's specific (not generic)

---

## RULE SET 3: APPROXIMATE NUMBERS

### Suppressed Number Patterns
```python
APPROXIMATE_NUMBER_PATTERNS = [
    r"^around\s+(\d+(?:\.\d+)?)\s*(?:%|percent|thousand|million|billion)?$",
    r"^approximately\s+(\d+(?:\.\d+)?)\s*(?:%|percent)?$",
    r"^about\s+(\d+(?:\.\d+)?)\s*(?:%|percent)?$",
    r"^roughly\s+(\d+(?:\.\d+)?)\s*(?:%|percent)?$",
    r"^~\s*(\d+(?:\.\d+)?)\s*(?:%|percent)?$",
    r"^(\d+(?:\.\d+)?)\s*(?:or more|or so|ish)\s*(?:%|percent)?$"
]
```

### Rule: is_approximate_number()
```python
def is_approximate_number(self, text: str, reason: str, context: str = "") -> bool:
    """
    Returns True if text is an approximate number phrase to suppress.
    
    Algorithm:
    1. Check if text matches any APPROXIMATE_NUMBER_PATTERNS
    2. If No → return False (not our concern)
    3. If Yes:
       a. Check if reason contains numerical conflict keywords:
          CONFLICT_KEYWORDS = [
              "mismatch", "conflict", "inconsistent", "contradict",
              "inconsistency", "discrepancy"
          ]
       b. If conflict found → return False (keep, indicates numerical inconsistency)
       c. Else → return True (suppress as intentional approximation)
    
    Examples:
    - "around 500" with reason="Approximate number" → return True (suppress)
    - "around 500" with reason="Numerical inconsistency: contradicts '200' on page 3" → return False (keep)
    - "approximately 200" with reason="Grammar" → return True (suppress)
    - "500" (not approximate) → return False (not our concern)
    """
```

### Exception Cases (Keep Despite Being Approximate)
- Reason contains: "mismatch", "conflict", "contradiction", "inconsistency"
- Context suggests numerical comparison (e.g., "around 500 vs. around 200")
- Example: Finding "around 500" when paragraph also mentions "around 200" → Keep (it's inconsistency)

---

## RULE SET 4: FILLER & BOILERPLATE TERMS

### Suppressed Filler Terms
```python
FILLER_TERMS = {
    "etc", "et cetera",
    "and so on", "and so forth",
    "etc.", "e.g.", "i.e.",
    "for example", "for instance",
    "in summary", "in conclusion",
    "as mentioned", "as stated", "as discussed"
}
```

### Rule: is_filler_term()
```python
def is_filler_term(self, text: str) -> bool:
    """
    Returns True if text is filler that should always be suppressed.
    
    Algorithm:
    1. Normalize text to lowercase, strip whitespace
    2. Check if text in FILLER_TERMS (exact match or substring)
    3. If Yes → return True (suppress as low-value filler)
    4. Else → return False
    
    Examples:
    - "etc" → return True (suppress)
    - "and so on" → return True (suppress)
    - "for example" → return True (suppress)
    - "for example," → return True (suppress, handle punctuation)
    - "example" (without "for") → return False (not filler, contextual word)
    """
```

### No Exceptions
- Filler terms are always low-value
- They don't contribute business meaning
- Suppression is strict

---

## RULE SET 5: CONTEXT-BASED BUSINESS RELEVANCE

### Business Keywords
```python
BUSINESS_KEYWORDS = {
    # Numerical/Financial
    "revenue", "profit", "cost", "expense", "amount", "quantity",
    "percentage", "percent", "%", "rate", "ratio", "count",
    "employee", "headcount", "volume", "number",
    
    # Dates/Timeline
    "date", "year", "quarter", "month", "deadline", "fiscal",
    "2023", "2024", "2025", "q1", "q2", "q3", "q4",
    
    # Inconsistency/Conflict
    "mismatch", "conflict", "contradiction", "inconsistent",
    "contradict", "inconsistency", "discrepancy", "differ",
    "differ from", "conflicts with", "contradicts",
    
    # Document/Policy
    "policy", "procedure", "rule", "regulation", "compliance",
    "requirement", "section", "chapter", "page", "reference",
    "defined", "definition", "glossary", "term",
    
    # Regulatory/Legal
    "legal", "regulatory", "compliance", "audit", "standard",
    "disclosure", "risk", "liability", "penalty", "enforce",
    
    # Critical Business
    "entity", "company", "organization", "department", "division",
    "client", "customer", "partner", "supplier",
    
    # Logic/Relationships
    "cross-reference", "cross reference", "reference to",
    "refers to", "see", "table", "figure", "exhibit",
    "broken link", "missing section"
}
```

### Rule: has_business_context()
```python
def has_business_context(self, reason: str, issue_type: IssueType, original_text: str = "") -> bool:
    """
    Returns True if reason/type/text contains evidence of business relevance.
    
    Algorithm:
    1. Combine reason + issue_type + original_text into analysis_block
    2. Convert to lowercase
    3. For each BUSINESS_KEYWORD:
       a. If keyword found in analysis_block → return True (business relevant)
    4. If no business keywords found → return False
    
    Examples:
    - reason="Employee count mismatch" → True (keywords: employee, mismatch)
    - reason="Revenue inconsistency: 500M vs 200M" → True (keywords: revenue, inconsistency)
    - reason="Grammar check" → False (no business keywords)
    - issue_type=TENSE + reason="Policy requires past tense" → True (keywords: policy, requires)
    """
```

---

## COMPOSITE RULE: is_business_relevant()

```python
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
    Main decision function. Returns (is_relevant, suppression_reason)
    
    Algorithm (Decision Tree):
    
    1. Check confidence threshold
       if confidence < self.min_relevance_score (0.60):
           return (False, "Low confidence")
    
    2. Check if pronoun
       if self.is_low_value_pronoun(original_text, reason, paragraph_context or ""):
           return (False, "Low-value pronoun")
    
    3. Check if generic adjective
       if self.is_low_value_adjective(original_text):
           return (False, "Generic adjective")
    
    4. Check if approximate number
       if self.is_approximate_number(original_text, reason, paragraph_context or ""):
           return (False, "Approximate number")
    
    5. Check if filler term
       if self.is_filler_term(original_text):
           return (False, "Filler term")
    
    6. Check if issue_type is ALWAYS_RELEVANT
       if issue_type in (IssueType.GRAMMAR, IssueType.TENSE) and has_business_context(...):
           return (True, None)
    
    7. Check for business context keywords
       if self.has_business_context(reason, issue_type, original_text):
           return (True, None)
    
    8. Default decision (no business relevance found)
       return (False, "No business relevance detected")
    
    Returns:
    - (True, None) if should be kept
    - (False, reason_string) if should be suppressed
    """
```

---

## TRANSPARENCY STATISTICS

### Tracking Dictionary
```python
self.transparency_stats = {
    "raw_findings_processed": 0,      # Total MergedIssues analyzed
    "pronoun_suppressions": 0,         # Low-value pronouns filtered
    "adjective_suppressions": 0,       # Generic adjectives filtered
    "number_suppressions": 0,          # Approximate numbers filtered
    "filler_suppressions": 0,          # Filler terms filtered
    "business_relevant_retained": 0,   # Findings that passed filter
}
```

### Method: get_transparency_stats()
```python
def get_transparency_stats(self) -> dict:
    """Returns statistics for audit trail and reporting"""
    return {
        **self.transparency_stats,
        "suppression_rate": (
            (self.transparency_stats["pronoun_suppressions"] +
             self.transparency_stats["adjective_suppressions"] +
             self.transparency_stats["number_suppressions"] +
             self.transparency_stats["filler_suppressions"]) /
            max(1, self.transparency_stats["raw_findings_processed"])
        )
    }
```

---

## EXPECTED BEHAVIOR EXAMPLES

### Example 1: Suppressed Pronoun
```
Input MergedIssue:
  original_text="it"
  suggested_text="the issue"
  reason="Ambiguous pronoun"
  confidence=0.75
  issue_type=GRAMMAR

Processing:
  1. Confidence 0.75 > 0.60 ✓
  2. is_low_value_pronoun("it", "Ambiguous pronoun", context)
     → Found in PRONOUNS_TO_SUPPRESS ✓
     → "Ambiguous pronoun" contains no business keywords
     → return True (should suppress)

Output: (False, "Low-value pronoun")
Action: Suppress this finding, mark as protected
```

### Example 2: Retained Pronoun (Business Context)
```
Input MergedIssue:
  original_text="they"
  suggested_text="the employees"
  reason="Ambiguous pronoun: 'they' could refer to employees OR managers"
  confidence=0.85
  issue_type=GRAMMAR
  context="...employees versus managers disagreed on policy..."

Processing:
  1. Confidence 0.85 > 0.60 ✓
  2. is_low_value_pronoun("they", reason, context)
     → Found in PRONOUNS_TO_SUPPRESS ✓
     → Reason contains "ambiguous" + context contains "versus"
     → Business keyword match in context ✓
     → return False (DON'T suppress)

Output: (True, None)
Action: KEEP this finding - it has business context
```

### Example 3: Suppressed Generic Adjective
```
Input MergedIssue:
  original_text="normal"
  suggested_text="typical"
  reason="Generic adjective"
  confidence=0.65
  issue_type=STYLE

Processing:
  1. Confidence 0.65 > 0.60 ✓
  2. is_low_value_pronoun("normal") → False
  3. is_low_value_adjective("normal")
     → Found in GENERIC_ADJECTIVES ✓
     → return True (should suppress)

Output: (False, "Generic adjective")
Action: Suppress this finding
```

### Example 4: Suppressed Approximate Number
```
Input MergedIssue:
  original_text="around 500"
  suggested_text="approximately 500"
  reason="Approximate number"
  confidence=0.60
  issue_type=STYLE

Processing:
  1. Confidence 0.60 >= 0.60 ✓
  2. is_approximate_number("around 500", "Approximate number")
     → Matches APPROXIMATE_NUMBER_PATTERNS ✓
     → Reason contains no conflict keywords ✓
     → return True (should suppress)

Output: (False, "Approximate number")
Action: Suppress - this is intentional approximation
```

### Example 5: Retained Approximate Number (Inconsistency)
```
Input MergedIssue:
  original_text="around 500"
  suggested_text="around 300"
  reason="Numerical inconsistency: contradicts 'approximately 300' on page 5"
  confidence=0.92
  issue_type=GRAMMAR
  context="Page 3: 'around 500 employees'... Page 5: 'around 300 employees'"

Processing:
  1. Confidence 0.92 > 0.60 ✓
  2. is_approximate_number("around 500", reason, context)
     → Matches APPROXIMATE_NUMBER_PATTERNS ✓
     → Reason contains "inconsistency" + "contradict" ✓ (conflict keywords)
     → return False (DON'T suppress)

Output: (True, None)
Action: KEEP this finding - it's a numerical inconsistency
```

### Example 6: Suppressed Filler Term
```
Input MergedIssue:
  original_text="etc"
  suggested_text="etc."
  reason="Missing period"
  confidence=0.75
  issue_type=PUNCTUATION

Processing:
  1. Confidence 0.75 > 0.60 ✓
  2. is_filler_term("etc")
     → Found in FILLER_TERMS ✓
     → return True (should suppress)

Output: (False, "Filler term")
Action: Suppress this finding - "etc" is always low-value
```

---

## DECISION MATRIX

| Original Text | Reason | Issue Type | Context | Keep/Suppress | Reason |
|--------------|--------|-----------|---------|--------------|--------|
| "it" | "Ambiguous pronoun" | GRAMMAR | normal | SUPPRESS | Low-value pronoun, no context |
| "they" | "Contradictory: they vs. he" | GRAMMAR | entities | KEEP | Business context (contradiction) |
| "normal" | "Generic adjective" | STYLE | normal | SUPPRESS | Generic adjective always suppressed |
| "around 500" | "Approximate number" | STYLE | normal | SUPPRESS | Intentional approximation |
| "around 500" | "Mismatch: vs. 300 on page 5" | GRAMMAR | inconsistent | KEEP | Numerical inconsistency (business) |
| "etc" | "Missing period" | PUNCTUATION | normal | SUPPRESS | Filler term always suppressed |
| "policy" | "Policy conflict noted" | GRAMMAR | compliance | KEEP | Business keyword (policy) |
| "various" | "Generic adjective" | STYLE | normal | SUPPRESS | Generic adjective always suppressed |

---

## IMPLEMENTATION CHECKLIST

- [ ] Define PRONOUNS_TO_SUPPRESS set
- [ ] Define GENERIC_ADJECTIVES set
- [ ] Define APPROXIMATE_NUMBER_PATTERNS regex list
- [ ] Define FILLER_TERMS set
- [ ] Define BUSINESS_KEYWORDS set
- [ ] Implement is_low_value_pronoun()
- [ ] Implement is_low_value_adjective()
- [ ] Implement is_approximate_number()
- [ ] Implement is_filler_term()
- [ ] Implement has_business_context()
- [ ] Implement is_business_relevant() (main decision function)
- [ ] Implement get_transparency_stats()
- [ ] Add unit tests for each rule
- [ ] Add integration tests with pipeline
- [ ] Validate suppression rate is 80-85%
- [ ] Validate business findings aren't suppressed
