import os
import time
import logging
import requests
from typing import Dict, Any, Optional
from dotenv import load_dotenv

logger = logging.getLogger("pipeline")
load_dotenv()

class ClaudeClient:
    """
    Client for communicating with the Anthropic Claude API.
    Endpoint: POST https://api.anthropic.com/v1/messages
    """

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or os.getenv("CLAUDE_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
        from src.model_router import MODEL_ROUTER
        raw_model = model or os.getenv("MODEL_EXECUTIVE_REPORT", os.getenv("ANTHROPIC_MODEL", os.getenv("CLAUDE_MODEL", MODEL_ROUTER.get_model("executive_report"))))
        if raw_model:
            raw_model = raw_model.replace("claude-sonnet-4.6", "claude-sonnet-4-6").replace("4.6", "4-6")
        self.model = raw_model
        self.url = "https://api.anthropic.com/v1/messages"
        self.timeout = 120
        self.max_retries = 3

    def send_message(self, prompt: str, system_prompt: str) -> str:
        if not self.api_key:
            raise ValueError("Anthropic API key is missing. Please set CLAUDE_API_KEY or ANTHROPIC_API_KEY in the environment or .env file.")

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }

        payload = {
            "model": self.model,
            "max_tokens": 4000,
            "system": system_prompt,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        }

        last_err = None
        for attempt in range(self.max_retries + 1):
            try:
                logger.info(f"Calling Anthropic Messages API (Attempt {attempt + 1}/{self.max_retries + 1}) for model {self.model}...")
                resp = requests.post(self.url, json=payload, headers=headers, timeout=self.timeout)
                
                if resp.status_code == 200:
                    resp_data = resp.json()
                    content_list = resp_data.get("content", [])
                    if content_list and isinstance(content_list, list):
                        return content_list[0].get("text", "")
                    raise ValueError(f"Unexpected response structure from Anthropic API: {resp_data}")
                    
                # Handle error status codes
                try:
                    err_msg = resp.json().get("error", {}).get("message", resp.text)
                except Exception:
                    err_msg = resp.text
                    
                raise RuntimeError(f"Anthropic API returned status {resp.status_code}: {err_msg}")
                
            except requests.exceptions.Timeout as e:
                logger.warning(f"Claude API timeout on attempt {attempt + 1}: {e}")
                last_err = e
            except requests.exceptions.ConnectionError as e:
                logger.warning(f"Claude API connection error on attempt {attempt + 1}: {e}")
                last_err = e
            except Exception as e:
                logger.warning(f"Unexpected error when calling Claude API on attempt {attempt + 1}: {e}")
                last_err = e
                
            if attempt < self.max_retries:
                sleep_sec = 2 ** attempt
                logger.info(f"Retrying Claude API call in {sleep_sec} seconds...")
                time.sleep(sleep_sec)
                
        raise last_err
