import logging
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional, Set
import json
from src.rag.config import RagConfig
from src.rag.vector_store import VectorStore

logger = logging.getLogger("pipeline")

class SemanticRetrievalAgent:
    """
    Retrieves semantically related Knowledge Objects using the existing ChromaDB collection
    and builds a weighted similarity graph.
    """

    def __init__(self, config: Optional[RagConfig] = None):
        self.config = config or RagConfig()
        self.vector_store = VectorStore(
            db_dir=self.config.chroma_db_dir,
            collection_prefix=self.config.collection_prefix
        )
        self.similarity_floor = getattr(self.config, "similarity_floor", 0.72)
        self.top_k = getattr(self.config, "retrieval_top_k", 10)

    def retrieve_similar_pairs(self, doc_id: str) -> Tuple[List[str], List[Tuple[str, str, float]], Dict[str, List[Tuple[str, float]]]]:
        """
        Queries ChromaDB for all chunk embeddings, finds top-k neighbors, applies floor,
        caches/reuses similarity graph outputs to avoid query roundtrips, and returns:
          - nodes: List of node IDs
          - edges: Deduplicated list of (id1, id2, similarity)
          - neighbor_lists: Dict of query_id -> list of (neighbor_id, similarity)
        """
        # Caching check
        from src.config import ROOT_DIR
        output_dir = ROOT_DIR / "data" / "output" / doc_id
        graph_cache = output_dir / "08_retrieval" / "similarity_graph.json"
        
        if graph_cache.exists():
            logger.info("Similarity graph cache hit! Loading cached pairs.")
            try:
                with open(graph_cache, "r", encoding="utf-8") as f:
                    cached_data = json.load(f)
                return (
                    cached_data["nodes"],
                    [tuple(e) for e in cached_data["edges"]],
                    {k: [tuple(nb) for nb in v] for k, v in cached_data["neighbor_lists"].items()}
                )
            except Exception as e:
                logger.error(f"Failed to read similarity graph cache: {e}")

        collection_name = self.vector_store._get_collection_name(doc_id)
        try:
            collection = self.vector_store.client.get_collection(name=collection_name)
        except Exception as e:
            logger.warning(f"ChromaDB collection {collection_name} not found: {e}")
            return [], [], {}

        # 1. Fetch all elements with their embeddings
        data = collection.get(include=["embeddings", "metadatas", "documents"])
        ids = data.get("ids", [])
        embeddings = data.get("embeddings", [])
        if not ids or embeddings is None or len(embeddings) == 0:
            logger.warning(f"ChromaDB collection {collection_name} is empty.")
            return [], [], {}

        # 2. Query in batch
        # We query for top_k + 1 results to account for self-match
        n_results = min(self.top_k + 1, len(ids))
        results = collection.query(
            query_embeddings=embeddings,
            n_results=n_results,
            include=["distances"]
        )

        nodes = ids
        edges_set = set()
        edges = []
        neighbor_lists = {}

        for i, query_id in enumerate(ids):
            neighbor_ids = results["ids"][i]
            distances = results["distances"][i]
            
            nb_list = []
            for neighbor_id, dist in zip(neighbor_ids, distances):
                if neighbor_id == query_id:
                    continue
                # Cosine distance is in [0, 2], similarity is 1.0 - distance
                similarity = 1.0 - dist
                if similarity >= self.similarity_floor:
                    nb_list.append((neighbor_id, similarity))
                    
                    # Deduplicate undirected edges
                    edge_key = tuple(sorted([query_id, neighbor_id]))
                    if edge_key not in edges_set:
                        edges_set.add(edge_key)
                        edges.append((edge_key[0], edge_key[1], similarity))
            
            # Sort neighbors by similarity descending
            nb_list.sort(key=lambda x: x[1], reverse=True)
            neighbor_lists[query_id] = nb_list

        # Sort all edges by similarity descending
        edges.sort(key=lambda x: x[2], reverse=True)

        # Write to cache
        if output_dir.exists():
            try:
                retrieval_dir = output_dir / "08_retrieval"
                retrieval_dir.mkdir(parents=True, exist_ok=True)
                with open(graph_cache, "w", encoding="utf-8") as f:
                    json.dump({
                        "nodes": nodes,
                        "edges": edges,
                        "neighbor_lists": neighbor_lists
                    }, f, indent=2)
                logger.info(f"Saved similarity graph cache to {graph_cache}")
            except Exception as e:
                logger.error(f"Failed to save similarity graph cache: {e}")

        return nodes, edges, neighbor_lists
