# AI Document Proofreading System

A Grammarly-style proofreading pipeline: Docling-based extraction → layout
analysis → protected-terms detection → LanguageTool + SymSpell spelling →
local-LLM grammar review → semantic validation → merge → annotated HTML +
JSON/Markdown/CSV reports.

## Setup

```bash
pip install -r requirements.txt 
python -m spacy download en_core_web_sm
```

You also need:
- A local Java runtime (JRE 17+) for `language_tool_python`.
- The SymSpell frequency dictionary at
  `models/frequency_dictionary_en_82_765.txt` (from the `symspellpy` repo).
- An Ollama server reachable at `OLLAMA_HOST` (defaults to
  `http://192.168.19.21:11434`) running `OLLAMA_MODEL` (defaults to
  `qwen2.5-coder:32b`).

## Run

```bash
python main.py your_document.pdf   # file must be in data/input/
```

Output is written to `data/output/<name>_<timestamp>/`, with one
subfolder per stage (`01_raw` ... `10_final`, plus `logs`). The final
deliverables are in `10_final/`: `annotated_original.html`,
`corrected_document.html`, `report.json`, `changes.md`, `summary.csv`.

## What changed in this refactor

The codebase had accumulated inconsistencies from being rewritten in
pieces. Every fix below was to make already-implemented logic connect
correctly, not to design new behavior:

- **`config.py` vs. everything else**: `pipeline.py`, `protected_terms.py`,
  `languagetool_agent.py`, `spell_agent.py`, `grammar_agent.py`,
  `semantic_validator.py`, and `merge_agent.py` all imported flat
  module-level constants (`DATA_OUTPUT_DIR`, `SPACY_MODEL`,
  `OLLAMA_HOST`, ...) that no longer existed — `config.py` had moved to
  nested dataclasses (`PipelineConfig.paths.data_output_dir`, etc.) but
  the agents weren't updated. Fixed by having every agent's constructor
  accept the specific config dataclass it needs (dependency injection),
  wired together once in `pipeline.py` from a single `PipelineConfig`.
- **`Sentence` had no document-level offsets**: `languagetool_agent.py`,
  `spell_agent.py`, and `pipeline.py` all read `sentence.doc_char_start`
  / `doc_char_end`, but `models.Sentence` only stored paragraph-relative
  `start_offset`/`end_offset`. Added the two fields plus
  `models.index_sentence_doc_offsets()`, called once in the pipeline
  right after paragraph offsets are indexed.
- **`.dict()` on plain dataclasses**: `validation_agent.py`,
  `merge_agent.py`, and `report_generator.py` called `.dict()` (a
  pydantic method) on plain `@dataclass` objects, which doesn't exist.
  Fixed with `utils.dataclass_kwargs()` for promoting a `Candidate` into
  a `ValidatedIssue`/`MergedIssue` (preserves Enum types), and
  `utils.save_json` (which already handles dataclasses recursively via
  `to_serializable`) for writing stage outputs to disk.
- **`pipeline.py` called stage 1-6 modules as free functions**
  (`extract_document(path)`, `analyze_layout(...)`, `split_sentences(...)`)
  while `extractor.py`, `layout_analyzer.py`, `filter.py`,
  `preprocessing.py`, `paragraph_builder.py`, and `sentence_splitter.py`
  are actually class-based (`DocumentExtractor.extract()`,
  `LayoutAnalyzer.analyze()`, ...). Rewrote `pipeline.py` to call the
  real class APIs.
- **`logger.py` vs. `pipeline.py`**: `pipeline.py` imported a
  `StageProgress` class that doesn't exist; `logger.py` actually exposes
  `PipelineLogger.stage()`. Rewrote `pipeline.py` to use `logger.stage()`.
- **Orphaned module**: `html_writer.py` (shared HTML shell/CSS) was never
  imported by `annotator.py`, which duplicated its own copy of the CSS
  and legend markup. `annotator.py` now uses `html_writer.page_shell()`.
- **`report_generator.py`** was missing the `summary.csv` deliverable
  called for in the spec (`report.json` + `changes.md` only existed) and
  didn't include page/paragraph numbers per issue. Added both.

All 16 pipeline stages were smoke-tested end-to-end with lightweight fakes
standing in for the external services (spaCy model, LanguageTool JVM,
SymSpell dictionary, Ollama server) that aren't available in every
environment, to confirm imports, data flow, and offset math are correct
independent of those services being installed.