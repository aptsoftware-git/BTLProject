from __future__ import annotations

import logging
from typing import List, Dict, Set, Optional
from src.comparative_analysis.models import TargetCompanyProfile, CompanyProfileChunk
from src.rag.config import RagConfig
from src.rag.retriever import Retriever
from src.rag.chunk_schema import DocumentChunk

logger = logging.getLogger("comparative_analysis.company_profile_retriever")

BUSINESS_QUERIES = [
    "Company Overview",
    "About the Company",
    "Industry",
    "Core Services",
    "Products",
    "Solutions",
    "Projects",
    "Technologies",
    "Clients",
    "Business Verticals",
    "Markets",
    "Geographic Presence",
    "Certifications",
    "Awards",
    "Mission",
    "Vision",
]


class CompanyProfileRetriever:
    """
    Component responsible for retrieving business-related chunks from the ChromaDB vector store
    or local indexed chunks for a given document_id using semantic search across 16 predefined queries.

    CRITICAL INVARIANT:
    - This component is NOT an LLM.
    - Does NOT summarize anything.
    - Does NOT re-process or re-parse the uploaded document from scratch.
    - Reuses existing RAG / ChromaDB / Embedding infrastructure.
    """

    def __init__(
        self,
        config: Optional[RagConfig] = None,
        top_k_per_query: int = 5
    ) -> None:
        """
        Initialize CompanyProfileRetriever.

        Args:
            config: RagConfig instance. If None, uses default RagConfig.
            top_k_per_query: Number of top matching chunks to retrieve per predefined business query.
        """
        self.config = config or RagConfig()
        self.top_k_per_query = top_k_per_query
        self._retriever: Optional[Retriever] = None

    @property
    def retriever(self) -> Retriever:
        """Lazy load RAG retriever instance."""
        if self._retriever is None:
            self._retriever = Retriever.from_config(self.config)
        return self._retriever

    def retrieve_profile(self, document_id: str) -> TargetCompanyProfile:
        """
        Performs multi-query semantic retrieval across ChromaDB for the document_id.

        Args:
            document_id: Unique identifier for the indexed document.

        Returns:
            TargetCompanyProfile containing consolidated, deduplicated, and similarity-ranked chunks.
        """
        logger.info("Initiating Phase 2 Company Profile Retrieval for document_id: %s", document_id)

        chunk_map: Dict[str, CompanyProfileChunk] = {}
        seen_texts: Set[str] = set()

        try:
            # 1. Attempt multi-query vector search across all 16 business queries
            for b_query in BUSINESS_QUERIES:
                try:
                    # Generate query embedding via existing QueryProcessor
                    query_emb = self.retriever.query_processor.generate_query_embedding(b_query)
                    
                    # Search vector store
                    vector_results = self.retriever._search_vector_store(
                        document_id=document_id,
                        query_emb=query_emb,
                        metadata_filter=None,
                        n_results=self.top_k_per_query
                    )

                    for chunk, sim_score in vector_results:
                        cid = chunk.metadata.chunk_id if (chunk and chunk.metadata) else f"chunk_{len(chunk_map)}"
                        text_normalized = chunk.content.strip().lower()

                        if cid not in chunk_map and text_normalized not in seen_texts:
                            seen_texts.add(text_normalized)
                            chunk_map[cid] = CompanyProfileChunk(
                                chunk_id=cid,
                                text=chunk.content,
                                metadata={
                                    "heading": getattr(chunk.metadata, "heading", None),
                                    "section": getattr(chunk.metadata, "section", None),
                                    "chunk_type": getattr(chunk.metadata, "chunk_type", "text"),
                                },
                                page_number=getattr(chunk.metadata, "page_number", 1),
                                similarity_score=round(float(sim_score), 4),
                                query_matched=b_query
                            )
                        elif cid in chunk_map:
                            # Update score if higher score found for duplicate chunk
                            if float(sim_score) > chunk_map[cid].similarity_score:
                                chunk_map[cid].similarity_score = round(float(sim_score), 4)

                except Exception as q_err:
                    logger.warning("Error searching query '%s' in ChromaDB: %s", b_query, q_err)

        except Exception as err:
            logger.error("ChromaDB vector search encountered an issue: %s", err)

        # 2. Fallback / supplementary chunk loading if ChromaDB queries returned fewer chunks
        if len(chunk_map) < 3:
            logger.info("Loading document chunks directly via load_stage6_chunks fallback for %s", document_id)
            try:
                from src.rag.chunk_utils import load_stage6_chunks
                from src.config import ROOT_DIR
                job_dir = ROOT_DIR / "data" / "output" / document_id
                c_data = load_stage6_chunks(job_dir, doc_id=document_id)
                fallback_chunks = c_data.get("chunks", [])
                for idx, c in enumerate(fallback_chunks):
                    cid = (c.get("metadata") or {}).get("chunk_id") or f"fallback_chunk_{idx}"
                    c_content = c.get("content") or c.get("text") or ""
                    text_norm = c_content.strip().lower()
                    if cid not in chunk_map and text_norm not in seen_texts:
                        seen_texts.add(text_norm)
                        p_num = (c.get("metadata") or {}).get("page_number") or 1
                        matched_q = "General Overview"
                        for q in BUSINESS_QUERIES:
                            if q.lower() in c_content.lower():
                                matched_q = q
                                break
                        
                        chunk_map[cid] = CompanyProfileChunk(
                            chunk_id=cid,
                            text=c_content,
                            metadata=c.get("metadata") or {},
                            page_number=p_num,
                            similarity_score=0.5,
                            query_matched=matched_q
                        )
            except Exception as fb_err:
                logger.error("Failed loading fallback document chunks: %s", fb_err)

        # 3. Consolidate and rank chunks by similarity score descending
        consolidated_chunks = list(chunk_map.values())
        consolidated_chunks.sort(key=lambda x: x.similarity_score, reverse=True)

        logger.info(
            "CompanyProfileRetriever finished: retrieved & deduplicated %d relevant chunks for document_id %s",
            len(consolidated_chunks),
            document_id
        )

        return TargetCompanyProfile(
            document_id=document_id,
            total_chunks=len(consolidated_chunks),
            chunks=consolidated_chunks,
            source_filename=f"doc_{document_id}.pdf"
        )
