import logging
import re
from typing import List, Set, Tuple
from src.rag.retrieval_models import ScoredChunk

logger = logging.getLogger("pipeline")

class ContextBuilder:
    """
    Builds RAG context strings from retrieved document chunks.
    Ensures token limits are respected, original document order is preserved,
    duplicate chunks are removed, and formatting is retained.
    """
    def __init__(self, max_tokens: int = 4000):
        self.max_tokens = max_tokens

    @staticmethod
    def _parse_chunk_index(chunk_id: str) -> int:
        """
        Extracts the numeric index from a chunk ID formatted like '{doc_id}_chunk_{idx:04d}'.
        """
        try:
            match = re.search(r"_chunk_(\d+)", chunk_id)
            if match:
                return int(match.group(1))
        except Exception:
            pass
        return 0

    def build_context(self, retrieved_chunks: List[ScoredChunk]) -> Tuple[str, List[str], List[int]]:
        """
        Selects chunks based on relevance/reranker scores up to max_tokens, 
        de-duplicates them, sorts them by original document order, and formats the context.
        
        Returns:
            Tuple[context_str, used_chunk_ids, page_references]
        """
        logger.info("Building context from retrieved chunks...")
        
        # 1. De-duplicate chunks based on chunk_id while preserving retrieval order
        seen_chunk_ids: Set[str] = set()
        deduplicated_chunks: List[ScoredChunk] = []
        for chunk in retrieved_chunks:
            chunk_id = chunk.metadata.chunk_id
            if chunk_id not in seen_chunk_ids:
                seen_chunk_ids.add(chunk_id)
                deduplicated_chunks.append(chunk)

        # 2. Select chunks up to max_tokens (respecting reranker ordering as input is sorted by reranker score)
        selected_chunks: List[ScoredChunk] = []
        current_tokens = 0
        
        for chunk in deduplicated_chunks:
            # Estimate tokens: use metadata estimate, fallback to character count estimation if 0 or None
            token_est = chunk.metadata.token_estimate or (len(chunk.content) // 4)
            # Add some token overhead for formatting (headings, page number labels)
            formatted_overhead_est = 50 
            
            if current_tokens + token_est + formatted_overhead_est <= self.max_tokens:
                selected_chunks.append(chunk)
                current_tokens += (token_est + formatted_overhead_est)
            else:
                logger.info(f"Skipping chunk {chunk.metadata.chunk_id} to avoid exceeding context window limit of {self.max_tokens} tokens.")
        
        # 3. Sort selected chunks to preserve original document order (by page number, then chunk index)
        selected_chunks.sort(key=lambda c: (c.metadata.page_number, self._parse_chunk_index(c.metadata.chunk_id)))

        # 3.5 Dynamic adjacent chunk merging (Phase 6 Optimization)
        merged_chunks = []
        for chunk in selected_chunks:
            if not merged_chunks:
                merged_chunks.append(chunk)
            else:
                prev = merged_chunks[-1]
                prev_idx = self._parse_chunk_index(prev.metadata.chunk_id)
                curr_idx = self._parse_chunk_index(chunk.metadata.chunk_id)
                
                if (curr_idx == prev_idx + 1 and 
                    prev.metadata.document_id == chunk.metadata.document_id and
                    prev.metadata.page_number == chunk.metadata.page_number and
                    prev.metadata.section == chunk.metadata.section):
                    
                    prev.content += "\n\n" + chunk.content
                    logger.info(f"Dynamically merged adjacent chunks {prev.metadata.chunk_id} and {chunk.metadata.chunk_id}")
                else:
                    merged_chunks.append(chunk)
        selected_chunks = merged_chunks

        # 4. Format context string
        context_parts = []
        used_chunk_ids = []
        page_references = set()
        
        for chunk in selected_chunks:
            used_chunk_ids.append(chunk.metadata.chunk_id)
            page_references.add(chunk.metadata.page_number)
            
            section_info = f"Section: {chunk.metadata.section}" if chunk.metadata.section else ""
            heading_info = f"Heading: {chunk.metadata.heading}" if chunk.metadata.heading else ""
            meta_header = f"[Page {chunk.metadata.page_number}]"
            if section_info or heading_info:
                meta_header += f" | {' > '.join(filter(None, [section_info, heading_info]))}"
            
            formatted_chunk = (
                f"{meta_header}\n"
                f"Content:\n{chunk.content.strip()}\n"
                f"-----------------------------------------\n"
            )
            context_parts.append(formatted_chunk)

        context_str = "\n".join(context_parts)
        
        logger.info(f"Context constructed with {len(selected_chunks)} chunks, total token estimate ~{current_tokens}.")
        return context_str, used_chunk_ids, sorted(list(page_references))
