"""
config.py
=========
Dataclass-based configuration. Each stage that needs tunable settings gets
its own small config dataclass; PipelineConfig aggregates them so main.py /
pipeline.py can build ONE object and inject the relevant piece into each
stage's constructor (dependency injection, not module-level globals -- this
is what keeps every agent testable and decoupled from `config.py`'s
internal layout).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent


@dataclass
class PathsConfig:
    data_input_dir: Path = ROOT_DIR / "data" / "input"
    data_output_dir: Path = ROOT_DIR / "data" / "output"
    models_dir: Path = ROOT_DIR / "models"


@dataclass
class DoclingConfig:
    enable_ocr: bool = False
    enable_table_extraction: bool = False


@dataclass
class SpacyConfig:
    model_name: str = "en_core_web_sm"


@dataclass
class SymSpellConfig:
    max_edit_distance: int = 2
    prefix_length: int = 7
    dictionary_path: Path = ROOT_DIR / "models" / "frequency_dictionary_en_82_765.txt"


@dataclass
class LanguageToolConfig:
    language: str = "en-US"


@dataclass
class OllamaConfig:
    # Networked machine, not localhost -- override via env var so the IP
    # isn't hardcoded/committed:
    #   export OLLAMA_HOST="http://192.168.19.21:11434"
    host: str = field(default_factory=lambda: os.environ.get("OLLAMA_HOST", "http://192.168.19.21:11434"))
    model: str = field(default_factory=lambda: os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:32b"))
    timeout_seconds: int = 180
    temperature: float = 0.0
    max_retries: int = 2
    # Avoid deepseek-r1:* and gpt-oss:* -- reasoning models tend to emit
    # chain-of-thought text even when told "return only JSON".


@dataclass
class ValidationConfig:
    protected_entity_labels: frozenset = frozenset({
        "PERSON", "ORG", "GPE", "PRODUCT", "WORK_OF_ART", "FAC", "NORP", "LOC",
    })
    auto_whitelist_min_occurrences: int = 2


@dataclass
class MergeConfig:
    confidence_boost_per_extra_source: float = 0.2
    max_confidence: float = 1.0


@dataclass
class PipelineConfig:
    paths: PathsConfig = field(default_factory=PathsConfig)
    docling: DoclingConfig = field(default_factory=DoclingConfig)
    spacy: SpacyConfig = field(default_factory=SpacyConfig)
    symspell: SymSpellConfig = field(default_factory=SymSpellConfig)
    languagetool: LanguageToolConfig = field(default_factory=LanguageToolConfig)
    ollama: OllamaConfig = field(default_factory=OllamaConfig)
    validation: ValidationConfig = field(default_factory=ValidationConfig)
    merge: MergeConfig = field(default_factory=MergeConfig)

    stage_folders: tuple = (
        "01_raw", "02_filtered", "03_preprocessed", "04_sentences",
        "05_protected_terms", "06_spell", "07_grammar", "08_validation",
        "09_semantic", "10_final", "logs",
    )

    def __post_init__(self):
        pref_path = ROOT_DIR / "data" / "preferences.json"
        if pref_path.exists():
            import json
            try:
                with open(pref_path, "r", encoding="utf-8") as f:
                    prefs = json.load(f)
                if "ollama_host" in prefs and prefs["ollama_host"]:
                    self.ollama.host = prefs["ollama_host"]
                if "ollama_model" in prefs and prefs["ollama_model"]:
                    self.ollama.model = prefs["ollama_model"]
                if "languagetool_language" in prefs and prefs["languagetool_language"]:
                    self.languagetool.language = prefs["languagetool_language"]
            except Exception:
                pass


def load_preferences() -> dict:
    pref_path = ROOT_DIR / "data" / "preferences.json"
    if pref_path.exists():
        import json
        try:
            with open(pref_path, "r", encoding="utf-8") as f:
                prefs = json.load(f)
            result = {}
            for k, v in prefs.items():
                result[k] = v
            # Inject nested form for backend/services compatibility
            if "ollama_model" in prefs:
                result.setdefault("ollama", {})["model"] = prefs["ollama_model"]
            if "ollama_host" in prefs:
                result.setdefault("ollama", {})["host"] = prefs["ollama_host"]
            return result
        except Exception:
            pass
    return {
        "ollama": {
            "model": "qwen2.5-coder:32b",
            "host": "http://192.168.19.21:11434"
        }
    }

