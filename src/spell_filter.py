"""
spell_filter.py
===============
High-Precision Spell Candidate Protection and Filtering Stage.

Optimized Flow:
  06_spell/spell_candidates.json
          ↓
  Extract unique sentence_ids from spell_candidates.json
          ↓
  Retrieve corresponding full sentences from 04_sentences/sentences.json
          ↓
  Process ONCE with spaCy nlp.pipe(batch_size=64)
          ↓
  06_spell/ner_entities.json (PERSON, ORG, GPE, LOC, FAC, PRODUCT, EVENT, NORP)
          ↓
  Build 06_spell/protected_terms.json
          ↓
  Multi-layer Precision Validation Gate:
    • OCR artifacts, single letters, ordinals, roman numerals
    • Acronyms & short codes
    • Sentence & Document-level NER entity shielding
    • Canonical corporate, geographic, and legal vocabularies
    • Domain, engineering, financial, and technical dictionaries
    • Document-level repeated terminology
    • Valid English dictionary word gate
    • Strict Levenshtein edit-distance threshold (<= 2 for short words)
          ↓
  06_spell/filtered_spell_candidates.json (Retained genuine spelling errors only)
  06_spell/rejected_spell_candidates.json (Full audit log with explicit rejection reasons)
"""

from __future__ import annotations

import re
import string
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import spacy
from symspellpy import SymSpell, Verbosity

from src.config import SpacyConfig, ROOT_DIR
from src.domain_words import VALID_DOMAIN_WORDS, is_valid_domain_term
from src.models import Candidate, IssueType, Sentence
from src.utils import load_json, save_json


# ---------------------------------------------------------------------------
# Canonical Gazetteers & Known Proper Vocabularies
# ---------------------------------------------------------------------------

CANONICAL_COUNTRIES: Set[str] = {
    "afghanistan", "albania", "algeria", "andorra", "angola", "argentina", "armenia",
    "australia", "austria", "azerbaijan", "bahamas", "bahrain", "bangladesh", "barbados",
    "belarus", "belgium", "belize", "benin", "bhutan", "bolivia", "bosnia", "botswana",
    "brazil", "brunei", "bulgaria", "burkina faso", "burundi", "cambodia", "cameroon",
    "canada", "chile", "china", "colombia", "congo", "costa rica", "croatia", "cuba",
    "cyprus", "czech republic", "denmark", "djibouti", "dominica", "ecuador", "egypt",
    "estonia", "ethiopia", "fiji", "finland", "france", "gabon", "gambia", "georgia",
    "germany", "ghana", "greece", "grenada", "guatemala", "guinea", "guyana", "haiti",
    "honduras", "hungary", "iceland", "india", "indonesia", "iran", "iraq", "ireland",
    "israel", "italy", "jamaica", "japan", "jordan", "kazakhstan", "kenya", "kuwait",
    "kyrgyzstan", "laos", "latvia", "lebanon", "lesotho", "liberia", "libya", "lithuania",
    "luxembourg", "madagascar", "malawi", "malaysia", "maldives", "mali", "malta",
    "mauritius", "mexico", "moldova", "monaco", "mongolia", "montenegro", "morocco",
    "mozambique", "myanmar", "namibia", "nepal", "netherlands", "new zealand", "nicaragua",
    "niger", "nigeria", "north korea", "norway", "oman", "pakistan", "panama", "paraguay",
    "peru", "philippines", "poland", "portugal", "qatar", "romania", "russia", "rwanda",
    "saudi arabia", "senegal", "serbia", "seychelles", "singapore", "slovakia", "slovenia",
    "somalia", "south africa", "south korea", "spain", "sri lanka", "sudan", "sweden",
    "switzerland", "syria", "taiwan", "tajikistan", "tanzania", "thailand", "togo",
    "trinidad and tobago", "tunisia", "turkey", "turkmenistan", "uganda", "ukraine",
    "united arab emirates", "united kingdom", "united states", "uruguay", "uzbekistan",
    "vatican", "venezuela", "vietnam", "yemen", "zambia", "zimbabwe"
}

CANONICAL_INDIAN_LOCATIONS: Set[str] = {
    "deoghar", "kolkata", "mumbai", "delhi", "bengaluru", "chennai", "hyderabad",
    "ahmedabad", "pune", "kovalam", "trivandrum", "thiruvananthapuram", "ranchi",
    "dhanbad", "jamshedpur", "bokaro", "patna", "bhubaneswar", "cuttack", "guwahati",
    "jaipur", "lucknow", "kanpur", "nagpur", "indore", "bhopal", "chandigarh", "surat",
    "vadodara", "durgapur", "asansol", "siliguri", "howrah", "jharkhand", "west bengal",
    "bengal", "odisha", "bihar", "assam", "maharashtra", "gujarat", "karnataka",
    "tamil nadu", "kerala", "andhra pradesh", "telangana", "uttar pradesh",
    "madhya pradesh", "rajasthan", "punjab", "haryana", "uttarakhand", "himachal pradesh",
    "goa", "sikkim", "tripura", "meghalaya", "manipur", "nagaland", "mizoram",
    "secunderabad", "visakhapatnam", "kochi", "coimbatore", "mysore", "mysuru"
}

