import re
import logging
from enum import Enum
from typing import List, Set, Optional, Dict, Any
from pydantic import BaseModel, Field

from src.rag.embedder import Embedder
from src.rag.chunk_schema import DocumentChunk, ChunkMetadata

logger = logging.getLogger("pipeline")

# Standard list of English stopwords for optional stopword removal
STOPWORDS: Set[str] = {
    "i", "me", "my", "myself", "we", "our", "ours", "ourselves", "you", "your", "yours", 
    "yourself", "yourselves", "he", "him", "his", "himself", "she", "her", "hers", 
    "herself", "it", "its", "itself", "they", "them", "their", "theirs", "themselves", 
    "what", "which", "who", "whom", "this", "that", "these", "those", "am", "is", "are", 
    "was", "were", "be", "been", "being", "have", "has", "had", "having", "do", "does", 
    "did", "doing", "a", "an", "the", "and", "but", "if", "or", "because", "as", "until", 
    "while", "of", "at", "by", "for", "with", "about", "against", "between", "into", 
    "through", "during", "before", "after", "above", "below", "to", "from", "up", "down", 
    "in", "out", "on", "off", "over", "under", "again", "further", "then", "once", "here", 
    "there", "when", "where", "why", "how", "all", "any", "both", "each", "few", "more", 
    "most", "other", "some", "such", "no", "nor", "not", "only", "own", "same", "so", 
    "than", "too", "very", "s", "t", "can", "will", "just", "don", "should", "now"
}

class QueryCategory(str, Enum):
    """Top-level taxonomy for query classification."""
    TEXT = "text"
    FACTUAL_ENTITY = "factual_entity"
    SUMMARY = "summary"
    TABLE = "table"
    IMAGE_VISUAL = "image_visual"
    MIXED = "mixed"

class QueryClassification(BaseModel):
    """Structured result of natural language query classification."""
    query: str
    primary_category: QueryCategory
    sub_intent: str
    has_explicit_table_request: bool = False
    has_explicit_visual_request: bool = False
    has_exact_entity_target: bool = False
    target_visual_type: Optional[str] = None  # "logo", "portrait", "diagram", "chart", "plant_photo", "general_image"
    target_person_name: Optional[str] = None
    target_entities: List[str] = Field(default_factory=list)
    confidence: float = 1.0
    suggested_depth: Dict[str, int] = Field(default_factory=dict)

    @property
    def top_k_retrieve(self) -> int:
        return self.suggested_depth.get("top_k_retrieve", 30)

    @property
    def top_k_rerank(self) -> int:
        return self.suggested_depth.get("top_k_rerank", 15)

    @property
    def top_k_final(self) -> int:
        return self.suggested_depth.get("top_k_final", 6)

