import logging
import os
import requests
from pathlib import Path
from typing import Optional, Dict, Any

from src.rag.ollama_client import OllamaClient
from src.rag.config import RagConfig

logger = logging.getLogger("pipeline")

class InferenceService:
    """
    Abstractions wrapper for LLM queries.
    This is the ONLY class in the contextual analysis module permitted to call LLM providers.
    Supports both Ollama (local) and Anthropic Claude (cloud API) backends.
    """

    def __init__(self, model_name: str = "qwen2.5-coder:7b"):
        self.model_name = model_name
        self.ollama_client = OllamaClient()
        self.prompts_dir = Path(__file__).parent / "prompts"
        
        # Load configuration settings
        self.config = RagConfig()
        self.provider = getattr(self.config, "provider", "ollama")
        self.claude_model = getattr(self.config, "claude_model", "claude-3-5-sonnet-20241022")

        # Load prompt templates
        self.system_prompt = self._load_prompt("system_prompt.txt")
        self.analysis_prompt_tmpl = self._load_prompt("analysis_prompt.txt")
        self.verification_prompt_tmpl = self._load_prompt("verification_prompt.txt")

    def _load_prompt(self, filename: str) -> str:
        path = self.prompts_dir / filename
        if not path.exists():
            logger.warning(f"Prompt file not found: {path}. Using empty fallback.")
            return ""
        return path.read_text(encoding="utf-8")

    def _call_claude(self, prompt: str, system: str) -> str:
        """Helper to invoke Anthropic Claude messages API via direct requests."""
        api_key = os.environ.get("CLAUDE_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            logger.error("CLAUDE_API_KEY / ANTHROPIC_API_KEY environment variable is not set. Falling back to empty response.")
            return ""

        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        
        payload = {
            "model": self.claude_model,
            "max_tokens": 4000,
            "system": system,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.0
        }
        
        try:
            logger.info(f"Sending request to Anthropic Claude ({self.claude_model})...")
            response = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=payload,
                timeout=180
            )
            response.raise_for_status()
            res_json = response.json()
            return res_json["content"][0]["text"].strip()
        except Exception as e:
            logger.error(f"Claude API query failed: {e}")
            return ""

    def run_analysis(self, context_section: str, objects_text: str) -> str:
        """
        Sends related Knowledge Objects to the LLM to identify potential inconsistencies.
        """
        prompt = self.analysis_prompt_tmpl.format(
            context_section=context_section,
            objects_text=objects_text
        )
        
        if self.provider == "claude":
            return self._call_claude(prompt, self.system_prompt)

        # Ollama local provider fallback
        options = {
            "temperature": 0.0  # Strict deterministic output
        }
        try:
            response = self.ollama_client.generate(
                model=self.model_name,
                prompt=prompt,
                system=self.system_prompt,
                options=options
            )
            return response.strip()
        except Exception as e:
            logger.error(f"InferenceService Ollama analysis query failed: {e}")
            return "[]"

    def run_verification(
        self,
        category: str,
        description: str,
        evidence: str,
        object_ids: str,
        section_path: str,
        objects_content: str
    ) -> str:
        """
        Sends candidate inconsistency to the LLM for verification and citation double check.
        """
        prompt = self.verification_prompt_tmpl.format(
            category=category,
            description=description,
            evidence=evidence,
            object_ids=object_ids,
            section_path=section_path,
            objects_content=objects_content
        )
        
        system = "You are a validation specialist. Confirm the veracity of the provided contradiction strictly using the cited content."
        
        if self.provider == "claude":
            return self._call_claude(prompt, system)

        # Ollama local provider fallback
        options = {
            "temperature": 0.0
        }
        try:
            response = self.ollama_client.generate(
                model=self.model_name,
                prompt=prompt,
                system=system,
                options=options
            )
            return response.strip()
        except Exception as e:
            logger.error(f"InferenceService Ollama verification query failed: {e}")
            return '{"verified": false, "confidence": 0.0}'