CANONICAL_CORPORATE_ENTITIES: Set[str] = {
    "todi", "ravi todi", "s.k. todi", "fitchner", "fichtner", "fichtner consulting",
    "btl", "btl epc", "btl epc limited", "bengal tools", "bengal tools limited",
    "shrachi", "shrachi group", "wartsila", "wurtsila", "vertexa", "tata", "birla",
    "adani", "ambani", "godrej", "bajaj", "mahindra", "l&t", "larsentoubro", "bhel",
    "ntpc", "powergrid", "nhpc", "sjvn", "thdc", "eesl", "seci", "dvc", "cesc",
    "wbsedcl", "wbsetcl", "jusnl", "bsphcl", "uppcl", "siemens", "alstom", "abb",
    "schneider", "toshiba", "hitachi", "ge", "technip", "kpmg", "pwc", "deloitte", "ey",
    "infosys", "tcs", "wipro", "hcl", "cognizant", "tech mahindra", "bagra", "ambedkar",
    "sail", "gail", "ongc", "iocnl", "boc", "vedanta", "hindalco", "jsw", "jindal"
}

KNOWN_ACRONYMS: Set[str] = {
    "cnc", "epc", "treds", "btl", "scada", "hvdc", "nse", "bse", "sebi", "rbi",
    "irdai", "gst", "gstin", "pan", "tan", "cin", "din", "llp", "huf", "epfo",
    "esic", "nsdl", "cdsl", "cibil", "isin", "lei", "npa", "crar", "slr", "crr",
    "nbfc", "aif", "reit", "invit", "sgb", "etf", "fii", "dii", "fpi", "fdi",
    "fema", "pmla", "sarfaesi", "ibc", "nclt", "nclat", "sat", "cci", "trai",
    "dgca", "fssai", "peso", "cea", "cerc", "serc", "posoco", "grid-india",
    "rldc", "sldc", "nldc", "statcom", "facts", "plc", "dcs", "rtu", "ied",
    "gis", "ais", "bess", "ppa", "psa", "discom", "genco", "transco", "appc",
    "rec", "escert", "pat", "rpo", "rgo", "mop", "mnre", "niti", "aayog",
    "cpri", "mw", "kw", "gw", "kv", "kva", "mva", "mvar", "hz", "ebitda",
    "ebit", "pbt", "roce", "roe", "cagr", "o&m", "boq", "loa", "loi", "jv",
    "spv", "emd", "bg", "pbg", "lc", "b2b", "b2c", "oem", "oems", "udin",
    "icai", "mca", "rera", "fy20", "fy21", "fy22", "fy23", "fy24", "fy25", "fy26",
    "q1", "q2", "q3", "q4", "yoy", "qoq", "csr", "inr", "usd", "eur", "gbp",
    "pvt", "ltd", "inc", "corp", "co", "mfg", "sqft", "sqm", "nos", "no", "dr",
    "ca", "cs", "cma", "agm", "egm", "roc", "tds", "tcs", "it", "ot", "iot"
}

ROMAN_NUMERALS: Set[str] = {
    "i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x",
    "xi", "xii", "xiii", "xiv", "xv", "xvi", "xvii", "xviii", "xix", "xx"
}

BRITISH_AMERICAN_PAIRS: Set[Tuple[str, str]] = {
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
    ("analog", "analogue"), ("installment", "instalment"), ("check", "cheque"),
    ("behavior", "behaviour"), ("favour", "favor"), ("honour", "honor")
}


def _levenshtein_distance(s1: str, s2: str) -> int:
    """Compute Levenshtein edit distance between two strings."""
    if len(s1) < len(s2):
        return _levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]


def _is_british_american_swap(orig: str, sug: str) -> bool:
    orig_l, sug_l = orig.lower(), sug.lower()
    if (orig_l, sug_l) in BRITISH_AMERICAN_PAIRS or (sug_l, orig_l) in BRITISH_AMERICAN_PAIRS:
        return True
    if orig_l.endswith("ise") and sug_l.endswith("ize") and orig_l[:-3] == sug_l[:-3]:
        return True
    if orig_l.endswith("ised") and sug_l.endswith("ized") and orig_l[:-4] == sug_l[:-4]:
        return True
    if orig_l.endswith("ising") and sug_l.endswith("izing") and orig_l[:-5] == sug_l[:-5]:
        return True
    if orig_l.endswith("our") and sug_l.endswith("or") and orig_l[:-3] == sug_l[:-2]:
        return True
    if orig_l.endswith("re") and sug_l.endswith("er") and orig_l[:-2] == sug_l[:-2]:
        return True
    return False


