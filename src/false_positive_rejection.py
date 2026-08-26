"""
false_positive_rejection.py
============================
Final False Positive Rejection Layer for Spelling & Grammar Validation.

Guarantees high-precision proofreading by shielding:
  1. Currencies & Financial Values (USD 5 trillion, ₹ 10 crore, $1.5 million, INR 20,000, EUR 3.2 billion, etc.)
  2. Percentages (80% of job, 15.5%, 100 bps, etc.)
  3. Dates, Years & Fiscal Years (FY 2024-25, 2023-24, Q1 FY25, 31st March 2024, etc.)
  4. Units & Measurements (MW, GW, kV, TPH, MT, sq ft, etc.)
  5. Acronyms, Abbreviations & Regulatory Codes (EBITDA, PAT, CIN, DIN, SEBI, BSE, NSE, etc.)
  6. Proper Nouns, Company Names, Person Names & Technical Vocabulary
  7. Context-Aware Sentence & Suggestion Quality Gate:
     - Rejects trivial formatting/casing/British-American preferences
     - Rejects OCR/dash/fragment artifacts
     - Rejects low-confidence/ambiguous suggestions
     - Validates full sentence improvement (preserving genuine SVA, tense, spelling, punctuation, word form errors)
"""

from __future__ import annotations

import re
import string
from typing import Any, Dict, List, Optional, Set, Tuple

from src.models import Candidate, IssueType, ProtectedTerm, SourceAgent
from src.spelling_standards import classify_variant_direction, should_reject_for_spelling_standard


# ---------------------------------------------------------------------------
# 1. Regex Patterns for Protected Domains & Formats
# ---------------------------------------------------------------------------

# Currencies & Currency Codes/Symbols
_CURRENCY_SYMBOLS = r"[₹$€£¥]"
_CURRENCY_WORDS = r"\b(?:USD|INR|EUR|GBP|JPY|AUD|CAD|CHF|CNY|SGD|AED|HKD|NZD|SEK|KRW|BRL|RUB|ZAR)\b|\bRs\.?"
_CURRENCY_PREFIX = rf"(?:(?:{_CURRENCY_WORDS})\s*|{_CURRENCY_SYMBOLS}\s*)"

_CURRENCY_MULTIPLIERS = (
    r"trillion|trillions|billion|billions|million|millions|crore|crores|lakh|lakhs|"
    r"thousand|thousands|hundred|hundreds|k|m|b|t|mn|bn|tn|cr|lac|lacs"
)

# e.g. "USD 5 trillion", "₹ 10 crore", "₹10 crore", "$1.5 million", "INR 20,000", "EUR 3.2 billion", "Rs. 500"
_FINANCIAL_VALUE_RE = re.compile(
    rf"(?:{_CURRENCY_PREFIX})?\d+(?:,\d+)*(?:\.\d+)?(?:\s*(?:{_CURRENCY_MULTIPLIERS})\b)?|"
    rf"(?:{_CURRENCY_PREFIX})\d+(?:,\d+)*(?:\.\d+)?(?:\s*(?:{_CURRENCY_MULTIPLIERS})\b)?|"
    rf"\b\d+(?:,\d+)*(?:\.\d+)?\s*(?:{_CURRENCY_MULTIPLIERS})\b",
    re.IGNORECASE,
)

# Standalone currency symbols and codes e.g. "USD", "INR", "₹", "$"
_STANDALONE_CURRENCY_RE = re.compile(
    rf"^(?:{_CURRENCY_WORDS}|{_CURRENCY_SYMBOLS})$",
    re.IGNORECASE,
)

