"""
ambiguity_taxonomy.py
========================
Single source of truth for the Ambiguity / Contextual Consistency Analysis
category taxonomy.

Before this module existed, four different, only loosely-overlapping
category lists were defined independently across the pipeline (the Claude
verification prompt, ambiguity_cluster_analyzer.py's LLM schema,
final_report_generator.py's local remap dict, and finding_filter.py's own
12-category set) -- several of which allowed Grammar/Spelling/Writing
Clarity/Undefined Term to reach the "Ambiguity Analysis" report, which is
Proofreading's territory, not this pipeline's.

Every module that assigns or re-maps a category for an ambiguity finding
must go through normalize_category() here. Anything that doesn't map to one
of APPROVED_CATEGORIES is rejected outright (returns None) -- callers must
treat that as "drop this finding", never substitute a default category.
"""

from __future__ import annotations

from typing import Optional

APPROVED_CATEGORIES = (
    "Cross-reference / contradiction",
    "Numerical inconsistency",
    "Pronoun / entity-reference ambiguity",
    "Terminology inconsistency",
    "Date / timeline inconsistency",
    "Unit / measurement inconsistency",
    "Internal factual contradiction",
    "Structural / convention inconsistency",
    "Missing / conflicting context",
)

# Categories that belong to Proofreading, never to Ambiguity Analysis.
# Listed explicitly (rather than just omitted) so the exclusion is visible
# and intentional to anyone reading this module.
_EXCLUDED_CATEGORIES = frozenset({
    "grammar issue", "grammar error", "grammar errors", "grammar",
    "spelling issue", "spelling error", "spelling errors", "spelling",
    "writing clarity", "writing quality", "writing style issues", "clarity",
    "vague wording", "ambiguities", "style", "stylistic",
    "undefined term", "undefined acronym", "acronym definition",
})

# Raw category strings actually emitted upstream (by the Claude prompt
# before this change, ambiguity_cluster_analyzer.py's LLM/fallback output,
# ambiguity_chunk_analyzer.py's LLM/fallback output, and legacy
# finding_filter.py names) mapped onto the approved taxonomy. Lookups are
# case-insensitive.
_ALIASES = {
    # Cross-reference / contradiction
    "possible contradiction": "Cross-reference / contradiction",
    "contradictory statement": "Cross-reference / contradiction",
    "contradictory statements": "Cross-reference / contradiction",
    "contradiction": "Cross-reference / contradiction",
    "contradictions": "Cross-reference / contradiction",
    "cross-reference issue": "Cross-reference / contradiction",
    "cross-reference inconsistency": "Cross-reference / contradiction",
    "cross-reference error": "Cross-reference / contradiction",
    "reference inconsistency": "Cross-reference / contradiction",
    "reference conflict": "Cross-reference / contradiction",
    "cross-reference mismatch": "Cross-reference / contradiction",
    "broken reference": "Cross-reference / contradiction",
    "cross-reference / contradiction": "Cross-reference / contradiction",

    # Numerical inconsistency
    "numeric inconsistency": "Numerical inconsistency",
    "numerical inconsistency": "Numerical inconsistency",
    "cross-chunk numerical inconsistency": "Numerical inconsistency",
    "numerical conflict": "Numerical inconsistency",
    "numerical mismatch": "Numerical inconsistency",
    "numerical ambiguity": "Numerical inconsistency",
    "numerical consistency": "Numerical inconsistency",
    "data quality": "Numerical inconsistency",

    # Pronoun / entity-reference ambiguity
    "pronoun ambiguity": "Pronoun / entity-reference ambiguity",
    "referential ambiguity": "Pronoun / entity-reference ambiguity",
    "ambiguous reference": "Pronoun / entity-reference ambiguity",
    "pronoun / entity-reference ambiguity": "Pronoun / entity-reference ambiguity",
    "entity/pronoun inconsistency": "Pronoun / entity-reference ambiguity",
    "pronoun inconsistency": "Pronoun / entity-reference ambiguity",

    # Terminology inconsistency
    "terminology conflict": "Terminology inconsistency",
    "terminology issue": "Terminology inconsistency",
    "terminology inconsistency": "Terminology inconsistency",
    "inconsistent terminology": "Terminology inconsistency",

    # Date / timeline inconsistency
    "date conflicts": "Date / timeline inconsistency",
    "date conflict": "Date / timeline inconsistency",
    "temporal ambiguity": "Date / timeline inconsistency",
    "temporal conflict": "Date / timeline inconsistency",
    "date / timeline inconsistency": "Date / timeline inconsistency",

    # Unit / measurement inconsistency
    "unit inconsistency": "Unit / measurement inconsistency",
    "unit / measurement inconsistency": "Unit / measurement inconsistency",
    "formatting inconsistency": "Unit / measurement inconsistency",

    # Internal factual contradiction
    "policy conflict": "Internal factual contradiction",
    "policy conflicts": "Internal factual contradiction",
    "policy inconsistency": "Internal factual contradiction",
    "governance inconsistency": "Internal factual contradiction",
    "business logic conflict": "Internal factual contradiction",
    "duplicate guidance": "Internal factual contradiction",
    "internal factual contradiction": "Internal factual contradiction",
    "designation inconsistency": "Internal factual contradiction",
    "designation conflict": "Internal factual contradiction",
    "internal factual contradiction / designation inconsistency": "Internal factual contradiction",

    # Structural / convention inconsistency
    "structural inconsistency": "Structural / convention inconsistency",
    "convention inconsistency": "Structural / convention inconsistency",
    "structural / convention inconsistency": "Structural / convention inconsistency",

    # Missing / conflicting context
    "missing context": "Missing / conflicting context",
    "missing information": "Missing / conflicting context",
    "missing evidence": "Missing / conflicting context",
    "unsupported claim": "Missing / conflicting context",
    "missing / conflicting context": "Missing / conflicting context",
}


def normalize_category(raw_category: Optional[str]) -> Optional[str]:
    """Maps a raw/legacy category string onto the approved taxonomy.

    Returns None if the category is unrecognized OR belongs to
    Proofreading's territory (grammar/spelling/style/vague-wording/
    undefined-term) -- callers must drop the finding in that case, never
    substitute a default category.
    """
    if not raw_category:
        return None
    key = str(raw_category).strip().lower()
    if key in _EXCLUDED_CATEGORIES:
        return None
    if key in {c.lower() for c in APPROVED_CATEGORIES}:
        # Already an approved category (case-insensitive exact match).
        for c in APPROVED_CATEGORIES:
            if c.lower() == key:
                return c
    return _ALIASES.get(key)
