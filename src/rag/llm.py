from typing import List, Dict, Optional
from src.rag.response_models import ModelMetadata

# The default model to fall back on if none is specified or if the requested model is invalid.
DEFAULT_MODEL_ID = "qwen2.5-coder:7b"

# Configuration-driven list of supported models.
SUPPORTED_MODELS_LIST = [
    ModelMetadata(
        id="qwen2.5-coder:7b",
        display_name="Qwen2.5 Coder 7B",
        description="Fast, high-performance model for document understanding, structured reasoning, and RAG."
    ),
    ModelMetadata(
        id="qwen2.5-coder:32b",
        display_name="Qwen2.5 Coder 32B",
        description="High-capacity model for complex document understanding and structured reasoning."
    ),
    ModelMetadata(
        id="qwen3:30b-a3b",
        display_name="Qwen3 30B",
        description="Balanced reasoning and natural conversational responses."
    ),
    ModelMetadata(
        id="qwen2.5:72b",
        display_name="Qwen2.5 72B",
        description="Highest-quality reasoning for very large and complex documents."
    ),
    ModelMetadata(
        id="deepseek-r1:32b",
        display_name="DeepSeek R1 32B",
        description="Excellent analytical reasoning for technical and research documents."
    ),
    ModelMetadata(
        id="gpt-oss:20b",
        display_name="GPT-OSS 20B",
        description="Fast response generation with good general reasoning."
    )
]

SUPPORTED_MODELS: Dict[str, ModelMetadata] = {model.id: model for model in SUPPORTED_MODELS_LIST}

def get_available_models() -> List[ModelMetadata]:
    """
    Returns the list of all available answer-generation models.
    """
    return SUPPORTED_MODELS_LIST

def validate_and_get_model(model_id: Optional[str]) -> str:
    """
    Validates the given model_id. Returns the model_id if valid,
    otherwise falls back to the default model.
    """
    if not model_id or model_id not in SUPPORTED_MODELS:
        return DEFAULT_MODEL_ID
    return model_id
