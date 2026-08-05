"""
domain_words.py
===============
Shared dictionary of valid English domain terminology, technical words,
and industry vocabulary that must NEVER be flagged as spelling errors.
"""

from typing import Set

VALID_DOMAIN_WORDS: Set[str] = {
    # Meaningful Technical & Domain Collocations / Multi-Word Expressions
    "hydel", "hydel plant", "hydel power", "hydel project", "hydel scheme", "hydel station",
    "hydro", "hydro plant", "hydroelectric", "hydroelectric plant", "hydroelectric power", "hydropower",
    "power plant", "solar plant", "thermal plant", "thermal power", "wind plant", "wind farm",
    "nuclear plant", "captive plant", "cogeneration plant", "balance of plant", "turnkey project", "epc contract",
    "substation", "substations", "switchyard", "switchyards", "transmission line", "distribution network",
    "megawatt", "megawatts", "gigawatt", "gigawatts", "kilowatt", "kilowatts",
    "mw", "kw", "gw", "kv", "kva", "mva", "capex", "opex", "discom", "discoms",
    "powergrid", "tariff", "tariffs", "feeder", "feeders", "transformer", "transformers",
    "infrastructural", "multimodal", "intermodal", "consortium", "consortiums",
    "decommissioning", "recommissioning", "brownfield", "greenfield", "commissioning",
    "photovoltaic", "biomass", "cogeneration", "sub-station", "grid-connected",
    "technip", "btl", "epc",

    # Names of People, Places & Organizations
    "kolkata", "bengal", "west bengal", "india", "delhi", "mumbai", "bengaluru", "chennai",
    "harvard", "harvard business school", "opm", "shrachi", "shrachi group", "bengal tools",
    "bengal tools limited", "btl epc", "btl epc limited", "ravi todi", "s.k. todi", "todi",

    # Common corporate & business abbreviations/terms
    "fy24", "fy25", "fy26", "fy23", "fy22", "q1", "q2", "q3", "q4", "yoy", "qoq",
    "ebitda", "ebit", "pbt", "pat", "roce", "roe", "cagr", "b2b", "b2c", "oem", "oems"
}


def is_valid_domain_term(word: str) -> bool:
    """Returns True if the word/phrase is a valid domain term, industry collocation, person name, or place name."""
    if not word or not isinstance(word, str):
        return False
    w_clean = word.strip().lower().rstrip(".,;:!?'\"")
    if w_clean in VALID_DOMAIN_WORDS:
        return True
    if w_clean.endswith("s") and w_clean[:-1] in VALID_DOMAIN_WORDS:
        return True
    for term in VALID_DOMAIN_WORDS:
        if " " in term and (w_clean == term or term in w_clean):
            return True
    return False
