"""
llm_fallback.py
================
Local-LLM fallback for the Comparative Analysis Claude agents.

Each Claude-dependent agent (CompanySummaryAgent, CompetitorSummaryAgent,
ExecutiveInsightsAgent, StrategicRecommendationAgent) previously had exactly
two outcomes: a successful Claude API call, or a generic, templated,
non-document-specific fallback (company name / industry substituted into
fixed boilerplate sentences). If the Claude API key is missing, out of
credits, rate-limited, or otherwise unreachable, every comparative analysis
report silently degraded to that boilerplate -- never a real synthesis of
the actual document/competitor data.

This adds a real middle option: before falling through to the boilerplate,
retry the exact same system/user prompt against a local Ollama model (see
model_router.py's "comparative_analysis_fallback" entry, qwen2.5-coder:32b
by default) on the same Ollama host already used elsewhere in this project
(src/rag/ollama_client.py, default http://192.168.19.21:11434). Each agent
still owns its own response parsing/validation -- this only supplies the
raw text, exactly like the Claude call does.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger("comparative_analysis.llm_fallback")


def call_local_llm_fallback(
    system_prompt: str,
    user_prompt: str,
    agent_name: str,
) -> Optional[str]:
    """
    Attempts one local-LLM generation as a stand-in for a failed/unavailable
    Claude call. Returns the raw response text, or None if the local model
    is also unreachable/fails -- callers should fall through to their own
    existing generic fallback in that case, never raise.
    """
    try:
        from src.rag.ollama_client import OllamaClient, OllamaClientError
        from src.model_router import MODEL_ROUTER
        from src.rag.config import RagConfig

        model = MODEL_ROUTER.get_model("comparative_analysis_fallback")
        # Same OLLAMA_HOST every other stage in this project reads (see
        # src/rag/config.py) -- not a second, independently-hardcoded host,
        # so overriding OLLAMA_HOST in .env affects this fallback too.
        client = OllamaClient(host=RagConfig().ollama_host)

        if not client.check_connection():
            logger.warning(
                "[%s] Local LLM fallback skipped: Ollama server at %s is unreachable.",
                agent_name, client.host,
            )
            return None

        logger.info(
            "[%s] Claude unavailable -- retrying with local LLM fallback (%s @ %s).",
            agent_name, model, client.host,
        )
        response = client.generate(model=model, prompt=user_prompt, system=system_prompt)
        if not response or not response.strip():
            logger.warning("[%s] Local LLM fallback returned an empty response.", agent_name)
            return None
        return response

    except Exception as exc:
        logger.warning("[%s] Local LLM fallback (Ollama) failed: %s", agent_name, exc)
        return None