_DICT_WORDS_CACHE: Optional[Set[str]] = None
_COMMON_WORDS_CACHE: Optional[Set[str]] = None
_DOMAIN_DICT_CACHE: Optional[Set[str]] = None
_SYM_SPELL_CACHE: Optional[SymSpell] = None


def get_cached_dictionaries() -> Tuple[Set[str], Set[str], Set[str]]:
    """Cache loaded frequency and domain dictionaries in memory for high-throughput multi-page jobs."""
    global _DICT_WORDS_CACHE, _COMMON_WORDS_CACHE, _DOMAIN_DICT_CACHE
    if _DICT_WORDS_CACHE is None or _COMMON_WORDS_CACHE is None or _DOMAIN_DICT_CACHE is None:
        dict_words: Set[str] = set()
        common_words: Set[str] = set()
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
                                dict_words.add(w)
                                if freq > 1000000:
                                    common_words.add(w)
                            except ValueError:
                                continue
            except Exception:
                pass

        domain_dict_terms: Set[str] = set()
        domain_dict_path = ROOT_DIR / "data" / "domain_dictionary.json"
        if domain_dict_path.exists():
            try:
                data = load_json(domain_dict_path)
                if isinstance(data, list):
                    domain_dict_terms = {str(item).lower().strip() for item in data}
            except Exception:
                pass

        _DICT_WORDS_CACHE = dict_words
        _COMMON_WORDS_CACHE = common_words
        _DOMAIN_DICT_CACHE = domain_dict_terms

    return _DICT_WORDS_CACHE, _COMMON_WORDS_CACHE, _DOMAIN_DICT_CACHE


def get_cached_symspell() -> Optional[SymSpell]:
    """Cache SymSpell dictionary instance for spelling suggestions."""
    global _SYM_SPELL_CACHE
    if _SYM_SPELL_CACHE is None:
        try:
            dict_path = ROOT_DIR / "models" / "frequency_dictionary_en_82_765.txt"
            if dict_path.exists():
                ss = SymSpell(max_dictionary_edit_distance=2, prefix_length=7)
                if ss.load_dictionary(str(dict_path), term_index=0, count_index=1):
                    _SYM_SPELL_CACHE = ss
        except Exception:
            _SYM_SPELL_CACHE = None
    return _SYM_SPELL_CACHE


