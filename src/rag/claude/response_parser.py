import re
import json
import logging

logger = logging.getLogger("pipeline")

class ResponseParser:
    """
    Parses and validates JSON responses returned by the Claude API.
    """

    def clean_and_parse_json(self, text: str) -> dict:
        text = text.strip()
        
        # Check for markdown code fences
        pattern = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)
        match = pattern.search(text)
        if match:
            json_str = match.group(1).strip()
        else:
            json_str = text
            
        try:
            parsed = json.loads(json_str)
            if not isinstance(parsed, dict):
                raise ValueError("Claude response must be a JSON dictionary object.")
            return parsed
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Claude JSON response. Raw string: {text}")
            
            # Regex fallback to find first '{' and last '}'
            start = json_str.find('{')
            end = json_str.rfind('}')
            if start != -1 and end != -1:
                try:
                    parsed = json.loads(json_str[start:end+1])
                    if isinstance(parsed, dict):
                        return parsed
                except Exception:
                    pass
            raise e
