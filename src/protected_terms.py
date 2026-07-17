"""
protected_terms.py
===================
Step 7: Protected Terms Builder.

Runs ONCE per document, on the full normalized text, before any spell/grammar
agent runs. Produces a set of character spans that no downstream agent's
suggestion is allowed to touch: person names, orgs, places, technical
identifiers, acronyms, citations, URLs, emails, roman numerals, etc.

This is the module that fixes the "Bently -> Bentley", "Ashish -> Hashish",
"GPUs -> Opus" class of false positive, regardless of which agent produced
the bad suggestion.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import List, Optional

import spacy

from src.config import SpacyConfig, ValidationConfig, ROOT_DIR
from src.models import ProtectedTerm

_ROMAN_NUMERAL_RE = re.compile(r"\b(?=[MDCLXVI])M{0,4}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})\b")
_URL_RE = re.compile(r"\b(?:https?://|www\.)\S+\b")
_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_CITATION_RE = re.compile(r"\(([A-Z][a-zA-Z]+(?:\s(?:&|and)\s[A-Z][a-zA-Z]+)?,?\s*\d{4}[a-z]?)\)|\[\d+(?:,\s*\d+)*\]|et al\.")
_ACRONYM_RE = re.compile(r"\b[A-Z]{2,}s?\b")  # GPUs, BLEU, ANSI
_MIXED_CASE_RE = re.compile(r"\b[a-zA-Z]*[a-z][A-Z][a-zA-Z]*\b|\b\w*\d\w*[a-zA-Z]\w*\b")  # ConvS2S, ByteNet, T5
_MATH_OPERATORS_RE = re.compile(r"[\w]+[\+\-\*/\^=<>]+[\w]+|\\(?:softmax|matmul|sin|cos|tan|log|exp|sqrt|cdot|approx|le|ge|sum|prod|alpha|beta|gamma|theta|lambda|sigma|pi|mu)\b", re.IGNORECASE)
_SUBSCRIPT_RE = re.compile(r"\b[a-zA-Z]+_[a-zA-Z0-9]+(?:\-[a-zA-Z0-9]+)*\b")
_PL_LIB_FW_RE = re.compile(
    r"\b(?:Python|Java|C|C\+\+|JavaScript|HTML|CSS|PyTorch|TensorFlow|NumPy|SciPy|spaCy|SymSpell|LanguageTool|Docling|fitz|docx|requests|transformers|vennify|T5|Ollama|JVM|JDK|JRE)\b",
    re.IGNORECASE
)
_GREEK_SYMBOLS_RE = re.compile(
    r"\b(?:alpha|beta|gamma|delta|epsilon|zeta|eta|theta|iota|kappa|lambda|mu|nu|xi|omicron|pi|rho|sigma|tau|upsilon|phi|chi|psi|omega)\b",
    re.IGNORECASE
)
_SCIENTIFIC_NOTATION_RE = re.compile(r"\b\d+(?:\.\d+)?[eE][+-]?\d+\b|\b\d+\^[-+]?\d+\b")
_FILE_NAME_RE = re.compile(r"\b[\w\-]+\.[a-zA-Z0-9]{1,4}\b")


class ProtectedTermsBuilder:
    """Builds the list of document spans that downstream agents must never modify."""

    def __init__(
        self,
        spacy_config: SpacyConfig,
        validation_config: ValidationConfig,
        whitelist_extra: Optional[List[str]] = None,
        nlp: Optional[spacy.Language] = None,
    ) -> None:
        self.nlp = nlp or spacy.load(spacy_config.model_name)
        self.protected_entity_labels = validation_config.protected_entity_labels
        self.auto_whitelist_min_occurrences = validation_config.auto_whitelist_min_occurrences
        self.whitelist_extra = set(whitelist_extra or [])

        # Load dictionary words to distinguish proper nouns/tech terms from spelling errors
        self.dict_words = set()
        self.common_words = set()
        dict_path = ROOT_DIR / "models" / "frequency_dictionary_en_82_765.txt"
        if dict_path.exists():
            try:
                with open(dict_path, "r", encoding="utf-8") as f:
                    for line in f:
                        parts = line.strip().split()
                        if len(parts) >= 2:
                            w = parts[0].lower()
                            try:
                                freq = int(parts[1])
                            except ValueError:
                                continue
                            self.dict_words.add(w)
                            if freq > 10000000:  # Threshold for very common English words
                                self.common_words.add(w)
            except Exception:
                pass

    def build(self, full_text: str) -> List[ProtectedTerm]:
        terms: List[ProtectedTerm] = []
        terms += self._named_entities(full_text)
        terms += self._regex_matches(full_text, _URL_RE, "URL")
        terms += self._regex_matches(full_text, _EMAIL_RE, "email")
        terms += self._regex_matches(full_text, _CITATION_RE, "citation/reference")
        terms += self._regex_matches(full_text, _ROMAN_NUMERAL_RE, "roman numeral", min_len=1)
        terms += self._regex_matches(full_text, _ACRONYM_RE, "ALLCAPS acronym")
        terms += self._regex_matches(full_text, _MIXED_CASE_RE, "mixedCase/technical identifier")
        terms += self._regex_matches(full_text, _MATH_OPERATORS_RE, "math operator/function")
        terms += self._regex_matches(full_text, _SUBSCRIPT_RE, "variable with subscript")
        terms += self._regex_matches(full_text, _PL_LIB_FW_RE, "programming language/library/framework")
        terms += self._regex_matches(full_text, _GREEK_SYMBOLS_RE, "greek symbol")
        terms += self._regex_matches(full_text, _SCIENTIFIC_NOTATION_RE, "scientific notation")
        terms += self._regex_matches(full_text, _FILE_NAME_RE, "file name")
        
        # Custom logic for single letter variables
        terms += self._single_letter_variables(full_text)
        
        # Author/affiliation heuristics on first page
        terms += self._author_first_page_terms(full_text)
        
        # Technical vocabulary terms
        terms += self._tech_vocabulary_terms(full_text)

        # Custom person names
        terms += self._detect_person_names(full_text)

        # Pronouns
        terms += self._detect_pronouns(full_text)

        terms += self._explicit_whitelist(full_text)
        terms += self._auto_whitelist_repeated_tokens(full_text)
        return self._dedupe(terms)

    def _named_entities(self, text: str) -> List[ProtectedTerm]:
        doc = self.nlp(text)
        return [
            ProtectedTerm(text=ent.text, char_start=ent.start_char, char_end=ent.end_char,
                          reason=f"NER:{ent.label_}")
            for ent in doc.ents if ent.label_ in self.protected_entity_labels
        ]

    @staticmethod
    def _regex_matches(text: str, pattern: re.Pattern, reason: str, min_len: int = 2) -> List[ProtectedTerm]:
        out = []
        for m in pattern.finditer(text):
            if len(m.group()) >= min_len:
                out.append(ProtectedTerm(text=m.group(), char_start=m.start(), char_end=m.end(), reason=reason))
        return out

    def _single_letter_variables(self, text: str) -> List[ProtectedTerm]:
        out = []
        for m in re.finditer(r"\b[a-zA-Z]\b", text):
            val = m.group()
            if val not in ("a", "A", "I"):
                out.append(ProtectedTerm(text=val, char_start=m.start(), char_end=m.end(), reason="single letter variable"))
        return out

    def _author_first_page_terms(self, text: str) -> List[ProtectedTerm]:
        out = []
        # Title/author block usually occupies first 2500 characters
        first_part = text[:2500]
        # Match capitalized words
        for m in re.finditer(r"\b[A-ZŁŚŹŻĆŃÓ][a-zA-Złśźżćńó']+\b", first_part):
            word = m.group()
            if word.lower() not in self.common_words:
                out.append(ProtectedTerm(text=word, char_start=m.start(), char_end=m.end(), reason="first page proper noun/author"))
        return out

    def _tech_vocabulary_terms(self, text: str) -> List[ProtectedTerm]:
        out = []
        tech_words = {
            "attention", "self-attention", "multi-head", "feed-forward", "scaled-dot",
            "encoder", "decoder", "transduction", "transformer", "sublayer", "dimension",
            "perplexity", "softmax", "residual", "normalization", "embeddings", "hyperparameters",
            "dropout", "bleu", "adam", "tensor", "codebase", "convolutional", "recurrent",
            "recurrents", "convolutions", "sequence", "sequences", "checkpoint", "tokenization",
            "tokens", "token", "vector", "vectors", "matrix", "matrices", "gradient", "gradients",
            "backpropagation", "neural", "network", "networks", "linear", "projection", "projections",
            "weight", "weights", "bias", "biases", "layer", "layers", "learning", "rate", "rates",
            "epoch", "epochs", "batch", "batches", "dataset", "datasets", "corpus", "corpora",
            "vocabulary", "vocabularies", "embedding", "parameters", "parameter", "activation",
            "activations", "regularization", "optimizer", "optimizers", "loss", "losses",
            "training", "inference", "architectures", "architecture", "model", "models",
            "baseline", "baselines", "state-of-the-art", "feedforward", "layernorm", "tensor2tensor",
            "deep", "learning", "machine", "translation", "nlp", "ai", "seq2seq", "convseq"
        }
        for w in tech_words:
            for m in re.finditer(r"\b" + re.escape(w) + r"\b", text, re.IGNORECASE):
                out.append(ProtectedTerm(text=m.group(), char_start=m.start(), char_end=m.end(), reason="DL/CS terminology"))
        return out

    def _explicit_whitelist(self, text: str) -> List[ProtectedTerm]:
        out = []
        for term in self.whitelist_extra:
            for m in re.finditer(re.escape(term), text):
                out.append(ProtectedTerm(text=term, char_start=m.start(), char_end=m.end(), reason="user whitelist"))
        return out

    def _auto_whitelist_repeated_tokens(self, text: str) -> List[ProtectedTerm]:
        """A word that looks unusual but appears identically 2+ times is far
        more likely a name/technical term than a typo (typos rarely repeat
        with the exact same misspelling across a document)."""
        tokens = re.findall(r"\b[A-Za-z][A-Za-z'-]{2,}\b", text)
        counts = Counter(w.lower() for w in tokens)
        out = []
        for tok_lower, n in counts.items():
            if n >= self.auto_whitelist_min_occurrences:
                if tok_lower in self.common_words:
                    continue
                if tok_lower in self.dict_words:
                    for m in re.finditer(r"\b" + re.escape(tok_lower) + r"\b", text, re.IGNORECASE):
                        out.append(ProtectedTerm(text=m.group(), char_start=m.start(), char_end=m.end(), reason=f"repeated {n}x valid term"))
                else:
                    for m in re.finditer(r"\b" + re.escape(tok_lower) + r"\b", text, re.IGNORECASE):
                        val = m.group()
                        if any(c.isupper() for c in val):
                            out.append(ProtectedTerm(text=val, char_start=m.start(), char_end=m.end(), reason=f"repeated {n}x proper noun/code"))
        return out

    _PRONOUNS = {
        "i", "me", "my", "mine", "myself",
        "you", "your", "yours", "yourself", "yourselves",
        "he", "him", "his", "himself",
        "she", "her", "hers", "herself",
        "it", "its", "itself",
        "we", "us", "our", "ours", "ourselves",
        "they", "them", "their", "theirs", "themselves"
    }

    def _detect_person_names(self, text: str) -> List[ProtectedTerm]:
        out = []
        # Match titles followed by capitalized names, or multiple capitalized words
        # e.g., Dr. Ramesh Kumar, John Smith, Alice Johnson
        pattern = re.compile(
            r"\b(?:Dr\.|Prof\.|Mr\.|Mrs\.|Ms\.)\s+[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*\b|"
            r"\b[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){1,2}\b"
        )
        for m in pattern.finditer(text):
            val = m.group()
            words = [w for w in re.findall(r"\b[A-Za-z]+\b", val)]
            
            # If the match starts with a common lowercase word or first word is a common noun/verb, skip
            if words:
                first_word_lower = words[0].lower()
                # Skip if the first word is a very common lowercase English word (like The, A, In, On, We, They, etc.)
                if first_word_lower in self.common_words:
                    continue
                # Also check all words; if they are all very common dictionary words in lowercase, skip
                if all(w.lower() in self.common_words for w in words):
                    continue
            
            out.append(ProtectedTerm(
                text=val,
                char_start=m.start(),
                char_end=m.end(),
                reason="person name"
            ))
        return out

    def _detect_pronouns(self, text: str) -> List[ProtectedTerm]:
        out = []
        pattern = re.compile(
            r"\b(?i:" + "|".join(re.escape(p) for p in self._PRONOUNS) + r")\b"
        )
        for m in pattern.finditer(text):
            out.append(ProtectedTerm(
                text=m.group(),
                char_start=m.start(),
                char_end=m.end(),
                reason="pronoun"
            ))
        return out

    @staticmethod
    def _dedupe(terms: List[ProtectedTerm]) -> List[ProtectedTerm]:
        seen = set()
        out = []
        for t in terms:
            key = (t.char_start, t.char_end)
            if key not in seen:
                seen.add(key)
                out.append(t)
        return sorted(out, key=lambda t: t.char_start)

    @staticmethod
    def overlaps(char_start: int, char_end: int, protected: List[ProtectedTerm]) -> Optional[ProtectedTerm]:
        for p in protected:
            if char_start < p.char_end and char_end > p.char_start:
                return p
        return None
