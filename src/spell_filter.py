"""
spell_filter.py
===============
Spell Candidate Protection/Filtering stage AFTER the existing Spell Agent.

Flow:
  04_sentences/sentences.json
          ↓
  spaCy NER — run ONCE over all extracted running-text sentences using nlp.pipe()
          ↓
  ner_entities.json
          ↓
  Build protected_terms.json
          ↓
  06_spell/spell_candidates.json
          ↓
  Protected-term filtering (match using sentence_id and precomputed vocabulary)
          ↓
  filtered_spell_candidates.json
          ↓
  Stage 4 Grammar

Key Requirements:
1. Use 04_sentences/sentences.json as text source (never run spaCy on raw candidates).
2. Process all sentences in batch with spaCy nlp.pipe() for maximum efficiency.
3. Extract & protect PERSON, ORG, GPE, LOC, FAC, PRODUCT, EVENT, NORP.
4. Protect acronyms, abbreviations, repeated proper terms, company names, domain terminology.
5. Use sentence_id from spell_candidates.json to match candidates against precomputed entities & terms.
6. Preserve raw spell_candidates.json unchanged.
7. Generate 06_spell/ner_entities.json, 06_spell/protected_terms.json, 06_spell/filtered_spell_candidates.json.
8. Record rejection reasons for every filtered candidate (e.g. PERSON_ENTITY, ORG_ENTITY, GPE_ENTITY, ACRONYM, DOMAIN_TERM).
9. Keep deterministic and fast. Optimize for HIGH PRECISION.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import spacy

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
    "goa", "sikkim", "tripura", "meghalaya", "manipur", "nagaland", "mizoram"
}

CANONICAL_CORPORATE_ENTITIES: Set[str] = {
    "todi", "ravi todi", "s.k. todi", "fitchner", "fichtner", "fichtner consulting",
    "btl", "btl epc", "btl epc limited", "bengal tools", "bengal tools limited",
    "shrachi", "shrachi group", "wartsila", "wurtsila", "vertexa", "tata", "birla",
    "adani", "ambani", "godrej", "bajaj", "mahindra", "l&t", "larsentoubro", "bhel",
    "ntpc", "powergrid", "nhpc", "sjvn", "thdc", "eesl", "seci", "dvc", "cesc",
    "wbsedcl", "wbsetcl", "jusnl", "bsphcl", "uppcl", "siemens", "alstom", "abb",
    "schneider", "toshiba", "hitachi", "ge", "technip", "kpmg", "pwc", "deloitte", "ey",
    "infosys", "tcs", "wipro", "hcl", "cognizant", "tech mahindra", "bagra", "ambedkar"
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
    "q1", "q2", "q3", "q4", "yoy", "qoq", "csr", "inr", "usd", "eur", "gbp"
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


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# SpellCandidateFilter Engine
# ---------------------------------------------------------------------------

class SpellCandidateFilter:
    """
    High-precision protection and filtering engine for spell checking candidates.
    Extracts entities once across sentences via spaCy nlp.pipe() and protects
    valid names, places, organizations, acronyms, and domain terminology.
    """

    PROTECTED_NER_LABELS = {
        "PERSON", "ORG", "GPE", "LOC", "FAC", "PRODUCT", "EVENT", "NORP", "LAW", "WORK_OF_ART"
    }

    _ACRONYM_REGEX = re.compile(r"\b[A-Z0-9/&.-]{2,}s?\b")
    _SLASH_ACRONYM_REGEX = re.compile(r"^[A-Z0-9]+(?:/[A-Z0-9]+)+$")
    _ABBREV_REGEX = re.compile(r"\b(?:Pvt|Ltd|Co|Inc|Corp|Govt|Dr|Prof|Mr|Mrs|Ms|Shri|Smt|Er)\.?\b", re.IGNORECASE)
    _DOTTED_NAME_REGEX = re.compile(r"\b(?:[A-Z]\.){1,4}\s*([A-Z][a-zA-Z]+)\b")
    _ADDRESS_SUFFIX_REGEX = re.compile(
        r"\b([A-Z][a-zA-Z]+)\s+(?:Marg|Road|Rd\.?|Street|St\.?|Nagar|Chowk|Colony|Society|Estate|Vihar|Puram|Bagh|Circle|Lane)\b"
    )

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

        # Load domain dictionary from data/domain_dictionary.json
        self.domain_dict_terms: Set[str] = set()
        domain_dict_path = ROOT_DIR / "data" / "domain_dictionary.json"
        if domain_dict_path.exists():
            try:
                data = load_json(domain_dict_path)
                if isinstance(data, list):
                    self.domain_dict_terms = {str(item).lower().strip() for item in data}
            except Exception:
                pass

        # Load frequency dictionary to recognize standard dictionary words
        self.dict_words: Set[str] = set()
        self.common_words: Set[str] = set()
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
                                self.dict_words.add(w)
                                if freq > 10000000:
                                    self.common_words.add(w)
                            except ValueError:
                                continue
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Step 1: spaCy NER across candidate sentences using nlp.pipe(batch_size=64)
    # ------------------------------------------------------------------
    def extract_ner_entities(self, sentences: List[Sentence], batch_size: int = 64) -> List[Dict[str, Any]]:
        """
        Run spaCy NER ONCE over unique candidate sentences using nlp.pipe(batch_size=64).
        Extracts PERSON, ORG, GPE, LOC, FAC, PRODUCT, EVENT, NORP, LAW, WORK_OF_ART.
        """
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

    # ------------------------------------------------------------------
    # Step 2: Build protected_terms.json
    # ------------------------------------------------------------------
    def build_protected_terms(
        self,
        sentences: List[Sentence],
        ner_entities: List[Dict[str, Any]],
        extra_whitelist: Optional[Set[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Build a comprehensive, deduplicated protected terms registry combining:
        - NER entities
        - Acronyms & Abbreviations
        - Canonical corporate & geographic vocabularies
        - Domain-specific terminology
        - Repeated proper terms across sentences
        - User whitelists
        """
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

    # ------------------------------------------------------------------
    # Step 3: Protected-term filtering
    # ------------------------------------------------------------------
    def filter_candidates(
        self,
        candidates: List[Candidate | dict],
        sentences: List[Sentence],
        ner_entities: List[Dict[str, Any]],
        protected_terms: List[Dict[str, Any]],
    ) -> Tuple[List[Candidate], List[Dict[str, Any]]]:
        """
        Match each candidate in spell_candidates.json against precomputed NER entities
        and protected terms, using sentence_id and token rules.

        Returns:
            (filtered_candidates, rejected_candidates_with_reasons)
        """
        # Build lookup indices for instant O(1) matching
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

            # Default: no rejection
            rejection_reason: Optional[str] = None
            matched_term: Optional[str] = None

            # ---------------------------------------------------------
            # Check 0: Trivial Identical / Case / British-American Swap
            # ---------------------------------------------------------
            if orig_lower == sug_lower:
                rejection_reason = "CAPITALIZATION_PREFERENCE"
                matched_term = orig
            elif _is_british_american_swap(orig, sug):
                rejection_reason = "BRITISH_AMERICAN_PREFERENCE"
                matched_term = orig

            # ---------------------------------------------------------
            # Check 1: Is this a genuine typo of a country or word?
            # E.g. "Bangaldesh" -> "Bangladesh", "occuring" -> "occurring", "renior" -> "senior"
            # ---------------------------------------------------------
            is_genuine_spelling_error = False

            if not rejection_reason:
                # 1a. Canonical Country Misspelling Check (e.g. Bangaldesh -> Bangladesh)
                if sug_lower in CANONICAL_COUNTRIES and orig_lower not in CANONICAL_COUNTRIES:
                    if _levenshtein_distance(orig_lower, sug_lower) <= 2:
                        is_genuine_spelling_error = True

                # 1b. Standard Lowercase Misspelling Check (e.g. occuring -> occurring, renior -> senior)
                elif orig.islower() and not orig_lower.isupper() and orig_lower not in KNOWN_ACRONYMS:
                    if not is_valid_domain_term(orig_lower) and orig_lower not in self.domain_dict_terms:
                        if orig_lower not in CANONICAL_INDIAN_LOCATIONS and orig_lower not in CANONICAL_CORPORATE_ENTITIES:
                            # Standard lowercase misspelling flagged by spell checker
                            is_genuine_spelling_error = True

            if is_genuine_spelling_error:
                accepted_candidates.append(cand)
                continue

            # ---------------------------------------------------------
            # Check 2: Acronyms & Short Codes (e.g. CNC, EPC, TREDS, CNC/EPC/TREDS)
            # ---------------------------------------------------------
            if not rejection_reason:
                if (orig.isupper() and len(orig) >= 2) or "/" in orig or orig_lower in KNOWN_ACRONYMS:
                    rejection_reason = "ACRONYM"
                    matched_term = orig
                elif self._SLASH_ACRONYM_REGEX.match(orig):
                    rejection_reason = "ACRONYM"
                    matched_term = orig

            # ---------------------------------------------------------
            # Check 3: Sentence-Level NER Entity Overlap (sentence_id match)
            # ---------------------------------------------------------
            if not rejection_reason and sid in entities_by_sentence:
                sent_ents = entities_by_sentence[sid]
                
                # Check character span overlap or exact entity text match within sentence
                for ent in sent_ents:
                    ent_text = ent["text"]
                    ent_lbl = ent["label"]
                    ent_lower = ent_text.lower()

                    # Exact text match or containment in entity
                    if orig_lower == ent_lower or orig_lower in ent_lower.split():
                        rejection_reason = f"{ent_lbl}_ENTITY"
                        matched_term = ent_text
                        break

                    # Doc offset span overlap check if offsets are populated
                    if cand.char_start is not None and cand.char_end is not None:
                        e_start = ent.get("doc_char_start")
                        e_end = ent.get("doc_char_end")
                        if e_start is not None and e_end is not None:
                            if cand.char_start < e_end and cand.char_end > e_start:
                                rejection_reason = f"{ent_lbl}_ENTITY"
                                matched_term = ent_text
                                break

            # ---------------------------------------------------------
            # Check 4: Document-Wide NER Entities (e.g. Todi, Fitchner, India, Deoghar, BTL EPC)
            # ---------------------------------------------------------
            if not rejection_reason:
                if orig_lower in doc_entities_lower:
                    rejection_reason = doc_entities_lower[orig_lower]
                    matched_term = orig

            # ---------------------------------------------------------
            # Check 5: Canonical Corporate, Place, & Person Names
            # ---------------------------------------------------------
            if not rejection_reason:
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
            # Check 6: Domain Terminology (e.g. hydel, switchyard, substation)
            # ---------------------------------------------------------
            if not rejection_reason:
                if is_valid_domain_term(orig_lower) or orig_lower in self.domain_dict_terms:
                    rejection_reason = "DOMAIN_TERM"
                    matched_term = orig

            # ---------------------------------------------------------
            # Check 7: Precomputed Protected Terms Registry Match
            # ---------------------------------------------------------
            if not rejection_reason:
                if orig_lower in protected_texts_lower:
                    rejection_reason = protected_texts_lower[orig_lower]
                    matched_term = orig
                elif sug_lower in protected_texts_lower and not orig.islower():
                    rejection_reason = protected_texts_lower[sug_lower]
                    matched_term = sug

            # ---------------------------------------------------------
            # Check 8: Abbreviations / Dotted Initial Terms
            # ---------------------------------------------------------
            if not rejection_reason:
                if self._ABBREV_REGEX.search(orig):
                    rejection_reason = "ABBREVIATION"
                    matched_term = orig

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

    # ------------------------------------------------------------------
    # Full Execution Flow: extract unique sentences -> NER -> filter -> save
    # ------------------------------------------------------------------
    def run(
        self,
        sentences: List[Sentence],
        candidates: List[Candidate | dict],
        output_dir: Optional[Path] = None,
        extra_whitelist: Optional[Set[str]] = None,
    ) -> Dict[str, Any]:
        """
        Executes the optimized protection/filtering stage:
          1. Extract unique sentence_ids referenced by candidates.
          2. Retrieve and deduplicate corresponding full sentences.
          3. Process ONCE using spaCy nlp.pipe(batch_size=64).
          4. Extract PERSON/ORG/GPE/LOC/FAC/PRODUCT/EVENT/NORP entities.
          5. Build protected terms.
          6. Filter candidates using sentence_id and protected vocabulary.
          7. Preserve raw spell_candidates.json and generate filtered/audit artifacts.
        """
        import time

        # Step 1: Extract unique sentence_ids referenced by spell_candidates
        candidate_sids: Set[int] = set()
        for c in candidates:
            sid = getattr(c, "sentence_id", None) if hasattr(c, "sentence_id") else c.get("sentence_id")
            if sid is not None:
                candidate_sids.add(sid)

        # Step 2: Retrieve & deduplicate corresponding full sentences from sentences
        sentence_map = {s.sentence_id: s for s in sentences}
        unique_candidate_sentences = [
            sentence_map[sid]
            for sid in sorted(candidate_sids)
            if sid in sentence_map
        ]

        # Step 3: spaCy NER ONCE over unique candidate sentences using nlp.pipe(batch_size=64)
        t_spacy_start = time.time()
        ner_entities = self.extract_ner_entities(unique_candidate_sentences, batch_size=64)
        spacy_processing_time = round(time.time() - t_spacy_start, 4)

        # Step 4: Build protected terms registry
        protected_terms = self.build_protected_terms(unique_candidate_sentences, ner_entities, extra_whitelist)

        # Step 5: Filter candidates using sentence_id and protected vocabulary
        filtered_candidates, rejected_records = self.filter_candidates(
            candidates=candidates,
            sentences=unique_candidate_sentences,
            ner_entities=ner_entities,
            protected_terms=protected_terms
        )

        # Breakdown of rejection reasons
        rejection_breakdown = Counter(r["rejection_reason"] for r in rejected_records)

        # Step 6: Save artifacts if output_dir provided
        if output_dir:
            out_p = Path(output_dir)
            out_p.mkdir(parents=True, exist_ok=True)
            save_json(ner_entities, out_p / "ner_entities.json")
            save_json(protected_terms, out_p / "protected_terms.json")
            save_json(filtered_candidates, out_p / "filtered_spell_candidates.json")
            save_json(rejected_records, out_p / "rejected_spell_candidates.json")

        return {
            "raw_candidates_count": len(candidates),
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
