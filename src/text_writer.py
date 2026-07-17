"""
text_writer.py
================
Thin wrapper around `utils.save_text` used by pipeline stages that need
to persist intermediate plain-text outputs (raw_text.txt,
filtered_text.txt, normalized_text.txt).
"""

from __future__ import annotations

from pathlib import Path

from src.utils import save_text


class TextWriter:
    """Writes plain-text intermediate outputs to disk."""

    @staticmethod
    def write(text: str, path: Path) -> None:
        save_text(text, path)