class QueryProcessor:
    """
    Handles preprocessing of natural language queries, semantic classification,
    intent routing, and query embedding generation.
    """

    KNOWN_DIRECTORS: List[str] = [
        "sunil kumar mittra", "sunil mittra", "ravi todi", "rhea todi", "avik mukherjee",
        "aviik mukherjee", "subrata paul", "arundhuti dhar", "sandipan chakravortty",
        "ketan mangaldas shanghavi", "ketan shanghavi", "sourav daspatnaik", "sourab kumar jha", "utkarsh tiwari"
    ]

    def __init__(self, embedder: Optional[Embedder] = None) -> None:
        self.embedder = embedder

    def preprocess_query(self, query: str, remove_stopwords: bool = False) -> str:
        """
        Applies lowercase folding, whitespace folding, punctuation stripping,
        and optional stopword filtering to prepare the query string.
        """
        if not query:
            return ""

        # 1. Lowercase folding
        processed = query.lower()

        # 2. Punctuation cleanup (replace special characters with spaces, keep alphanumeric)
        processed = re.sub(r'[^\w\s]', ' ', processed)

        # 3. Collapse multiple spaces and strip ends
        processed = re.sub(r'\s+', ' ', processed).strip()

        # 4. Optional stopword removal
        if remove_stopwords:
            words = processed.split()
            words = [w for w in words if w not in STOPWORDS]
            processed = " ".join(words)

        return processed

    def classify_query(self, query: str) -> QueryClassification:
        """
        Classifies user query into text, factual/entity, summary, table, image/visual, or mixed.
        Detects specific entity targets, visual asset types, and table display flags.
        """
        q_raw = query.strip()
        q = q_raw.lower()

        def has_phrase(phrases: List[str]) -> bool:
            return any(re.search(rf"\b{re.escape(p)}\b", q) for p in phrases)

        # 1. Visual request detection
        logo_triggers = ["logo", "company logo", "brand logo", "emblem", "insignia", "show logo", "show the logo"]
        is_logo_query = has_phrase(logo_triggers)

        portrait_triggers = [
            "photo of", "photos of", "portrait", "portraits", "photograph of", "photographs of",
            "picture of", "pictures of", "headshot", "headshots", "along with their photos",
            "along with photos", "with photos", "with photo", "show photo", "show photos",
            "show portrait", "show picture", "director's photo", "directors photo", "director photo"
        ]
        is_portrait_query = has_phrase(portrait_triggers)

        diagram_chart_triggers = [
            "diagram", "flowchart", "architecture diagram", "schematic", "chart", "graph", "plot",
            "trend chart", "pie chart", "bar chart", "flow diagram", "system diagram"
        ]
        is_diagram_query = has_phrase(diagram_chart_triggers)

        general_visual_triggers = [
            "image", "images", "figure", "figures", "visual", "visuals", "photo", "photos",
            "illustration", "illustrations", "picture", "pictures", "look like", "show me image", "show the image"
        ]
        has_visual_intent = is_logo_query or is_portrait_query or is_diagram_query or has_phrase(general_visual_triggers)

        # 2. Table request detection
        explicit_table_triggers = [
            "show the table", "show table", "display the table", "display table",
            "give the table", "give me the table", "tabular format", "table of", "table for",
            "in a table", "view table", "see the table"
        ]
        is_explicit_table = has_phrase(explicit_table_triggers)
        
        general_table_triggers = [
            "table", "tabular", "balance sheet", "p&l table", "metrics table", "comparison table",
            "financial highlights table", "schedule table"
        ]
        has_table_intent = is_explicit_table or has_phrase(general_table_triggers)

        # 3. Summary request detection
        summary_triggers = [
            "summarize", "summarise", "summary", "overview", "synopsis", "outline",
            "executive summary", "comprehensive overview", "all divisions", "brief overview",
            "describe all", "key highlights", "timeline", "chronology", "history of company"
        ]
        is_summary_query = has_phrase(summary_triggers)

        # 4. Factual & Entity request detection
        company_id_triggers = [
            "company name", "name of company", "name of the company", "which company", "what company",
            "who is the company", "document subject"
        ]
        is_company_id = has_phrase(company_id_triggers)

        cin_triggers = ["cin", "corporate identification number", "company identification number"]
        is_cin = has_phrase(cin_triggers)

        office_triggers = [
            "registered office", "corporate office", "office address", "address of", "where is the office",
            "factory address", "plant location", "facilities location"
        ]
        is_office = has_phrase(office_triggers)

        auditor_triggers = [
            "statutory auditor", "statutory auditors", "internal auditor", "secretarial auditor",
            "cost auditor", "auditors", "audit firm", "independent auditor", "auditor report"
        ]
        is_auditor = has_phrase(auditor_triggers)

        leadership_triggers = [
            "board of directors", "composition of board", "board members", "directors",
            "managing director", "whole-time director", "whole time director", "executive director",
            "independent director", "non-executive director", "chairman", "chairperson",
            "key managerial personnel", "kmp", "chief financial officer", "cfo", "company secretary", "cs"
        ]
        is_leadership = has_phrase(leadership_triggers)

        # Detect specific person mention
        detected_person = None
        for d_name in self.KNOWN_DIRECTORS:
            if re.search(rf"\b{re.escape(d_name)}\b", q):
                detected_person = d_name
                break

        # Check for target entities
        target_entities = []
        if detected_person:
            target_entities.append(detected_person.title())
        if is_cin or "u29100wb1992plc054541" in q:
            target_entities.append("CIN")
        if is_office:
            target_entities.append("Office Address")
        if is_auditor:
            target_entities.append("Statutory Auditors")
        if is_company_id or "btl" in q:
            target_entities.append("BTL EPC LIMITED")

        # Determine Visual Target Type
        target_visual_type = None
        if is_logo_query:
            target_visual_type = "logo"
        elif is_portrait_query or (has_visual_intent and (detected_person or is_leadership)):
            target_visual_type = "portrait"
        elif is_diagram_query:
            target_visual_type = "diagram"
        elif has_visual_intent:
            target_visual_type = "general_image"

        # Determine Primary Category & Sub-Intent
        primary_category: QueryCategory
        sub_intent: str

        # Check for MIXED queries (compound intent: visual + text, or table + narrative explanation)
        is_mixed_visual = has_visual_intent and (
            has_phrase(["along with", "with photos", "and their photos", "and photo", "with pictures", "and photos", "with picture"]) or 
            ("list" in q and "photo" in q) or 
            (is_summary_query and has_visual_intent)
        )
        is_mixed_table = is_explicit_table and has_phrase(["explain", "describe", "analyze", "why", "how", "evaluate"])

        if is_mixed_visual:
            primary_category = QueryCategory.MIXED
            sub_intent = "mixed_visual_text"
        elif is_mixed_table:
            primary_category = QueryCategory.MIXED
            sub_intent = "mixed_table_text"
        elif has_visual_intent:
            primary_category = QueryCategory.IMAGE_VISUAL
            if is_logo_query:
                sub_intent = "logo"
            elif target_visual_type == "portrait":
                sub_intent = "person_portrait"
            elif is_diagram_query:
                sub_intent = "diagram_chart"
            else:
                sub_intent = "general_visual"
        elif is_explicit_table or (has_table_intent and not has_phrase(["how", "why", "who"])):
            primary_category = QueryCategory.TABLE
            sub_intent = "table_view" if is_explicit_table else "financial_table"
        elif is_summary_query:
            primary_category = QueryCategory.SUMMARY
            if "timeline" in q or "chronolog" in q or "history" in q:
                sub_intent = "timeline"
            elif "detail" in q or "comprehensive" in q:
                sub_intent = "detailed_summary"
            else:
                sub_intent = "broad_summary"
        elif is_company_id:
            primary_category = QueryCategory.FACTUAL_ENTITY
            sub_intent = "company_identity"
        elif is_cin:
            primary_category = QueryCategory.FACTUAL_ENTITY
            sub_intent = "cin_lookup"
        elif is_office:
            primary_category = QueryCategory.FACTUAL_ENTITY
            sub_intent = "registered_office"
        elif is_auditor:
            primary_category = QueryCategory.FACTUAL_ENTITY
            sub_intent = "statutory_auditor"
        elif is_leadership or detected_person:
            primary_category = QueryCategory.FACTUAL_ENTITY
            sub_intent = "leadership_board" if (is_leadership and not detected_person) else "person_lookup"
        elif any(w in q for w in ["revenue", "pat", "pbt", "turnover", "profit", "ebitda", "crore", "sales", "fy24", "fy23"]):
            primary_category = QueryCategory.FACTUAL_ENTITY
            sub_intent = "financial_metrics"
        else:
            primary_category = QueryCategory.TEXT
            sub_intent = "direct_factual"

        # Suggested retrieval depth
        depth_map = {
            QueryCategory.FACTUAL_ENTITY: {"top_k_retrieve": 35, "top_k_rerank": 20, "top_k_final": 6},
            QueryCategory.SUMMARY: {"top_k_retrieve": 50, "top_k_rerank": 30, "top_k_final": 14},
            QueryCategory.TABLE: {"top_k_retrieve": 40, "top_k_rerank": 25, "top_k_final": 8},
            QueryCategory.IMAGE_VISUAL: {"top_k_retrieve": 40, "top_k_rerank": 25, "top_k_final": 8},
            QueryCategory.MIXED: {"top_k_retrieve": 50, "top_k_rerank": 30, "top_k_final": 12},
            QueryCategory.TEXT: {"top_k_retrieve": 30, "top_k_rerank": 15, "top_k_final": 6},
        }

        return QueryClassification(
            query=query,
            primary_category=primary_category,
            sub_intent=sub_intent,
            has_explicit_table_request=is_explicit_table,
            has_explicit_visual_request=has_visual_intent,
            has_exact_entity_target=bool(target_entities or detected_person),
            target_visual_type=target_visual_type,
            target_person_name=detected_person,
            target_entities=target_entities,
            confidence=0.95,
            suggested_depth=depth_map.get(primary_category, {"top_k_retrieve": 30, "top_k_rerank": 15, "top_k_final": 6})
        )

    def generate_query_embedding(self, query: str) -> List[float]:
        """
        Generates a vector embedding of the query for semantic search.
        """
        logger.info("Generating query embedding...")
        if self.embedder is None:
            from src.rag.embedder import Embedder
            self.embedder = Embedder()
        
        # Build a temporary mock chunk to feed to Embedder
        dummy_chunk = DocumentChunk(
            content=query,
            metadata=ChunkMetadata(
                chunk_id="temp_query",
                document_id="temp_query",
                page_number=1,
                chunk_type="text",
                word_count=len(query.split()),
                token_estimate=len(query.split())
            )
        )
        
        embeddings = self.embedder.generate_embeddings([dummy_chunk])
        if not embeddings:
            raise ValueError("Failed to generate query embedding.")
            
        return embeddings[0]

