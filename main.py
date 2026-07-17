"""Entry point: run the proofreading pipeline on a single document.

Usage:
    python main.py                  # interactively pick a file from data/input/
    python main.py <filename>       # run directly on data/input/<filename>
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List

from src.config import PipelineConfig
from src.extractor import SUPPORTED_EXTENSIONS
from src.pipeline import ProofreadingPipeline


def _list_candidate_documents(input_dir: Path) -> List[Path]:
    if not input_dir.exists():
        return []
    return sorted(
        p for p in input_dir.iterdir()
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
    )


def _choose_input_file(config: PipelineConfig) -> Path:
    """Return the document to process: from argv[1] if given, otherwise by
    prompting the user to pick one from data/input/."""
    input_dir = config.paths.data_input_dir

    if len(sys.argv) >= 2:
        path = input_dir / sys.argv[1]
        if not path.exists():
            print(f"File not found: {path}")
            sys.exit(1)
        return path

    candidates = _list_candidate_documents(input_dir)
    supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))

    if not candidates:
        print(f"No documents found in {input_dir}")
        print(f"Add a file ({supported}) there, or run: python main.py <filename>")
        sys.exit(1)

    if len(candidates) == 1:
        print(f"Using the only document found in data/input/: {candidates[0].name}")
        return candidates[0]

    print(f"Documents found in {input_dir}:\n")
    for idx, path in enumerate(candidates, start=1):
        print(f"  {idx}. {path.name}")

    while True:
        choice = input(f"\nChoose a document [1-{len(candidates)}]: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(candidates):
            return candidates[int(choice) - 1]
        print(f"Please enter a number between 1 and {len(candidates)}.")


def main() -> None:
    config = PipelineConfig()
    input_path = _choose_input_file(config)

    with ProofreadingPipeline(config) as pipeline:
        result = pipeline.run(input_path)

    print("\nDone.")
    print(f"Output: {result['run_dir']}")
    print(f"Issues found: {result['total_issues']}")
    print(f"Rejected (protected terms): {result['rejected_protected']}")
    print(f"Rejected (semantic check): {result['rejected_semantic']}")


if __name__ == "__main__":
    main()