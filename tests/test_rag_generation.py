import pytest
import time
from typing import List, Dict, Optional, Any
from unittest.mock import patch, MagicMock
import requests


from src.rag.response_models import GroundedAnswerResponse, ModelMetadata
from src.rag.llm import validate_and_get_model, get_available_models, DEFAULT_MODEL_ID
from src.rag.ollama_client import (
    OllamaClient,
    OllamaClientError,
    OllamaConnectionError,
    OllamaModelMissingError,
    OllamaTimeoutError
)
from src.rag.context_builder import ContextBuilder
from src.rag.prompt_builder import PromptBuilder, SYSTEM_PROMPT
from src.rag.conversation_memory import ConversationMemory
from src.rag.chat_service import ChatService
from src.rag.retrieval_models import ScoredChunk, RetrievalOutput
from src.rag.chunk_schema import ChunkMetadata


# =====================================================================
# 1. LLM CONFIGURATION TESTS
# =====================================================================

def test_get_available_models():
    models = get_available_models()
    assert len(models) == 5
    ids = [m.id for m in models]
    assert "qwen2.5-coder:32b" in ids
    assert "deepseek-r1:32b" in ids


def test_validate_and_get_model():
    # Valid model
    assert validate_and_get_model("deepseek-r1:32b") == "deepseek-r1:32b"
    # Invalid model
    assert validate_and_get_model("invalid-model") == DEFAULT_MODEL_ID
    # None/Empty
    assert validate_and_get_model(None) == DEFAULT_MODEL_ID


# =====================================================================
# 2. OLLAMA CLIENT TESTS
# =====================================================================

@patch("requests.post")
def test_ollama_client_success(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"response": "This is a grounded answer."}
    mock_post.return_value = mock_resp

    client = OllamaClient(max_retries=0)
    res = client.generate("qwen2.5-coder:32b", "What is RAG?")
    assert res == "This is a grounded answer."
    mock_post.assert_called_once()


@patch("requests.post")
def test_ollama_client_timeout_handling(mock_post):
    # Simulate timeout on all attempts
    mock_post.side_effect = requests.exceptions.Timeout("Timeout occurred")

    client = OllamaClient(max_retries=1, timeout=2)
    with pytest.raises(OllamaTimeoutError):
        client.generate("qwen2.5-coder:32b", "What is RAG?")
    
    # 1 initial attempt + 1 retry = 2 calls total
    assert mock_post.call_count == 2


@patch("requests.post")
def test_ollama_client_connection_error(mock_post):
    mock_post.side_effect = requests.exceptions.ConnectionError("Connection failed")

    client = OllamaClient(max_retries=0)
    with pytest.raises(OllamaConnectionError):
        client.generate("qwen2.5-coder:32b", "What is RAG?")