# Percentages e.g. "80%", "80 %", "15.5%", "80% of job", "100 bps", "5.2 percentage points"
_PERCENTAGE_RE = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:%|percent|percentage|pct|basis\s+points|bps)\b(?:\s+of\s+[\w\s'-]+)?",
    re.IGNORECASE,
)

# Dates, Years, Fiscal Years, Quarters
_MONTHS = (
    r"Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Sept|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?"
)
_FISCAL_YEAR_RE = re.compile(
    r"\b(?:FY\s*)?\d{4}[-\/]\d{2,4}\b|\bFY\s*\d{2,4}\b|\b(?:Q[1-4]|H[1-2])\s*(?:FY\s*)?\d{2,4}\b",
    re.IGNORECASE,
)
_CALENDAR_DATE_RE = re.compile(
    rf"\b\d{{1,2}}(?:st|nd|rd|th)?\s+(?:{_MONTHS}),?\s+\d{{2,4}}\b|"
    rf"\b(?:{_MONTHS})\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+\d{{2,4}}\b|"
    rf"\b\d{{1,2}}[\/\-\.]\d{{1,2}}[\/\-\.]\d{{2,4}}\b|"
    r"\b(?:19|20)\d{2}\b",
    re.IGNORECASE,
)

# Units of Measurement & Engineering Rates
_UNITS_OF_MEASURE = (
    r"MW|GW|kW|kWh|MWh|GWh|kV|kVA|MVA|MVAR|Hz|kHz|MHz|GHz|V|A|W|mA|mV|"
    r"MT|MMT|TPH|TPD|kg|g|mg|tonne|tonnes|tons|ton|lbs|oz|"
    r"km|m|cm|mm|sq\s*ft|sqft|sq\s*m|sqm|sq\s*km|sqkm|acres|hectares|inches|ft|yd|"
    r"ltr|liter|litres|kl|ml|m3|cu\s*m|cft|RPM|bar|psi|dB|deg\s*C|°C|°F|Kcal|BTU"
)
_MEASUREMENT_RE = re.compile(
    rf"\b\d+(?:,\d+)*(?:\.\d+)?\s*(?:{_UNITS_OF_MEASURE})\b|\b(?:{_UNITS_OF_MEASURE})\b",
    re.IGNORECASE,
)

# Technical Terms & Domain Words
_TECH_TERMS: Set[str] = {
    "scada", "hvdc", "feedforward", "layernorm", "switchyard", "substation",
    "discom", "genco", "transco", "statcom", "facts", "plc", "dcs", "rtu",
    "ied", "gis", "ais", "bess", "ppa", "psa", "self-attention", "multi-head",
    "transformer", "encoder", "decoder", "fitchner", "fichtner", "wartsila", "wurtsila"
}

# Acronyms, Stock Tickers, Accounting & Regulatory Abbreviations
_KNOWN_ACRONYMS_AND_REGULATORY: Set[str] = {
    "ebitda", "ebit", "pat", "pbt", "roce", "roe", "cagr", "eps", "nav", "aum",
    "sebi", "icai", "icsi", "udin", "mca", "rera", "cin", "din", "pan", "tan", "gst", "gstin",
    "llp", "huf", "epfo", "esic", "nsdl", "cdsl", "cibil", "isin", "lei", "npa", "crar",
    "slr", "crr", "nbfc", "aif", "reit", "invit", "sgb", "etf", "fii", "dii", "fpi",
    "fdi", "fema", "pmla", "sarfaesi", "ibc", "nclt", "nclat", "sat", "cci", "trai",
    "dgca", "fssai", "peso", "cea", "cerc", "serc", "posoco", "gridcontroller", "grid-india",
    "rldc", "sldc", "nldc", "statcom", "facts", "plc", "dcs", "rtu", "ied", "gis", "ais",
    "bess", "ppa", "psa", "discom", "genco", "transco", "appc", "rec", "escert", "rpo", "rgo",
    "mop", "mnre", "niti", "aayog", "cpri", "ntpc", "powergrid", "nhpc", "sjvn", "thdc",
    "eesl", "seci", "dvc", "cesc", "wbsedcl", "wbsetcl", "jusnl", "bsphcl", "uppcl",
    "siemens", "alstom", "abb", "schneider", "toshiba", "hitachi", "ge", "technip",
    "kpmg", "pwc", "deloitte", "ey", "infosys", "tcs", "wipro", "hcl", "cognizant",
    "tech mahindra", "sail", "gail", "ongc", "iocl", "boc", "vedanta", "hindalco",
    "jsw", "jindal", "btl", "btl epc", "epc", "o&m", "boq", "loa", "loi", "jv", "spv",
    "emd", "bg", "pbg", "lc", "b2b", "b2c", "oem", "oems", "csr", "tds", "agm", "egm",
    "roc", "cnc", "treds", "scada", "hvdc", "bse", "nse", "rbi", "irdai"
}

_ACRONYM_PATTERN = re.compile(r"\b[A-Z0-9/&.-]{2,}s?\b")
_ROMAN_NUMERAL_PATTERN = re.compile(r"\b(?=[MDCLXVI])M{0,4}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})\b")

# Proper Name Title Prefixes
_TITLE_PREFIX_PATTERN = re.compile(
    r"\b(?:Dr\.|Prof\.|Mr\.|Mrs\.|Ms\.|Shri|Smt\.|Er\.|Adv\.|CA|CS|CMA)\s+[A-Z][a-zA-Z0-9'-]+(?:\s+[A-Z][a-zA-Z0-9'-]+)*\b"
)

# Known Proper & Company Entities
_KNOWN_ENTITIES: Set[str] = {
    "btl", "btl epc", "btl epc limited", "bengal tools", "bengal tools limited",
    "shrachi", "shrachi group", "fichtner", "fichtner consulting", "fitchner",
    "wartsila", "wurtsila", "vertexa", "sunil kumar mittra", "ravi todi", "rhea todi",
    "aviik mukherjee", "subrata paul", "arundhuti dhar", "sandipan chakravortty",
    "ketan mangaldas shanghavi", "sourav daspatnaik", "ambedkar", "b.r. ambedkar",
    "s.k. todi", "kolkata", "mumbai", "delhi", "bengaluru", "chennai", "hyderabad",
    "ranchi", "dhanbad", "jamshedpur", "bokaro", "patna", "bhubaneswar", "cuttack",
    "deoghar", "kovalam", "trivandrum", "thiruvananthapuram", "west bengal", "jharkhand",
    "odisha", "bihar", "assam", "maharashtra", "gujarat", "karnataka", "tamil nadu",
    "kerala", "andhra pradesh", "telangana", "uttar pradesh", "madhya pradesh", "rajasthan",
    "punjab", "haryana", "uttarakhand", "himachal pradesh", "goa", "sikkim"
}

# Genuine high-frequency English misspellings that must NEVER be shielded as entities
_CONFIRMED_GENUINE_MISSPELLINGS: Set[str] = {
    "recieve", "recieved", "recieving", "definitiely", "definately", "seperate", "seperated",
    "seperating", "untill", "occured", "occuring", "occurrance", "comapny", "annnual",
    "proffreading", "succesful", "succesfully", "goverment", "environemnt", "managment",
    "developement", "refered", "begining", "existance", "catagory", "acheive", "beleive",
    "guarentee", "neccessary", "unneccessary", "tommorow", "trully", "publically"
}

# British / American spelling pairs
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


# ---------------------------------------------------------------------------
# 2. False Positive Rejection Layer Core
# ---------------------------------------------------------------------------

class FalsePositiveRejectionLayer:
    """
    Final Authoritative False Positive Rejection Engine.
    Evaluates candidate spelling and grammar issues across financial, numeric, entity,
    and contextual linguistic gates before persistence or UI rendering.
    """

    def __init__(self, protected_terms: Optional[List[ProtectedTerm | dict]] = None, spelling_standard: str = "both") -> None:
        self.spelling_standard = spelling_standard
        self.protected_terms = protected_terms or []
        self.protected_spans: List[Tuple[int, int, str]] = []
        self.protected_texts: Dict[str, str] = {}

        for pt in self.protected_terms:
            text = pt.get("text") if isinstance(pt, dict) else getattr(pt, "text", "")
            reason = pt.get("reason") if isinstance(pt, dict) else getattr(pt, "reason", "PROTECTED_TERM")
            start = pt.get("char_start") if isinstance(pt, dict) else getattr(pt, "char_start", None)
            end = pt.get("char_end") if isinstance(pt, dict) else getattr(pt, "char_end", None)

            if text:
                self.protected_texts[text.strip().lower()] = str(reason)
            if start is not None and end is not None and start < end:
                self.protected_spans.append((int(start), int(end), str(reason)))

    @staticmethod
    def is_british_american_swap(orig: str, sug: str) -> bool:
        orig_l, sug_l = orig.lower().strip(), sug.lower().strip()
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

    @staticmethod
    def is_protected_financial_or_numeric_expression(text: str, sentence_text: str = "") -> Optional[str]:
        """
        Detects if text or its occurrence in sentence_text is a protected financial,
        currency, percentage, date, measurement, or numeric quantity.
        """
        clean_text = text.strip()
        clean_lower = clean_text.lower()

        if not clean_text:
            return None

        # 1. Direct match on financial value / currency expressions
        if _STANDALONE_CURRENCY_RE.fullmatch(clean_text):
            return "PROTECTED_CURRENCY_CODE_OR_SYMBOL"

        if _FINANCIAL_VALUE_RE.fullmatch(clean_text):
            return "PROTECTED_FINANCIAL_VALUE_EXPRESSION"

        if _PERCENTAGE_RE.fullmatch(clean_text):
            return "PROTECTED_PERCENTAGE_EXPRESSION"

        if _FISCAL_YEAR_RE.fullmatch(clean_text):
            return "PROTECTED_FISCAL_YEAR_EXPRESSION"

        if _CALENDAR_DATE_RE.fullmatch(clean_text):
            return "PROTECTED_DATE_EXPRESSION"

        if _MEASUREMENT_RE.fullmatch(clean_text):
            return "PROTECTED_MEASUREMENT_UNIT_EXPRESSION"

        # 2. Check individual financial units & multipliers
        if clean_lower in {
            "usd", "inr", "eur", "gbp", "jpy", "rs", "rs.", "crore", "crores", "lakh", "lakhs",
            "trillion", "trillions", "billion", "billions", "million", "millions", "thousand",
            "thousands", "hundred", "hundreds", "fy", "ebitda", "pat", "pbt", "bps", "pct"
        }:
            return "PROTECTED_FINANCIAL_UNIT"

        # 3. If surrounding sentence is provided, check if candidate token is embedded inside a financial pattern
        if sentence_text:
            # Check financial value spans in sentence
            for m in _FINANCIAL_VALUE_RE.finditer(sentence_text):
                pos = sentence_text.find(clean_text)
                if pos != -1 and m.start() <= pos and pos + len(clean_text) <= m.end():
                    return "PROTECTED_FINANCIAL_CONTEXT"

            # Check percentage spans in sentence (e.g. "80% of job")
            for m in _PERCENTAGE_RE.finditer(sentence_text):
                pos = sentence_text.find(clean_text)
                if pos != -1 and m.start() <= pos and pos + len(clean_text) <= m.end():
                    return "PROTECTED_PERCENTAGE_CONTEXT"

            # Check fiscal year / date spans in sentence (e.g. "FY 2024-25")
            for m in _FISCAL_YEAR_RE.finditer(sentence_text):
                pos = sentence_text.find(clean_text)
                if pos != -1 and m.start() <= pos and pos + len(clean_text) <= m.end():
                    return "PROTECTED_FISCAL_YEAR_CONTEXT"

            for m in _CALENDAR_DATE_RE.finditer(sentence_text):
                pos = sentence_text.find(clean_text)
                if pos != -1 and m.start() <= pos and pos + len(clean_text) <= m.end():
                    return "PROTECTED_DATE_CONTEXT"

            for m in _MEASUREMENT_RE.finditer(sentence_text):
                pos = sentence_text.find(clean_text)
                if pos != -1 and m.start() <= pos and pos + len(clean_text) <= m.end():
                    return "PROTECTED_MEASUREMENT_CONTEXT"

        return None

    def is_protected_entity_or_proper_noun(self, original: str, suggestion: str) -> Optional[str]:
        orig_clean = original.strip()
        orig_lower = orig_clean.lower()
        sug_lower = suggestion.strip().lower()

        # Never shield confirmed genuine typos
        if orig_lower in _CONFIRMED_GENUINE_MISSPELLINGS:
            return None

        # 1. Known corporate, proper, or geographic entity
        if orig_lower in _KNOWN_ENTITIES or sug_lower in _KNOWN_ENTITIES:
            return "PROTECTED_PROPER_ENTITY"

        # 2. Acronyms, stock tickers, statutory abbreviations
        if orig_lower in _KNOWN_ACRONYMS_AND_REGULATORY:
            return "PROTECTED_ACRONYM_OR_REGULATORY_CODE"

        if _ACRONYM_PATTERN.fullmatch(orig_clean) and len(orig_clean) >= 2:
            return "PROTECTED_ALL_CAPS_ACRONYM"

        if _ROMAN_NUMERAL_PATTERN.fullmatch(orig_clean):
            return "PROTECTED_ROMAN_NUMERAL"

        if _TITLE_PREFIX_PATTERN.search(orig_clean):
            return "PROTECTED_PERSON_NAME_WITH_TITLE"

        # 3. Technical terms & domain vocabulary
        if orig_lower in _TECH_TERMS or sug_lower in _TECH_TERMS:
            return "PROTECTED_TECHNICAL_TERM"

        # 4. Explicit protected terms match
        if orig_lower in self.protected_texts:
            return f"PROTECTED_REGISTRY_{self.protected_texts[orig_lower]}"

        return None

    def evaluate_candidate(
        self,
        original: str,
        suggestion: str,
        sentence_text: str = "",
        issue_type: str = "grammar",
        source: str = "gramformer",
        confidence: Optional[float] = None,
        char_start: Optional[int] = None,
        char_end: Optional[int] = None,
    ) -> Tuple[bool, Optional[str], int]:
        """
        Evaluates a candidate issue against the False Positive Rejection Layer.
        Returns:
            (is_rejected: bool, rejection_reason: Optional[str], quality_score: int)
        """
        orig = (original or "").strip()
        sug = (suggestion or "").strip()
        orig_lower = orig.lower()
        sug_lower = sug.lower()
        sent_clean = (sentence_text or "").strip()
        conf_val = float(confidence) if isinstance(confidence, (int, float)) else 0.85

        # ---------------------------------------------------------
        # Hard Check 0: Confirmed Genuine Spelling Errors (Always Retain)
        # ---------------------------------------------------------
        if orig_lower in _CONFIRMED_GENUINE_MISSPELLINGS and len(sug) > 0:
            return (False, None, 95)

        # ---------------------------------------------------------
        # Hard Check 1: Empty or Identical Text
        # ---------------------------------------------------------
        if not orig or not sug:
            return (True, "EMPTY_ORIGINAL_OR_SUGGESTION", 0)

        if orig == sug:
            return (True, "IDENTICAL_ORIGINAL_AND_SUGGESTION", 0)

        # Stray bullet points or leading dashes (fragment check)
        if re.match(r"^[\-–—•·*]", orig):
            return (True, "FRAGMENT_LEADING_PUNCTUATION", 0)

        # ---------------------------------------------------------
        # Hard Check 2: Formatting, Capitalization & Regional Variant Preferences
        # ---------------------------------------------------------
        # Pure capitalization differences (e.g. EBITDA -> Ebitda, USD -> Usd, FY -> Fy)
        if orig_lower == sug_lower:
            # Check if this is at the very beginning of a sentence where lowercase was an error
            is_sentence_start = sent_clean.startswith(orig)
            if not is_sentence_start or orig.isupper():
                return (True, "CAPITALIZATION_PREFERENCE_ONLY", 10)

        # British vs American regional spelling variant
        if self.is_british_american_swap(orig, sug):
            variant_dir = classify_variant_direction(orig, sug)
            if should_reject_for_spelling_standard(orig, sug, self.spelling_standard):
                return (True, f"Out of Scope (British/American Spelling Preference: {variant_dir})", 10)

        # Formatting-only differences (spaces around punctuation, hyphen variants)
        orig_normalized = re.sub(r"[\s\-_–—'\"`]", "", orig_lower)
        sug_normalized = re.sub(r"[\s\-_–—'\"`]", "", sug_lower)
        if orig_normalized == sug_normalized and len(orig_normalized) > 0:
            # Punctuation/spacing preference only
            return (True, "FORMATTING_OR_PUNCTUATION_NOTATION_ONLY", 15)

        # ---------------------------------------------------------
        # Hard Check 3: Protected Financial, Currency, Percentage, Date, Unit
        # ---------------------------------------------------------
        fin_reason = self.is_protected_financial_or_numeric_expression(orig, sent_clean)
        if fin_reason:
            return (True, fin_reason, 0)

        # Also check if suggestion is trying to change financial notation
        sug_fin_reason = self.is_protected_financial_or_numeric_expression(sug, sent_clean)
        if sug_fin_reason and any(c.isdigit() for c in orig):
            return (True, f"{sug_fin_reason}_MODIFICATION_SUPPRESSED", 0)

        # ---------------------------------------------------------
        # Hard Check 4: Protected Entities, Acronyms, Names & Terms
        # ---------------------------------------------------------
        entity_reason = self.is_protected_entity_or_proper_noun(orig, sug)
        if entity_reason:
            return (True, entity_reason, 0)

        # Span-based overlap check against document protected registry
        if char_start is not None and char_end is not None and char_start < char_end:
            for p_start, p_end, p_reason in self.protected_spans:
                if char_start < p_end and char_end > p_start:
                    return (True, f"PROTECTED_SPAN_{p_reason}", 0)

        # ---------------------------------------------------------
        # Hard Check 5: OCR Artifacts, Fragments & Non-Sentence Text
        # ---------------------------------------------------------
        if len(orig) < 2 and not orig.isalpha():
            return (True, "OCR_ARTIFACT_OR_SYMBOL", 0)

        # Stray bullet points or leading dashes
        if re.match(r"^[\-–—•·*]", orig):
            return (True, "FRAGMENT_LEADING_PUNCTUATION", 0)

        if sent_clean and len(re.findall(r"[A-Za-z]+", sent_clean)) < 3:
            # Too short context to safely judge grammar
            return (True, "INSUFFICIENT_SENTENCE_CONTEXT", 10)

        # ---------------------------------------------------------
        # Hard Check 6: Full-Sentence Context Validation for Grammar / Tense
        # ---------------------------------------------------------
        i_type_clean = str(issue_type).lower()
        if i_type_clean in ("grammar", "tense", "verb_form"):
            # Check if this is a genuine subject-verb agreement or tense error
            is_sva_or_tense_fix = self._is_genuine_grammar_correction(orig, sug, sent_clean)
            if not is_sva_or_tense_fix:
                # If confidence is below 0.80 and no clear structural error, suppress
                if conf_val < 0.80:
                    return (True, "LOW_CONFIDENCE_UNCONFIRMED_GRAMMAR", 20)

        # ---------------------------------------------------------
        # Quality Score Calculation for Accepted Findings
        # ---------------------------------------------------------
        quality_score = max(50, min(100, round(conf_val * 100)))
        return (False, None, quality_score)

    @staticmethod
    def _is_genuine_grammar_correction(orig: str, sug: str, sentence_text: str) -> bool:
        """
        Validates whether a proposed grammatical replacement represents a genuine
        grammatical rule fix (subject-verb agreement, tense consistency, invalid word form, etc.)
        rather than an arbitrary stylistic rewrite.
        """
        orig_l, sug_l = orig.lower().strip(), sug.lower().strip()

        # Subject-verb agreement pairs
        sva_pairs = {
            ("are", "is"), ("is", "are"),
            ("were", "was"), ("was", "were"),
            ("have", "has"), ("has", "have"),
            ("do", "does"), ("does", "do"),
            ("go", "goes"), ("goes", "go"),
            ("lead", "leads"), ("leads", "lead"),
            ("grow", "grows"), ("grows", "grow"),
            ("approved", "approve"), ("approve", "approved"),
            ("has went", "has gone"), ("have went", "have gone"),
            ("have completed", "has completed"), ("has completed", "have completed"),
            ("completed", "complete"), ("complete", "completed")
        }
        if (orig_l, sug_l) in sva_pairs:
            return True

        # Verb form / tense inflection fixes (e.g. "go" -> "goes", "grow" -> "is growing", "went" -> "gone")
        if orig_l.endswith("s") and not sug_l.endswith("s") and orig_l[:-1] == sug_l:
            return True
        if sug_l.endswith("s") and not orig_l.endswith("s") and sug_l[:-1] == orig_l:
            return True
        if orig_l.endswith("ed") and not sug_l.endswith("ed") and orig_l[:-2] == sug_l:
            return True
        if sug_l.endswith("ed") and not orig_l.endswith("ed") and sug_l[:-2] == orig_l:
            return True

        # Common invalid word forms
        invalid_forms = {
            ("more better", "better"),
            ("irregardless", "regardless"),
            ("could of", "could have"),
            ("should of", "should have"),
            ("would of", "would have"),
            ("an book", "a book"),
            ("a apple", "an apple"),
        }
        if (orig_l, sug_l) in invalid_forms:
            return True

        # Punctuation fixes (e.g. double period ".." -> ".")
        if ".." in orig and ".." not in sug:
            return True

        # Article agreement
        if (orig_l, sug_l) in {("a", "an"), ("an", "a"), ("the", "a"), ("a", "the")}:
            return True

        # No recognised structural grammar-rule pattern matched -- this is
        # not a confirmed genuine correction (previously this fell through
        # to `return True` unconditionally, which silently disabled the
        # low-confidence suppression branch in Hard Check 6 for every
        # grammar/tense candidate).
        return False
