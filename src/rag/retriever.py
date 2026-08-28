import json
import logging
import re
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
        
        # 1. Person Portrait / Visual Entity Intent (Explicitly asking for person photos/portraits)
        person_visual_triggers = [
            "portrait", "portraits", "headshot", "headshots", "along with their photos",
            "along with photos", "with photos", "with photo", "show photo", "show photos",
            "show portrait", "show picture", "director's photo", "directors photo", "photo of", "photos of",
            "picture of", "pictures of", "image of", "images of"
        ]
        if has_any(person_visual_triggers) or (("photo" in q or "picture" in q or "image" in q) and any(d in q for d in ["director", "board", "person", "people", "man", "woman"])):
            return "person_portrait_visual"

        # 2. General Visual / Diagram / Chart Intent
        visual_terms = [
            "chart", "graph", "diagram", "figure", "image", "illustration",
            "flowchart", "architecture", "map", "plot", "layout", "visual", "look like",
            "sketch", "infographic", "schematic", "trend", "pie chart", "bar chart", "logo",
            "photo", "photos", "picture", "pictures", "photograph", "photographs"
        ]
        if has_any(visual_terms):
            return "visual"
            
        # 3. Table / Tabular Intent
        table_terms = ["table", "tabular", "column", "row", "metrics table", "comparison table", "schedule", "sprint progress", "financial metrics table"]
        if has_any(table_terms):
            return "table_based"

        # 4. Registered Office & CIN Multi-question check
        if ("registered office" in q or "corporate office" in q) and ("cin" in q or "corporate identification number" in q):
            return "direct_factual"

        # 4.1 Summary & Syntheses (Summary of divisions, executive summary, comprehensive review)
        summary_terms = ["summarise", "summarize", "summary", "overview", "synopsis", "outline", "all divisions", "cross-page", "executive summary", "comprehensive"]
        if has_any(summary_terms):
            if "detail" in q or "comprehensive" in q or "extensive" in q:
                return "detailed_summary"
            return "broad_summary"

        # 4.2 Primary Company Identification Intent
        company_id_terms = [
            "company name", "name of the company", "which company", "what company", "who is the company",
            "name of company", "what is the name of company", "document subject"
        ]
        if has_any(company_id_terms):
            return "primary_company_identification"

        # 4.5 CIN Lookup Intent
        if any(k in q for k in ["cin", "corporate identification number", "company identification number"]):
            return "cin_lookup"

        # 4.7 Person Biography / Qualification / Experience Intent -- must
        # resolve to the person's actual linked text chunks (biography,
        # qualifications, education, experience), never rely on the
        # portrait's own short metadata alone.
        person_bio_terms = [
            "qualification", "qualifications", "educational background", "educational qualification",
            "educated", "alma mater", "biography", "bio of", "profile of",
            "professional experience", "work experience", "experience of", "career of",
            "years of experience", "credentials", "expertise of", "achievements of",
            "about him", "about her", "his experience", "her experience", "their experience",
            "experience", "biography of",
        ]
        if has_any(person_bio_terms):
            return "person_biography"

        # 5. Entity / Person Lookup & Statutory Auditors (Biographies, Roles, Auditors)
        person_lookup_terms = [
            "who is", "who are", "who was", "name of the", "names of", "person", "people",
            "founder", "promoter", "statutory auditor", "statutory auditors", "auditors", "audit firm"
        ]
        if has_any(person_lookup_terms):
            return "entity_person_lookup"

        # 6. Corporate Office / Registered Office / Corporate Directory Facts
        corporate_factual_terms = [
            "registered office", "corporate office", "office address", "address of", "where is the office",
            "internal auditor", "secretarial auditor", "cost auditor", "cfo", "chief financial officer",
            "cs", "company secretary", "compliance officer", "bankers", "manufacturing facilities",
            "manufacturing plant", "manufacturing units", "business division", "business divisions"
        ]
        if has_any(corporate_factual_terms):
            return "corporate_office_factual"

        # 7. Leadership & Board Governance
        board_terms = [
            "board of directors", "composition of board", "board members", "directors",
            "managing director", "whole-time director", "whole time director", "executive director",
            "independent director", "non-executive director", "chairman", "chairperson",
            "executive chairman", "key managerial personnel", "kmp", "audit committee",
            "nomination committee", "stakeholder committee", "csr committee", "governance", "leadership"
        ]
        if has_any(board_terms):
            return "leadership_board"

        # 8. Financial Metrics & Performance
        financial_terms = [
            "revenue", "turnover", "income", "sales", "earnings", "profit", "pat", "pbt", "ebitda",
            "financial", "fy24", "fy25", "fy23", "crore", "lakh", "million", "billion", "balance sheet",
            "p&l", "profit and loss", "cash flow", "dividend", "expenditure", "net worth", "borrowings",
            "assets", "liabilities", "standalone", "consolidated"
        ]
        if has_any(financial_terms):
            return "financial"

        # Secondary Mappings
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
            "primary_company_identification": (35, 20, 6),
            "corporate_office_factual": (35, 20, 6),
            "cin_lookup": (35, 20, 5),
            "direct_factual": (25, 15, 6),
            "entity_person_lookup": (35, 20, 8),
            "person_biography": (40, 25, 10),
            "person_portrait_visual": (45, 30, 12),
            "leadership_board": (45, 30, 10),
            "financial": (45, 30, 10),
            "table_based": (40, 25, 10),
            "broad_summary": (50, 30, 14),
            "detailed_summary": (50, 30, 14),
            "visual": (35, 20, 8),
            "image": (35, 20, 8),
            "summary": (45, 25, 10),
            "timeline": (35, 20, 8),
            "comparison": (40, 25, 10),
            "list": (35, 20, 8),
            "product": (30, 15, 6),
            "manufacturing": (30, 15, 6)
        }
        return depths.get(intent, (30, 15, 8))

    @staticmethod
    def normalize_entity_text(name: str) -> str:
        """
        Normalizes person names, designations, company names, and entities
        by removing honorifics, punctuation, and collapsing whitespace.
        """
        import re
        if not name:
            return ""
        n = str(name).lower()
        for prefix in ["mr.", "mr ", "mrs.", "mrs ", "ms.", "ms ", "dr.", "dr ", "shri ", "smt ", "m/s.", "m/s ", "pcs "]:
            if n.startswith(prefix):
                n = n[len(prefix):]
        n = re.sub(r"[^\w\s]", " ", n)
        return re.sub(r"\s+", " ", n).strip()

    @staticmethod
    def fuzzy_match_entity(query_text: str, target_text: str, threshold: float = 0.80) -> bool:
        """
        Fuzzy entity matching with normalization, token subset matching, and typo tolerance.
        """
        import difflib
        q_norm = Retriever.normalize_entity_text(query_text)
        t_norm = Retriever.normalize_entity_text(target_text)
        if not q_norm or not t_norm:
            return False
        if q_norm == t_norm or q_norm in t_norm or t_norm in q_norm:
            return True
        q_tokens = set(q_norm.split())
        t_tokens = set(t_norm.split())
        if q_tokens and (q_tokens.issubset(t_tokens) or t_tokens.issubset(q_tokens)):
            return True
        sim = difflib.SequenceMatcher(None, q_norm, t_norm).ratio()
        return sim >= threshold

    def expand_query(self, query: str) -> str:
        """
        Expands query terms with generic corporate-role/domain synonyms (title
        abbreviations, visual-content vocabulary). Never expands to any
        specific company name, person name, address, or ID -- those come
        from the document's own entity registry via `_get_expanded_aliases`,
        not a fixed dictionary.
        """
        import re
        expanded = query
        synonyms = {
            r"\b(md)\b": "managing director MD",
            r"\b(wtd)\b": "whole-time director WTD",
            r"\b(cfo)\b": "chief financial officer CFO",
            r"\b(cs)\b": "company secretary CS",
            r"\b(cin)\b": "corporate identification number CIN",
            r"\b(kmp)\b": "key managerial personnel KMP",
            r"\b(pat)\b": "profit after tax PAT",
            r"\b(pbt)\b": "profit before tax PBT",
            r"\b(diagram|flowchart|architecture)\b": "diagram flowchart architecture visual figure illustration schematic workflow system diagram",
            r"\b(chart|graph|plot)\b": "chart graph plot visual trend curve data graphic figure",
            r"\b(figure|image|photo|illustration|picture|portrait)\b": "figure image photo portrait illustration visual picture diagram graphic"
        }
        for pattern, replacement in synonyms.items():
            if re.search(pattern, query, re.IGNORECASE):
                expanded += " " + replacement
        return expanded

    def _get_expanded_aliases(self, query: str, known_entities: Optional[List[str]] = None) -> List[str]:
        """
        Extracts generic role/section keyword aliases for exact matching and
        candidate boosting -- plus, when the caller supplies the document's
        own known-entity registry (e.g. names grounded from its own image
        chunks), any entity whose name overlaps the query is expanded into
        its own name-part variants (full name, first name, last name).
        Nothing here is specific to any one company/person/address/ID.
        """
        import re
        q = query.lower()
        aliases = []

        role_terms = {
            r"\b(company name|name of company|name of the company)\b": ["company name"],
            r"\b(managing director|md)\b": ["managing director", "md"],
            r"\b(whole-time director|whole time director|wtd)\b": ["whole-time director", "whole time director", "wtd"],
            r"\b(independent director|independent directors)\b": ["independent director"],
            r"\b(chairman|chairperson)\b": ["chairman", "chairperson"],
            r"\b(board of directors|directors|board)\b": ["board of directors", "directors", "board members", "composition of board"],
            r"\b(registered office)\b": ["registered office"],
            r"\b(corporate office)\b": ["corporate office"],
            r"\b(cin|corporate identification number)\b": ["cin", "corporate identification number"],
            r"\b(auditor|statutory auditor|auditors)\b": ["statutory auditors", "auditor"],
            r"\b(cfo|chief financial officer)\b": ["chief financial officer", "cfo"],
            r"\b(cs|company secretary)\b": ["company secretary", "cs"],
            r"\b(business division|divisions)\b": ["business division"],
            r"\b(manufacturing facilities|manufacturing plant)\b": ["manufacturing facilities"],
            r"\b(revenue|turnover|sales)\b": ["revenue from operations", "total income", "turnover", "sales"],
            r"\b(profit|pat|pbt)\b": ["profit after tax", "pat", "profit before tax", "pbt", "net profit"],
        }
        for pattern, keywords in role_terms.items():
            if re.search(pattern, q):
                aliases.extend(keywords)

        # Document-derived entity variants: only entities actually present in
        # THIS document's own registry, expanded into name-part variants
        # generically (never a fixed roster).
        for ent in (known_entities or []):
            ent_norm = Retriever.normalize_entity_text(ent)
            if not ent_norm:
                continue
            tokens = ent_norm.split()
            if ent_norm in q or any(len(t) > 2 and t in q for t in tokens):
                aliases.append(ent_norm)
                aliases.extend(t for t in tokens if len(t) > 2)

        return aliases

    def _search_exact_phrases(self, chunks: List[DocumentChunk], query: str) -> List[DocumentChunk]:
        """
        Searches for exact key multi-word phrases and role names from the query across all chunks.
        """
        import re
        matched = []
        q_lower = query.lower()
        
        phrases = re.findall(r'"([^"]+)"', query)
        if not phrases:
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
            for alias in aliases:
                if alias in heading_lower or alias in caption_lower:
                    score += 5
                elif alias in content_lower or alias in section_lower:
                    score += 3

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

    # India's Companies Act CIN format is a fixed, publicly standardized
    # pattern (not any one company's specific value): 1 letter + 5 digits +
    # 2 letters + 4 digits + 3 letters + 6 digits.
    _CIN_PATTERN = re.compile(r"\b[A-Z]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6}\b")

    def _boost_candidates(
        self,
        clean_query: str,
        fused_results: List[Tuple[DocumentChunk, float, float]],
        intent: Optional[str] = None
    ) -> List[Tuple[DocumentChunk, float, float]]:
        """
        Authority-aware candidate boosting: prioritizes exact factual statements, official directory tables,
        board of directors profiles, registered office, and entity matches. Purely content-based -- no
        hardcoded page numbers, company names, or person rosters; boosts are derived from the query's own
        role/keyword terms and from entities the document itself has grounded (chunk.metadata.people /
        entity_name).
        """
        import re
        q = clean_query.lower()
        boosted = []
        is_visual_query = (intent in ("visual", "person_portrait_visual"))

        # Document's own known people/entities (from every chunk's grounded
        # `people` / `entity_name` fields), used for generic entity-lookup
        # boosting -- never a fixed roster.
        doc_known_people = set()
        for chunk, _, _ in fused_results:
            for p in (getattr(chunk.metadata, "people", None) or []):
                if p:
                    doc_known_people.add(Retriever.normalize_entity_text(p))
            en = getattr(chunk.metadata, "entity_name", None)
            if en:
                doc_known_people.add(Retriever.normalize_entity_text(en))
        doc_known_people.discard("")

        # Person/entity-first resolution: if the query names one of the
        # document's own grounded people (any person, never a fixed
        # roster), resolve their stable document-scoped entity_id --
        # entity_linker computed and stamped the same key onto that
        # person's portrait chunk and every text chunk that discusses them
        # at indexing time -- so it can be used below to route
        # bio/qualification/experience/portrait questions to their own
        # linked chunks specifically, not just generic keyword overlap.
        from src.rag.entity_linker import generate_entity_key
        resolved_entity_key = None
        doc_id_for_entity = None
        for chunk, _, _ in fused_results:
            if getattr(chunk.metadata, "document_id", None):
                doc_id_for_entity = chunk.metadata.document_id
                break
        if doc_id_for_entity:
            for person in sorted(doc_known_people, key=len, reverse=True):
                if person and len(person) > 2 and person in q:
                    resolved_entity_key = generate_entity_key(doc_id_for_entity, person)
                    break

        aliases = self._get_expanded_aliases(q, known_entities=list(doc_known_people))
        q_words = [w for w in re.findall(r'\b[a-zA-Z0-9_\-\.]{3,}\b', q) if w not in ("what", "when", "where", "which", "who", "the", "and", "for", "with", "from", "about", "this", "that", "document")]

        for chunk, rrf, sem in fused_results:
            boost = 0.0
            meta = chunk.metadata
            page = meta.page_number
            content_lower = (chunk.content or "").lower()
            heading_lower = (meta.heading or "").lower()
            section_lower = (meta.section or "").lower()
            person_name = (getattr(meta, "entity_name", None) or "").lower()

            # 1. Primary Company Identification -- generic structural signal:
            # this content is generically an early-document / corporate-info
            # section, not a specific page number.
            if intent == "primary_company_identification":
                if any(k in heading_lower or k in section_lower for k in ("corporate information", "general information", "about the company", "company overview", "company name")):
                    boost += 0.55
                elif page <= 3:
                    boost += 0.25

            # 2. Corporate Office / Registered Office / Directory -- generic keyword match only
            if intent == "corporate_office_factual" or any(k in q for k in ["registered office", "corporate office", "cin", "auditor", "secretary", "cfo", "division", "facility"]):
                if any(alias in heading_lower or alias in content_lower for alias in ["registered office", "corporate office", "statutory auditors", "business division"]):
                    boost += 0.45

            # 2.2 Statutory Auditor & Auditor's Report Boosting
            if any(k in q for k in ["auditor", "audit report", "statutory auditor", "independent auditor"]):
                if "auditor" in heading_lower or "auditor" in section_lower or "auditor" in content_lower:
                    boost += 0.80

            # 2.3 Table Chunk Boosting
            if intent == "table_based" or any(k in q for k in ["table", "metrics table", "comparison table", "financial highlights"]):
                if meta.chunk_type == "table" or meta.table_id:
                    boost += 0.70

            # 2.5 CIN Direct Search -- generic CIN-format regex, not any one document's specific value
            if any(k in q for k in ["cin", "corporate identification number"]):
                if Retriever._CIN_PATTERN.search(chunk.content or "") or "cin:" in content_lower:
                    boost += 0.85

            # 3. Leadership & Board / Person Lookup -- generic entity-derived boost, no page numbers
            if intent in ("leadership_board", "person_portrait_visual", "entity_person_lookup", "person_biography"):
                for d_name in doc_known_people:
                    if len(d_name) > 2 and d_name in q:
                        if d_name in person_name or Retriever.fuzzy_match_entity(d_name, person_name):
                            boost += 0.80
                        if d_name in heading_lower or d_name in content_lower:
                            boost += 0.50

                # Generic directory/listing signal: a query about the board
                # or leadership as a GROUP (no specific name mentioned) has
                # no single entity to match against. Instead, boost chunks
                # that themselves mention multiple of the document's own
                # known people together -- a content-based signal that this
                # chunk is a director/leadership listing or directory
                # section, without any hardcoded page number.
                if intent in ("leadership_board", "entity_person_lookup"):
                    co_mentioned = sum(
                        1 for d_name in doc_known_people
                        if len(d_name) > 2 and (d_name in content_lower or d_name in heading_lower)
                    )
                    if co_mentioned >= 2:
                        boost += min(0.75, 0.20 * co_mentioned)

            # 4. Exact Phrase & Entity-Role Match
            for alias in aliases:
                if alias in heading_lower:
                    boost += 0.45
                    break
                elif alias in content_lower:
                    boost += 0.35
                    break

            # 5. Image & Visual Target
            if meta.chunk_type == "image":
                if hasattr(meta, "retrievable") and meta.retrievable is False:
                    boost -= 1.50
                elif getattr(meta, "importance_score", None) == "LOW" or (getattr(meta, "image_type", None) or "").lower() == "decorative":
                    boost -= 1.50
                elif is_visual_query:
                    boost += 0.50
                    if getattr(meta, "importance_score", None) == "HIGH":
                        boost += 0.30
                    if getattr(meta, "association_method", None) in ("explicit_caption", "same_card_layout", "ocr_grounded_identity", "signature_text_grounded"):
                        boost += 0.40

                    # Generic (non-hardcoded) entity match: this image's own
                    # grounded entity_name -- populated for ANY person via
                    # explicit caption / same-card layout / OCR, not just a
                    # fixed roster -- is compared directly against the query.
                    # Supports exact single-person, multi-person (each image
                    # scored independently per its own entity_name), and
                    # generic semantic-description-based queries alike.
                    candidate_entity = (getattr(meta, "entity_name", None) or person_name or "").strip().lower()
                    if candidate_entity:
                        if candidate_entity in q or Retriever.fuzzy_match_entity(candidate_entity, q):
                            boost += 0.80
                        else:
                            name_tokens = [
                                t for t in re.findall(r"[a-z]+", candidate_entity)
                                if len(t) > 2 and t not in ("mr", "mrs", "ms", "dr", "shri", "smt", "er")
                            ]
                            matched_tokens = sum(1 for t in name_tokens if t in q_words)
                            if name_tokens and matched_tokens >= max(1, len(name_tokens) - 1):
                                boost += 0.65
                else:
                    # For purely text questions, penalize image chunks so text evidence is preferred
                    boost -= 0.30

            # 6. Table Target
            if meta.chunk_type == "table" and (intent == "table_based" or "table" in q):
                boost += 0.40

            # 7. Person/Entity-First Routing: once a specific person has
            # been resolved from the query (above), strongly prefer the
            # chunks entity_linker actually linked to that exact person --
            # their own biography/qualification/experience text for a
            # person_biography question, their own portrait for a visual
            # question -- over generic keyword/vector similarity alone.
            if resolved_entity_key:
                chunk_entity_id = getattr(meta, "entity_id", None)
                chunk_entity_ids = getattr(meta, "entity_ids", None) or []
                is_entity_match = chunk_entity_id == resolved_entity_key or resolved_entity_key in chunk_entity_ids

                if is_entity_match:
                    if intent == "person_biography" and meta.chunk_type != "image":
                        boost += 3.00
                    elif is_visual_query and meta.chunk_type == "image":
                        boost += 3.00
                    elif meta.chunk_type != "image":
                        boost += 1.20
                else:
                    if intent == "person_biography" and meta.chunk_type == "image":
                        # A pure biography/qualification question should not
                        # surface the portrait (this person's own or anyone
                        # else's) as if it answered the question.
                        boost -= 1.00
                    elif is_visual_query and meta.chunk_type == "image" and chunk_entity_id:
                        # A different, specifically-named person's portrait
                        # when this person's photo was asked for.
                        boost -= 1.00

            boosted.append((chunk, rrf + boost, sem))
            
        boosted.sort(key=lambda x: x[1], reverse=True)
        return boosted

    def _search_images(self, chunks: List[DocumentChunk], query: str, intent: Optional[str] = None) -> List[DocumentChunk]:
        """
        Dedicated visual search with verified person-to-portrait matching, logo search,
        and strict visual gating (suppressing images for non-visual text queries).
        """
        from src.rag.image_processor import ImageRetrievalValidator, PortraitSpatialValidator
        import re

        # Document's own grounded entity registry (from every image chunk's
        # entity_name, populated generically -- not a hardcoded roster) so
        # query-target detection can tell a real person-name query apart
        # from a generic/semantic visual query (e.g. "the substation
        # construction site image") without guessing.
        doc_known_entities = list({
            c.metadata.entity_name for c in chunks
            if c.metadata.chunk_type == "image" and getattr(c.metadata, "entity_name", None)
        })

        # Step 1: Detect query target and check for visual intent
        target_info = ImageRetrievalValidator.detect_query_target(query, known_entities=doc_known_entities)
        if not target_info.get("is_visual", False) or target_info.get("target_type") == "pure_text":
            return []

        # Reject ambiguous surname-only queries (e.g. "photo of Todi")
        if target_info.get("target_type") == "ambiguous_surname":
            logger.info(f"Visual search rejected for ambiguous surname-only query: '{query}'")
            return []

        q_lower = query.lower()
        matched = []
        target_type = target_info.get("target_type")

        # 1. Logo query handler ("show the logo", "company logo")
        if target_type == "logo":
            for c in chunks:
                if c.metadata.chunk_type == "image":
                    meta = c.metadata
                    meta_dict = meta.model_dump() if hasattr(meta, "model_dump") else (meta.dict() if hasattr(meta, "dict") else meta.__dict__)
                    if ImageRetrievalValidator.validate_image_candidate(meta_dict, query, intent=intent, doc_id=meta.document_id, known_entities=doc_known_entities):
                        matched.append(c)
            if matched:
                return self._deduplicate_chunks(matched)

        # 2. Check for Board Collection visual query ("Board of Directors along with photos")
        if target_type == "board_collection":
            for c in chunks:
                if c.metadata.chunk_type == "image":
                    meta = c.metadata
                    meta_dict = meta.model_dump() if hasattr(meta, "model_dump") else (meta.dict() if hasattr(meta, "dict") else meta.__dict__)
                    if ImageRetrievalValidator.validate_image_candidate(meta_dict, query, intent=intent, doc_id=meta.document_id, known_entities=doc_known_entities):
                        matched.append(c)
            if matched:
                return self._deduplicate_chunks(matched)

        # 3. Check for Individual or Multi-Director Portrait Query
        if target_type == "multi_portrait":
            target_persons = target_info.get("target_persons", []) or target_info.get("target_directors", [])
            for p in target_persons:
                p_matched = []
                for c in chunks:
                    if c.metadata.chunk_type == "image":
                        meta = c.metadata
                        meta_dict = meta.model_dump() if hasattr(meta, "model_dump") else (meta.dict() if hasattr(meta, "dict") else meta.__dict__)
                        if ImageRetrievalValidator.validate_single_director_image(meta_dict, p, doc_id=meta.document_id):
                            p_matched.append(c)
                if p_matched:
                    matched.extend(p_matched)
            if matched:
                return self._deduplicate_chunks(matched)

        elif target_type == "portrait":
            target_person = target_info.get("target_person") or target_info.get("target_director")
            if target_person:
                for c in chunks:
                    if c.metadata.chunk_type == "image":
                        meta = c.metadata
                        meta_dict = meta.model_dump() if hasattr(meta, "model_dump") else (meta.dict() if hasattr(meta, "dict") else meta.__dict__)
                        if ImageRetrievalValidator.validate_single_director_image(meta_dict, target_person, doc_id=meta.document_id):
                            matched.append(c)
                if matched:
                    return self._deduplicate_chunks(matched)

        # 4. Captioned Figure / Diagram / Chart Query
        fig_match = re.search(r'(?i)\b(?:figure|fig\.?|chart|diagram|image|photo|illustration)\s*#?\s*(\d+)\b', query)
        fig_target_num = fig_match.group(1) if fig_match else None

        for c in chunks:
            if c.metadata.chunk_type != "image" and not c.metadata.image_id:
                continue

            meta = c.metadata
            meta_dict = meta.model_dump() if hasattr(meta, "model_dump") else (meta.dict() if hasattr(meta, "dict") else meta.__dict__)
            if not ImageRetrievalValidator.validate_image_candidate(meta_dict, query, intent=intent, doc_id=meta.document_id, known_entities=doc_known_entities):
                continue

            title = (getattr(meta, "title", None) or "").lower()
            subtitle = (getattr(meta, "subtitle", None) or "").lower()
            caption = (getattr(meta, "caption", None) or getattr(meta, "caption_text", None) or meta.heading or "").lower()
            explicit_cap = (getattr(meta, "explicit_caption", None) or "").lower()
            entity_name = (getattr(meta, "entity_name", None) or "").lower()
            designation = (getattr(meta, "designation", None) or "").lower()
            section_heading = (getattr(meta, "section_heading", None) or meta.section or "").lower()
            ocr = (getattr(meta, "ocr_text", None) or "").lower()
            vlm = (getattr(meta, "semantic_description", None) or "").lower()
            objs = [str(o).lower() for o in (getattr(meta, "objects", []) or [])]
            ents = [str(e).lower() for e in (getattr(meta, "detected_entities", []) or [])]
            kws = [str(k).lower() for k in (getattr(meta, "keywords", []) or [])]

            if fig_target_num:
                if (fig_target_num in caption or 
                    fig_target_num in explicit_cap or 
                    fig_target_num in title or 
                    (meta.image_id and fig_target_num in meta.image_id)):
                    matched.append(c)
                    continue

            visual_triggers = ImageRetrievalValidator.VISUAL_TRIGGERS
            q_words = [w for w in re.findall(r'\w+', q_lower) if len(w) > 2 and w not in visual_triggers]
            if q_words:
                match_count = 0
                for w in q_words:
                    if (w in title or 
                        w in subtitle or 
                        w in explicit_cap or 
                        w in caption or 
                        w in entity_name or 
                        w in designation or 
                        w in section_heading or 
                        w in ocr or 
                        w in vlm or 
                        any(w in o for o in objs) or 
                        any(w in e for e in ents) or 
                        any(w in k for k in kws)):
                        match_count += 1
                if match_count > 0:
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
        is_visual_query = (intent in ("visual", "person_portrait_visual") or any(vt in query.lower() for vt in ["photo", "portrait", "logo", "diagram", "chart", "image of", "picture of"]))
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

        # Document's own known people/entities (from every chunk's grounded
        # `people` / `entity_name` fields), reused for generic alias
        # expansion and ambiguity detection throughout this method -- never
        # a fixed roster.
        doc_known_people = set()
        for c in search_chunks:
            for p in (getattr(c.metadata, "people", None) or []):
                if p:
                    doc_known_people.add(Retriever.normalize_entity_text(p))
            en = getattr(c.metadata, "entity_name", None)
            if en:
                doc_known_people.add(Retriever.normalize_entity_text(en))
        doc_known_people.discard("")
        doc_known_people = list(doc_known_people)

        # 5. Multi-Stage Candidates Collection
        candidates_dict = {}
        def add_candidates(chunks_list):
            for c in chunks_list:
                if c and c.metadata and c.metadata.chunk_id:
                    candidates_dict[c.metadata.chunk_id] = c
        
        # Stage A0: Person/Entity-First Resolution. If the query names one of
        # the document's own grounded people, resolve their stable
        # entity_id (the same key entity_linker stamped onto that person's
        # portrait chunk and every text chunk that discusses them at
        # indexing time) and GUARANTEE the correct linked chunks are in the
        # candidate pool for a person-oriented intent -- not left to chance
        # keyword/vector ranking. A qualifications/education/experience/
        # biography question is guaranteed their real text chunks (not just
        # the portrait's own short metadata); a portrait/photo question is
        # guaranteed their own portrait, not an unrelated image.
        from src.rag.entity_linker import generate_entity_key
        q_lower = clean_query.lower()
        resolved_entity_key = None
        for person in sorted(doc_known_people, key=len, reverse=True):
            if person and len(person) > 2 and person in q_lower:
                resolved_entity_key = generate_entity_key(document_id, person)
                break

        person_oriented_intent = intent in (
            "person_biography", "entity_person_lookup", "leadership_board", "person_portrait_visual"
        )
        if resolved_entity_key and person_oriented_intent:
            linked = []
            for c in search_chunks:
                meta = c.metadata
                c_entity_id = getattr(meta, "entity_id", None)
                c_entity_ids = getattr(meta, "entity_ids", None) or []
                if c_entity_id != resolved_entity_key and resolved_entity_key not in c_entity_ids:
                    continue
                if intent == "person_biography":
                    if meta.chunk_type != "image":
                        linked.append(c)
                elif is_visual_query:
                    if meta.chunk_type == "image":
                        linked.append(c)
                else:
                    linked.append(c)
            if linked:
                logger.info(
                    f"[entity_resolution] query resolved to entity_id={resolved_entity_key} "
                    f"-> guaranteeing {len(linked)} linked chunk(s) for intent={intent}."
                )
            add_candidates(linked)

        # Stage A: Metadata & Heading-Aware Search
        meta_candidates = self._search_metadata(search_chunks, query)
        add_candidates(meta_candidates)
        
        # Stage B: Heading & TOC Search
        toc_candidates = self._search_toc_and_headings(search_chunks, doc_struct, query)
        add_candidates(toc_candidates)
        
        # Stage C: Entity Search (with expanded aliases and typo tolerance)
        entity_candidates = self._search_entity_index(entity_index, query)
        add_candidates(entity_candidates)
        
        # Stage D: Dedicated Table Search
        table_candidates = self._search_tables(search_chunks, query)
        add_candidates(table_candidates)
        
        # Stage E: Dedicated Image & Visual Search (Query-gated & verified)
        image_candidates = self._search_images(search_chunks, query, intent=intent)
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
        
        # For visual queries with verified image candidates, ensure they are preserved in candidate_list
        # (is_visual_query computed once above, at the top of retrieve(), and reused everywhere in
        # this method -- previously recomputed here and below with narrower, drifting keyword sets)
        if is_visual_query and image_candidates:
            cand_dict = {c.metadata.chunk_id: c for c, _, _ in fused_results}
            for ic in image_candidates:
                cand_dict[ic.metadata.chunk_id] = ic
            candidate_list = list(image_candidates) + [c for cid, c in cand_dict.items() if cid not in {ic.metadata.chunk_id for ic in image_candidates}][:top_k_rerank]
        else:
            candidate_list = [chunk for chunk, _, _ in fused_results[:top_k_rerank]]
        
        # 7. First-Pass Reranking
        reranked = self.reranker.rerank(query, candidate_list)
        
        # Apply structured intent weights (e.g. tables for table queries, auditor sections for auditor queries, visual for image queries)
        weighted_reranked = []
        for chunk, score in reranked:
            adj_score = score
            meta = chunk.metadata
            c_lower = (chunk.content or "").lower()
            h_lower = (meta.heading or "").lower()
            t_lower = (getattr(meta, "title", "") or "").lower()
            
            if (intent == "table_based" or "table" in query.lower()) and (meta.chunk_type == "table" or meta.table_id):
                adj_score += 2.0
            if any(k in query.lower() for k in ["auditor", "audit report", "statutory auditor"]) and ("auditor" in h_lower or "auditor" in c_lower):
                adj_score += 2.0
            if (intent in ("visual", "person_portrait_visual") or "photo" in query.lower() or "logo" in query.lower() or "image of" in query.lower()) and meta.chunk_type == "image":
                adj_score += 3.0
                if "logo" in query.lower() and (getattr(meta, "image_type", None) == "Logo" or "logo" in t_lower):
                    adj_score += 3.0
                
            weighted_reranked.append((chunk, adj_score))
            
        weighted_reranked.sort(key=lambda x: x[1], reverse=True)
        reranked = weighted_reranked
        
        # 8. Two-Pass Retrieval Fallback
        max_rerank_score = max([score for _, score in reranked]) if reranked else 0.0
        aliases = self._get_expanded_aliases(query, known_entities=doc_known_people)
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
            
        # 8.5 Score Floor & Authority Preservation:
        # Guarantee that exact entity / official directory chunks keep top reranking scores
        adjusted_reranked = []
        for chunk, score in reranked:
            meta = chunk.metadata
            c_text = (chunk.content or "").lower()
            c_head = (meta.heading or "").lower()
            p_name = (getattr(meta, "entity_name", None) or getattr(meta, "title", None) or getattr(meta, "person_name", None) or "").lower()
            
            # Authoritative exact-match score floor -- content-based only, no fixed page numbers
            if any(alias in c_text or alias in c_head for alias in aliases):
                score = max(score, 0.95)

            # CIN exact matching floor -- generic CIN-format regex, not any one document's specific value
            if intent == "cin_lookup" or any(k in query.lower() for k in ["cin", "corporate identification number"]):
                if Retriever._CIN_PATTERN.search(chunk.content or "") or "cin:" in c_text:
                    score = max(score, 0.98)

            if (intent in ("person_portrait_visual", "visual") or is_visual_query) and meta.chunk_type == "image":
                if image_candidates and chunk.metadata.chunk_id in {ic.metadata.chunk_id for ic in image_candidates}:
                    score = max(score, 0.99)
                elif p_name and any(Retriever.fuzzy_match_entity(alias, p_name) or alias in p_name or p_name in alias for alias in aliases):
                    score = max(score, 0.99)
                elif "logo" in query.lower() and (getattr(meta, "image_type", None) == "Logo" or "logo" in (getattr(meta, "title", "") or "").lower()):
                    score = max(score, 0.99)
                else:
                    score = max(score, 0.50)

            if p_name and any(Retriever.fuzzy_match_entity(alias, p_name) or alias in p_name or p_name in alias for alias in aliases):
                score = max(score, 0.95)
                
            adjusted_reranked.append((chunk, score))
            
        adjusted_reranked.sort(key=lambda x: x[1], reverse=True)
        reranked = adjusted_reranked
            
        # 9. Parent-Child & Structured Section Expansion
        top_ranked = list(reranked[:top_k_final])
        if is_visual_query and image_candidates:
            top_ids = {c.metadata.chunk_id for c, _ in top_ranked}
            for ic in image_candidates:
                if ic.metadata.chunk_id not in top_ids:
                    top_ranked.insert(0, (ic, 0.99))
        expanded_chunks = self._expand_context(top_ranked, search_chunks, doc_struct)
        
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
            
        # Retrieval Gating: Filter image chunks using ImageRetrievalValidator
        from src.rag.image_processor import ImageRetrievalValidator
        doc_known_entities_gate = list({
            c.metadata.entity_name for c in search_chunks
            if c.metadata.chunk_type == "image" and getattr(c.metadata, "entity_name", None)
        })
        gated_scored = []
        for sc in scored_chunks:
            if sc.metadata.chunk_type == "image":
                meta = sc.metadata
                meta_dict = meta.model_dump() if hasattr(meta, "model_dump") else (meta.dict() if hasattr(meta, "dict") else meta.__dict__)
                if is_visual_query:
                    if not ImageRetrievalValidator.validate_image_candidate(meta_dict, query, intent=intent, doc_id=meta.document_id, known_entities=doc_known_entities_gate):
                        continue
                else:
                    # Pure text query: filter out non-retrievable or decorative images
                    if hasattr(meta, "retrievable") and meta.retrievable is False:
                        continue
                    if getattr(meta, "importance_score", None) == "LOW":
                        continue
                    if (getattr(meta, "image_type", None) or "").lower() == "decorative":
                        continue
            gated_scored.append(sc)
        scored_chunks = gated_scored
            
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

    def _resolve_output_dir(self, document_id: str) -> Path:
        from src.config import ROOT_DIR
        candidates = [
            ROOT_DIR / "data" / "output" / document_id,
            Path(self.config.chroma_db_dir).parent / "output" / document_id,
            Path(self.config.chroma_db_dir).parent / document_id,
            Path(self.config.chroma_db_dir) / document_id,
        ]
        for c in candidates:
            if c.exists() and ((c / "06_chunks" / "document_chunks.json").exists() or (c / "document_chunks.json").exists() or (c / "02_docling" / "structured_document.json").exists()):
                return c
        for c in candidates:
            if c.exists():
                return c
        return ROOT_DIR / "data" / "output" / document_id

    def _load_structured_document(self, document_id: str) -> Optional[StructuredDocument]:
        output_dir = self._resolve_output_dir(document_id)
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
            if ent_clean in q_lower or any(alias in ent_clean or ent_clean in alias for alias in aliases) or Retriever.fuzzy_match_entity(q_lower, ent_clean):
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
        
        for item in scored_results:
            if isinstance(item, tuple):
                chunk = item[0]
                score = item[1] if len(item) > 1 else 0.99
            else:
                chunk = item
                score = 0.99

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
        output_dir = self._resolve_output_dir(document_id)
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

                    raw_img_p = str(meta_data.get("image_path") or "").replace("\\", "/")
                    norm_img_p = None
                    if "05_images/image_" in raw_img_p:
                        norm_img_p = f"05_images/{raw_img_p.split('05_images/')[-1]}"
                    elif raw_img_p.startswith("05_images/image_"):
                        norm_img_p = raw_img_p

                    raw_img_u = str(meta_data.get("image_url") or "").replace("\\", "/")
                    norm_img_u = None
                    if "/05_images/image_" in raw_img_u:
                        norm_img_u = raw_img_u
                    elif norm_img_p:
                        norm_img_u = f"/outputs/{document_id}/{norm_img_p}"

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
                        image_path=norm_img_p,
                        image_url=norm_img_u,
                        image_type=meta_data.get("image_type"),
                        title=meta_data.get("title"),
                        subtitle=meta_data.get("subtitle"),
                        explicit_caption=meta_data.get("explicit_caption"),
                        caption_text=meta_data.get("caption_text") or meta_data.get("caption"),
                        entity_name=meta_data.get("entity_name"),
                        designation=meta_data.get("designation"),
                        entity_id=meta_data.get("entity_id"),
                        entity_ids=self._parse_list_meta(meta_data.get("entity_ids")),
                        linked_text_chunk_ids=self._parse_list_meta(meta_data.get("linked_text_chunk_ids")),
                        text_before=meta_data.get("text_before"),
                        text_after=meta_data.get("text_after"),
                        nearby_text=meta_data.get("nearby_text"),
                        layout_context=meta_data.get("layout_context"),
                        importance_score=meta_data.get("importance_score", "MEDIUM") or "MEDIUM",
                        retrievable=meta_data.get("retrievable", True) if isinstance(meta_data.get("retrievable"), bool) else (str(meta_data.get("retrievable")).lower() != "false"),
                        association_method=meta_data.get("association_method", "none") or "none",
                        confidence=float(meta_data.get("confidence", 1.0) or 1.0),
                        association_confidence=float(meta_data.get("association_confidence", meta_data.get("confidence", 1.0)) or 1.0),
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

                # Also inject all image metadata JSONs from 05_images if not already represented
                existing_img_ids = {c.metadata.image_id for c in chunks if c.metadata.image_id}
                existing_img_paths = {c.metadata.image_path for c in chunks if c.metadata.image_path}
                images_dir = output_dir / "05_images"
                if images_dir.exists():
                    for jf in sorted(list(images_dir.glob("image_*.json"))):
                        stem = jf.stem
                        rel_path = f"05_images/{stem}.png"
                        png_path = images_dir / f"{stem}.png"
                        if not png_path.exists() or png_path.stat().st_size == 0:
                            # Orphaned metadata JSON with no backing image file --
                            # never surface a chunk with no valid file mapping.
                            logger.warning(f"Skipping image metadata {jf.name}: no backing PNG at {png_path}")
                            continue
                        try:
                            with open(jf, "r", encoding="utf-8") as f:
                                im_data = json.load(f)
                            im_id = im_data.get("image_id") or stem
                            if im_id not in existing_img_ids and rel_path not in existing_img_paths:
                                bboxes = []
                                b_raw = im_data.get("bounding_box")
                                if b_raw:
                                    if isinstance(b_raw, dict):
                                        bboxes.append(BoundingBox(**b_raw))
                                    elif isinstance(b_raw, BoundingBox):
                                        bboxes.append(b_raw)
                                
                                title = im_data.get("title") or im_data.get("caption") or f"Visual on Page {im_data.get('page', 1)}"
                                subtitle = im_data.get("subtitle")
                                explicit_caption = im_data.get("explicit_caption")
                                caption_text = im_data.get("caption_text") or im_data.get("caption")
                                entity_name = im_data.get("entity_name")
                                designation = im_data.get("designation")
                                sec_heading = im_data.get("section_heading")
                                vlm_desc = im_data.get("semantic_description") or ""
                                ocr_text = im_data.get("ocr_text") or ""
                                text_before = im_data.get("text_before")
                                text_after = im_data.get("text_after")
                                nearby_text = im_data.get("nearby_text")
                                image_type = im_data.get("image_type") or "Photo"
                                importance_score = im_data.get("importance_score", "MEDIUM") or "MEDIUM"
                                retrievable = im_data.get("retrievable", True)
                                association_method = im_data.get("association_method", "none") or "none"
                                association_confidence = float(im_data.get("association_confidence", im_data.get("confidence", 1.0)) or 1.0)
                                confidence = float(im_data.get("confidence", 1.0) or 1.0)
                                
                                # Construct searchable content text
                                content_parts = [
                                    f"Document Section: {sec_heading or 'Visual Assets'}",
                                    "Content:",
                                    f"Image ID: {im_id}",
                                    f"Image Type: {image_type}",
                                    f"Page: {im_data.get('page', 1)}",
                                    f"Image Title: {title}"
                                ]
                                if subtitle:
                                    content_parts.append(f"Image Subtitle: {subtitle}")
                                if explicit_caption:
                                    content_parts.append(f"Explicit Document Caption: {explicit_caption}")
                                if caption_text and caption_text != title:
                                    content_parts.append(f"Image Caption: {caption_text}")
                                if entity_name:
                                    role_part = f" ({designation})" if designation else ""
                                    content_parts.append(f"Associated Person/Entity: {entity_name}{role_part}")
                                if sec_heading:
                                    content_parts.append(f"Section Heading: {sec_heading}")
                                if vlm_desc:
                                    content_parts.append(f"Image Semantic Description: {vlm_desc}")
                                if ocr_text:
                                    content_parts.append(f"Image OCR Text: {ocr_text}")
                                if text_before:
                                    content_parts.append(f"Preceding Text Context: {text_before[:150]}")
                                if text_after:
                                    content_parts.append(f"Succeeding Text Context: {text_after[:150]}")
                                if nearby_text and nearby_text not in (text_before, text_after):
                                    content_parts.append(f"Adjacent Profile Text: {nearby_text[:250]}")

                                keywords = im_data.get("keywords") or []
                                if keywords:
                                    content_parts.append(f"Keywords: {', '.join(keywords)}")

                                img_meta = ChunkMetadata(
                                    chunk_id=f"{document_id}_img_{stem}",
                                    document_id=document_id,
                                    page_number=int(im_data.get("page", 1)),
                                    chunk_type="image",
                                    heading=title,
                                    section=sec_heading or "Visual Assets",
                                    section_heading=sec_heading,
                                    hierarchy_path=[],
                                    source_element_ids=[im_id],
                                    word_count=len("\n".join(content_parts).split()),
                                    token_estimate=len("\n".join(content_parts).split()) * 2,
                                    bounding_boxes=bboxes,
                                    image_id=im_id,
                                    image_path=rel_path,
                                    image_url=f"/outputs/{document_id}/{rel_path}",
                                    image_type=image_type,
                                    title=title,
                                    subtitle=subtitle,
                                    explicit_caption=explicit_caption,
                                    caption_text=caption_text,
                                    entity_name=entity_name,
                                    designation=designation,
                                    entity_id=im_data.get("entity_id"),
                                    linked_text_chunk_ids=im_data.get("linked_text_chunk_ids") or [],
                                    text_before=text_before,
                                    text_after=text_after,
                                    nearby_text=nearby_text,
                                    layout_context=im_data.get("layout_context"),
                                    importance_score=importance_score,
                                    retrievable=retrievable,
                                    association_method=association_method,
                                    association_confidence=association_confidence,
                                    confidence=confidence,
                                    caption=caption_text or title,
                                    ocr_text=ocr_text,
                                    semantic_description=vlm_desc,
                                    objects=im_data.get("objects", []),
                                    detected_entities=im_data.get("detected_entities", []),
                                    keywords=keywords
                                )
                                chunks.append(DocumentChunk(content="\n".join(content_parts), metadata=img_meta))
                                existing_img_ids.add(im_id)
                                existing_img_paths.add(rel_path)
                        except Exception as e:
                            logger.warning(f"Failed to load image metadata {jf.name}: {e}")

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
                    explicit_caption=meta_data.get("explicit_caption") or None,
                    caption_text=meta_data.get("caption_text") or meta_data.get("caption") or None,
                    entity_name=meta_data.get("entity_name") or None,
                    designation=meta_data.get("designation") or None,
                    entity_id=meta_data.get("entity_id") or None,
                    entity_ids=self._parse_list_meta(meta_data.get("entity_ids")),
                    linked_text_chunk_ids=self._parse_list_meta(meta_data.get("linked_text_chunk_ids")),
                    text_before=meta_data.get("text_before") or None,
                    text_after=meta_data.get("text_after") or None,
                    nearby_text=meta_data.get("nearby_text") or None,
                    layout_context=meta_data.get("layout_context") or None,
                    importance_score=meta_data.get("importance_score", "MEDIUM") or "MEDIUM",
                    retrievable=str(meta_data.get("retrievable", "True")).lower() != "false",
                    association_method=meta_data.get("association_method", "none") or "none",
                    confidence=float(meta_data.get("confidence", 1.0) or 1.0),
                    association_confidence=float(meta_data.get("association_confidence", meta_data.get("confidence", 1.0)) or 1.0),
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

