import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Set, Optional
import chromadb

from src.rag.chunk_schema import DocumentChunk
from src.rag.utils import convert_bbox

logger = logging.getLogger("pipeline")

class VectorStore:
    """
    Manages collection creation, metadata serialization, and chunk storage in ChromaDB.
    """

    _clients = {}

    def __init__(self, db_dir: Path, collection_prefix: str = "doc_") -> None:
        self.db_dir = db_dir
        self.collection_prefix = collection_prefix
        self._collections = {}
        # Initialize persistent ChromaDB client as singleton per directory path
        db_path_str = str(self.db_dir.resolve())
        if db_path_str not in VectorStore._clients:
            self.db_dir.mkdir(parents=True, exist_ok=True)
            VectorStore._clients[db_path_str] = chromadb.PersistentClient(path=db_path_str)
        self.client = VectorStore._clients[db_path_str]

    def _get_collection_name(self, document_id: str) -> str:
        """
        Formulates a valid collection name based on doc_hash or document_id.
        Reuses ChromaDB collections across jobs matching the same SHA-256 document fingerprint.
        """
        doc_hash = None
        try:
            from backend.services import get_job, DATA_DIR
            job = get_job(document_id)
            if job and "doc_hash" in job:
                doc_hash = job["doc_hash"]
            else:
                meta_file = DATA_DIR / document_id / "metadata.json"
                if meta_file.exists():
                    import json
                    with open(meta_file, "r", encoding="utf-8") as f:
                        meta_data = json.load(f)
                        doc_hash = meta_data.get("doc_hash")
        except Exception:
            pass

        # Candidate names
        clean_doc_id = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in document_id)
        name_doc_id = f"{self.collection_prefix}{clean_doc_id}"[:63]

        if doc_hash:
            clean_hash_id = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in doc_hash[:16])
            name_hash = f"{self.collection_prefix}{clean_hash_id}"[:63]
        else:
            name_hash = None

        # Check existing collections in ChromaDB
        try:
            existing_names = [col.name for col in self.client.list_collections()]
            if name_hash and name_hash in existing_names:
                return name_hash
            if name_doc_id in existing_names:
                return name_doc_id
        except Exception:
            pass

        return name_hash if name_hash else name_doc_id

    def get_existing_chunk_ids(self, document_id: str) -> Set[str]:
        """
        Retrieves the IDs of all chunks currently indexed in the document's collection.
        Returns an empty set if the collection does not exist.
        """
        collection_name = self._get_collection_name(document_id)
        if collection_name in self._collections:
            collection = self._collections[collection_name]
        else:
            try:
                collection = self.client.get_collection(name=collection_name)
                self._collections[collection_name] = collection
            except Exception:
                return set()
        try:
            results = collection.get()
            return set(results.get("ids", []))
        except Exception:
            return set()

    def index_chunks(
        self, 
        document_id: str, 
        chunks: List[DocumentChunk], 
        embeddings: List[List[float]]
    ) -> None:
        """
        Stores chunks and their pre-computed embeddings in a dedicated collection for the document.
        Skips indexing if Chroma collection already contains all vectors.
        """
        if not chunks or not embeddings:
            return

        collection_name = self._get_collection_name(document_id)
        existing_ids = self.get_existing_chunk_ids(document_id)
        
        chunk_ids = {c.metadata.chunk_id for c in chunks}
        if chunk_ids and chunk_ids.issubset(existing_ids):
            logger.info(f"[CACHE HIT] ChromaDB collection '{collection_name}' already contains all {len(chunks)} vectors. Skipping indexing.")
            return

        assert len(chunks) == len(embeddings), "Number of chunks must match number of embeddings."
        
        collection_name = self._get_collection_name(document_id)
        if collection_name in self._collections:
            collection = self._collections[collection_name]
        else:
            logger.info(f"Creating/getting ChromaDB collection: {collection_name}")
            collection = self.client.get_or_create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"}
            )
            self._collections[collection_name] = collection

        ids = []
        documents = []
        metadatas = []

        for chunk, emb in zip(chunks, embeddings):
            meta = chunk.metadata
            
            # Serialize metadata to flat dict of simple types for ChromaDB compatibility
            flat_metadata = {
                "document_id": str(meta.document_id),
                "chunk_id": str(meta.chunk_id),
                "page_number": int(meta.page_number),
                "chunk_type": str(meta.chunk_type),
                "heading": str(meta.heading or ""),
                "section": str(meta.section or ""),
                "word_count": int(meta.word_count),
                "token_estimate": int(meta.token_estimate),
            }

            # Serialize list fields to JSON strings
            flat_metadata["hierarchy_path"] = json.dumps(meta.hierarchy_path)
            flat_metadata["source_element_ids"] = json.dumps(meta.source_element_ids)
            flat_metadata["element_types"] = json.dumps(getattr(meta, "element_types", []))
            flat_metadata["relationships"] = json.dumps(getattr(meta, "relationships", {}))
            
            # Enriched metadata serialization (Phase 6 Optimization)
            if getattr(meta, "report_number", None):
                flat_metadata["report_number"] = str(meta.report_number)
            if getattr(meta, "state", None):
                flat_metadata["state"] = str(meta.state)
            if getattr(meta, "region", None):
                flat_metadata["region"] = str(meta.region)
            if getattr(meta, "district", None):
                flat_metadata["district"] = str(meta.district)
                
            for list_field in ["people", "organizations", "groups", "dates", "weapons", "locations", "keywords"]:
                val = getattr(meta, list_field, [])
                flat_metadata[list_field] = json.dumps(val)

            # Extract image_id or table_id if applicable
            if meta.image_id:
                flat_metadata["image_id"] = str(meta.image_id)
            if meta.table_id:
                flat_metadata["table_id"] = str(meta.table_id)

            ids.append(meta.chunk_id)
            documents.append(chunk.content)
            metadatas.append(flat_metadata)

        # Upsert chunks directly with their pre-generated embeddings
        logger.info(f"Upserting {len(ids)} chunks to ChromaDB collection: {collection_name}")
        collection.upsert(
            ids=ids,
            embeddings=embeddings,
            metadatas=metadatas,
            documents=documents
        )
        logger.info(f"Successfully indexed {len(ids)} chunks in ChromaDB.")
