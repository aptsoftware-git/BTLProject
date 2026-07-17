import re
import logging
from typing import List, Set, Optional
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

class QueryProcessor:
    """
    Handles preprocessing of natural language queries and query embedding generation.
    """

    def __init__(self, embedder: Embedder) -> None:
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

    def generate_query_embedding(self, query: str) -> List[float]:
        """
        Generates a vector embedding of the query for semantic search.
        """
        logger.info("Generating query embedding...")
        
        # Build a temporary mock chunk to feed to Embedder
        # We need to wrap it since Embedder expects a list of DocumentChunks
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
