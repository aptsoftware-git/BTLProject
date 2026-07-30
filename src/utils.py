"""
utils.py
========
Small, dependency-free helper functions shared across pipeline stages.
"""

from __future__ import annotations

import dataclasses
import json
import re
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any


def timestamp() -> str:
    """Return a filesystem-safe timestamp, e.g. 20260708_143210."""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def ensure_dir(path: Path) -> Path:
    """Create a directory (and parents) if it doesn't already exist."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def to_serializable(obj: Any) -> Any:
    """Recursively convert dataclasses / enums into JSON-serialisable types."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {k: to_serializable(v) for k, v in dataclasses.asdict(obj).items()}
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, (list, tuple)):
        return [to_serializable(v) for v in obj]
    if isinstance(obj, dict):
        return {k: to_serializable(v) for k, v in obj.items()}
    if isinstance(obj, Path):
        return str(obj)
    return obj


def save_json(data: Any, path: Path) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(to_serializable(data), fh, indent=2, ensure_ascii=False)


def save_text(text: str, path: Path) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8") as fh:
        fh.write(text)


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def load_text(path: Path) -> str:
    with path.open("r", encoding="utf-8") as fh:
        return fh.read()


def dataclass_kwargs(obj: Any) -> dict:
    """
    Return {field_name: value} for a dataclass INSTANCE, preserving the
    actual attribute values/types (no serialization, no deep copy).

    Used to "promote" a dataclass instance into a subclass that adds extra
    fields, e.g. Candidate -> ValidatedIssue -> MergedIssue:

        issue = ValidatedIssue(**dataclass_kwargs(candidate), is_protected=True)

    This is preferred over a hand-rolled `.dict()` method because it keeps
    Enum members as Enum members (a hand-rolled serializer that turns them
    into strings would silently break `issue.issue_type == IssueType.X`
    comparisons downstream).
    """
    return {f.name: getattr(obj, f.name) for f in dataclasses.fields(obj)}


URL_PATTERN = re.compile(
    r"(https?://\S+|www\.\S+)", re.IGNORECASE
)
EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
MARKDOWN_HEADING_PATTERN = re.compile(r"^\s{0,3}#{1,6}\s+")
MARKDOWN_EMPHASIS_PATTERN = re.compile(r"(\*\*|\*|__|_|`)")
MARKDOWN_TABLE_ROW_PATTERN = re.compile(r"^\s*\|.*\|\s*$")
MARKDOWN_TABLE_SEPARATOR_PATTERN = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?\s*$")
PAGE_NUMBER_PATTERN = re.compile(r"^\s*(page\s+)?\d+\s*(/\s*\d+)?\s*$", re.IGNORECASE)
ROMAN_NUMERAL_PATTERN = re.compile(
    r"^(?=[MDCLXVI])M{0,4}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})$", re.IGNORECASE
)
ACRONYM_PATTERN = re.compile(r"^[A-Z]{2,}[A-Z0-9]*$")
CITATION_PATTERN = re.compile(r"^\[\d+(,\s*\d+)*\]$|^\(\s*[A-Za-z.,&\s]+,?\s*\d{4}[a-z]?\s*\)$")


def strip_markdown(text: str) -> str:
    """Remove common markdown artifacts from a block of text."""
    lines = []
    for line in text.splitlines():
        if MARKDOWN_TABLE_ROW_PATTERN.match(line) or MARKDOWN_TABLE_SEPARATOR_PATTERN.match(line):
            continue
        line = MARKDOWN_HEADING_PATTERN.sub("", line)
        line = MARKDOWN_EMPHASIS_PATTERN.sub("", line)
        lines.append(line)
    return "\n".join(lines)


def remove_urls_and_emails(text: str) -> str:
    text = URL_PATTERN.sub("", text)
    text = EMAIL_PATTERN.sub("", text)
    return text


def is_page_number(text: str) -> bool:
    return bool(PAGE_NUMBER_PATTERN.match(text.strip()))


def is_roman_numeral(token: str) -> bool:
    token = token.strip(".")
    return bool(token) and bool(ROMAN_NUMERAL_PATTERN.match(token))


def is_acronym(token: str) -> bool:
    return bool(ACRONYM_PATTERN.match(token))


def is_citation(token: str) -> bool:
    return bool(CITATION_PATTERN.match(token.strip()))
