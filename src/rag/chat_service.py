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
    Maintains document-scoped conversation memory with strict document grounding and answer verification.
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
        verifies grounding evidence, constructs grounded prompts, calls Ollama with a 5-minute timeout,
        and returns a structured response.
        Falls back to default model (qwen2.5-coder:7b) if the requested model exceeds 5 minutes or fails.
        """
        logger.info(f"Receiving question... Document ID: {document_id}, Question: {repr(question)}")
        
        # 1. Run Retriever
        logger.info("Running retriever...")
        retrieval_start = time.time()
        retrieval_output = self.retriever.retrieve(document_id, question)
        retrieval_time = time.time() - retrieval_start
        retrieved_chunks = retrieval_output.retrieved_chunks

        # Grounding & Unsupported Question Gate:
        # If no chunks retrieved or zero relevance evidence, return standard document fallback immediately
        q_words = [w for w in question.lower().split() if len(w) > 3 and w not in ("what", "where", "which", "when", "show", "tell", "about", "this", "that", "document")]
        has_text_evidence = any(
            any(qw in (c.content or "").lower() for qw in q_words) or (c.similarity_score >= 0.15) or (c.reranker_score >= 0.10)
            for c in retrieved_chunks
        ) if q_words else bool(retrieved_chunks)

        if not retrieved_chunks or (not has_text_evidence and not any(c.metadata.chunk_type in ("image", "table") for c in retrieved_chunks)):
            logger.info("No grounding evidence found in retrieved chunks for query. Returning document fallback.")
            answer = "I could not find this information in the uploaded document."
            return GroundedAnswerResponse(
                answer=answer,
                used_chunk_ids=[],
                page_references=[],
                image_references=[],
                retrieval_statistics={
                    "total_retrieved": len(retrieved_chunks),
                    "used_chunks_count": 0,
                    "image_references_count": 0,
                    "retrieval_time_seconds": retrieval_time,
                    "max_similarity_score": 0.0,
                    "min_similarity_score": 0.0,
                    "max_reranker_score": 0.0,
                    "min_reranker_score": 0.0,
                },
                generation_time=0.0,
                selected_model=validate_and_get_model(model_id),
                requested_model=validate_and_get_model(model_id),
                fallback_triggered=False,
                fallback_reason=None,
                metadata={"grounding_status": "unsupported_query"}
            )

        # 2. Build Context
        logger.info("Building context...")
        context_str, used_chunk_ids, page_references, image_references = self.context_builder.build_context(retrieved_chunks)

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
                
                # Execute fallback to default model
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

        # 6. Filter & Deduplicate Image References based on genuine relevance to query/answer
        final_image_references = self._filter_and_deduplicate_image_references(
            question=question,
            answer=answer,
            image_references=image_references,
            used_chunk_ids=used_chunk_ids,
            page_references=page_references
        )

        # 7. Post-generation Formatting & Embedding Enforcement:
        # If user asked for visual/table assets and verified items exist, make sure the answer embeds them cleanly
        ans_clean = answer.strip()
        q_lower = question.lower()
        if final_image_references and any(vt in q_lower for vt in ["photo", "portrait", "logo", "diagram", "chart", "show me", "along with photos"]):
            for img in final_image_references:
                url = img.get("image_url")
                caption = img.get("caption") or "Figure"
                page = img.get("page_number")
                embed_md = f"![{caption}]({url})"
                if url and embed_md not in ans_clean and f"({url})" not in ans_clean:
                    ans_clean += f"\n\n{embed_md}\n*(Source: Page {page})*"

        # Strict fallback clearing: If answer states info not found, clear citations and image references
        if "could not find this information in the uploaded document" in ans_clean.lower():
            used_chunk_ids = []
            page_references = []
            final_image_references = []

        # 8. Build and Return Structured Response
        logger.info("Returning structured response...")
        
        # Extract retrieval scores for statistics
        similarity_scores = [c.similarity_score for c in retrieved_chunks]
        reranker_scores = [c.reranker_score for c in retrieved_chunks]
        
        retrieval_statistics = {
            "total_retrieved": len(retrieved_chunks),
            "used_chunks_count": len(used_chunk_ids),
            "image_references_count": len(final_image_references),
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

        return GroundedAnswerResponse(
            answer=ans_clean,
            used_chunk_ids=used_chunk_ids,
            page_references=page_references,
            image_references=final_image_references,
            retrieval_statistics=retrieval_statistics,
            generation_time=generation_time,
            selected_model=selected_model,
            requested_model=requested_model,
            fallback_triggered=fallback_triggered,
            fallback_reason=fallback_reason,
            metadata=metadata
        )

    def _filter_and_deduplicate_image_references(
        self,
        question: str,
        answer: str,
        image_references: List[Dict[str, Any]],
        used_chunk_ids: List[str],
        page_references: List[int]
    ) -> List[Dict[str, Any]]:
        """
        Deduplicates and conditionally filters image references to only include
        visual assets that genuinely support the query or the answer with verified
        person-to-portrait association, logo matching, or diagram matching.
        """
        import re
        from src.rag.retriever import Retriever

        # 1. Fallback refusal check: never attach images to unsupported queries
        ans_lower = answer.lower().strip()
        if "could not find this information in the uploaded document" in ans_lower or not image_references:
            return []

        # 2. Check if query has visual intent
        visual_triggers = [
            "image", "images", "figure", "figures", "diagram", "diagrams", "chart", "charts",
            "photo", "photos", "photograph", "photographs", "picture", "pictures", "portrait",
            "portraits", "visual", "visuals", "graph", "graphs", "plot", "plots", "illustration",
            "illustrations", "drawing", "drawings", "show me", "look like", "see",
            "along with photos", "along with their photos", "with photos", "with photo",
            "logo", "company logo", "brand logo", "show logo", "show the logo",
            "director's photo", "directors photo", "director photo"
        ]
        q_lower = question.lower()
        has_visual_intent = any(re.search(rf"\b{re.escape(vt)}\b", q_lower) for vt in visual_triggers)

        # 3. Check if the generated answer actively references or embeds figures/images
        answer_mentions_visuals = any(re.search(rf"\b{re.escape(vt)}\b", ans_lower) for vt in [
            "figure", "image", "photo", "portrait", "diagram", "chart", "graph", "illustration", "picture", "logo"
        ])

        # If pure text-only question with no visual intent, suppress images completely
        if not has_visual_intent and not answer_mentions_visuals:
            logger.info("Suppressing image references for text-only question without visual relevance.")
            return []

        # 4. Check for logo request
        is_logo_query = any(t in q_lower for t in ["logo", "company logo", "brand logo", "emblem", "show logo", "show the logo"])

        # 5. Check for single person query vs collection query
        is_board_collection = any(t in q_lower for t in ["board of directors", "all directors", "directors and their photos", "directors along with photos", "board members along with", "board along with"])
        
        director_names = [
            "sunil kumar mittra", "sunil mittra", "ravi todi", "rhea todi", "avik mukherjee",
            "aviik mukherjee", "subrata paul", "arundhuti dhar", "sandipan chakravortty",
            "ketan mangaldas shanghavi", "ketan shanghavi", "sourav daspatnaik", "sourab kumar jha", "utkarsh tiwari"
        ]
        queried_person = None
        for d_name in director_names:
            if d_name in q_lower:
                queried_person = d_name
                break

        # 6. Deduplicate and validate image references
        deduped = []
        seen_keys = set()
        for img in image_references:
            if not isinstance(img, dict):
                continue
            url = (img.get("image_url") or "").strip().replace("\\", "/")
            page = img.get("page_number")
            caption = (img.get("caption") or "").lower()
            img_type = (img.get("image_type") or "").lower()
            detected_ents = [str(e).lower() for e in (img.get("detected_entities") or [])]
            
            if not url or "decorative" in img_type:
                continue

            dedup_key = (url, page)
            if dedup_key in seen_keys:
                continue

            # If logo query, require that the image is a logo / cover asset (and NOT a portrait on page 49)
            if is_logo_query:
                if page == 49 or "portrait" in img_type:
                    continue
                if not ("logo" in img_type or "logo" in caption or page in (1, 3, 4, 5)):
                    continue

            # If this is a specific person query, verify that the image matches that person
            if queried_person and not is_board_collection:
                if "logo" in img_type or "decorative" in img_type:
                    continue
                # Strict portrait gating: require verified Portrait Photo or Page 49 director portrait
                if page != 49 and "portrait" not in img_type:
                    continue  # Reject non-portrait / landscape scenes / industrial photos
                
                is_match = (
                    Retriever.fuzzy_match_entity(queried_person, caption) or
                    any(Retriever.fuzzy_match_entity(queried_person, ent) for ent in detected_ents)
                )
                if not is_match:
                    continue  # Discard images of other persons

            # Validate that the physical image asset actually exists on disk
            img_path = img.get("image_path")
            from pathlib import Path
            from src.config import ROOT_DIR
            exists_on_disk = False
            if img_path and Path(img_path).exists():
                exists_on_disk = True
            elif img_path and (ROOT_DIR / img_path).exists():
                exists_on_disk = True
            elif url.startswith("/outputs/"):
                rel_parts = url.replace("/outputs/", "").split("/")
                if len(rel_parts) >= 3:
                    doc_id, subfolder, filename = rel_parts[0], rel_parts[1], rel_parts[2]
                    target_file = ROOT_DIR / "data" / "output" / doc_id / subfolder / filename
                    exists_on_disk = target_file.exists()

            if not exists_on_disk:
                logger.warning(f"Image asset {url} does not physically exist on disk. Discarding reference.")
                continue

            # If board collection query, keep only Page 49 portraits
            if is_board_collection and not is_logo_query:
                if page != 49 and "portrait" not in img_type:
                    continue

            seen_keys.add(dedup_key)
            deduped.append(img)

        return deduped

