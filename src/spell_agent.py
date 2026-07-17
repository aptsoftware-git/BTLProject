"""
spell_agent.py
==============

Stage 9: SymSpell Fallback Agent

LanguageTool is the primary spelling detector.

SymSpell is consulted ONLY for words that LanguageTool did not flag.

If the SymSpell dictionary is unavailable, this agent disables itself
gracefully and the pipeline continues normally.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import List, Set, Tuple

from symspellpy import SymSpell, Verbosity

from src.config import SymSpellConfig
from src.models import (
    Candidate,
    IssueType,
    Sentence,
    SourceAgent,
)

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'-]*")


class SpellAgent:

    """
    SymSpell fallback spelling detector.

    Never acts as the primary checker.

    Never crashes the pipeline.
    """

    def __init__(self, config: SymSpellConfig):

        self.config = config

        self.logger = logging.getLogger("pipeline")

        self.available = False

        self.sym_spell = SymSpell(
            max_dictionary_edit_distance=config.max_edit_distance,
            prefix_length=config.prefix_length,
        )

        dictionary = Path(config.dictionary_path)

        if not dictionary.exists():

            self.logger.warning(
                "SymSpell dictionary not found: %s",
                dictionary,
            )

            self.logger.warning(
                "SpellAgent will run in fallback-disabled mode."
            )

            return

        try:

            loaded = self.sym_spell.load_dictionary(
                str(dictionary),
                term_index=0,
                count_index=1,
            )

            if loaded:

                self.available = True

                self.logger.info(
                    "Loaded SymSpell dictionary."
                )

            else:

                self.logger.warning(
                    "Could not load SymSpell dictionary."
                )

        except Exception as exc:

            self.logger.warning(
                "Failed loading SymSpell dictionary (%s).",
                exc,
            )

            self.available = False

    ##################################################################

    def run(
        self,
        sentence: Sentence,
        already_flagged_spans: Set[Tuple[int, int]],
    ) -> List[Candidate]:

        """
        Run SymSpell ONLY on words that LanguageTool
        did not already report.
        """

        if not self.available:
            return []

        if sentence.doc_char_start is None:

            raise ValueError(
                "Sentence offsets have not been indexed."
            )

        candidates: List[Candidate] = []

        for match in _WORD_RE.finditer(sentence.text):

            word = match.group()

            if len(word) < 3:
                continue

            abs_start = sentence.doc_char_start + match.start()

            abs_end = sentence.doc_char_start + match.end()

            overlap = any(

                abs_start < end and abs_end > start

                for start, end in already_flagged_spans

            )

            if overlap:
                continue

            suggestions = self.sym_spell.lookup(

                word.lower(),

                Verbosity.TOP,

                max_edit_distance=self.config.max_edit_distance,

            )

            if not suggestions:
                continue

            best = suggestions[0]

            if best.term.lower() == word.lower():
                continue

            candidates.append(

                Candidate(

                    sentence_id=sentence.sentence_id,

                    char_start=abs_start,

                    char_end=abs_end,

                    original_text=word,

                    suggested_text=self._match_case(

                        word,

                        best.term,

                    ),

                    issue_type=IssueType.SPELLING,

                    source=SourceAgent.SYMSPELL,

                    reason="SymSpell fallback suggestion",

                    confidence=0.40,

                )

            )

        return candidates

    ##################################################################

    @staticmethod
    def _match_case(
        original: str,
        suggestion: str,
    ) -> str:

        if original.isupper():
            return suggestion.upper()

        if original.istitle():
            return suggestion.capitalize()

        return suggestion.lower()