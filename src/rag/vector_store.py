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

    def __init__(self, db_dir: Optional[Path] = None, collection_prefix: str = "doc_") -> None:
        if db_dir is None:
            from src.config import ROOT_DIR
            db_dir = ROOT_DIR / "data" / "chromadb"
        self.db_dir = Path(db_dir)
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
            if getattr(meta, "image_path", None):
                flat_metadata["image_path"] = str(meta.image_path)
            if getattr(meta, "image_url", None):
                flat_metadata["image_url"] = str(meta.image_url)
            if getattr(meta, "image_type", None):
                flat_metadata["image_type"] = str(meta.image_type)
            if getattr(meta, "caption", None):
                flat_metadata["caption"] = str(meta.caption)
            if getattr(meta, "ocr_text", None):
                flat_metadata["ocr_text"] = str(meta.ocr_text)
            if getattr(meta, "semantic_description", None):
                flat_metadata["semantic_description"] = str(meta.semantic_description)
            for img_list in ["objects", "detected_entities"]:
                val = getattr(meta, img_list, [])
                if val:
                    flat_metadata[img_list] = json.dumps(val)

            # Document-grounded image metadata (entity association, layout
            # grounding, and retrieval gating) -- required so a chunk loaded
            # straight from ChromaDB (bypassing document_chunks.json) still
            # carries the same portrait/signature/logo association and
            # retrievability signals as the primary load path.
            if getattr(meta, "title", None):
                flat_metadata["title"] = str(meta.title)
            if getattr(meta, "subtitle", None):
                flat_metadata["subtitle"] = str(meta.subtitle)
            if getattr(meta, "explicit_caption", None):
                flat_metadata["explicit_caption"] = str(meta.explicit_caption)
            if getattr(meta, "caption_text", None):
                flat_metadata["caption_text"] = str(meta.caption_text)
            if getattr(meta, "entity_name", None):
                flat_metadata["entity_name"] = str(meta.entity_name)
            if getattr(meta, "designation", None):
                flat_metadata["designation"] = str(meta.designation)
            if getattr(meta, "section_heading", None):
                flat_metadata["section_heading"] = str(meta.section_heading)
            if getattr(meta, "text_before", None):
                flat_metadata["text_before"] = str(meta.text_before)
            if getattr(meta, "text_after", None):
                flat_metadata["text_after"] = str(meta.text_after)
            if getattr(meta, "nearby_text", None):
                flat_metadata["nearby_text"] = str(meta.nearby_text)
            if getattr(meta, "entity_id", None):
                flat_metadata["entity_id"] = str(meta.entity_id)
            if getattr(meta, "entity_ids", None):
                flat_metadata["entity_ids"] = json.dumps(meta.entity_ids)
            if getattr(meta, "linked_text_chunk_ids", None):
                flat_metadata["linked_text_chunk_ids"] = json.dumps(meta.linked_text_chunk_ids)
            if getattr(meta, "layout_context", None):
                flat_metadata["layout_context"] = str(meta.layout_context)
            if getattr(meta, "importance_score", None):
                flat_metadata["importance_score"] = str(meta.importance_score)
            if getattr(meta, "retrievable", None) is not None:
                flat_metadata["retrievable"] = bool(meta.retrievable)
            if getattr(meta, "association_method", None):
                flat_metadata["association_method"] = str(meta.association_method)
            if getattr(meta, "association_confidence", None) is not None:
                flat_metadata["association_confidence"] = float(meta.association_confidence)
            if getattr(meta, "confidence", None) is not None:
                flat_metadata["confidence"] = float(meta.confidence)

            if meta.bounding_boxes:
                bboxes_data = []
                for b in meta.bounding_boxes:
                    if hasattr(b, "model_dump"):
                        bboxes_data.append(b.model_dump())
                    elif hasattr(b, "dict"):
                        bboxes_data.append(b.dict())
                    elif isinstance(b, dict):
                        bboxes_data.append(b)
                flat_metadata["bounding_boxes"] = json.dumps(bboxes_data)

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

    def delete_chunks(self, document_id: str, chunk_ids: List[str]) -> int:
        """
        Removes specific chunk records (e.g. orphaned image chunks left behind
        by deduplication) from the document's collection by chunk_id.
        Returns the number of ids actually requested for deletion (0 if the
        collection does not exist or the id list is empty).
        """
        if not chunk_ids:
            return 0

        collection_name = self._get_collection_name(document_id)
        if collection_name in self._collections:
            collection = self._collections[collection_name]
        else:
            try:
                collection = self.client.get_collection(name=collection_name)
                self._collections[collection_name] = collection
            except Exception:
                return 0

        try:
            collection.delete(ids=chunk_ids)
            logger.info(f"Deleted {len(chunk_ids)} orphaned chunk record(s) from ChromaDB collection: {collection_name}")
            return len(chunk_ids)
        except Exception as e:
            logger.warning(f"Failed to delete chunk records from ChromaDB collection {collection_name}: {e}")
            return 0

    def update_chunk_metadata(self, document_id: str, updates: Dict[str, Dict[str, Any]]) -> int:
        """
        Merges the given per-field updates (e.g. entity_id/linked_text_chunk_ids
        computed by a post-indexing pass such as entity_linker) into the
        EXISTING metadata of each already-indexed chunk, by chunk_id. Does not
        touch embeddings/documents -- metadata-only, so it never requires a
        re-embed. Returns the number of chunk records actually updated.
        """
        if not updates:
            return 0

        collection_name = self._get_collection_name(document_id)
        if collection_name in self._collections:
            collection = self._collections[collection_name]
        else:
            try:
                collection = self.client.get_collection(name=collection_name)
                self._collections[collection_name] = collection
            except Exception:
                return 0

        chunk_ids = list(updates.keys())
        try:
            existing = collection.get(ids=chunk_ids)
        except Exception as e:
            logger.warning(f"Failed to fetch existing metadata for update in {collection_name}: {e}")
            return 0

        existing_ids = existing.get("ids", []) or []
        existing_metadatas = existing.get("metadatas", []) or []
        if not existing_ids:
            return 0

        merged_ids = []
        merged_metadatas = []
        for chunk_id, meta in zip(existing_ids, existing_metadatas):
            field_updates = updates.get(chunk_id)
            if not field_updates:
                continue
            merged = dict(meta or {})
            merged.update(field_updates)
            merged_ids.append(chunk_id)
            merged_metadatas.append(merged)

        if not merged_ids:
            return 0

        try:
            collection.update(ids=merged_ids, metadatas=merged_metadatas)
            logger.info(f"Updated metadata for {len(merged_ids)} chunk record(s) in ChromaDB collection: {collection_name}")
            return len(merged_ids)
        except Exception as e:
            logger.warning(f"Failed to update chunk metadata in ChromaDB collection {collection_name}: {e}")
            return 0
