"""
model_router.py
===============
Centralized AI Model Router for the AI Document Intelligence Platform.

No model names should be hardcoded throughout the project.
Every stage retrieves its target model through this centralized configuration.
"""

from __future__ import annotations

import os
from typing import Dict

# Default Model Router configuration mapping stage names to target models
DEFAULT_MODEL_ROUTER: Dict[str, str] = {
    "grammar_review": os.environ.get("MODEL_GRAMMAR_REVIEW", os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:7b")),
    "knowledge_extraction": os.environ.get("MODEL_KNOWLEDGE_EXTRACTION", "qwen2.5-coder:7b"),
    "semantic_validation": os.environ.get("MODEL_SEMANTIC_VALIDATION", "qwen2.5-coder:7b"),
    "vision_analysis": os.environ.get("MODEL_VISION_ANALYSIS", "qwen2.5vl:latest"),
    "rag_chat": os.environ.get("MODEL_RAG_CHAT", "qwen2.5-coder:32b"),
    "context_analysis": os.environ.get("MODEL_CONTEXT_ANALYSIS", "qwen2.5-coder:7b"),
    "comparative_analysis": os.environ.get("MODEL_COMPARATIVE_ANALYSIS", "qwen2.5-coder:7b"),
    "executive_report": os.environ.get("MODEL_EXECUTIVE_REPORT", os.environ.get("CLAUDE_MODEL", os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6"))),
    "embedding_model": os.environ.get("MODEL_EMBEDDING", "BAAI/bge-small-en-v1.5"),
}


class ModelRouter:
    """Centralized Model Router for looking up stage models dynamically."""

    def __init__(self, overrides: Dict[str, str] | None = None) -> None:
        self._router: Dict[str, str] = dict(DEFAULT_MODEL_ROUTER)
        if overrides:
            self._router.update(overrides)

    def get_model(self, stage: str) -> str:
        """Retrieve target model for a given stage."""
        return self._router.get(stage, DEFAULT_MODEL_ROUTER.get(stage, "qwen2.5-coder:7b"))

    def __getitem__(self, stage: str) -> str:
        return self.get_model(stage)

    def to_dict(self) -> Dict[str, str]:
        return dict(self._router)


# Global singleton instance
MODEL_ROUTER = ModelRouter()


def get_model_for_stage(stage: str) -> str:
    """Helper function to fetch model name for a specific pipeline stage."""
    return MODEL_ROUTER.get_model(stage)
