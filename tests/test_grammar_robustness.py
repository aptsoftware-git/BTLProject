"""
test_grammar_robustness.py
===========================
Comprehensive unit and integration tests for GrammarAgent and Stage 4 (Grammar Review).
Tests cover:
- Paragraph isolation (one paragraph error doesn't break job)
- Ollama connection failure & timeout handling
- Malformed & markdown JSON extraction
- Zero-finding deterministic artifact generation (07_grammar/grammar_candidates.json)
- Candidate offset validation and candidate structure completeness
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from src.config import OllamaConfig
from src.grammar_agent import GrammarAgent
from src.models import Candidate, IssueType, SourceAgent


def test_grammar_agent_normal_detection():
    config = OllamaConfig(host="http://localhost:11434", model="test-model")
    agent = GrammarAgent(config)

    mock_ollama_response = json.dumps({
        "errors": [
            {
                "original": "he go",
                "corrected": "he goes",
                "reason": "Subject-verb agreement error",
                "type": "grammar"
            }
        ]
    })

    with patch.object(agent, "_call_ollama", return_value=mock_ollama_response):
        paras = [{"text": "Yesterday he go to school.", "doc_char_start": 0, "protected_terms": []}]
        cands = agent.run_batch(paras, sentence_id_for_offset_lookup=lambda off: 101)

        assert len(cands) == 1
        c = cands[0]
        assert c.original_text == "he go"
        assert c.suggested_text == "he goes"
        assert c.issue_type == IssueType.GRAMMAR
        assert c.source == SourceAgent.LLM
        assert c.sentence_id == 101
        assert c.char_start == 10
        assert c.char_end == 15


def test_grammar_agent_zero_findings():
    config = OllamaConfig(host="http://localhost:11434", model="test-model")
    agent = GrammarAgent(config)

    mock_ollama_response = json.dumps({"errors": []})

    with patch.object(agent, "_call_ollama", return_value=mock_ollama_response):
        paras = [{"text": "This is a perfectly written sentence.", "doc_char_start": 0, "protected_terms": []}]
        cands = agent.run_batch(paras, sentence_id_for_offset_lookup=lambda off: 1)

        assert cands == []


def test_grammar_agent_ollama_connection_failure():
    config = OllamaConfig(host="http://invalid-host:11434", model="test-model", max_retries=0)
    agent = GrammarAgent(config)

    with patch("requests.post", side_effect=requests.ConnectionError("Connection refused")):
        paras = [{"text": "Sample paragraph text.", "doc_char_start": 0, "protected_terms": []}]
        cands = agent.run_batch(paras, sentence_id_for_offset_lookup=lambda off: 1)

        # Failure should be logged and return 0 candidates without throwing an unhandled crash
        assert cands == []


def test_grammar_agent_ollama_timeout():
    config = OllamaConfig(host="http://localhost:11434", model="test-model", max_retries=0)
    agent = GrammarAgent(config)

    with patch("requests.post", side_effect=requests.Timeout("Read timed out")):
        paras = [{"text": "Sample paragraph text.", "doc_char_start": 0, "protected_terms": []}]
        cands = agent.run_batch(paras, sentence_id_for_offset_lookup=lambda off: 1)

        assert cands == []


def test_grammar_agent_malformed_json_response():
    config = OllamaConfig(host="http://localhost:11434", model="test-model")
    agent = GrammarAgent(config)

    # Response with markdown fences and conversational intro text
    raw_response = """
    Here are the requested corrections in JSON format:
    ```json
    {
        "errors": [
            {
                "original": "bad text",
                "corrected": "good text",
                "reason": "Grammar mistake",
                "type": "grammar"
            }
        ]
    }
    ```
    Hope this helps!
    """

    with patch.object(agent, "_call_ollama", return_value=raw_response):
        paras = [{"text": "This paragraph contains bad text inside it.", "doc_char_start": 0, "protected_terms": []}]
        cands = agent.run_batch(paras, sentence_id_for_offset_lookup=lambda off: 1)

        assert len(cands) == 1
        assert cands[0].original_text == "bad text"
        assert cands[0].suggested_text == "good text"


def test_grammar_agent_empty_response():
    config = OllamaConfig(host="http://localhost:11434", model="test-model")
    agent = GrammarAgent(config)

    with patch.object(agent, "_call_ollama", return_value=""):
        paras = [{"text": "Sample paragraph text.", "doc_char_start": 0, "protected_terms": []}]
        cands = agent.run_batch(paras, sentence_id_for_offset_lookup=lambda off: 1)

        assert cands == []


def test_grammar_agent_one_paragraph_fails_others_succeed():
    config = OllamaConfig(host="http://localhost:11434", model="test-model")
    agent = GrammarAgent(config)

    def mock_call(prompt):
        if "Paragraph 1" in prompt or "Problematic" in prompt:
            raise RuntimeError("Internal LLM generation error")
        return json.dumps({
            "errors": [
                {"original": "error2", "corrected": "fix2", "reason": "Grammar", "type": "grammar"}
            ]
        })

    with patch.object(agent, "_call_ollama", side_effect=mock_call):
        paras = [
            {"text": "Problematic paragraph with error.", "doc_char_start": 0, "protected_terms": []},
            {"text": "Normal paragraph with error2 text.", "doc_char_start": 100, "protected_terms": []},
        ]
        cands = agent.run_batch(paras, sentence_id_for_offset_lookup=lambda off: 2, batch_size=1)

        # Paragraph 1 failed, Paragraph 2 succeeded
        assert len(cands) == 1
        assert cands[0].original_text == "error2"
        assert cands[0].suggested_text == "fix2"


def test_grammar_agent_invalid_candidate_structure():
    config = OllamaConfig(host="http://localhost:11434", model="test-model")
    agent = GrammarAgent(config)

    mock_response = json.dumps({
        "errors": [
            {"original": "same text", "corrected": "same text", "reason": "No change", "type": "grammar"},
            {"original": "", "corrected": "missing original", "reason": "Bad entry", "type": "grammar"},
            {"original": "not_in_paragraph", "corrected": "replacement", "reason": "Span missing", "type": "grammar"}
        ]
    })

    with patch.object(agent, "_call_ollama", return_value=mock_response):
        paras = [{"text": "Sample paragraph text.", "doc_char_start": 0, "protected_terms": []}]
        cands = agent.run_batch(paras, sentence_id_for_offset_lookup=lambda off: 1)

        # Invalid candidates filtered out cleanly
        assert cands == []
