import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Set

from src.rag.config import RagConfig
from src.rag.chunk_schema import DocumentChunk, ChunkMetadata
from src.rag.query_processor import QueryProcessor
from src.rag.bm25_search import BM25Search
from src.rag.hybrid_search import HybridSearch
from src.rag.reranker import Reranker
from src.rag.vector_store import VectorStore
from src.rag.retrieval_models import ScoredChunk, RetrievalOutput
from src.rag.document_schema import BoundingBox, StructuredDocument, DocumentElement

logger = logging.getLogger("pipeline")

class Retriever:
    """
    Main RAG retrieval engine coordinating query processing, hybrid search (semantic + BM25),
    metadata filtering, and cross-encoder reranking.
    """

    def __init__(
        self, 
        config: RagConfig, 
        query_processor: QueryProcessor,
        vector_store: VectorStore,
        reranker: Reranker
    ) -> None:
        self.config = config
        self.query_processor = query_processor
        self.vector_store = vector_store
        self.reranker = reranker

    @classmethod
    def from_config(cls, config: Optional[RagConfig] = None) -> "Retriever":
        """
        Factory method to initialize the Retriever and all its dependencies from a RAG configuration.
        """
        config = config or RagConfig()
        
        from src.rag.embedding_provider import SentenceTransformersEmbeddingProvider
        from src.rag.embedder import Embedder
        
        # Ingest/indexing dependencies
        provider = SentenceTransformersEmbeddingProvider(
            model_name=config.embedding_model,
            device=config.embedding_device
        )
        embedder = Embedder(provider)
        vector_store = VectorStore(db_dir=config.chroma_db_dir, collection_prefix=config.collection_prefix)
        query_processor = QueryProcessor(embedder)
        
        # Reranking dependencies
        reranker = Reranker(model_name=config.reranker_model, device=config.reranker_device)
        
        return cls(config, query_processor, vector_store, reranker)

    def detect_intent(self, query: str) -> str:
        import re
        q = query.lower()
        
        def has_any(terms):
            return any(re.search(rf"\b{re.escape(term)}\b", q) for term in terms)
        
        # 1. Visual / Image Intent
        visual_terms = [
            "chart", "graph", "diagram", "figure", "image", "illustration", "photo", "picture",
            "flowchart", "architecture", "map", "plot", "layout", "visual", "look like",
            "sketch", "infographic", "schematic", "trend", "pie chart", "bar chart"
        ]
        if has_any(visual_terms):
            return "visual"
            
        # 2. Table / Tabular Intent
        table_terms = ["table", "tabular", "column", "row", "metrics table", "comparison table", "schedule", "sprint progress"]
        if has_any(table_terms):
            return "table_based"

        # 3. Leadership & Board Governance
        board_terms = [
            "board of directors", "composition of board", "board members", "directors",
            "managing director", "whole-time director", "whole time director", "executive director",
            "independent director", "non-executive director", "chairman", "chairperson",
            "executive chairman", "key managerial personnel", "kmp", "audit committee",
            "nomination committee", "stakeholder committee", "csr committee", "governance", "leadership"
        ]
        if has_any(board_terms):
            return "leadership_board"

        # 4. Entity / Person Lookup (Auditors, Executives, Founders)
        person_lookup_terms = [
            "who is", "who are", "who was", "name of the", "names of", "person", "people",
            "auditor", "auditors", "statutory auditor", "statutory auditors", "internal auditor",
            "secretarial auditor", "cost auditor", "cfo", "chief financial officer", "cs",
            "company secretary", "compliance officer", "founder", "promoter"
        ]
        if has_any(person_lookup_terms):
            return "entity_person_lookup"

        # 5. Financial Metrics & Performance
        financial_terms = [
            "revenue", "turnover", "income", "sales", "earnings", "profit", "pat", "pbt", "ebitda",
            "financial", "fy24", "fy25", "fy23", "crore", "lakh", "million", "billion", "balance sheet",
            "p&l", "profit and loss", "cash flow", "dividend", "expenditure", "net worth", "borrowings",
            "assets", "liabilities", "standalone", "consolidated"
        ]
        if has_any(financial_terms):
            return "financial"

        # 6. Direct Factual / Entity Lookups (Registered Office, CIN, Incorporation, Definition)
        factual_terms = [
            "registered office", "corporate office", "cin", "corporate identification number",
            "founded", "established in", "year of incorporation", "date of incorporation",
            "isin", "listing", "symbol", "pan", "tan", "gst", "address of", "contact details",
            "headquarters", "where is the office", "incorporation", "when was", "what is the date"
        ]
        if has_any(factual_terms):
            return "direct_factual"

        # 7. Broad Summary & Syntheses
        summary_terms = ["summarise", "summarize", "summary", "overview", "synopsis", "outline", "all divisions", "cross-page", "executive summary", "comprehensive"]
        if has_any(summary_terms):
            if "detail" in q or "comprehensive" in q or "extensive" in q:
                return "detailed_summary"
            return "broad_summary"

        # Secondary / Legacy Intent Mappings
        if has_any(["timeline", "chronology", "history", "chronological", "sequence"]):
            return "timeline"
        if has_any(["compare", "comparison", "difference", "versus", "vs", "similarities"]):
            return "comparison"
        if has_any(["product", "services", "offerings", "brands"]):
            return "product"
        if has_any(["plant", "manufactur", "factory", "site", "production"]):
            return "manufacturing"
        if has_any(["list", "enumerate", "name all", "what are the", "which people", "entities"]):
            return "list"
        if has_any(["how to", "procedure", "steps", "guide", "instructions", "process"]):
            return "procedure"
        if has_any(["percent", "ratio", "statistics", "stats", "rate", "number of"]):
            return "statistics"
        if has_any(["section", "chapter", "page", "navigate", "go to", "find in"]):
            return "navigation"
        if has_any(["explain", "why", "how", "reason"]):
            return "explanation"
            
        return "direct_factual"

    def _get_intent_depth(self, intent: str) -> Tuple[int, int, int]:
        # returns (top_k_retrieve, top_k_rerank, top_k_final)
        depths = {
            "direct_factual": (25, 15, 6),
            "entity_person_lookup": (40, 25, 10),
            "leadership_board": (45, 30, 12),
            "financial": (45, 30, 12),
            "table_based": (40, 25, 10),
            "broad_summary": (60, 40, 20),
            "detailed_summary": (60, 40, 20),
            "visual": (35, 20, 8),
            "image": (35, 20, 8),
            "summary": (50, 30, 12),
            "timeline": (40, 25, 12),
            "comparison": (45, 25, 12),
            "board": (45, 30, 12),
            "governance": (45, 30, 12),
            "committee": (45, 30, 12),
            "product": (35, 20, 8),
            "manufacturing": (35, 20, 8),
            "table": (40, 25, 10),
            "list": (40, 25, 10),
            "procedure": (30, 15, 8),
            "statistics": (30, 15, 8),
            "navigation": (30, 15, 8),
            "explanation": (30, 15, 8),
            "fact": (25, 15, 6)
        }
        return depths.get(intent, (30, 15, 8))

    def expand_query(self, query: str) -> str:
        """
        Expands query terms with corporate, leadership, financial, and domain-specific aliases.
        """
        import re
        expanded = query
        synonyms = {
            r"\b(managing director|md)\b": "managing director MD Ravi Todi promoter and managing director executive director",
            r"\b(whole-time director|whole time director|wtd)\b": "whole-time director whole time director WTD Rhea Todi executive director",
            r"\b(independent director|independent directors)\b": "independent director non-executive independent director Sourav Daspatnaik committee chairman",
            r"\b(board of directors|board members|the board|directors)\b": "board of directors directors board members corporate governance composition of board executive committee",
            r"\b(chairman|chairperson)\b": "board chairman chairperson executive chairman S.K. Todi Sourav Daspatnaik leadership",
            r"\b(chief financial officer|cfo)\b": "chief financial officer CFO head of finance finance director",
            r"\b(company secretary|cs)\b": "company secretary CS compliance officer",
            r"\b(statutory auditor|statutory auditors|auditor's report|auditor opinion|auditors)\b": "statutory auditor statutory auditors independent auditor independent auditor's report audit report opinion Ind AS",
            r"\b(registered office|corporate office)\b": "registered office corporate office address Kolkata West Bengal CIN",
            r"\b(revenue|turnover|sales)\b": "revenue from operations total income turnover sales gross revenue financial performance",
            r"\b(profit|pat|pbt)\b": "profit after tax PAT profit before tax PBT net profit net income operating profit",
            r"\b(financial performance|financial results)\b": "standalone profit and loss consolidated profit and loss balance sheet revenue PAT financial statements",
            r"\b(business divisions|divisions|businesses)\b": "business divisions ash handling water management solar epc agro machinery engineering division",
            r"\b(projects|major projects|ongoing projects)\b": "major projects ongoing projects EPC projects Pakri Maitree Yadadri Adani",
            r"\b(subsidiary|subsidiaries)\b": "subsidiary companies group company associate companies joint ventures",
            r"\b(plant|factory|manufacturing facility)\b": "manufacturing plant factory site production facility works unit",
            r"\b(diagram|flowchart|architecture)\b": "diagram flowchart architecture visual figure illustration schematic workflow system diagram",
            r"\b(chart|graph|plot)\b": "chart graph plot visual trend curve data graphic figure",
            r"\b(figure|image|photo|illustration|picture)\b": "figure image photo illustration visual picture diagram graphic",
            r"\b(committee|committees)\b": "audit committee nomination and remuneration committee stakeholder relationship committee corporate social responsibility committee"
        }
        for pattern, replacement in synonyms.items():
            if re.search(pattern, query, re.IGNORECASE):
                expanded += " " + replacement
        return expanded

    def _get_expanded_aliases(self, query: str) -> List[str]:
        """
        Extracts specific alias keywords and phrases for exact matching and candidate boosting.
        """
        import re
        q = query.lower()
        aliases = []
        
        if re.search(r"\b(managing director|md)\b", q):
            aliases.extend(["managing director", "md", "ravi todi", "promoter and managing director"])
        if re.search(r"\b(whole-time director|whole time director|wtd)\b", q):
            aliases.extend(["whole-time director", "whole time director", "wtd", "rhea todi", "executive director"])
        if re.search(r"\b(independent director|independent directors)\b", q):
            aliases.extend(["independent director", "non-executive independent director", "sourav daspatnaik"])
        if re.search(r"\b(board of directors|directors|board)\b", q):
            aliases.extend(["board of directors", "directors", "board members", "composition of board", "corporate governance"])
        if re.search(r"\b(auditor|statutory auditor|auditors)\b", q):
            aliases.extend(["statutory auditor", "independent auditor", "independent auditor's report", "audit report", "auditor's opinion"])
        if re.search(r"\b(registered office|corporate office|cin)\b", q):
            aliases.extend(["registered office", "corporate office", "corporate identification number", "cin:"])
        if re.search(r"\b(cfo|chief financial officer)\b", q):
            aliases.extend(["chief financial officer", "cfo"])
        if re.search(r"\b(cs|company secretary)\b", q):
            aliases.extend(["company secretary", "compliance officer", "cs"])
        if re.search(r"\b(revenue|turnover|sales)\b", q):
            aliases.extend(["revenue from operations", "total income", "turnover", "sales"])
        if re.search(r"\b(profit|pat|pbt)\b", q):
            aliases.extend(["profit after tax", "pat", "profit before tax", "pbt", "net profit"])
            
        return aliases

    def _search_exact_phrases(self, chunks: List[DocumentChunk], query: str) -> List[DocumentChunk]:
        """
        Searches for exact key multi-word phrases and role names from the query across all chunks.
        """
        import re
        matched = []
        q_lower = query.lower()
        
        # Extract quoted phrases or multi-word entity phrases
        phrases = re.findall(r'"([^"]+)"', query)
        if not phrases:
            # Extract meaningful 2-3 word sequences
            words = [w for w in re.findall(r'\b[a-zA-Z0-9_\-\.]{3,}\b', q_lower) if w not in ("what", "when", "where", "which", "who", "whom", "whose", "why", "how", "the", "and", "for", "with", "from", "about", "this", "that", "document", "report", "company")]
            if len(words) >= 2:
                for i in range(len(words) - 1):
                    phrases.append(f"{words[i]} {words[i+1]}")
            phrases.extend(self._get_expanded_aliases(query))

        if not phrases:
            return []

        for c in chunks:
            c_text = (c.content or "").lower()
            c_heading = (c.metadata.heading or "").lower()
            c_sec = (c.metadata.section or "").lower()
            
            for phrase in phrases:
                p_clean = phrase.lower().strip()
                if len(p_clean) < 3:
                    continue
                if p_clean in c_text or p_clean in c_heading or p_clean in c_sec:
                    matched.append(c)
                    break
                    
        return self._deduplicate_chunks(matched)

    def _search_tables(self, all_chunks: List[DocumentChunk], query: str) -> List[DocumentChunk]:
        """
        Dedicated table chunk search for numerical, tabular, financial, and list-based questions.
        Scans markdown table content, captions, headings, and column headers.
        """
        import re
        matched = []
        q_lower = query.lower()
        q_words = [w for w in re.findall(r'\b[a-zA-Z0-9_\-\.]{3,}\b', q_lower) if w not in ("what", "when", "where", "which", "who", "the", "and", "for", "with", "from", "about", "this", "that", "document")]
        aliases = self._get_expanded_aliases(query)
        
        for c in all_chunks:
            if c.metadata.chunk_type != "table" and not c.metadata.table_id:
                continue
            
            meta = c.metadata
            content_lower = (c.content or "").lower()
            heading_lower = (meta.heading or "").lower()
            section_lower = (meta.section or "").lower()
            caption_lower = (getattr(meta, "caption", None) or "").lower()
            
            score = 0
            # Check exact aliases in table
            for alias in aliases:
                if alias in heading_lower or alias in caption_lower:
                    score += 5
                elif alias in content_lower or alias in section_lower:
                    score += 3

            # Check individual query words
            for w in q_words:
                if w in heading_lower or w in caption_lower:
                    score += 3
                elif w in section_lower:
                    score += 2
                elif w in content_lower:
                    score += 1
                    
            if score > 0:
                matched.append((c, score))
                
        matched.sort(key=lambda x: x[1], reverse=True)
        return [c for c, _ in matched]

    def _boost_candidates(
        self, 
        clean_query: str, 
        fused_results: List[Tuple[DocumentChunk, float, float]],
        intent: Optional[str] = None
    ) -> List[Tuple[DocumentChunk, float, float]]:
        """
        Authority-aware candidate boosting: prioritizes exact factual statements, official tables,
        entity-role matches, and relevant document sections over broad semantic matches.
        """
        import re
        q = clean_query.lower()
        boosted = []
        visual_terms = ["diagram", "chart", "graph", "figure", "image", "illustration", "photo", "picture", "flowchart", "architecture", "map", "plot", "layout", "visual", "look like", "workflow", "schematic", "trend"]
        is_visual_query = (intent == "visual") or any(vt in q for vt in visual_terms)
        
        # Extract aliases for exact role/entity boost
        aliases = self._get_expanded_aliases(q)
        q_words = [w for w in re.findall(r'\b[a-zA-Z0-9_\-\.]{3,}\b', q) if w not in visual_terms and w not in ("what", "when", "where", "which", "who", "the", "and", "for", "with", "from", "about", "this", "that", "document")]

        for chunk, rrf, sem in fused_results:
            boost = 0.0
            meta = chunk.metadata
            content_lower = (chunk.content or "").lower()
            heading_lower = (meta.heading or "").lower()
            section_lower = (meta.section or "").lower()
            
            # 1. Exact Phrase & Entity-Role Match in Content or Heading (+0.45)
            for alias in aliases:
                if alias in heading_lower:
                    boost += 0.45
                    break
                elif alias in content_lower:
                    boost += 0.35
                    break

            # 2. Section Relevance Match (Official Sections) (+0.35)
            if "auditor" in q and any(sec in section_lower or sec in heading_lower for sec in ["independent auditor", "auditor's report", "statutory auditor"]):
                boost += 0.40
            if any(term in q for term in ["board", "director", "governance", "kmp", "leadership"]) and any(sec in section_lower or sec in heading_lower for sec in ["board of directors", "board's report", "directors' report", "corporate governance", "corporate information"]):
                boost += 0.40
            if any(term in q for term in ["registered office", "cin", "corporate office", "incorporation"]) and any(sec in section_lower or sec in heading_lower for sec in ["corporate information", "general information", "company information"]):
                boost += 0.40
            if any(term in q for term in ["revenue", "profit", "financial", "pat", "pbt", "balance sheet"]) and any(sec in section_lower or sec in heading_lower for sec in ["financial statement", "profit and loss", "balance sheet", "financial highlights"]):
                boost += 0.35

            # 3. Table Target for Table/Financial/List queries (+0.40)
            if meta.chunk_type == "table":
                if intent in ("table_based", "table", "financial", "direct_factual", "list") or "table" in q:
                    boost += 0.40
                
            # 4. Figure/Image Target for Visual queries (+0.50)
            if meta.chunk_type == "image":
                if is_visual_query:
                    boost += 0.50
                caption = (getattr(meta, "caption", None) or meta.heading or "").lower()
                ocr = (getattr(meta, "ocr_text", None) or "").lower()
                vlm = (getattr(meta, "semantic_description", None) or "").lower()
                objs = [str(o).lower() for o in (getattr(meta, "objects", []) or [])]
                
                if q_words and any(w in caption or w in ocr or w in vlm or any(w in o for o in objs) for w in q_words):
                    boost += 0.40
                
            # 5. People / Roles Target (+0.25)
            if any(term in q for term in ["people", "person", "who", "names", "director", "auditor", "cfo", "cs"]) and (getattr(meta, "people", None) or meta.chunk_type == "text"):
                boost += 0.25
                
            # 6. Location Target (+0.20)
            if any(term in q for term in ["location", "where", "place", "state", "region", "district", "country", "office", "address"]) and (getattr(meta, "locations", None) or getattr(meta, "state", None)):
                boost += 0.20
                
            # 7. Date Target (+0.20)
            if any(term in q for term in ["date", "when", "year", "month", "timeline", "chronology", "incorporation", "founded"]) and getattr(meta, "dates", None):
                boost += 0.20
                
            # 8. Report Number Target (+0.40)
            report_match = re.search(r'(?i)\breport\s*(\d+)\b', q)
            if report_match:
                rep_str = f"Report {report_match.group(1)}"
                if getattr(meta, "report_number", None) == rep_str:
                    boost += 0.50
                elif rep_str.lower() in section_lower:
                    boost += 0.30
            
            boosted.append((chunk, rrf + boost, sem))
            
        boosted.sort(key=lambda x: x[1], reverse=True)
        return boosted

    def _search_images(self, chunks: List[DocumentChunk], query: str) -> List[DocumentChunk]:
        """
        Dedicated visual search matching query keywords, figure numbers, captions,
        OCR text, semantic descriptions, detected objects, entities, and keywords.
        """
        matched = []
        q_lower = query.lower()
        
        import re
        fig_match = re.search(r'(?i)\b(?:figure|fig\.?|chart|diagram|image|photo|illustration)\s*#?\s*(\d+)\b', query)
        fig_target_num = fig_match.group(1) if fig_match else None

        visual_terms = ["diagram", "chart", "graph", "figure", "image", "illustration", "photo", "picture", "flowchart", "architecture", "map", "plot", "layout", "visual", "look like", "workflow", "schematic", "trend"]
        is_visual_query = any(vt in q_lower for vt in visual_terms)

        for c in chunks:
            if c.metadata.chunk_type != "image" and not c.metadata.image_id:
                continue

            meta = c.metadata
            caption = (getattr(meta, "caption", None) or meta.heading or "").lower()
            ocr = (getattr(meta, "ocr_text", None) or "").lower()
            vlm = (getattr(meta, "semantic_description", None) or "").lower()
            objs = [str(o).lower() for o in (getattr(meta, "objects", []) or [])]
            ents = [str(e).lower() for e in (getattr(meta, "detected_entities", []) or [])]
            kws = [str(k).lower() for k in (getattr(meta, "keywords", []) or [])]

            # 1. Figure number exact match
            if fig_target_num:
                if fig_target_num in caption or (meta.image_id and fig_target_num in meta.image_id):
                    matched.append(c)
                    continue

            # 2. Query words matching caption, OCR, VLM description, objects, entities, keywords
            q_words = [w for w in re.findall(r'\w+', q_lower) if len(w) > 2 and w not in visual_terms]
            if q_words:
                match_count = 0
                for w in q_words:
                    if w in caption or w in ocr or w in vlm or any(w in o for o in objs) or any(w in e for e in ents) or any(w in k for k in kws):
                        match_count += 1
                if match_count > 0:
                    matched.append(c)
                    continue

            # 3. If it's a general visual query, include image chunks
            if is_visual_query:
                matched.append(c)

        return self._deduplicate_chunks(matched)

    def retrieve(
        self, 
        document_id: str, 
        query: str, 
        metadata_filter: Optional[Dict[str, Any]] = None
    ) -> RetrievalOutput:
        """
        Coordinates query classification, multi-stage candidate collection,
        dedicated table and visual retrieval, hybrid fusion, authority-aware reranking,
        two-pass fallback, and parent-child section expansion.
        """
        import time
        start_time = time.time()
        
        # 1. Intent Detection & Depth Routing (Query-Aware Retrieval)
        intent = self.detect_intent(query)
        top_k_retrieve, top_k_rerank, top_k_final = self._get_intent_depth(intent)
        logger.info(f"Detected intent: {intent} -> (retrieve={top_k_retrieve}, rerank={top_k_rerank}, final={top_k_final})")
        
        # 2. Query Expansion (Entity & Alias Expansion)
        expanded_query = self.expand_query(query)
        clean_query = self.query_processor.preprocess_query(expanded_query)
        
        # 3. Load Chunks & Structured Document
        all_chunks = self._load_document_chunks(document_id)
        if not all_chunks:
            logger.warning(f"No chunks found for document {document_id}.")
            return RetrievalOutput(question=query, retrieved_chunks=[], debug_info={"intent": intent})
            
        doc_struct = self._load_structured_document(document_id)
        search_chunks = self._filter_chunks(all_chunks, metadata_filter)
        if not search_chunks:
            logger.warning(f"No chunks matched metadata filter {metadata_filter}.")
            return RetrievalOutput(question=query, retrieved_chunks=[], debug_info={"intent": intent})
        
        # 4. Build Entity Index
        entity_index = self._build_entity_index(search_chunks)
        
        # 5. Multi-Stage Candidates Collection
        candidates_dict = {}
        def add_candidates(chunks_list):
            for c in chunks_list:
                if c and c.metadata and c.metadata.chunk_id:
                    candidates_dict[c.metadata.chunk_id] = c
        
        # Stage A: Metadata & Heading-Aware Search
        meta_candidates = self._search_metadata(search_chunks, query)
        add_candidates(meta_candidates)
        
        # Stage B: Heading & TOC Search
        toc_candidates = self._search_toc_and_headings(search_chunks, doc_struct, query)
        add_candidates(toc_candidates)
        
        # Stage C: Entity Search (with expanded aliases)
        entity_candidates = self._search_entity_index(entity_index, query)
        add_candidates(entity_candidates)
        
        # Stage D: Dedicated Table Search
        table_candidates = self._search_tables(search_chunks, query)
        add_candidates(table_candidates)
        
        # Stage E: Dedicated Image & Visual Search
        image_candidates = self._search_images(search_chunks, query)
        add_candidates(image_candidates)
        
        # Stage F: Exact Phrase Search
        exact_candidates = self._search_exact_phrases(search_chunks, query)
        add_candidates(exact_candidates)
        
        # Stage G: BM25 Search
        bm25_search = BM25Search(search_chunks)
        bm25_results = bm25_search.search(clean_query, top_k=top_k_retrieve)
        add_candidates([chunk for chunk, _ in bm25_results])
        
        # Stage H: Vector Search
        query_emb = self.query_processor.generate_query_embedding(query)
        vector_results = self._search_vector_store(document_id, query_emb, metadata_filter, n_results=top_k_retrieve)
        add_candidates([chunk for chunk, _ in vector_results])
        
        # 6. Fusion & RRF Sorting
        fused_results = HybridSearch.fuse_results(
            vector_results,
            bm25_results,
            k=60
        )
        
        fused_chunk_ids = {c.metadata.chunk_id for c, _, _ in fused_results}
        for cand in candidates_dict.values():
            cid = cand.metadata.chunk_id
            if cid not in fused_chunk_ids:
                fused_results.append((cand, 0.01, 0.01))
                
        fused_results = self._boost_candidates(clean_query, fused_results, intent=intent)
        candidate_list = [chunk for chunk, _, _ in fused_results[:top_k_rerank]]
        
        # 7. First-Pass Reranking
        reranked = self.reranker.rerank(query, candidate_list)
        
        # 8. Two-Pass Retrieval Fallback
        # If first-pass evidence is weak or lacks direct role/entity match, execute targeted fallback
        max_rerank_score = max([score for _, score in reranked]) if reranked else 0.0
        aliases = self._get_expanded_aliases(query)
        has_targeted_terms = bool(aliases or "board" in query.lower() or "director" in query.lower() or "auditor" in query.lower() or "office" in query.lower())
        
        if max_rerank_score < 0.20 and has_targeted_terms:
            logger.info(f"First-pass retrieval score low ({max_rerank_score:.3f}). Running two-pass retrieval fallback...")
            refined_terms = " ".join(aliases) if aliases else query
            refined_query = f"{query} {refined_terms}"
            
            fallback_exact = self._search_exact_phrases(search_chunks, refined_query)
            fallback_tables = self._search_tables(search_chunks, refined_query)
            fallback_meta = self._search_metadata(search_chunks, refined_query)
            
            refined_emb = self.query_processor.generate_query_embedding(refined_query)
            second_vector_results = self._search_vector_store(document_id, refined_emb, metadata_filter, n_results=top_k_retrieve)
            second_candidates = [chunk for chunk, _ in second_vector_results]
            
            all_fallback = fallback_exact + fallback_tables + fallback_meta + second_candidates
            combined_dict = {c.metadata.chunk_id: c for c in (candidate_list + all_fallback)}
            candidate_list = list(combined_dict.values())[:top_k_rerank]
            
            reranked = self.reranker.rerank(refined_query, candidate_list)
            logger.info(f"Two-pass fallback completed. Top score: {max([s for _, s in reranked]) if reranked else 0.0:.3f}")
            
        # 9. Parent-Child & Structured Section Expansion
        expanded_chunks = self._expand_context(reranked[:top_k_final], search_chunks, doc_struct)
        
        # 10. Format Output Scored Chunks
        scored_chunks = []
        semantic_score_map = {c.metadata.chunk_id: sem for c, _, sem in fused_results}
        rerank_score_map = {c.metadata.chunk_id: score for c, score in reranked}
        
        for chunk in expanded_chunks:
            cid = chunk.metadata.chunk_id
            scored_chunks.append(ScoredChunk(
                content=chunk.content,
                metadata=chunk.metadata,
                similarity_score=semantic_score_map.get(cid, 0.01),
                reranker_score=rerank_score_map.get(cid, 0.01)
            ))
            
        scored_chunks.sort(key=lambda x: x.reranker_score, reverse=True)
            
        # Debug Logging
        retrieval_time = time.time() - start_time
        debug_info = {
            "intent": intent,
            "top_k_retrieve": top_k_retrieve,
            "top_k_rerank": top_k_rerank,
            "top_k_final": top_k_final,
            "metadata_matches": len(meta_candidates),
            "toc_matches": len(toc_candidates),
            "entity_matches": len(entity_candidates),
            "table_matches": len(table_candidates),
            "exact_matches": len(exact_candidates),
            "bm25_count": len(bm25_results),
            "vector_count": len(vector_results),
            "expanded_count": len(expanded_chunks),
            "retrieval_time_seconds": retrieval_time
        }
        
        # Save logs
        try:
            from src.config import ROOT_DIR
            job_dir = ROOT_DIR / "data" / "output" / document_id
            if job_dir.exists():
                retrieval_dir = job_dir / "08_retrieval"
                retrieval_dir.mkdir(parents=True, exist_ok=True)
                
                with open(retrieval_dir / "last_query.json", "w", encoding="utf-8") as f:
                    json.dump({
                        "query": query,
                        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                    }, f, indent=2)
                    
                chunks_list = []
                for sc in scored_chunks:
                    meta = sc.metadata
                    bbox_list = []
                    if meta.bounding_boxes:
                        for bbox in meta.bounding_boxes:
                            bbox_list.append(bbox.model_dump() if hasattr(bbox, "model_dump") else bbox.dict())
                    chunks_list.append({
                        "chunk_id": meta.chunk_id,
                        "chunk_type": meta.chunk_type,
                        "page_number": meta.page_number,
                        "heading": meta.heading,
                        "section": meta.section,
                        "similarity_score": sc.similarity_score,
                        "reranker_score": sc.reranker_score,
                        "content": sc.content,
                        "bounding_boxes": bbox_list
                    })
                with open(retrieval_dir / "retrieved_chunks.json", "w", encoding="utf-8") as f:
                    json.dump({"chunks": chunks_list}, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save retrieval query logs: {e}")
            
        return RetrievalOutput(
            question=query,
            retrieved_chunks=scored_chunks,
            debug_info=debug_info
        )

    def _load_structured_document(self, document_id: str) -> Optional[StructuredDocument]:
        output_dir = Path(self.config.chroma_db_dir).parent / "output" / document_id
        doc_file = output_dir / "02_docling" / "structured_document.json"
        if not doc_file.exists():
            doc_file = output_dir / "structured_document.json"
        if doc_file.exists():
            try:
                with open(doc_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return StructuredDocument(**data)
            except Exception as e:
                logger.error(f"Failed to load structured document: {e}")
        return None

    def _build_entity_index(self, chunks: List[DocumentChunk]) -> Dict[str, List[DocumentChunk]]:
        index = {}
        for c in chunks:
            meta = c.metadata
            entities = []
            if meta.people: entities.extend(meta.people)
            if meta.organizations: entities.extend(meta.organizations)
            if meta.locations: entities.extend(meta.locations)
            if meta.dates: entities.extend(meta.dates)
            if meta.keywords: entities.extend(meta.keywords)
            
            for ent in entities:
                ent_clean = ent.lower().strip()
                if not ent_clean or len(ent_clean) < 3:
                    continue
                if ent_clean not in index:
                    index[ent_clean] = []
                index[ent_clean].append(c)
        return index

    def _deduplicate_chunks(self, chunks: List[DocumentChunk]) -> List[DocumentChunk]:
        seen = set()
        deduped = []
        for c in chunks:
            if c and c.metadata and c.metadata.chunk_id:
                if c.metadata.chunk_id not in seen:
                    seen.add(c.metadata.chunk_id)
                    deduped.append(c)
        return deduped

    def _search_entity_index(self, index: Dict[str, List[DocumentChunk]], query: str) -> List[DocumentChunk]:
        matched = []
        q_lower = query.lower()
        aliases = [a.lower() for a in self._get_expanded_aliases(query)]
        
        for ent_name, chunks in index.items():
            ent_clean = ent_name.lower()
            if ent_clean in q_lower or any(alias in ent_clean or ent_clean in alias for alias in aliases):
                matched.extend(chunks)
        return self._deduplicate_chunks(matched)

    def _search_metadata(self, chunks: List[DocumentChunk], query: str) -> List[DocumentChunk]:
        matched = []
        q = query.lower()
        aliases = [a.lower() for a in self._get_expanded_aliases(query)]
        
        # Section Keyword Aliases
        alias_tokens = {
            "client": ["marquee", "client", "customer", "clientele"],
            "board": ["director", "board", "governance", "managerial", "leadership", "kmp", "corporate governance"],
            "auditor": ["auditor", "statutory auditor", "independent auditor", "audit report", "audit"],
            "office": ["registered office", "corporate office", "cin", "corporate information", "general information"],
            "award": ["award", "recognition", "accreditation", "honor"],
            "project": ["project", "order book", "contract", "turnkey", "epc"],
            "certification": ["certification", "iso", "quality"],
            "subsidiary": ["subsidiary", "joint venture", "associate"],
            "facility": ["facility", "plant", "factory", "works", "manufacturing"],
            "financial": ["financial statement", "profit and loss", "balance sheet", "revenue", "cash flow", "financial highlights"]
        }
        
        target_keys = list(aliases)
        for cat, keywords in alias_tokens.items():
            if any(k in q for k in keywords):
                target_keys.extend(keywords)

        for c in chunks:
            meta = c.metadata
            sec_title = (getattr(meta, "section_heading", None) or meta.heading or meta.section or "").lower()
            
            # Direct or alias heading match
            if sec_title and (sec_title in q or any(tk in sec_title for tk in target_keys)):
                matched.append(c)
            elif "table" in q and meta.chunk_type == "table":
                matched.append(c)
            elif any(term in q for term in ["image", "figure", "chart", "diagram"]) and meta.chunk_type == "image":
                matched.append(c)
                
        return self._deduplicate_chunks(matched)

    def _search_toc_and_headings(self, chunks: List[DocumentChunk], doc_struct: Optional[StructuredDocument], query: str) -> List[DocumentChunk]:
        matched = []
        q = query.lower()
        aliases = [a.lower() for a in self._get_expanded_aliases(query)]
        
        # Heading tokens to check
        heading_keywords = [
            "marquee", "client", "customer", "director", "board", "award", "project",
            "certification", "subsidiary", "facility", "plant", "auditor", "registered office",
            "corporate information", "financial", "revenue", "governance"
        ]
        matched_keywords = [k for k in heading_keywords if k in q] + aliases

        for c in chunks:
            sec_title = (getattr(c.metadata, "section_heading", None) or c.metadata.heading or c.metadata.section or "").lower()
            if any(mk in sec_title for mk in matched_keywords if len(mk) > 2):
                matched.append(c)
                
        if doc_struct:
            for el in doc_struct.elements:
                if el.type == "heading" and (el.text.lower() in q or any(mk in el.text.lower() for mk in matched_keywords if len(mk) > 2)):
                    for c in chunks:
                        sec_title = (getattr(c.metadata, "section_heading", None) or c.metadata.heading or c.metadata.section or "").lower()
                        if el.text.lower() in sec_title:
                            matched.append(c)
                            
        return self._deduplicate_chunks(matched)

    def _expand_context(self, scored_results: List[Tuple[DocumentChunk, float]], all_chunks: List[DocumentChunk], doc_struct: Optional[StructuredDocument]) -> List[DocumentChunk]:
        expanded = []
        seen = set()
        
        chunk_indices = {c.metadata.chunk_id: idx for idx, c in enumerate(all_chunks)}
        
        for chunk, score in scored_results:
            cid = chunk.metadata.chunk_id
            if cid in seen:
                continue
                
            expanded.append(chunk)
            seen.add(cid)
            
            # Section-level Sibling Expansion (Phase 5 Section-Level Retrieval)
            sec_id = getattr(chunk.metadata, "section_id", None)
            sec_heading = getattr(chunk.metadata, "section_heading", None) or chunk.metadata.section
            
            if sec_id or sec_heading:
                for sibling in all_chunks:
                    sib_id = sibling.metadata.chunk_id
                    if sib_id not in seen:
                        sib_sec_id = getattr(sibling.metadata, "section_id", None)
                        sib_sec_heading = getattr(sibling.metadata, "section_heading", None) or sibling.metadata.section
                        if (sec_id and sib_sec_id == sec_id) or (sec_heading and sib_sec_heading == sec_heading):
                            expanded.append(sibling)
                            seen.add(sib_id)

            # Parent Section Header Expansion
            heading = chunk.metadata.heading
            section = chunk.metadata.section
            if heading or section:
                for parent_c in all_chunks:
                    p_id = parent_c.metadata.chunk_id
                    if p_id not in seen:
                        if parent_c.metadata.chunk_type == "heading" and (
                            (heading and parent_c.content.strip() == heading.strip()) or
                            (section and parent_c.content.strip() in section)
                        ):
                            expanded.append(parent_c)
                            seen.add(p_id)

            idx = chunk_indices.get(cid)
            if idx is not None:
                if idx > 0:
                    prev_c = all_chunks[idx - 1]
                    if prev_c.metadata.chunk_id not in seen:
                        if prev_c.metadata.heading == chunk.metadata.heading or prev_c.metadata.section == chunk.metadata.section:
                            expanded.append(prev_c)
                            seen.add(prev_c.metadata.chunk_id)
                if idx < len(all_chunks) - 1:
                    next_c = all_chunks[idx + 1]
                    if next_c.metadata.chunk_id not in seen:
                        if next_c.metadata.heading == chunk.metadata.heading or next_c.metadata.section == chunk.metadata.section:
                            expanded.append(next_c)
                            seen.add(next_c.metadata.chunk_id)
                            
            meta = chunk.metadata
            if meta.chunk_type in ("table", "image"):
                for other in all_chunks:
                    if other.metadata.chunk_id not in seen:
                        if other.metadata.chunk_type == "caption" and (other.metadata.table_id == meta.table_id or other.metadata.image_id == meta.image_id):
                            expanded.append(other)
                            seen.add(other.metadata.chunk_id)
                        elif other.metadata.page_number == meta.page_number and other.metadata.chunk_type == "text" and (other.metadata.heading == meta.heading or other.metadata.section == meta.section):
                            expanded.append(other)
                            seen.add(other.metadata.chunk_id)
            elif meta.chunk_type == "text":
                # If text refers to a figure or diagram, expand the corresponding image chunk
                import re
                fig_refs = re.findall(r'(?i)\b(?:figure|fig\.?|chart|diagram|image|photo)\s*#?\s*(\d+)\b', chunk.content)
                if fig_refs:
                    for other in all_chunks:
                        if other.metadata.chunk_id not in seen and (other.metadata.chunk_type == "image" or other.metadata.image_id):
                            for ref_num in fig_refs:
                                other_cap = (getattr(other.metadata, "caption", None) or other.metadata.heading or "").lower()
                                if ref_num in other_cap or (other.metadata.image_id and ref_num in other.metadata.image_id):
                                    expanded.append(other)
                                    seen.add(other.metadata.chunk_id)
                            
        def parse_chunk_idx(chunk_id: str) -> int:
            import re
            try:
                m = re.search(r"_chunk_(\d+)", chunk_id)
                if m:
                    return int(m.group(1))
            except Exception:
                pass
            return 0
            
        expanded.sort(key=lambda c: (c.metadata.page_number, parse_chunk_idx(c.metadata.chunk_id)))
        return expanded

    def _parse_list_meta(self, val) -> List[str]:
        if not val:
            return []
        if isinstance(val, list):
            return val
        if isinstance(val, str):
            try:
                return json.loads(val)
            except Exception:
                return [val]
        return []

    def _load_document_chunks(self, document_id: str) -> List[DocumentChunk]:
        """
        Tries to load chunks from the local document_chunks.json file,
        falling back to ChromaDB if the file does not exist.
        """
        output_dir = Path(self.config.chroma_db_dir).parent / "output" / document_id
        from src.rag.chunk_utils import load_stage6_chunks
        data = load_stage6_chunks(output_dir, doc_id=document_id, materialize_cache=True)
        if data.get("chunks"):
            try:
                logger.info(f"Loading chunks for document: {document_id}")
                chunks = []
                for c in data.get("chunks", []):
                    meta_data = c.get("metadata", {})
                    
                    bboxes = []
                    for bbox_data in meta_data.get("bounding_boxes", []):
                        if bbox_data:
                            if isinstance(bbox_data, dict):
                                bboxes.append(BoundingBox(**bbox_data))
                            elif isinstance(bbox_data, BoundingBox):
                                bboxes.append(bbox_data)

                    meta = ChunkMetadata(
                        chunk_id=meta_data.get("chunk_id"),
                        document_id=meta_data.get("document_id"),
                        page_number=meta_data.get("page_number"),
                        chunk_type=meta_data.get("chunk_type"),
                        heading=meta_data.get("heading"),
                        section=meta_data.get("section"),
                        hierarchy_path=meta_data.get("hierarchy_path", []),
                        source_element_ids=meta_data.get("source_element_ids", []),
                        word_count=meta_data.get("word_count", 0),
                        token_estimate=meta_data.get("token_estimate", 0),
                        bounding_boxes=bboxes,
                        image_id=meta_data.get("image_id"),
                        image_path=meta_data.get("image_path"),
                        image_url=meta_data.get("image_url"),
                        image_type=meta_data.get("image_type"),
                        caption=meta_data.get("caption"),
                        ocr_text=meta_data.get("ocr_text"),
                        semantic_description=meta_data.get("semantic_description"),
                        objects=self._parse_list_meta(meta_data.get("objects")),
                        detected_entities=self._parse_list_meta(meta_data.get("detected_entities")),
                        table_id=meta_data.get("table_id"),
                        report_number=meta_data.get("report_number"),
                        state=meta_data.get("state"),
                        region=meta_data.get("region"),
                        district=meta_data.get("district"),
                        people=self._parse_list_meta(meta_data.get("people")),
                        organizations=self._parse_list_meta(meta_data.get("organizations")),
                        groups=self._parse_list_meta(meta_data.get("groups")),
                        dates=self._parse_list_meta(meta_data.get("dates")),
                        weapons=self._parse_list_meta(meta_data.get("weapons")),
                        locations=self._parse_list_meta(meta_data.get("locations")),
                        keywords=self._parse_list_meta(meta_data.get("keywords"))
                    )
                    chunks.append(DocumentChunk(content=c.get("content"), metadata=meta))
                return chunks
            except Exception as e:
                logger.warning(f"Failed to read chunks file ({e}). Falling back to ChromaDB.")

        collection_name = self.vector_store._get_collection_name(document_id)
        try:
            logger.info(f"Retrieving chunks directly from ChromaDB collection: {collection_name}")
            collection = self.vector_store.client.get_collection(name=collection_name)
            results = collection.get(include=["metadatas", "documents"])
            
            chunks = []
            for cid, doc, meta_data in zip(results["ids"], results["documents"], results["metadatas"]):
                hierarchy_path = json.loads(meta_data.get("hierarchy_path", "[]"))
                source_element_ids = json.loads(meta_data.get("source_element_ids", "[]"))
                
                bboxes_raw = json.loads(meta_data.get("bounding_boxes", "[]")) if isinstance(meta_data.get("bounding_boxes"), str) else meta_data.get("bounding_boxes", [])
                bboxes = []
                for b in bboxes_raw:
                    if isinstance(b, dict):
                        bboxes.append(BoundingBox(**b))
                
                meta = ChunkMetadata(
                    chunk_id=meta_data.get("chunk_id"),
                    document_id=meta_data.get("document_id"),
                    page_number=int(meta_data.get("page_number", 1)),
                    chunk_type=meta_data.get("chunk_type"),
                    heading=meta_data.get("heading") or None,
                    section=meta_data.get("section") or None,
                    hierarchy_path=hierarchy_path,
                    source_element_ids=source_element_ids,
                    word_count=int(meta_data.get("word_count", 0)),
                    token_estimate=int(meta_data.get("token_estimate", 0)),
                    bounding_boxes=bboxes,
                    image_id=meta_data.get("image_id"),
                    image_path=meta_data.get("image_path"),
                    image_url=meta_data.get("image_url"),
                    image_type=meta_data.get("image_type"),
                    caption=meta_data.get("caption"),
                    ocr_text=meta_data.get("ocr_text"),
                    semantic_description=meta_data.get("semantic_description"),
                    objects=self._parse_list_meta(meta_data.get("objects")),
                    detected_entities=self._parse_list_meta(meta_data.get("detected_entities")),
                    table_id=meta_data.get("table_id"),
                    report_number=meta_data.get("report_number"),
                    state=meta_data.get("state"),
                    region=meta_data.get("region"),
                    district=meta_data.get("district"),
                    people=self._parse_list_meta(meta_data.get("people")),
                    organizations=self._parse_list_meta(meta_data.get("organizations")),
                    groups=self._parse_list_meta(meta_data.get("groups")),
                    dates=self._parse_list_meta(meta_data.get("dates")),
                    weapons=self._parse_list_meta(meta_data.get("weapons")),
                    locations=self._parse_list_meta(meta_data.get("locations")),
                    keywords=self._parse_list_meta(meta_data.get("keywords"))
                )
                chunks.append(DocumentChunk(content=doc, metadata=meta))
            return chunks
        except Exception as e:
            logger.error(f"Failed to load chunks from ChromaDB: {e}")
            return []

    def _filter_chunks(self, chunks: List[DocumentChunk], metadata_filter: Optional[Dict[str, Any]]) -> List[DocumentChunk]:
        if not metadata_filter:
            return chunks
            
        filtered = []
        for chunk in chunks:
            match = True
            meta = chunk.metadata
            for key, val in metadata_filter.items():
                if val is None:
                    continue
                if key == "page_number" and meta.page_number != val:
                    match = False
                elif key == "chunk_type" and meta.chunk_type != val:
                    match = False
                elif key == "heading" and meta.heading != val:
                    match = False
                elif key == "section" and meta.section != val:
                    match = False
                elif key == "image_id" and meta.image_id != val:
                    match = False
                elif key == "table_id" and meta.table_id != val:
                    match = False
            if match:
                filtered.append(chunk)
        return filtered

    def _search_vector_store(
        self, 
        document_id: str, 
        query_emb: List[float], 
        metadata_filter: Optional[Dict[str, Any]],
        n_results: Optional[int] = None
    ) -> List[Tuple[DocumentChunk, float]]:
        collection_name = self.vector_store._get_collection_name(document_id)
        logger.info(f"Running vector search in collection: {collection_name}")
        
        where_dict = {}
        if metadata_filter:
            for key, val in metadata_filter.items():
                if val is not None and key in ("page_number", "chunk_type", "heading", "section", "image_id", "table_id"):
                    where_dict[key] = val

        try:
            collection = self.vector_store.client.get_collection(name=collection_name)
            limit = n_results or self.config.top_k_retrieve
            
            query_args: Dict[str, Any] = {
                "query_embeddings": [query_emb],
                "n_results": min(limit, len(collection.get()["ids"]))
            }
            if where_dict:
                query_args["where"] = where_dict
                
            results = collection.query(**query_args)
            scored_chunks = []
            
            ids = results.get("ids", [[]])[0]
            documents = results.get("documents", [[]])[0]
            metadatas = results.get("metadatas", [[]])[0]
            distances = results.get("distances", [[]])[0]
            
            for cid, doc, meta_data, dist in zip(ids, documents, metadatas, distances):
                hierarchy_path = json.loads(meta_data.get("hierarchy_path", "[]"))
                source_element_ids = json.loads(meta_data.get("source_element_ids", "[]"))
                
                bboxes_raw = json.loads(meta_data.get("bounding_boxes", "[]")) if isinstance(meta_data.get("bounding_boxes"), str) else meta_data.get("bounding_boxes", [])
                bboxes = []
                for b in bboxes_raw:
                    if isinstance(b, dict):
                        bboxes.append(BoundingBox(**b))

                meta = ChunkMetadata(
                    chunk_id=meta_data.get("chunk_id"),
                    document_id=meta_data.get("document_id"),
                    page_number=int(meta_data.get("page_number", 1)),
                    chunk_type=meta_data.get("chunk_type"),
                    heading=meta_data.get("heading") or None,
                    section=meta_data.get("section") or None,
                    hierarchy_path=hierarchy_path,
                    source_element_ids=source_element_ids,
                    word_count=int(meta_data.get("word_count", 0)),
                    token_estimate=int(meta_data.get("token_estimate", 0)),
                    bounding_boxes=bboxes,
                    image_id=meta_data.get("image_id"),
                    image_path=meta_data.get("image_path"),
                    image_url=meta_data.get("image_url"),
                    image_type=meta_data.get("image_type"),
                    caption=meta_data.get("caption"),
                    ocr_text=meta_data.get("ocr_text"),
                    semantic_description=meta_data.get("semantic_description"),
                    objects=self._parse_list_meta(meta_data.get("objects")),
                    detected_entities=self._parse_list_meta(meta_data.get("detected_entities")),
                    table_id=meta_data.get("table_id"),
                    report_number=meta_data.get("report_number"),
                    state=meta_data.get("state"),
                    region=meta_data.get("region"),
                    district=meta_data.get("district"),
                    people=self._parse_list_meta(meta_data.get("people")),
                    organizations=self._parse_list_meta(meta_data.get("organizations")),
                    groups=self._parse_list_meta(meta_data.get("groups")),
                    dates=self._parse_list_meta(meta_data.get("dates")),
                    weapons=self._parse_list_meta(meta_data.get("weapons")),
                    locations=self._parse_list_meta(meta_data.get("locations")),
                    keywords=self._parse_list_meta(meta_data.get("keywords"))
                )
                
                similarity = 1.0 - float(dist)
                scored_chunks.append((DocumentChunk(content=doc, metadata=meta), similarity))
                
            return scored_chunks
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            return []