@patch("requests.post")
def test_ollama_client_model_missing_404(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_post.return_value = mock_resp

    client = OllamaClient(max_retries=1)
    with pytest.raises(OllamaModelMissingError):
        client.generate("non-existent-model", "What is RAG?")
    
    # Missing model should fail immediately without retrying
    assert mock_post.call_count == 1


@patch("requests.post")
def test_ollama_client_model_missing_json_error(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.json.return_value = {"error": "model 'qwen-missing' not found, pull it first"}
    mock_post.return_value = mock_resp

    client = OllamaClient(max_retries=0)
    with pytest.raises(OllamaModelMissingError):
        client.generate("qwen-missing", "What is RAG?")


# =====================================================================
# 3. CONTEXT BUILDER TESTS
# =====================================================================

def _create_mock_scored_chunk(chunk_id: str, content: str, page: int, tokens: int, score: float = 0.8) -> ScoredChunk:
    metadata = ChunkMetadata(
        chunk_id=chunk_id,
        document_id="doc_1",
        page_number=page,
        chunk_type="text",
        word_count=len(content.split()),
        token_estimate=tokens,
        bounding_boxes=[]
    )
    return ScoredChunk(content=content, metadata=metadata, similarity_score=score, reranker_score=score)


def test_context_builder_ordering_and_deduplication():
    # Setup retrieved chunks (sorted by relevance/reranker_score)
    # Note: retrieval order is chunk B (highest score), then chunk A, then chunk C.
    chunk_a = _create_mock_scored_chunk("doc_chunk_0001", "Paragraph from Page 1.", page=1, tokens=50, score=0.8)
    chunk_b = _create_mock_scored_chunk("doc_chunk_0002", "Paragraph from Page 2.", page=2, tokens=50, score=0.9)
    chunk_c = _create_mock_scored_chunk("doc_chunk_0003", "Another paragraph Page 1.", page=1, tokens=50, score=0.7)
    chunk_duplicate = _create_mock_scored_chunk("doc_chunk_0001", "Paragraph from Page 1.", page=1, tokens=50, score=0.6)

    retrieved = [chunk_b, chunk_a, chunk_c, chunk_duplicate]

    builder = ContextBuilder(max_tokens=350)
    context_str, used_ids, page_refs = builder.build_context(retrieved)

    # De-duplicated should keep only 3 chunks: A, B, C (duplicate chunk_0001 is filtered)
    assert len(used_ids) == 3
    assert "doc_chunk_0001" in used_ids
    assert "doc_chunk_0002" in used_ids
    assert "doc_chunk_0003" in used_ids
    assert page_refs == [1, 2]

    # Verification of page ordering preservation: Page 1 content must appear before Page 2
    # In Page 1, doc_chunk_0001 must appear before doc_chunk_0003
    lines = [line for line in context_str.split("\n") if "[Page" in line]
    assert "[Page 1]" in lines[0]
    assert "[Page 1]" in lines[1]
    assert "[Page 2]" in lines[2]


def test_context_builder_token_budgeting():
    # Setup chunks with larger token estimates
    chunk_a = _create_mock_scored_chunk("chunk_1", "A" * 100, page=1, tokens=100, score=0.9)
    chunk_b = _create_mock_scored_chunk("chunk_2", "B" * 100, page=2, tokens=100, score=0.8)
    chunk_c = _create_mock_scored_chunk("chunk_3", "C" * 100, page=3, tokens=100, score=0.7)

    # Max tokens = 200 (including formatting overhead)
    # Chunk A (100 + 50 overhead) fits. Chunk B (100 + 50 overhead) would exceed, so it's skipped.
    # Chunk C also exceeds.
    builder = ContextBuilder(max_tokens=220)
    context_str, used_ids, page_refs = builder.build_context([chunk_a, chunk_b, chunk_c])

    assert len(used_ids) == 1
    assert "chunk_1" in used_ids


# =====================================================================
# 4. PROMPT BUILDER TESTS
# =====================================================================

def test_prompt_builder():
    builder = PromptBuilder()
    context = "[Page 1] Content:\nThis is some document text."
    question = "What is the document about?"
    history = [
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello"}
    ]

    prompt_data = builder.build_prompt(context, question, history)
    
    assert prompt_data["system"] == SYSTEM_PROMPT
    assert "Document Context:" in prompt_data["prompt"]
    assert "This is some document text." in prompt_data["prompt"]
    assert "Conversation History:" in prompt_data["prompt"]
    assert "User: Hi" in prompt_data["prompt"]
    assert "Assistant: Hello" in prompt_data["prompt"]
    assert "Question: What is the document about?" in prompt_data["prompt"]


# =====================================================================
# 5. CONVERSATION MEMORY TESTS
# =====================================================================

def test_conversation_memory():
    memory = ConversationMemory(default_depth=2)
    doc_a = "document_a"
    doc_b = "document_b"

    # Add message to doc_a
    memory.add_message(doc_a, "user", "Hello A")
    memory.add_message(doc_a, "assistant", "Hi A")
    
    # Add message to doc_b (checks isolation)
    memory.add_message(doc_b, "user", "Hello B")
    
    assert len(memory.get_history(doc_a)) == 2
    assert len(memory.get_history(doc_b)) == 1
    assert memory.get_history(doc_a)[0]["content"] == "Hello A"
    assert memory.get_history(doc_b)[0]["content"] == "Hello B"

    # Add more turns to doc_a to exceed depth (depth=2 pairs = 4 turns max)
    memory.add_message(doc_a, "user", "Q2")
    memory.add_message(doc_a, "assistant", "A2")
    memory.add_message(doc_a, "user", "Q3")
    memory.add_message(doc_a, "assistant", "A3")

    history_a = memory.get_history(doc_a)
    assert len(history_a) == 4  # Truncated to depth limit (last 4 turns)
    assert history_a[0]["content"] == "Q2"
    assert history_a[-1]["content"] == "A3"

    # Clear history
    memory.clear_history(doc_a)
    assert len(memory.get_history(doc_a)) == 0
    assert len(memory.get_history(doc_b)) == 1  # Unaffected


# =====================================================================
# 6. CHAT SERVICE INTEGRATION TESTS
# =====================================================================

class FakeRetriever:
    def __init__(self, chunks):
        self.chunks = chunks

    def retrieve(self, document_id: str, query: str):
        return RetrievalOutput(question=query, retrieved_chunks=self.chunks)


class FakeOllamaClient:
    def __init__(self, response_text, fail_models=None):
        self.response_text = response_text
        self.fail_models = fail_models or []
        self.last_prompt = None
        self.last_system = None
        self.last_model = None

    def generate(self, model: str, prompt: str, system: Optional[str] = None, options=None, timeout=None, **kwargs):
        self.last_model = model
        self.last_prompt = prompt
        self.last_system = system
        if model in self.fail_models:
            raise OllamaTimeoutError(f"Model '{model}' timed out after 300s")
        return self.response_text


def test_chat_service_success():
    # Setup mock dependencies
    chunk_a = _create_mock_scored_chunk("chunk_1", "Python was created by Guido van Rossum.", page=1, tokens=50)
    retriever = FakeRetriever([chunk_a])
    ollama_client = FakeOllamaClient("Guido van Rossum")
    
    service = ChatService(
        retriever=retriever,
        ollama_client=ollama_client,
        context_builder=ContextBuilder(),
        prompt_builder=PromptBuilder(),
        memory=ConversationMemory()
    )

    response = service.answer_question("doc_test", "Who created Python?")
    
    assert isinstance(response, GroundedAnswerResponse)
    assert response.answer == "Guido van Rossum"
    assert response.used_chunk_ids == ["chunk_1"]
    assert response.page_references == [1]
    assert response.selected_model == DEFAULT_MODEL_ID
    assert response.generation_time >= 0.0
    assert response.retrieval_statistics["total_retrieved"] == 1
    assert response.retrieval_statistics["used_chunks_count"] == 1
    assert response.fallback_triggered is False


def test_chat_service_model_fallback_on_timeout():
    chunk_a = _create_mock_scored_chunk("chunk_1", "Python was created by Guido van Rossum.", page=1, tokens=50)
    retriever = FakeRetriever([chunk_a])
    # Configure qwen2.5:72b to fail/timeout, while default model qwen2.5-coder:32b succeeds
    ollama_client = FakeOllamaClient("Guido van Rossum", fail_models=["qwen2.5:72b"])

    service = ChatService(
        retriever=retriever,
        ollama_client=ollama_client,
        context_builder=ContextBuilder(),
        prompt_builder=PromptBuilder(),
        memory=ConversationMemory()
    )

    response = service.answer_question("doc_test", "Who created Python?", model_id="qwen2.5:72b")

    assert response.answer == "Guido van Rossum"
    assert response.selected_model == DEFAULT_MODEL_ID
    assert response.requested_model == "qwen2.5:72b"
    assert response.fallback_triggered is True
    assert "exceeded 5-minute timeout" in response.fallback_reason


def test_chat_service_empty_retrieval_unsupported_question():
    # Empty retrieval context
    retriever = FakeRetriever([])
    fallback_ans = "I could not find this information in the uploaded document."
    ollama_client = FakeOllamaClient(fallback_ans)

    service = ChatService(
        retriever=retriever,
        ollama_client=ollama_client,
        context_builder=ContextBuilder(),
        prompt_builder=PromptBuilder(),
        memory=ConversationMemory()
    )

    response = service.answer_question("doc_test", "What is the capital of Mars?")

    assert isinstance(response, GroundedAnswerResponse)
    assert response.answer == fallback_ans
    assert response.used_chunk_ids == []
    assert response.page_references == []
