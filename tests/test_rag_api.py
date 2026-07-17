import pytest
import asyncio
from unittest.mock import patch, MagicMock

from backend.routes import (
    get_rag_models,
    rag_chat,
    get_rag_history,
    delete_rag_history,
    clear_rag_history_post
)
from backend.schemas import RagChatRequest
from src.rag.response_models import GroundedAnswerResponse


def run_async(coro):
    """Helper to run async coroutines synchronously in tests."""
    return asyncio.run(coro)


def test_api_get_models():
    """
    Verifies get_rag_models route returns supported model list with recommended flag.
    """
    response = run_async(get_rag_models())
    assert len(response) == 5
    
    # Verify model fields
    model_ids = [m.id for m in response]
    assert "qwen2.5-coder:32b" in model_ids
    assert "deepseek-r1:32b" in model_ids
    
    # Verify recommended flag
    qwen_coder = next(m for m in response if m.id == "qwen2.5-coder:32b")
    assert qwen_coder.recommended is True
    
    deepseek = next(m for m in response if m.id == "deepseek-r1:32b")
    assert deepseek.recommended is False


@patch("backend.routes.get_chat_service")
def test_api_chat(mock_get_service):
    """
    Verifies rag_chat route generates grounded answer response using ChatService.
    """
    mock_service = MagicMock()
    mock_response = GroundedAnswerResponse(
        answer="FastAPI RAG is connected end-to-end.",
        used_chunk_ids=["chunk_a1"],
        page_references=[2],
        retrieval_statistics={"total_retrieved": 2},
        generation_time=1.2,
        selected_model="qwen2.5-coder:32b"
    )
    mock_service.answer_question.return_value = mock_response
    mock_get_service.return_value = mock_service

    payload = RagChatRequest(
        document_id="test_doc_id",
        question="Is the RAG connected?",
        selected_model="qwen2.5-coder:32b",
        conversation_history_depth=5
    )

    response = run_async(rag_chat(payload))
    assert response.answer == "FastAPI RAG is connected end-to-end."
    assert response.used_chunk_ids == ["chunk_a1"]
    assert response.page_references == [2]
    
    # Assert ChatService was invoked with correct arguments
    mock_service.answer_question.assert_called_once_with(
        document_id="test_doc_id",
        question="Is the RAG connected?",
        model_id="qwen2.5-coder:32b",
        history_depth=5
    )


@patch("backend.routes.get_chat_service")
def test_api_history_and_clear(mock_get_service):
    """
    Verifies conversation history routes for fetching, clearing, and post-clearing.
    """
    mock_service = MagicMock()
    mock_service.memory.get_history.return_value = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there"}
    ]
    mock_get_service.return_value = mock_service

    # 1. Test GET history
    response = run_async(get_rag_history("test_doc_id"))
    assert response["document_id"] == "test_doc_id"
    assert len(response["history"]) == 2
    assert response["history"][0]["role"] == "user"

    # 2. Test DELETE history
    response = run_async(delete_rag_history("test_doc_id"))
    assert response["status"] == "success"
    mock_service.memory.clear_history.assert_called_with("test_doc_id")

    # 3. Test POST clear history
    response = run_async(clear_rag_history_post("test_doc_id"))
    assert response["status"] == "success"