class SpellCandidateFilter:
    """
    High-Precision Protection and Filtering Engine for Spell Checking Candidates.
    """

    PROTECTED_NER_LABELS = {
        "PERSON", "ORG", "GPE", "LOC", "FAC", "PRODUCT", "EVENT", "NORP", "LAW", "WORK_OF_ART",
        "MONEY", "PERCENT", "DATE", "TIME", "QUANTITY", "CARDINAL", "ORDINAL"
    }

    _ACRONYM_REGEX = re.compile(r"\b[A-Z0-9/&.-]{2,}s?\b")
    _SLASH_ACRONYM_REGEX = re.compile(r"^[A-Z0-9]+(?:/[A-Z0-9]+)+$")
    _ABBREV_REGEX = re.compile(r"\b(?:Pvt|Ltd|Co|Inc|Corp|Govt|Dr|Prof|Mr|Mrs|Ms|Shri|Smt|Er|Adv)\.?\b", re.IGNORECASE)
    _DOTTED_NAME_REGEX = re.compile(r"\b(?:[A-Z]\.){1,4}\s*([A-Z][a-zA-Z]+)\b")
    _ADDRESS_SUFFIX_REGEX = re.compile(
        r"\b([A-Z][a-zA-Z]+)\s+(?:Marg|Road|Rd\.?|Street|St\.?|Nagar|Chowk|Colony|Society|Estate|Vihar|Puram|Bagh|Circle|Lane)\b"
    )
    _ORDINAL_REGEX = re.compile(r"^\d+(?:st|nd|rd|th)$", re.IGNORECASE)

    def __init__(
        self,
        spacy_config: Optional[SpacyConfig] = None,
        nlp: Optional[spacy.Language] = None,
        whitelist_extra: Optional[Set[str]] = None,
    ) -> None:
        self.spacy_config = spacy_config or SpacyConfig()
        if nlp is not None:
            self.nlp = nlp
        else:
            try:
                self.nlp = spacy.load(self.spacy_config.model_name)
            except Exception:
                self.nlp = None

        self.whitelist_extra = set(whitelist_extra or [])
        self.dict_words, self.common_words, self.domain_dict_terms = get_cached_dictionaries()
        self.sym_spell = get_cached_symspell()

    def is_candidate_pre_rejected(self, cand: Candidate | dict) -> Optional[str]:
        """
        Fast lightweight pre-check to identify items that are definitely not genuine spelling errors
        before running spaCy NER. Returns rejection reason string if pre-rejected, else None.
        """
        orig = (getattr(cand, "original_text", None) or (cand.get("original_text") if isinstance(cand, dict) else "") or "").strip()
        sug = (getattr(cand, "suggested_text", None) or (cand.get("suggested_text") if isinstance(cand, dict) else "") or "").strip()
        orig_lower = orig.lower()
        sug_lower = sug.lower()

        # Check 0: Genuine Typo of Canonical Country or Location -> do not pre-reject!
        is_genuine_proper_misspelling = (
            (sug_lower in CANONICAL_COUNTRIES and orig_lower not in CANONICAL_COUNTRIES and _levenshtein_distance(orig_lower, sug_lower) <= 2) or
            (sug_lower in CANONICAL_INDIAN_LOCATIONS and orig_lower not in CANONICAL_INDIAN_LOCATIONS and _levenshtein_distance(orig_lower, sug_lower) <= 2)
        )
        if is_genuine_proper_misspelling:
            return None

        # 1. OCR Artifacts, Single-Letter Fragments, Symbols, Numbers, Financial Values
        if len(orig) < 2:
            return "SINGLE_LETTER_OR_OCR_ARTIFACT"
        if not re.search(r"[A-Za-z]", orig):
            return "NUMERIC_OR_SYMBOL_TOKEN"
        if re.search(r"\d", orig) or self._ORDINAL_REGEX.match(orig):
            return "ORDINAL_OR_NUMERIC_CODE"
        if orig_lower in ROMAN_NUMERALS:
            return "ROMAN_NUMERAL"

        # Financial, Currency, Percentage, Date & Measurement Unit expressions
        from src.false_positive_rejection import FalsePositiveRejectionLayer
        fin_reason = FalsePositiveRejectionLayer.is_protected_financial_or_numeric_expression(orig)
        if fin_reason:
            return fin_reason

        # 2. Capitalization / British-American Swap
        if orig_lower == sug_lower and len(orig_lower) > 0:
            return "CAPITALIZATION_PREFERENCE"
        if _is_british_american_swap(orig, sug):
            return "BRITISH_AMERICAN_PREFERENCE"

        # 3. Acronyms & Short Codes
        if (orig.isupper() and len(orig) >= 2) or "/" in orig or orig_lower in KNOWN_ACRONYMS:
            return "ACRONYM"
        if self._SLASH_ACRONYM_REGEX.match(orig):
            return "ACRONYM"

        # 4. Canonical Corporate, Place, & Person Names
        if orig_lower in CANONICAL_CORPORATE_ENTITIES:
            return "ORG_ENTITY" if orig_lower in {"btl", "btl epc", "fitchner", "fichtner", "wartsila", "shrachi", "vertexa"} else "PERSON_ENTITY"
        if orig_lower in CANONICAL_INDIAN_LOCATIONS or orig_lower in CANONICAL_COUNTRIES:
            return "GPE_ENTITY"

        # 5. Domain Terminology
        if is_valid_domain_term(orig_lower) or orig_lower in self.domain_dict_terms:
            return "DOMAIN_TERM"

        # 6. Abbreviations
        if self._ABBREV_REGEX.search(orig):
            return "ABBREVIATION"

        # 7. Valid English Dictionary Words
        if orig_lower in self.dict_words and orig_lower not in {"occuring", "recieve", "seperate", "untill", "definately"}:
            return "VALID_DICTIONARY_WORD"

        return None

    def extract_ner_entities(self, sentences: List[Sentence], batch_size: int = 64) -> List[Dict[str, Any]]:
        """Run spaCy NER ONCE over unique candidate sentences using nlp.pipe(batch_size=64)."""
        if not self.nlp or not sentences:
            return []

        texts = [s.text for s in sentences]
        docs = list(self.nlp.pipe(texts, batch_size=batch_size))

        ner_entities: List[Dict[str, Any]] = []

        for sent, doc in zip(sentences, docs):
            for ent in doc.ents:
                if ent.label_ in self.PROTECTED_NER_LABELS:
                    ent_text = ent.text.strip()
                    if not ent_text:
                        continue
                    doc_start = (sent.doc_char_start + ent.start_char) if sent.doc_char_start is not None else None
                    doc_end = (sent.doc_char_start + ent.end_char) if sent.doc_char_start is not None else None
                    ner_entities.append({
                        "sentence_id": sent.sentence_id,
                        "text": ent_text,
                        "label": ent.label_,
                        "start_char": ent.start_char,
                        "end_char": ent.end_char,
                        "doc_char_start": doc_start,
                        "doc_char_end": doc_end,
                        "page": sent.page
                    })

        return ner_entities

    def build_protected_terms(
        self,
        sentences: List[Sentence],
        ner_entities: List[Dict[str, Any]],
        extra_whitelist: Optional[Set[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Build a comprehensive, deduplicated protected terms registry."""
        protected_list: List[Dict[str, Any]] = []
        seen_keys: Set[Tuple[str, str]] = set()

        def add_term(text: str, category: str, reason: str, sid: Optional[int] = None, d_start: Optional[int] = None, d_end: Optional[int] = None):
            t_clean = text.strip()
            if not t_clean or len(t_clean) < 2:
                return
            key = (t_clean.lower(), category)
            if key not in seen_keys:
                seen_keys.add(key)
                protected_list.append({
                    "text": t_clean,
                    "category": category,
                    "reason": reason,
                    "sentence_id": sid,
                    "doc_char_start": d_start,
                    "doc_char_end": d_end
                })

        # 1. NER Entities
        for ent in ner_entities:
            lbl = ent.get("label", "ENTITY")
            add_term(
                text=ent["text"],
                category=f"{lbl}_ENTITY",
                reason=f"{lbl}_ENTITY",
                sid=ent.get("sentence_id"),
                d_start=ent.get("doc_char_start"),
                d_end=ent.get("doc_char_end")
            )

        # 2. Canonical Vocabularies
        for country in CANONICAL_COUNTRIES:
            add_term(country.title(), "GPE_ENTITY", "CANONICAL_GPE")
        for loc in CANONICAL_INDIAN_LOCATIONS:
            add_term(loc.title(), "GPE_ENTITY", "CANONICAL_LOCATION")
        for corp in CANONICAL_CORPORATE_ENTITIES:
            add_term(corp.title() if not corp.isupper() else corp, "ORG_ENTITY", "CANONICAL_CORPORATE_ENTITY")
        for acr in KNOWN_ACRONYMS:
            add_term(acr.upper(), "ACRONYM", "ACRONYM")
        for dom in VALID_DOMAIN_WORDS:
            add_term(dom, "DOMAIN_TERM", "DOMAIN_DICTIONARY_TERM")
        for dom in self.domain_dict_terms:
            add_term(dom, "DOMAIN_TERM", "DOMAIN_DICTIONARY_TERM")

        # 3. Sentence Scan for Acronyms, Multi-Word Proper Terms & Repeated Tokens
        full_text = " ".join([s.text for s in sentences])
        all_tokens = re.findall(r"\b[A-Za-z0-9/&'-]{2,}s?\b", full_text)
        token_counts = Counter(w.lower() for w in all_tokens)

        for sent in sentences:
            s_text = sent.text
            # Acronyms & slash acronyms
            for m in self._ACRONYM_REGEX.finditer(s_text):
                val = m.group()
                if (val.isupper() and len(val) >= 2) or "/" in val or val.lower() in KNOWN_ACRONYMS:
                    d_start = (sent.doc_char_start + m.start()) if sent.doc_char_start is not None else None
                    d_end = (sent.doc_char_start + m.end()) if sent.doc_char_start is not None else None
                    add_term(val, "ACRONYM", "ACRONYM", sent.sentence_id, d_start, d_end)

            # Dotted abbrev proper nouns
            for m in self._DOTTED_NAME_REGEX.finditer(s_text):
                val = m.group(1)
                if val.lower() not in self.common_words:
                    d_start = (sent.doc_char_start + m.start(1)) if sent.doc_char_start is not None else None
                    d_end = (sent.doc_char_start + m.end(1)) if sent.doc_char_start is not None else None
                    add_term(val, "PROPER_NOUN", "PROPER_NOUN_DOTTED_INITIAL", sent.sentence_id, d_start, d_end)

            # Address suffix locations
            for m in self._ADDRESS_SUFFIX_REGEX.finditer(s_text):
                val = m.group(1)
                if val.lower() not in self.common_words:
                    d_start = (sent.doc_char_start + m.start(1)) if sent.doc_char_start is not None else None
                    d_end = (sent.doc_char_start + m.end(1)) if sent.doc_char_start is not None else None
                    add_term(val, "LOC_ENTITY", "ADDRESS_LOCALITY_TERM", sent.sentence_id, d_start, d_end)

        # 4. Repeated Proper Terms (Document-level vocabulary)
        for tok_lower, count in token_counts.items():
            if count >= 2 and tok_lower not in self.common_words:
                if tok_lower in CANONICAL_CORPORATE_ENTITIES or tok_lower in CANONICAL_INDIAN_LOCATIONS:
                    add_term(tok_lower.title(), "PROPER_NOUN", "REPEATED_PROPER_TERM")
                elif any(c.isupper() for c in tok_lower):
                    add_term(tok_lower, "PROPER_NOUN", "REPEATED_PROPER_TERM")

        # 5. Whitelists
        all_whitelist = self.whitelist_extra.union(extra_whitelist or set())
        for wl in all_whitelist:
            add_term(wl, "WHITELIST", "USER_WHITELIST")

        return protected_list

    def filter_candidates(
        self,
        candidates: List[Candidate | dict],
        sentences: List[Sentence],
        ner_entities: List[Dict[str, Any]],
        protected_terms: List[Dict[str, Any]],
    ) -> Tuple[List[Candidate], List[Dict[str, Any]]]:
        """
        Match each candidate in spell_candidates.json against precomputed NER entities,
        canonical dictionaries, strict edit-distance rules, and protected terms.
        """
        # Lookup indices
        sentence_map: Dict[int, Sentence] = {s.sentence_id: s for s in sentences}
        entities_by_sentence: Dict[int, List[Dict[str, Any]]] = {}
        for ent in ner_entities:
            sid = ent.get("sentence_id")
            if sid is not None:
                entities_by_sentence.setdefault(sid, []).append(ent)

        # Build document-wide entity & protected text dictionaries
        doc_entities_lower: Dict[str, str] = {}
        for ent in ner_entities:
            t = ent["text"].strip().lower()
            if t:
                doc_entities_lower[t] = f"{ent['label']}_ENTITY"

        protected_texts_lower: Dict[str, str] = {}
        for pt in protected_terms:
            t = pt["text"].strip().lower()
            if t:
                protected_texts_lower[t] = pt.get("reason", pt.get("category", "PROTECTED_TERM"))

        accepted_candidates: List[Candidate] = []
        rejected_records: List[Dict[str, Any]] = []

        for item in candidates:
            cand = Candidate(**item) if isinstance(item, dict) else item
            orig = (cand.original_text or "").strip()
            sug = (cand.suggested_text or "").strip()
            orig_lower = orig.lower()
            sug_lower = sug.lower()
            sid = cand.sentence_id

            rejection_reason: Optional[str] = None
            matched_term: Optional[str] = None

            # If suggested_text is empty, consult SymSpell for correction suggestion
            if not sug and self.sym_spell is not None:
                suggestions = self.sym_spell.lookup(orig_lower, Verbosity.TOP, max_edit_distance=2)
                if suggestions:
                    cand.suggested_text = suggestions[0].term
                    sug = cand.suggested_text
                    sug_lower = sug.lower()

            if not sug and not rejection_reason:
                rejection_reason = "NO_VALID_CORRECTION_SUGGESTION"
                matched_term = orig

            # ---------------------------------------------------------
            # Check 0: Genuine Typo of Canonical Country or Location
            # E.g. "Bangaldesh" -> "Bangladesh" (edit distance <= 2)
            # ---------------------------------------------------------
            is_genuine_proper_misspelling = (
                (sug_lower in CANONICAL_COUNTRIES and orig_lower not in CANONICAL_COUNTRIES and _levenshtein_distance(orig_lower, sug_lower) <= 2) or
                (sug_lower in CANONICAL_INDIAN_LOCATIONS and orig_lower not in CANONICAL_INDIAN_LOCATIONS and _levenshtein_distance(orig_lower, sug_lower) <= 2)
            )

            # ---------------------------------------------------------
            # 1. OCR Artifacts, Single-Letter Fragments, Symbols, Numbers, Financial Values
            # ---------------------------------------------------------
            if not rejection_reason:
                if len(orig) < 2:
                    rejection_reason = "SINGLE_LETTER_OR_OCR_ARTIFACT"
                    matched_term = orig
                elif not re.search(r"[A-Za-z]", orig):
                    rejection_reason = "NUMERIC_OR_SYMBOL_TOKEN"
                    matched_term = orig
                elif re.search(r"\d", orig) or self._ORDINAL_REGEX.match(orig):
                    rejection_reason = "ORDINAL_OR_NUMERIC_CODE"
                    matched_term = orig
                elif orig_lower in ROMAN_NUMERALS:
                    rejection_reason = "ROMAN_NUMERAL"
                    matched_term = orig
                else:
                    from src.false_positive_rejection import FalsePositiveRejectionLayer
                    sent_obj = sentence_map.get(sid)
                    s_text = sent_obj.text if sent_obj else ""
                    fin_reason = FalsePositiveRejectionLayer.is_protected_financial_or_numeric_expression(orig, s_text)
                    if fin_reason:
                        rejection_reason = fin_reason
                        matched_term = orig

            # ---------------------------------------------------------
            # 2. Trivial Identical / Capitalization / British-American Swap
            # ---------------------------------------------------------
            if not rejection_reason:
                if orig_lower == sug_lower:
                    rejection_reason = "CAPITALIZATION_PREFERENCE"
                    matched_term = orig
                elif _is_british_american_swap(orig, sug):
                    rejection_reason = "BRITISH_AMERICAN_PREFERENCE"
                    matched_term = orig

            # ---------------------------------------------------------
            # 3. Acronyms & Short Codes (e.g. CNC, EPC, TREDS, CNC/EPC/TREDS)
            # ---------------------------------------------------------
            if not rejection_reason:
                if (orig.isupper() and len(orig) >= 2) or "/" in orig or orig_lower in KNOWN_ACRONYMS:
                    rejection_reason = "ACRONYM"
                    matched_term = orig
                elif self._SLASH_ACRONYM_REGEX.match(orig):
                    rejection_reason = "ACRONYM"
                    matched_term = orig

            # ---------------------------------------------------------
            # 4. Canonical Corporate, Place, & Person Names
            # ---------------------------------------------------------
            if not rejection_reason and not is_genuine_proper_misspelling:
                if orig_lower in CANONICAL_CORPORATE_ENTITIES:
                    rejection_reason = "ORG_ENTITY" if orig_lower in {"btl", "btl epc", "fitchner", "fichtner", "wartsila", "shrachi", "vertexa"} else "PERSON_ENTITY"
                    matched_term = orig
                elif orig_lower in CANONICAL_INDIAN_LOCATIONS:
                    rejection_reason = "GPE_ENTITY"
                    matched_term = orig
                elif orig_lower in CANONICAL_COUNTRIES:
                    rejection_reason = "GPE_ENTITY"
                    matched_term = orig

            # ---------------------------------------------------------
            # 5. Sentence-Level NER Entity Overlap (sentence_id match)
            # ---------------------------------------------------------
            if not rejection_reason and not is_genuine_proper_misspelling and sid in entities_by_sentence:
                sent_ents = entities_by_sentence[sid]
                for ent in sent_ents:
                    ent_text = ent["text"]
                    ent_lbl = ent["label"]
                    ent_lower = ent_text.lower()

                    if orig_lower == ent_lower or orig_lower in ent_lower.split():
                        rejection_reason = f"{ent_lbl}_ENTITY"
                        matched_term = ent_text
                        break

                    if cand.char_start is not None and cand.char_end is not None:
                        e_start = ent.get("doc_char_start")
                        e_end = ent.get("doc_char_end")
                        if e_start is not None and e_end is not None:
                            if cand.char_start < e_end and cand.char_end > e_start:
                                rejection_reason = f"{ent_lbl}_ENTITY"
                                matched_term = ent_text
                                break

            # ---------------------------------------------------------
            # 6. Document-Wide NER Entities
            # ---------------------------------------------------------
            if not rejection_reason and not is_genuine_proper_misspelling and orig_lower in doc_entities_lower:
                rejection_reason = doc_entities_lower[orig_lower]
                matched_term = orig

            # ---------------------------------------------------------
            # 7. Domain Terminology & Protected Terms Registry Match
            # ---------------------------------------------------------
            if not rejection_reason:
                if is_valid_domain_term(orig_lower) or orig_lower in self.domain_dict_terms:
                    rejection_reason = "DOMAIN_TERM"
                    matched_term = orig
                elif orig_lower in protected_texts_lower and not is_genuine_proper_misspelling:
                    rejection_reason = protected_texts_lower[orig_lower]
                    matched_term = orig
                elif sug_lower in protected_texts_lower and not is_genuine_proper_misspelling and not orig.islower():
                    rejection_reason = protected_texts_lower[sug_lower]
                    matched_term = sug

            # ---------------------------------------------------------
            # 8. Abbreviations / Dotted Initial Terms
            # ---------------------------------------------------------
            if not rejection_reason:
                if self._ABBREV_REGEX.search(orig):
                    rejection_reason = "ABBREVIATION"
                    matched_term = orig

            # ---------------------------------------------------------
            # 9. Valid English Word Gate (Never flag valid dictionary words as typos)
            # ---------------------------------------------------------
            if not rejection_reason:
                if orig_lower in self.dict_words and orig_lower not in {"occuring", "recieve", "seperate", "untill", "definately"}:
                    rejection_reason = "VALID_DICTIONARY_WORD"
                    matched_term = orig

            # ---------------------------------------------------------
            # 10. Strict Levenshtein Edit-Distance & Confidence Gate
            # ---------------------------------------------------------
            if not rejection_reason:
                dist = _levenshtein_distance(orig_lower, sug_lower)
                # Short words (<= 6 chars) must have edit distance <= 2; longer <= 3
                max_allowed_dist = 2 if len(orig) <= 6 else 3
                if dist > max_allowed_dist or dist == 0:
                    rejection_reason = "HIGH_EDIT_DISTANCE_OR_UNRELIABLE"
                    matched_term = f"dist={dist}"

            # ---------------------------------------------------------
            # Decision
            # ---------------------------------------------------------
            if rejection_reason:
                rejected_records.append({
                    "sentence_id": cand.sentence_id,
                    "original_text": cand.original_text,
                    "suggested_text": cand.suggested_text,
                    "char_start": cand.char_start,
                    "char_end": cand.char_end,
                    "issue_type": cand.issue_type,
                    "source": cand.source,
                    "rejection_reason": rejection_reason,
                    "matched_term": matched_term,
                    "page_number": cand.page_number
                })
            else:
                accepted_candidates.append(cand)

        return accepted_candidates, rejected_records

    def run(
        self,
        sentences: List[Sentence],
        candidates: List[Candidate | dict],
        output_dir: Optional[Path] = None,
        extra_whitelist: Optional[Set[str]] = None,
    ) -> Dict[str, Any]:
        """
        Executes the optimized protection/filtering stage:
          1. Filter input candidates for spelling-type items.
          2. Identify unresolved spelling candidates (skipping already pre-rejected items).
          3. Process spaCy NER ONLY over sentences containing unresolved candidates.
          4. Build protected terms registry.
          5. Filter spell candidates through multi-layer precision gate (SymSpell + dictionary + edit distance).
          6. Generate filtered_spell_candidates.json and rejected_spell_candidates.json audit artifacts.
        """
        import time

        # Extract only spelling-type candidates if mixed candidates passed
        spelling_candidates: List[Candidate | dict] = []
        for c in candidates:
            itype = getattr(c, "issue_type", None) if hasattr(c, "issue_type") else (c.get("issue_type") if isinstance(c, dict) else None)
            if itype is None or itype == IssueType.SPELLING or itype == "spelling":
                spelling_candidates.append(c)

        # Step 1: Identify unresolved candidates that require spaCy NER
        unresolved_sids: Set[int] = set()
        all_candidate_sids: Set[int] = set()
        sentence_map = {s.sentence_id: s for s in sentences}

        for c in spelling_candidates:
            sid = getattr(c, "sentence_id", None) if hasattr(c, "sentence_id") else c.get("sentence_id")
            if sid is not None:
                all_candidate_sids.add(sid)
                if not self.is_candidate_pre_rejected(c):
                    unresolved_sids.add(sid)

        # Step 2: Run spaCy NER ONLY over sentences with unresolved candidates (for 216-page doc efficiency)
        target_sids = unresolved_sids if unresolved_sids else all_candidate_sids
        unique_candidate_sentences = [
            sentence_map[sid]
            for sid in sorted(target_sids)
            if sid in sentence_map
        ]

        t_spacy_start = time.time()
        ner_entities = self.extract_ner_entities(unique_candidate_sentences, batch_size=64) if unique_candidate_sentences else []
        spacy_processing_time = round(time.time() - t_spacy_start, 4)

        # Step 3: Build protected terms registry
        protected_terms = self.build_protected_terms(unique_candidate_sentences, ner_entities, extra_whitelist)

        # Step 4: Filter candidates through multi-layer precision gate
        filtered_candidates, rejected_records = self.filter_candidates(
            candidates=spelling_candidates,
            sentences=unique_candidate_sentences,
            ner_entities=ner_entities,
            protected_terms=protected_terms
        )

        # Breakdown of rejection reasons
        rejection_breakdown = Counter(r["rejection_reason"] for r in rejected_records)

        # Step 5: Save artifacts if output_dir provided
        if output_dir:
            out_p = Path(output_dir)
            out_p.mkdir(parents=True, exist_ok=True)
            save_json(ner_entities, out_p / "ner_entities.json")
            save_json(protected_terms, out_p / "protected_terms.json")
            save_json(filtered_candidates, out_p / "filtered_spell_candidates.json")
            save_json(rejected_records, out_p / "rejected_spell_candidates.json")

        return {
            "raw_candidates_count": len(spelling_candidates),
            "unique_candidate_sentences_count": len(unique_candidate_sentences),
            "spacy_processing_time_seconds": spacy_processing_time,
            "ner_entities_count": len(ner_entities),
            "protected_terms_count": len(protected_terms),
            "filtered_candidates_count": len(filtered_candidates),
            "rejected_candidates_count": len(rejected_records),
            "rejection_breakdown": dict(rejection_breakdown),
            "filtered_candidates": filtered_candidates,
            "rejected_candidates": rejected_records,
            "ner_entities": ner_entities,
            "protected_terms": protected_terms,
        }
