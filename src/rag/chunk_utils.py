import re
from typing import List

def estimate_tokens(text: str) -> int:
    """
    Estimates the number of tokens in a text block.
    Uses tiktoken if installed, falling back to a word-based heuristic (words * 1.3).
    """
    if not text:
        return 0
        
    try:
        import tiktoken
        # Use cl100k_base (standard for GPT models)
        encoding = tiktoken.get_encoding("cl100k_base")
        return len(encoding.encode(text))
    except (ImportError, Exception):
        # Fallback to word-count based estimation (1 word is approx 1.3 tokens)
        words = len(text.split())
        return int(words * 1.3) + 1

def count_words(text: str) -> int:
    """
    Counts the number of words in a text block.
    """
    if not text:
        return 0
    # Split by whitespace, ignoring punctuation
    words = re.findall(r'\b\w+\b', text)
    return len(words)

def format_section_path(headings: List[str]) -> str:
    """
    Formats a list of headings into a section hierarchy string.
    Example: ['Chapter 1', 'Section A'] -> 'Chapter 1 > Section A'
    """
    if not headings:
        return "Root"
    return " > ".join(headings)
