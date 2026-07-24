import time
import logging
from typing import List, Dict, Any, Optional

from src.rag.config import RagConfig
from src.rag.retriever import Retriever
from src.rag.context_builder import ContextBuilder
from src.rag.prompt_builder import PromptBuilder
from src.rag.ollama_client import OllamaClient
from src.rag.conversation_memory import ConversationMemory
from src.rag.response_models import GroundedAnswerResponse
from src.rag.llm import validate_and_get_model, DEFAULT_MODEL_ID

logger = logging.getLogger("pipeline")

class ChatService:
    """
    Orchestrates the AI Answer Generation Layer (RAG).
    Handles: Question -> Retriever -> Context Builder -> Prompt Builder -> Selected Local LLM -> Structured Response.
    Maintains document-scoped conversation memory.
    """
    def __init__(
        self,
        retriever: Optional[Retriever] = None,
        ollama_client: Optional[OllamaClient] = None,
        context_builder: Optional[ContextBuilder] = None,
        prompt_builder: Optional[PromptBuilder] = None,
        memory: Optional[ConversationMemory] = None,
    ):
        # Allow injecting custom instances for testability
        self.retriever = retriever or Retriever.from_config()
        self.ollama_client = ollama_client or OllamaClient()
        self.context_builder = context_builder or ContextBuilder()
        self.prompt_builder = prompt_builder or PromptBuilder()
        self.memory = memory or ConversationMemory()

    def answer_question(
        self,
        document_id: str,
        question: str,
        model_id: Optional[str] = None,
        history_depth: Optional[int] = None,
    ) -> GroundedAnswerResponse:
        """
        Processes a user question about a document, performs hybrid retrieval, 
        constructs grounded prompts, calls Ollama with a 5-minute timeout, and returns a structured response.
        Falls back to default model (qwen2.5-coder:32b) if the requested model exceeds 5 minutes or fails.
        """
        logger.info(f"Receiving question... Document ID: {document_id}, Question: {repr(question)}")
        
        # 1. Run Retriever
        logger.info("Running retriever...")
        retrieval_start = time.time()
        retrieval_output = self.retriever.retrieve(document_id, question)
        retrieval_time = time.time() - retrieval_start
        retrieved_chunks = retrieval_output.retrieved_chunks

        # 2. Build Context
        logger.info("Building context...")
        context_str, used_chunk_ids, page_references = self.context_builder.build_context(retrieved_chunks)

        # 3. Retrieve Conversation History & Build Prompt
        logger.info("Preparing prompt...")
        history = self.memory.get_history(document_id, depth=history_depth)
        prompt_data = self.prompt_builder.build_prompt(context_str, question, history)

        # 4. Generate Answer using the Selected Model (5-minute timeout & automatic fallback to default)
        logger.info("Calling Ollama...")
        requested_model = validate_and_get_model(model_id)
        default_model = DEFAULT_MODEL_ID

        selected_model = requested_model
        fallback_triggered = False
        fallback_reason = None
        
        generation_start = time.time()
        try:
            logger.info(f"Attempting answer generation with model '{requested_model}' (timeout: 300s / 5 mins)...")
            answer = self.ollama_client.generate(
                model=requested_model,
                prompt=prompt_data["prompt"],
                system=prompt_data["system"],
                timeout=300
            )
        except Exception as err:
            if requested_model != default_model:
                logger.warning(
                    f"Model '{requested_model}' failed or exceeded 5 minutes timeout: {err}. "
                    f"Falling back to default model '{default_model}'..."
                )
                fallback_triggered = True
                fallback_reason = (
                    f"Requested model '{requested_model}' exceeded 5-minute timeout or failed ({str(err)}). "
                    f"Automatically fell back to default model '{default_model}'."
                )
                selected_model = default_model
                
                # Execute fallback to default model (qwen2.5-coder:32b)
                answer = self.ollama_client.generate(
                    model=default_model,
                    prompt=prompt_data["prompt"],
                    system=prompt_data["system"],
                    timeout=300
                )
            else:
                raise err

        generation_time = time.time() - generation_start
        logger.info(f"Answer generated successfully using model '{selected_model}' in {generation_time:.2f}s.")

        # 5. Save Interaction to Conversation Memory
        self.memory.add_message(document_id, "user", question)
        self.memory.add_message(document_id, "assistant", answer)

        # 6. Build and Return Structured Response
        logger.info("Returning structured response...")
        
        # Extract retrieval scores for statistics
        similarity_scores = [c.similarity_score for c in retrieved_chunks]
        reranker_scores = [c.reranker_score for c in retrieved_chunks]
        
        retrieval_statistics = {
            "total_retrieved": len(retrieved_chunks),
            "used_chunks_count": len(used_chunk_ids),
            "retrieval_time_seconds": retrieval_time,
            "max_similarity_score": max(similarity_scores) if similarity_scores else 0.0,
            "min_similarity_score": min(similarity_scores) if similarity_scores else 0.0,
            "max_reranker_score": max(reranker_scores) if reranker_scores else 0.0,
            "min_reranker_score": min(reranker_scores) if reranker_scores else 0.0,
        }

        metadata = {
            "prompt_length": len(prompt_data["prompt"]),
            "system_prompt_length": len(prompt_data["system"]),
            "history_length": len(history),
            "requested_model": requested_model,
            "selected_model": selected_model,
            "fallback_triggered": fallback_triggered,
            "fallback_reason": fallback_reason,
            "debug_info": retrieval_output.debug_info
        }

        # Print developer debug logs (Phase 6 Optimization)
        if retrieval_output.debug_info:
            logger.info("======= DEVELOPER RETRIEVAL DEBUG =======")
            logger.info(f"Query Intent: {retrieval_output.debug_info.get('intent')}")
            logger.info(f"Retrieval Depth Config: {retrieval_output.debug_info.get('top_k_retrieve')} -> {retrieval_output.debug_info.get('top_k_rerank')} -> {retrieval_output.debug_info.get('top_k_final')}")
            logger.info("Top Candidates Reranked:")
            for cand in retrieval_output.debug_info.get("candidates", []):
                logger.info(f"  - Chunk: {cand['chunk_id']} (Page {cand['page']}) | RRF: {cand['rrf_score']:.4f} | Sem: {cand['similarity_score']:.4f} | Heading: {cand['heading']}")
            logger.info(f"Context Length: {len(context_str)} characters")
            logger.info("=========================================")

        return GroundedAnswerResponse(
            answer=answer.strip(),
            used_chunk_ids=used_chunk_ids,
            page_references=page_references,
            retrieval_statistics=retrieval_statistics,
            generation_time=generation_time,
            selected_model=selected_model,
            requested_model=requested_model,
            fallback_triggered=fallback_triggered,
            fallback_reason=fallback_reason,
            metadata=metadata
        )
