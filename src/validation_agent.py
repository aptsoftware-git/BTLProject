"""
validation_agent.py
====================
Step 10: Validation Agent.

Single gatekeeper for EVERY candidate regardless of source (LanguageTool,
SymSpell, or the LLM). If a candidate's span overlaps a protected term, it
is dropped -- tagged, not silently discarded, so rejected.json stays useful
for debugging/demo purposes.
"""

from __future__ import annotations

from typing import List, Tuple

from src.models import Candidate, ProtectedTerm, ValidatedIssue
from src.protected_terms import ProtectedTermsBuilder
from src.utils import dataclass_kwargs


APPROVED_TYPES = {
    "spelling", "grammar", "missing_hyphen", "incorrect_hyphenation",
    "missing_space", "extra_space", "hyphenation", "spacing", "punctuation", "tense", "verb_form"
}

REJECTED_KEYWORDS = {
    "style", "rewrite", "tone", "readability", "phrasing", "reword",
    "enhancement", "content", "engaging", "concise", "formal", "clarity", "flow",
    "word choice", "paraphrase", "simplification", "preference", "british", "american"
}

BRITISH_AMERICAN_PAIRS = {
    ("fertiliser", "fertilizer"), ("fertilisers", "fertilizers"),
    ("colour", "color"), ("colours", "colors"),
    ("flavour", "flavor"), ("flavours", "flavors"),
    ("humour", "humor"), ("labour", "labor"), ("neighbour", "neighbor"), ("neighbours", "neighbors"),
    ("centre", "center"), ("centres", "centers"),
    ("theatre", "theater"), ("theatres", "theaters"),
    ("analyse", "analyze"), ("analysed", "analyzed"), ("analysing", "analyzing"),
    ("catalyse", "catalyze"), ("catalysed", "catalyzed"),
    ("organisation", "organization"), ("organisations", "organizations"),
    ("realise", "realize"), ("realised", "realized"), ("realising", "realizing"),
    ("optimise", "optimize"), ("optimised", "optimized"),
    ("prioritise", "prioritize"), ("prioritised", "prioritized"),
    ("emphasise", "emphasize"), ("emphasised", "emphasized"),
    ("licence", "license"), ("defence", "defense"), ("offence", "offense"), ("pretence", "pretense"),
    ("travelled", "traveled"), ("travelling", "traveling"),
    ("cancelled", "canceled"), ("cancelling", "canceling"),
    ("modelling", "modeling"), ("modeller", "modeler"),
    ("fulfil", "fulfill"), ("enrol", "enroll"), ("skilful", "skillful"),
    ("program", "programme"), ("catalog", "catalogue"), ("dialog", "dialogue"),
    ("analog", "analogue"), ("installment", "instalment"), ("check", "cheque")
}


import re


from src.false_positive_rejection import FalsePositiveRejectionLayer


class ValidationAgent:
    """Filters candidate corrections against protected terms and strict proofreading scope."""

    def __init__(self, protected_terms: List[ProtectedTerm]) -> None:
        self.protected_terms = protected_terms
        self.protected_texts = {p.text.lower().strip(): p for p in protected_terms if p.text}
        self.rejection_layer = FalsePositiveRejectionLayer(protected_terms)

    def _is_british_american_swap(self, orig: str, sug: str) -> bool:
        if (orig, sug) in BRITISH_AMERICAN_PAIRS or (sug, orig) in BRITISH_AMERICAN_PAIRS:
            return True
        # Heuristic for -ise / -ize, -our / -or, -re / -er suffix swaps
        if orig.endswith("ise") and sug.endswith("ize") and orig[:-3] == sug[:-3]:
            return True
        if orig.endswith("ised") and sug.endswith("ized") and orig[:-4] == sug[:-4]:
            return True
        if orig.endswith("ising") and sug.endswith("izing") and orig[:-5] == sug[:-5]:
            return True
        if orig.endswith("our") and sug.endswith("or") and orig[:-3] == sug[:-2]:
            return True
        if orig.endswith("re") and sug.endswith("er") and orig[:-2] == sug[:-2]:
            return True
        return False

    def _find_protected_match(self, orig_lower: str, sug_lower: str, char_start: Optional[int], char_end: Optional[int]) -> Optional[ProtectedTerm]:
        # 1. Span-based overlap check
        if char_start is not None and char_end is not None and char_start >= 0 and char_end > char_start:
            hit = ProtectedTermsBuilder.overlaps(char_start, char_end, self.protected_terms)
            if hit:
                return hit

        if not orig_lower:
            return None

        # 2. Exact string match check
        if orig_lower in self.protected_texts:
            return self.protected_texts[orig_lower]
        if sug_lower in self.protected_texts:
            return self.protected_texts[sug_lower]

        # 3. Multi-word phrase containment check (e.g. "hydel" inside protected term "hydel plant")
        for term_text_lower, term_obj in self.protected_texts.items():
            words = set(re.findall(r"\b[A-Za-z0-9'-]+\b", term_text_lower))
            if len(words) > 1:
                if orig_lower in words or sug_lower in words:
                    return term_obj

        return None

    def validate(self, candidates: List[Candidate | dict]) -> Tuple[List[ValidatedIssue], List[ValidatedIssue]]:
        """Returns (accepted, rejected)."""
        accepted: List[ValidatedIssue] = []
        rejected: List[ValidatedIssue] = []
        for item in candidates:
            candidate = Candidate(**item) if isinstance(item, dict) else item
            orig = (candidate.original_text or "").strip()
            sug = (candidate.suggested_text or "").strip()
            orig_lower = orig.lower()
            sug_lower = sug.lower()
            type_str = str(candidate.issue_type or "").lower()
            reason_str = str(candidate.reason or "").lower()

            # Run False Positive Rejection Layer check
            is_rejected, reject_reason, _ = self.rejection_layer.evaluate_candidate(
                original=orig,
                suggestion=sug,
                sentence_text="",
                issue_type=type_str,
                source=str(candidate.source),
                confidence=candidate.confidence,
                char_start=candidate.char_start,
                char_end=candidate.char_end,
            )

            if not is_rejected:
                hit = self._find_protected_match(orig_lower, sug_lower, candidate.char_start, candidate.char_end)
                if hit:
                    is_rejected = True
                    reason_name = str(hit.reason or "PROTECTED_TERM").upper().replace(" ", "_")
                    reject_reason = f"PROTECTED_{reason_name}"
                elif self._is_british_american_swap(orig_lower, sug_lower):
                    is_rejected = True
                    reject_reason = "Out of Scope (British/American Spelling Preference)"
                elif any(kw in type_str or kw in reason_str for kw in REJECTED_KEYWORDS):
                    is_rejected = True
                    reject_reason = "Out of Scope (Style/Tone/Rewrite Suggestion)"
                elif orig_lower == sug_lower and len(orig_lower) > 0:
                    is_rejected = True
                    reject_reason = "Out of Scope (Capitalization Preference Only)"

            issue = ValidatedIssue(
                **dataclass_kwargs(candidate),
                is_protected=is_rejected,
                protected_reason=reject_reason,
            )
            if is_rejected:
                rejected.append(issue)
            else:
                accepted.append(issue)
        return accepted, rejected
