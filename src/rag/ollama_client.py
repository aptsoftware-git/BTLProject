import time
import requests
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger("pipeline")

class OllamaClientError(Exception):
    """Base exception for Ollama client errors."""
    pass

class OllamaConnectionError(OllamaClientError):
    """Raised when the Ollama server is unreachable."""
    pass

class OllamaModelMissingError(OllamaClientError):
    """Raised when the requested model is not found on the Ollama server."""
    pass

class OllamaTimeoutError(OllamaClientError):
    """Raised when a request to Ollama times out."""
    pass

class OllamaClient:
    """
    Dedicated client for communicating with a remote Ollama server.
    """
    def __init__(
        self,
        host: str = "http://192.168.19.21:11434",
        timeout: int = 300,
        max_retries: int = 2
    ):
        self.host = host.rstrip('/')
        self.timeout = timeout
        self.max_retries = max_retries

    def check_connection(self) -> bool:
        """
        Checks if the Ollama server is running and reachable.
        """
        try:
            resp = requests.get(f"{self.host}/api/tags", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False

    def list_local_models(self) -> List[str]:
        """
        Lists all downloaded model names on the Ollama server.
        """
        try:
            resp = requests.get(f"{self.host}/api/tags", timeout=10)
            if resp.status_code == 200:
                models_info = resp.json().get("models", [])
                return [m["name"] for m in models_info]
        except Exception as e:
            logger.warning(f"Failed to fetch models list from Ollama: {e}")
        return []

    def generate(
        self,
        model: str,
        prompt: str,
        system: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None,
        timeout: Optional[int] = None
    ) -> str:
        """
        Calls the Ollama /api/generate endpoint with retry logic and detailed error handling.
        """
        url = f"{self.host}/api/generate"
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
        }
        if system:
            payload["system"] = system
        if options:
            payload["options"] = options

        req_timeout = timeout or self.timeout

        last_err = None
        for attempt in range(self.max_retries + 1):
            try:
                logger.info(f"Calling Ollama generate (Attempt {attempt + 1}/{self.max_retries + 1}) for model {model} (timeout={req_timeout}s)...")
                resp = requests.post(url, json=payload, timeout=req_timeout)
                
                if resp.status_code == 404:
                    raise OllamaModelMissingError(f"Model '{model}' is not found on Ollama server at {self.host}.")
                
                if resp.status_code != 200:
                    try:
                        err_detail = resp.json()
                        err_msg = err_detail.get("error", str(err_detail))
                    except Exception:
                        err_msg = resp.text
                    
                    if "not found" in err_msg.lower() or "does not exist" in err_msg.lower():
                        raise OllamaModelMissingError(f"Model '{model}' is not found on Ollama server: {err_msg}")
                    
                    raise OllamaClientError(f"Ollama server returned status code {resp.status_code}: {err_msg}")
                
                resp_json = resp.json()
                return resp_json.get("response", "")

            except requests.exceptions.Timeout as e:
                logger.warning(f"Ollama timeout on attempt {attempt + 1}: {e}")
                last_err = OllamaTimeoutError(f"Request to Ollama at {self.host} timed out after {self.timeout}s.")
            except requests.exceptions.ConnectionError as e:
                logger.warning(f"Ollama connection error on attempt {attempt + 1}: {e}")
                last_err = OllamaConnectionError(f"Failed to connect to Ollama server at {self.host}. Is the service running and accessible?")
            except OllamaModelMissingError as e:
                # Missing model is a configuration issue; do not retry.
                raise e
            except Exception as e:
                logger.warning(f"Unexpected Ollama error on attempt {attempt + 1}: {e}")
                last_err = OllamaClientError(f"Unexpected error when calling Ollama: {str(e)}")

            if attempt < self.max_retries:
                sleep_duration = 2 ** attempt
                logger.info(f"Retrying Ollama call in {sleep_duration} seconds...")
                time.sleep(sleep_duration)

        raise last_err

    def generate_vision(
        self,
        model: str,
        prompt: str,
        image_bytes_b64: str,
        options: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Calls Ollama generate endpoint with a base64 encoded image.
        """
        url = f"{self.host}/api/generate"
        payload = {
            "model": model,
            "prompt": prompt,
            "images": [image_bytes_b64],
            "stream": False,
        }
        if options:
            payload["options"] = options

        last_err = None
        for attempt in range(self.max_retries + 1):
            try:
                logger.info(f"Calling Ollama generate_vision (Attempt {attempt + 1}/{self.max_retries + 1}) for model {model}...")
                resp = requests.post(url, json=payload, timeout=self.timeout)
                
                if resp.status_code == 404:
                    raise OllamaModelMissingError(f"Model '{model}' is not found on Ollama server at {self.host}.")
                
                if resp.status_code != 200:
                    try:
                        err_detail = resp.json()
                        err_msg = err_detail.get("error", str(err_detail))
                    except Exception:
                        err_msg = resp.text
                    raise OllamaClientError(f"Ollama vision server returned status code {resp.status_code}: {err_msg}")
                
                resp_json = resp.json()
                return resp_json.get("response", "")

            except requests.exceptions.Timeout as e:
                logger.warning(f"Ollama timeout on attempt {attempt + 1}: {e}")
                last_err = OllamaTimeoutError(f"Request to Ollama at {self.host} timed out after {self.timeout}s.")
            except requests.exceptions.ConnectionError as e:
                logger.warning(f"Ollama connection error on attempt {attempt + 1}: {e}")
                last_err = OllamaConnectionError(f"Failed to connect to Ollama server at {self.host}.")
            except Exception as e:
                logger.warning(f"Unexpected Ollama error on attempt {attempt + 1}: {e}")
                last_err = OllamaClientError(f"Unexpected error: {str(e)}")

            if attempt < self.max_retries:
                time.sleep(2 ** attempt)

        raise last_err

