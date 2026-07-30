import json
import logging
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from collections import Counter

from src.rag.config import RagConfig
from src.rag.contextual_analysis.semantic_retrieval_agent import SemanticRetrievalAgent
from src.rag.contextual_analysis.clustering import LouvainClusterer

logger = logging.getLogger("pipeline")

class AmbiguityPipeline:
    """
    Orchestration pipeline for ambiguity chunk analysis.
    Phase 1: Semantically retrieves chunks, performs Louvain clustering,
    and writes visual/machine-readable debug reports to 09_semantic_clusters/.
    """

    def __init__(self, config: Optional[RagConfig] = None):
        self.config = config or RagConfig()
        self.retrieval_agent = SemanticRetrievalAgent(self.config)

    def _generate_topic_label(self, chunks: List[dict]) -> str:
        """Deterministic topic generator using keywords, headings, and entities."""
        keywords = []
        entities = []
        headings = []
        for chunk in chunks:
            meta = chunk.get("metadata", {})
            keywords.extend(meta.get("keywords", []))
            entities.extend(meta.get("people", []) + meta.get("organizations", []))
            h = meta.get("heading")
            if h:
                headings.append(h)
        
        # Exclude generic keywords
        stop_kws = {"document", "section", "content", "root", "page", "image", "table", "figure"}
        kw_counter = Counter([k.lower() for k in keywords if len(k) > 2 and k.lower() not in stop_kws])
        ent_counter = Counter(entities)
        hd_counter = Counter(headings)
        
        topic_parts = []
        if hd_counter:
            topic_parts.append(hd_counter.most_common(1)[0][0])
        if kw_counter:
            top_kws = [k[0].title() for k in kw_counter.most_common(2)]
            topic_parts.extend(top_kws)
        if ent_counter:
            topic_parts.append(ent_counter.most_common(1)[0][0])
            
        if not topic_parts:
            return "General Content"
            
        # Deduplicate
        seen = set()
        unique_parts = []
        for part in topic_parts:
            if part.lower() not in seen:
                seen.add(part.lower())
                unique_parts.append(part)
        return " & ".join(unique_parts[:3])

    def run_clustering(self, job_dir: Path, doc_id: str, force_regenerate: bool = False) -> Dict[str, Any]:
        logger.info(f"Running Ambiguity Pipeline (Phase 1 Clustering) for job: {doc_id}")
        
        # Cache hit check
        cache_clusters_path = job_dir / "09_semantic_clusters" / "semantic_clusters.json"
        if not force_regenerate and cache_clusters_path.exists() and cache_clusters_path.stat().st_size > 0:
            logger.info(f"[CACHE HIT] Semantic clusters already exist for job {doc_id}. Skipping re-clustering.")
            try:
                with open(cache_clusters_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to read cached semantic clusters: {e}. Re-running...")

        # 1. Load document chunks for full text/metadata mapping
        chunks_json_path = job_dir / "06_chunks" / "document_chunks.json"
        if not chunks_json_path.exists():
            chunks_json_path = job_dir / "document_chunks.json"
            
        chunks_by_id = {}
        file_name = "unknown"
        if chunks_json_path.exists():
            try:
                with open(chunks_json_path, "r", encoding="utf-8") as f:
                    chunks_data = json.load(f)
                    file_name = chunks_data.get("file_name", "unknown")
                    for c in chunks_data.get("chunks", []):
                        meta = c.get("metadata", {})
                        cid = meta.get("chunk_id")
                        if cid:
                            chunks_by_id[cid] = c
            except Exception as e:
                logger.error(f"Failed to load document chunks for ambiguity pipeline: {e}")

        # 2. Retrieve similarity graph from ChromaDB
        nodes, edges, neighbor_lists = self.retrieval_agent.retrieve_similar_pairs(doc_id)
        
        # 3. Perform Louvain Clustering
        if not nodes:
            logger.warning("Empty similarity graph. Falling back to section-based groups.")
            sections = {}
            for cid, c in chunks_by_id.items():
                sec = c.get("metadata", {}).get("section") or "Root"
                sections.setdefault(sec, []).append(cid)
            clusters = [oids for oids in sections.values() if len(oids) >= 2]
            nodes = list(chunks_by_id.keys())
        else:
            clusterer = LouvainClusterer(nodes, edges)
            clusters = clusterer.get_clusters()

        # 4. Partition clusters into semantic clusters (size >= 2) and isolated chunks
        semantic_clusters_raw = [c for c in clusters if len(c) >= 2]
        all_clustered_nodes = set()
        for c in semantic_clusters_raw:
            all_clustered_nodes.update(c)
        isolated_chunks = [node for node in nodes if node not in all_clustered_nodes]
        
        # Sort semantic clusters by size descending
        semantic_clusters_raw.sort(key=lambda x: len(x), reverse=True)
        
        # Build pairwise similarity matrix dictionary
        similarity_matrix = {n: {} for n in nodes}
        for u, v, w in edges:
            if u in similarity_matrix and v in similarity_matrix:
                similarity_matrix[u][v] = round(w, 4)
                similarity_matrix[v][u] = round(w, 4)
        
        # 5. Build structured clusters list
        clusters_output = []
        for idx, oids in enumerate(semantic_clusters_raw, start=1):
            cluster_chunks = []
            cluster_node_set = set(oids)
            
            # Find edges within the cluster to calculate average similarity
            cluster_edges = [w for u, v, w in edges if u in cluster_node_set and v in cluster_node_set]
            avg_sim = sum(cluster_edges) / max(1, len(cluster_edges)) if cluster_edges else 0.72
            
            for oid in oids:
                c = chunks_by_id.get(oid, {})
                meta = c.get("metadata", {})
                hierarchy = meta.get("hierarchy_path", [])
                heading_path = " -> ".join(hierarchy) if hierarchy else (meta.get("heading") or "Root")
                
                # Chunk similarity within cluster
                chunk_sims = [similarity_matrix[oid][other] for other in oids if other != oid and other in similarity_matrix[oid]]
                chunk_sim_score = sum(chunk_sims) / max(1, len(chunk_sims)) if chunk_sims else avg_sim
                
                cluster_chunks.append({
                    "chunk_id": oid,
                    "page": meta.get("page_number", 1),
                    "heading_path": heading_path,
                    "chunk_type": meta.get("chunk_type", "text"),
                    "text": c.get("content", ""),
                    "metadata": meta,
                    "similarity": round(chunk_sim_score, 4)
                })
                
            topic = self._generate_topic_label(cluster_chunks)
            
            clusters_output.append({
                "cluster_id": f"cluster_{idx:03d}",
                "cluster_size": len(oids),
                "topic_summary": topic,
                "average_similarity": round(avg_sim, 4),
                "chunk_ids": oids,
                "chunks": cluster_chunks
            })

        # Calculate statistics
        total_chunks = len(nodes)
        total_clusters = len(semantic_clusters_raw)
        largest_cluster = max([len(c) for c in semantic_clusters_raw]) if semantic_clusters_raw else 0
        smallest_cluster = min([len(c) for c in semantic_clusters_raw]) if semantic_clusters_raw else 0
        avg_cluster_size = sum([len(c) for c in semantic_clusters_raw]) / max(1, total_clusters)
        
        total_edges = len(edges)
        avg_similarity = sum(e[2] for e in edges) / max(1, total_edges) if edges else 0.0
        
        pages_set = {c.get("metadata", {}).get("page_number", 1) for c in chunks_by_id.values()}
        total_pages = len(pages_set) if pages_set else 1
        
        total_headings = len([c for c in chunks_by_id.values() if c.get("metadata", {}).get("chunk_type") == "heading"])
        total_tables = len([c for c in chunks_by_id.values() if c.get("metadata", {}).get("chunk_type") == "table"])
        total_images = len([c for c in chunks_by_id.values() if c.get("metadata", {}).get("chunk_type") == "image"])
        
        total_neighbors = sum(len(nb) for nb in neighbor_lists.values()) if neighbor_lists else 0
        avg_neighbors = total_neighbors / max(1, total_chunks)

        # 6. Write output files to data/output/{job_id}/09_semantic_clusters/
        output_folder = job_dir / "09_semantic_clusters"
        output_folder.mkdir(parents=True, exist_ok=True)
        
        # Output 1: semantic_clusters.json
        with open(output_folder / "semantic_clusters.json", "w", encoding="utf-8") as f:
            json.dump(clusters_output, f, indent=2, ensure_ascii=False)
            
        # Output 2: similarity_graph.json
        with open(output_folder / "similarity_graph.json", "w", encoding="utf-8") as f:
            json.dump({
                "nodes": nodes,
                "edges": edges
            }, f, indent=2, ensure_ascii=False)
            
        # Output 3: retrieval_statistics.json
        stats_output = {
            "total_chunks": total_chunks,
            "total_clusters": total_clusters,
            "average_cluster_size": round(avg_cluster_size, 2),
            "largest_cluster": largest_cluster,
            "smallest_cluster": smallest_cluster,
            "isolated_chunks": len(isolated_chunks),
            "average_neighbors": round(avg_neighbors, 2),
            "similarity_threshold": self.retrieval_agent.similarity_floor,
            "retrieval_top_k": self.retrieval_agent.top_k,
            "total_similarity_edges": total_edges,
            "average_similarity": round(avg_similarity, 4),
            "total_pages": total_pages,
            "total_headings": total_headings,
            "total_tables": total_tables,
            "total_images": total_images
        }
        with open(output_folder / "retrieval_statistics.json", "w", encoding="utf-8") as f:
            json.dump(stats_output, f, indent=2)

        # Output 4: semantic_clusters.md
        md_lines = [
            f"# Semantic Topic Clusters Report\n",
            f"**File**: `{file_name}`  \n",
            f"**Document Job ID**: `{doc_id}`\n\n",
            f"---"
        ]
        for idx, cluster in enumerate(clusters_output, start=1):
            md_lines.append(f"\n# Cluster {idx}\n")
            md_lines.append(f"**Topic**: {cluster['topic_summary']}  ")
            
            pages = sorted(list(set(c["page"] for c in cluster["chunks"])))
            pages_str = ", ".join(map(str, pages)) if len(pages) > 1 else str(pages[0])
            md_lines.append(f"**Pages**: {pages_str}  ")
            md_lines.append(f"**Chunks**: {cluster['cluster_size']}  ")
            md_lines.append(f"**Average Similarity**: {cluster['average_similarity']:.2f}  ")
            
            keywords_all = []
            entities_all = []
            for chunk in cluster["chunks"]:
                keywords_all.extend(chunk["metadata"].get("keywords", []))
                entities_all.extend(chunk["metadata"].get("people", []) + chunk["metadata"].get("organizations", []))
            
            common_kws = [k[0] for k in Counter(keywords_all).most_common(5)]
            common_ents = [e[0] for e in Counter(entities_all).most_common(4)]
            
            md_lines.append(f"**Common Keywords**: {', '.join(common_kws) if common_kws else 'None'}  ")
            md_lines.append(f"**Entities**: {', '.join(common_ents) if common_ents else 'None'}  ")
            md_lines.append(f"**Summary**: This cluster groups all `{cluster['topic_summary']}` related semantic chunks.  ")
            md_lines.append(f"\n### Chunks\n")
            
            for c_idx, chunk in enumerate(cluster["chunks"], start=1):
                md_lines.append(f"#### Chunk {chunk['chunk_id']}")
                md_lines.append(f"* **Heading**: {chunk['heading_path']}")
                md_lines.append(f"* **Similarity**: {chunk['similarity']:.2f}")
                
                preview = chunk['text'].strip().replace("\n", " ")
                preview_short = preview[:150] + "..." if len(preview) > 150 else preview
                md_lines.append(f"* **Preview**: {preview_short}\n")
            md_lines.append(f"---")
            
        md_lines.append(f"\n# Summary Statistics\n")
        md_lines.append(f"- **Total Chunks**: {total_chunks}")
        md_lines.append(f"- **Total Clusters**: {total_clusters}")
        md_lines.append(f"- **Average Cluster Size**: {avg_cluster_size:.2f}")
        md_lines.append(f"- **Largest Cluster**: {largest_cluster}")
        md_lines.append(f"- **Smallest Cluster**: {smallest_cluster}")
        md_lines.append(f"- **Isolated Chunks**: {len(isolated_chunks)}")
        
        with open(output_folder / "semantic_clusters.md", "w", encoding="utf-8") as f:
            f.write("\n".join(md_lines))

        # Output 5: cluster_summary.md (Executive overview with table)
        summary_lines = [
            f"# Semantic Cluster Summary\n",
            f"## Document Statistics",
            f"- Total Semantic Chunks: {total_chunks}",
            f"- Total Clusters: {total_clusters}",
            f"- Average Cluster Size: {avg_cluster_size:.2f}",
            f"- Largest Cluster: {largest_cluster} chunks",
            f"- Smallest Cluster: {smallest_cluster} chunks",
            f"- Isolated Chunks: {len(isolated_chunks)}\n",
            f"## Cluster Overview\n",
            f"| Cluster | Topic (deterministic) | Size | Pages |",
            f"|:---------|:-----------------------|:-----:|:------|"
        ]
        for idx, cluster in enumerate(clusters_output, start=1):
            pages = sorted(list(set(c["page"] for c in cluster["chunks"])))
            if len(pages) == 1:
                pages_str = f"Page {pages[0]}"
            else:
                pages_str = f"Pages {pages[0]}–{pages[-1]}"
            summary_lines.append(f"| {idx} | {cluster['topic_summary']} | {cluster['cluster_size']} | {pages_str} |")
            
        with open(output_folder / "cluster_summary.md", "w", encoding="utf-8") as f:
            f.write("\n".join(summary_lines))

        # Output 6: cluster_inspector.html using standard string and replacement mapping
        html_template = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Semantic Cluster Inspector</title>
  <!-- Load D3.js -->
  <script src="https://cdnjs.cloudflare.com/ajax/libs/d3/7.8.5/d3.min.js"></script>
  <style>
    :root {
      --primary: #4f46e5;
      --primary-light: #e0e7ff;
      --bg: #f8fafc;
      --card-bg: #ffffff;
      --text: #1e293b;
      --text-muted: #64748b;
      --border: #e2e8f0;
      --shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1);
    }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
      background: var(--bg);
      margin: 0;
      padding: 0;
      display: flex;
      height: 100vh;
      color: var(--text);
      overflow: hidden;
    }
    .sidebar {
      width: 260px;
      background: var(--card-bg);
      border-right: 1px solid var(--border);
      display: flex;
      flex-direction: column;
      height: 100%;
      box-sizing: border-box;
      box-shadow: 2px 0 8px rgba(0,0,0,0.02);
    }
    .sidebar-header {
      padding: 24px 20px;
      border-bottom: 1px solid var(--border);
      text-align: center;
    }
    .sidebar-header h2 {
      margin: 0;
      font-size: 16px;
      font-weight: 700;
      color: var(--primary);
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }
    .nav-list {
      flex: 1;
      padding: 15px 10px;
      overflow-y: auto;
      list-style: none;
      margin: 0;
    }
    .nav-item {
      padding: 12px 16px;
      border-radius: 8px;
      cursor: pointer;
      margin-bottom: 6px;
      font-size: 14px;
      font-weight: 500;
      color: var(--text-muted);
      transition: all 0.2s;
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .nav-item:hover {
      background: #f1f5f9;
      color: var(--text);
    }
    .nav-item.active {
      background: var(--primary-light);
      color: var(--primary);
      font-weight: 600;
    }
    .main-content {
      flex: 1;
      display: flex;
      flex-direction: column;
      height: 100%;
      overflow: hidden;
    }
    .content-tab {
      display: none;
      flex-direction: column;
      height: 100%;
      box-sizing: border-box;
      overflow-y: auto;
      padding: 30px;
    }
    .content-tab.active {
      display: flex;
    }
    
    /* Overview Tab */
    .dashboard-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
      gap: 20px;
      margin-bottom: 30px;
    }
    .stat-card {
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 20px;
      box-shadow: var(--shadow);
      display: flex;
      flex-direction: column;
    }
    .stat-title {
      font-size: 13px;
      font-weight: 600;
      color: var(--text-muted);
      margin-bottom: 8px;
      text-transform: uppercase;
      letter-spacing: 0.02em;
    }
    .stat-value {
      font-size: 28px;
      font-weight: 800;
      color: var(--primary);
    }
    
    /* Explorer Tab */
    .explorer-container {
      display: flex;
      gap: 20px;
      height: 100%;
      overflow: hidden;
    }
    .explorer-list {
      width: 320px;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: var(--card-bg);
      overflow-y: auto;
      padding: 10px;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .explorer-item {
      padding: 12px;
      border-radius: 6px;
      border: 1px solid var(--border);
      cursor: pointer;
      transition: all 0.2s;
    }
    .explorer-item:hover {
      background: #f8fafc;
    }
    .explorer-item.active {
      border-color: var(--primary);
      background: #f5f3ff;
    }
    .explorer-detail {
      flex: 1;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: var(--card-bg);
      overflow-y: auto;
      padding: 25px;
      display: flex;
      flex-direction: column;
      gap: 20px;
    }
    
    /* Matrix View */
    .matrix-table-container {
      overflow: auto;
      max-height: 80vh;
      border: 1px solid var(--border);
      border-radius: 8px;
    }
    .matrix-table {
      border-collapse: collapse;
      font-size: 12px;
      width: 100%;
      background: #fff;
    }
    .matrix-table th, .matrix-table td {
      border: 1px solid var(--border);
      padding: 8px 12px;
      text-align: center;
    }
    .matrix-table th {
      background: #f1f5f9;
      position: sticky;
      top: 0;
      z-index: 10;
    }
    .matrix-cell-intensity {
      color: #fff;
      font-weight: bold;
    }
    
    /* Graph View */
    .network-svg-container {
      flex: 1;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: #ffffff;
      position: relative;
      overflow: hidden;
      min-height: 500px;
    }
    .node {
      stroke: #fff;
      stroke-width: 1.5px;
      cursor: pointer;
    }
    .link {
      stroke: #94a3b8;
      stroke-opacity: 0.6;
    }
    .tooltip {
      position: absolute;
      background: rgba(15, 23, 42, 0.9);
      color: #fff;
      padding: 8px 12px;
      border-radius: 6px;
      font-size: 12px;
      pointer-events: none;
      display: none;
      z-index: 20;
      box-shadow: 0 4px 10px rgba(0,0,0,0.15);
    }
    
    /* Search & Filter Controls */
    .controls-panel {
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 20px;
      margin-bottom: 25px;
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
      gap: 15px;
    }
    .control-group {
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .control-group label {
      font-size: 12px;
      font-weight: 600;
      color: var(--text-muted);
    }
    .control-input {
      padding: 8px 12px;
      border: 1px solid var(--border);
      border-radius: 6px;
      font-size: 13px;
      outline: none;
    }
    
    /* General classes */
    .badge {
      padding: 2px 8px;
      border-radius: 4px;
      font-size: 11px;
      font-weight: bold;
      color: #fff;
      text-transform: uppercase;
      display: inline-block;
    }
    .badge-type-text { background: #10b981; }
    .badge-type-heading { background: #3b82f6; }
    .badge-type-table { background: #06b6d4; }
    .badge-type-image { background: #8b5cf6; }
    .badge-type-list { background: #f59e0b; }
    
    .chunk-card {
      background: #fafafa;
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 15px;
      margin-bottom: 15px;
    }
    .chunk-text {
      font-family: monospace;
      font-size: 12.5px;
      background: #ffffff;
      padding: 10px;
      border: 1px solid var(--border);
      border-radius: 6px;
      white-space: pre-wrap;
      overflow-x: auto;
    }
    .meta-toggle {
      background: none;
      border: none;
      color: var(--primary);
      text-decoration: underline;
      font-size: 12px;
      cursor: pointer;
      padding: 0;
      margin-top: 6px;
    }
    .meta-block {
      display: none;
      font-family: monospace;
      font-size: 11px;
      background: #f1f5f9;
      padding: 8px;
      border-radius: 4px;
      white-space: pre-wrap;
      margin-top: 5px;
      border: 1px solid var(--border);
    }
  </style>
</head>
<body>
  <div class="sidebar">
    <div class="sidebar-header">
      <h2>Cluster Inspector</h2>
    </div>
    <ul class="nav-list">
      <li class="nav-item active" onclick="switchTab('tab-overview')">🏠 Overview Dashboard</li>
      <li class="nav-item" onclick="switchTab('tab-explorer')">📂 Cluster Explorer</li>
      <li class="nav-item" onclick="switchTab('tab-network')">🕸️ Similarity Network</li>
      <li class="nav-item" onclick="switchTab('tab-matrix')">📊 Similarity Matrix</li>
      <li class="nav-item" onclick="switchTab('tab-retrieval')">🔍 Retrieval Inspector</li>
      <li class="nav-item" onclick="switchTab('tab-topics')">🏷️ Cluster Topics</li>
      <li class="nav-item" onclick="switchTab('tab-search-filter')">🔎 Search & Filters</li>
    </ul>
  </div>
  
  <div class="main-content">
    
    <!-- 1. Overview Dashboard -->
    <div id="tab-overview" class="content-tab active">
      <h1 style="margin-top:0;">Semantic Summary Dashboard</h1>
      <div class="dashboard-grid">
        <div class="stat-card">
          <span class="stat-title">Total Chunks</span>
          <span class="stat-value" id="stat-total-chunks">0</span>
        </div>
        <div class="stat-card">
          <span class="stat-title">Total Clusters</span>
          <span class="stat-value" id="stat-total-clusters">0</span>
        </div>
        <div class="stat-card">
          <span class="stat-title">Avg Cluster Size</span>
          <span class="stat-value" id="stat-avg-size">0</span>
        </div>
        <div class="stat-card">
          <span class="stat-title">Largest Cluster</span>
          <span class="stat-value" id="stat-largest">0</span>
        </div>
        <div class="stat-card">
          <span class="stat-title">Smallest Cluster</span>
          <span class="stat-value" id="stat-smallest">0</span>
        </div>
        <div class="stat-card">
          <span class="stat-title">Similarity Threshold</span>
          <span class="stat-value" id="stat-threshold">0</span>
        </div>
        <div class="stat-card">
          <span class="stat-title">Total Similarity Edges</span>
          <span class="stat-value" id="stat-edges">0</span>
        </div>
        <div class="stat-card">
          <span class="stat-title">Isolated Chunks</span>
          <span class="stat-value" id="stat-isolated">0</span>
        </div>
      </div>
      
      <h2>Document Layout Breakdown</h2>
      <div class="dashboard-grid">
        <div class="stat-card">
          <span class="stat-title">Total Pages</span>
          <span class="stat-value" id="stat-pages">0</span>
        </div>
        <div class="stat-card">
          <span class="stat-title">Total Headings</span>
          <span class="stat-value" id="stat-headings">0</span>
        </div>
        <div class="stat-card">
          <span class="stat-title">Total Tables</span>
          <span class="stat-value" id="stat-tables">0</span>
        </div>
        <div class="stat-card">
          <span class="stat-title">Total Images</span>
          <span class="stat-value" id="stat-images">0</span>
        </div>
      </div>
    </div>
    
    <!-- 2. Cluster Explorer -->
    <div id="tab-explorer" class="content-tab">
      <h1 style="margin-top:0;">Cluster Explorer</h1>
      <div class="explorer-container">
        <div class="explorer-list" id="explorer-list-div"></div>
        <div class="explorer-detail" id="explorer-detail-div">
          <div class="no-selection" style="margin:auto; color:var(--text-muted);">Select a cluster on the left to explore</div>
        </div>
      </div>
    </div>
    
    <!-- 3. Similarity Network -->
    <div id="tab-network" class="content-tab">
      <h1 style="margin-top:0;">Similarity Network Graph</h1>
      <div class="network-svg-container" id="network-container">
        <svg id="network-svg" width="100%" height="100%"></svg>
        <div class="tooltip" id="graph-tooltip"></div>
      </div>
    </div>
    
    <!-- 4. Similarity Matrix -->
    <div id="tab-matrix" class="content-tab">
      <h1 style="margin-top:0;">Similarity Matrix</h1>
      <div class="controls-panel" style="grid-template-columns: 1fr 1fr; margin-bottom:15px;">
        <div class="control-group">
          <label>Matrix Filter (Similarity Threshold)</label>
          <input type="range" class="control-input" id="matrix-thresh" min="0.5" max="1.0" step="0.02" value="0.72" oninput="renderMatrix()"/>
          <span id="matrix-thresh-val" style="font-size:12px;">0.72</span>
        </div>
      </div>
      <div class="matrix-table-container">
        <table class="matrix-table" id="matrix-table-element"></table>
      </div>
    </div>
    
    <!-- 5. Retrieval Inspector -->
    <div id="tab-retrieval" class="content-tab">
      <h1 style="margin-top:0;">Retrieval Inspector</h1>
      <div class="controls-panel" style="grid-template-columns: 1fr; margin-bottom:15px;">
        <div class="control-group">
          <label>Select Pivot Chunk to Inspect</label>
          <select id="retrieval-pivot-select" class="control-input" onchange="renderRetrievalInspector()"></select>
        </div>
      </div>
      <div id="retrieval-inspector-results"></div>
    </div>
    
    <!-- 6. Cluster Topics -->
    <div id="tab-topics" class="content-tab">
      <h1 style="margin-top:0;">Deterministic Cluster Topic Labels</h1>
      <div id="topics-list-container" style="background:#fff; border:1px solid var(--border); border-radius:8px; padding:20px;"></div>
    </div>
    
    <!-- 7. Advanced Search & Filtering -->
    <div id="tab-search-filter" class="content-tab">
      <h1 style="margin-top:0;">Search & Filtering</h1>
      <div class="controls-panel">
        <div class="control-group">
          <label>Query Search (text, id, keyword, heading)</label>
          <input type="text" class="control-input" id="sf-query" placeholder="Type here..." oninput="applySearchFilters()"/>
        </div>
        <div class="control-group">
          <label>Filter by Chunk Type</label>
          <select class="control-input" id="sf-type" onchange="applySearchFilters()">
            <option value="all">All Types</option>
            <option value="text">Text</option>
            <option value="heading">Heading</option>
            <option value="table">Table</option>
            <option value="image">Image</option>
            <option value="list">List</option>
          </select>
        </div>
        <div class="control-group">
          <label>Min Cluster Size</label>
          <input type="number" class="control-input" id="sf-minsize" value="2" min="1" oninput="applySearchFilters()"/>
        </div>
      </div>
      <div id="sf-results" style="display:flex; flex-direction:column; gap:15px;"></div>
    </div>
    
  </div>

  <script>
    // Injected Data
    var clusters = /* INJECT_CLUSTERS */;
    var stats = /* INJECT_STATS */;
    var graph = /* INJECT_GRAPH */;
    var matrixData = /* INJECT_MATRIX */;
    var neighborLists = /* INJECT_NEIGHBORS */;
    var chunksById = {};
    
    // Index chunks by ID
    clusters.forEach(function(c) {
      c.chunks.forEach(function(ch) {
        chunksById[ch.chunk_id] = ch;
      });
    });
    
    // Switch tabs helper
    window.switchTab = function(tabId) {
      var tabs = document.getElementsByClassName("content-tab");
      for (var i = 0; i < tabs.length; i++) {
        tabs[i].classList.remove("active");
      }
      var navItems = document.getElementsByClassName("nav-item");
      for (var i = 0; i < navItems.length; i++) {
        navItems[i].classList.remove("active");
      }
      document.getElementById(tabId).classList.add("active");
      
      // Highlight active nav item
      var targetIdx = 0;
      if (tabId === "tab-overview") targetIdx = 0;
      else if (tabId === "tab-explorer") targetIdx = 1;
      else if (tabId === "tab-network") { targetIdx = 2; renderNetwork(); }
      else if (tabId === "tab-matrix") { targetIdx = 3; renderMatrix(); }
      else if (tabId === "tab-retrieval") { targetIdx = 4; renderRetrievalInspector(); }
      else if (tabId === "tab-topics") targetIdx = 5;
      else if (tabId === "tab-search-filter") targetIdx = 6;
      navItems[targetIdx].classList.add("active");
    };

    // 1. Render Dashboard
    document.getElementById("stat-total-chunks").innerText = stats.total_chunks;
    document.getElementById("stat-total-clusters").innerText = stats.total_clusters;
    document.getElementById("stat-avg-size").innerText = stats.average_cluster_size;
    document.getElementById("stat-largest").innerText = stats.largest_cluster;
    document.getElementById("stat-smallest").innerText = stats.smallest_cluster;
    document.getElementById("stat-threshold").innerText = stats.similarity_threshold;
    document.getElementById("stat-edges").innerText = stats.total_similarity_edges;
    document.getElementById("stat-isolated").innerText = stats.isolated_chunks;
    document.getElementById("stat-pages").innerText = stats.total_pages;
    document.getElementById("stat-headings").innerText = stats.total_headings;
    document.getElementById("stat-tables").innerText = stats.total_tables;
    document.getElementById("stat-images").innerText = stats.total_images;

    // 2. Render Explorer
    var explorerList = document.getElementById("explorer-list-div");
    explorerList.innerHTML = "";
    clusters.forEach(function(cluster, idx) {
      var item = document.createElement("div");
      item.className = "explorer-item";
      item.onclick = function() { selectExplorerCluster(idx); };
      item.innerHTML = `
        <div style="font-weight:bold; color:var(--primary);">${cluster.cluster_id.toUpperCase()}</div>
        <div style="font-size:12px; color:var(--text-muted); font-weight:600;">${cluster.topic_summary}</div>
        <div style="font-size:11px; margin-top:4px;">Size: ${cluster.cluster_size} | Page range: ${cluster.chunks[0].page} - ${cluster.chunks[cluster.chunks.length-1].page}</div>
      `;
      explorerList.appendChild(item);
    });
    
    function selectExplorerCluster(idx) {
      var items = document.getElementsByClassName("explorer-item");
      for (var i = 0; i < items.length; i++) {
        items[i].classList.remove("active");
      }
      items[idx].classList.add("active");
      
      var cluster = clusters[idx];
      var detailDiv = document.getElementById("explorer-detail-div");
      
      var chunksHtml = "";
      cluster.chunks.forEach(function(ch, cIdx) {
        var typeClass = "badge-type-" + ch.chunk_type.toLowerCase();
        chunksHtml += `
          <div class="chunk-card">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
              <span style="font-weight:bold; font-family:monospace;">${ch.chunk_id}</span>
              <div>
                <span class="badge ${typeClass}">${ch.chunk_type}</span>
                <span class="badge" style="background:#64748b;">PAGE ${ch.page}</span>
              </div>
            </div>
            <div style="font-size:12px; color:var(--text-muted); margin-bottom:8px;"><strong>Heading Path:</strong> ${ch.heading_path}</div>
            <div class="chunk-text">${escapeHtml(ch.text)}</div>
            <button class="meta-toggle" onclick="toggleMeta('${ch.chunk_id}')">Toggle Metadata Dictionary</button>
            <pre class="meta-block" id="meta-${ch.chunk_id}">${escapeHtml(JSON.stringify(ch.metadata, null, 2))}</pre>
          </div>
        `;
      });
      
      detailDiv.innerHTML = `
        <h2 style="margin:0; color:var(--primary);">${cluster.cluster_id.toUpperCase()} - ${cluster.topic_summary}</h2>
        <div style="display:grid; grid-template-columns: 1fr 1fr; gap:15px; font-size:13px; background:#f8fafc; padding:15px; border-radius:6px; border:1px solid var(--border);">
          <div><strong>Size:</strong> ${cluster.cluster_size} chunks</div>
          <div><strong>Average Cluster Similarity:</strong> ${cluster.average_similarity}</div>
          <div><strong>Keywords:</strong> ${cluster.chunks[0].metadata.keywords ? cluster.chunks[0].metadata.keywords.slice(0,5).join(', ') : 'None'}</div>
          <div><strong>Involved Pages:</strong> ${Array.from(new Set(cluster.chunks.map(c => c.page))).join(', ')}</div>
        </div>
        <div>
          <h3>Member Chunks</h3>
          ${chunksHtml}
        </div>
      `;
    }
    
    window.toggleMeta = function(chunkId) {
      var block = document.getElementById("meta-" + chunkId);
      block.style.display = (block.style.display === "block") ? "none" : "block";
    };

    function escapeHtml(text) {
      return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
    }

    // 3. Render Similarity D3 Network
    var networkRendered = false;
    function renderNetwork() {
      if (networkRendered) return;
      networkRendered = true;
      
      var width = document.getElementById("network-container").clientWidth;
      var height = document.getElementById("network-container").clientHeight || 550;
      
      var svg = d3.select("#network-svg")
        .attr("width", width)
        .attr("height", height);
      
      // Color scheme for communities
      var color = d3.scaleOrdinal(d3.schemeCategory10);
      
      // Build lookup for nodes
      var nodeCommunity = {};
      clusters.forEach(function(cluster, cIdx) {
        cluster.chunk_ids.forEach(function(nid) {
          nodeCommunity[nid] = cIdx;
        });
      });
      
      var nodesData = graph.nodes.map(function(nid) {
        return { id: nid, group: nodeCommunity[nid] !== undefined ? nodeCommunity[nid] : -1 };
      });
      
      var linksData = graph.edges.map(function(e) {
        return { source: e[0], target: e[1], value: e[2] };
      });
      
      var simulation = d3.forceSimulation(nodesData)
        .force("link", d3.forceLink(linksData).id(d => d.id).distance(100))
        .force("charge", d3.forceManyBody().strength(-150))
        .force("center", d3.forceCenter(width / 2, height / 2));
      
      var container = svg.append("g");
      
      // Zoom and pan
      svg.call(d3.zoom().on("zoom", function(event) {
        container.attr("transform", event.transform);
      }));
      
      var link = container.append("g")
        .selectAll("line")
        .data(linksData)
        .enter().append("line")
        .attr("class", "link")
        .attr("stroke-width", d => Math.max(1, (d.value - 0.7) * 10));
      
      var tooltip = d3.select("#graph-tooltip");
      
      var node = container.append("g")
        .selectAll("circle")
        .data(nodesData)
        .enter().append("circle")
        .attr("class", "node")
        .attr("r", 10)
        .attr("fill", d => d.group === -1 ? "#94a3b8" : color(d.group))
        .on("mouseover", function(event, d) {
          tooltip.style("display", "block")
            .html(`<strong>ID:</strong> ${d.id}<br/><strong>Cluster Group:</strong> ${d.group === -1 ? 'Isolated' : 'Cluster ' + (d.group + 1)}`)
            .style("left", (event.pageX - 280) + "px")
            .style("top", (event.pageY - 120) + "px");
        })
        .on("mouseout", function() {
          tooltip.style("display", "none");
        })
        .on("click", function(event, d) {
          // Switch to explorer tab and highlight
          var clusterIdx = d.group;
          if (clusterIdx !== -1) {
            switchTab("tab-explorer");
            selectExplorerCluster(clusterIdx);
          }
        });
      
      simulation.on("tick", () => {
        link
          .attr("x1", d => d.source.x)
          .attr("y1", d => d.source.y)
          .attr("x2", d => d.target.x)
          .attr("y2", d => d.target.y);
        
        node
          .attr("cx", d => d.x)
          .attr("cy", d => d.y);
      });
    }

    // 4. Render Similarity Matrix
    window.renderMatrix = function() {
      var threshold = parseFloat(document.getElementById("matrix-thresh").value);
      document.getElementById("matrix-thresh-val").innerText = threshold;
      
      var table = document.getElementById("matrix-table-element");
      table.innerHTML = "";
      
      // Header row
      var headerRow = document.createElement("tr");
      headerRow.appendChild(document.createElement("th")); // empty top-left cell
      graph.nodes.forEach(function(nid) {
        var th = document.createElement("th");
        th.innerText = nid.split("_").pop(); // short ID representation
        th.title = nid;
        headerRow.appendChild(th);
      });
      table.appendChild(headerRow);
      
      // Rows
      graph.nodes.forEach(function(rowId) {
        var row = document.createElement("tr");
        var th = document.createElement("th");
        th.innerText = rowId.split("_").pop();
        th.title = rowId;
        row.appendChild(th);
        
        graph.nodes.forEach(function(colId) {
          var td = document.createElement("td");
          if (rowId === colId) {
            td.innerText = "1.00";
            td.style.backgroundColor = "rgba(79, 70, 229, 0.9)";
            td.style.color = "#fff";
          } else {
            var score = (matrixData[rowId] && matrixData[rowId][colId]) ? matrixData[rowId][colId] : 0.0;
            if (score >= threshold) {
              td.innerText = score.toFixed(2);
              var alpha = (score - 0.7) / 0.3; // scale color intensity
              td.style.backgroundColor = `rgba(79, 70, 229, ${alpha})`;
              td.style.color = alpha > 0.5 ? "#fff" : "#1e293b";
            } else {
              td.innerText = "-";
              td.style.color = "#e2e8f0";
            }
          }
          row.appendChild(td);
        });
        table.appendChild(row);
      });
    }

    // 5. Render Retrieval Inspector
    var pivotSelect = document.getElementById("retrieval-pivot-select");
    pivotSelect.innerHTML = "";
    graph.nodes.forEach(function(nid) {
      var opt = document.createElement("option");
      opt.value = nid;
      opt.innerText = nid;
      pivotSelect.appendChild(opt);
    });
    
    window.renderRetrievalInspector = function() {
      var pivotId = pivotSelect.value;
      var resultsDiv = document.getElementById("retrieval-inspector-results");
      
      if (!pivotId) return;
      
      var neighbors = neighborLists[pivotId] || [];
      var pivotChunk = chunksById[pivotId] || { text: "N/A", metadata: {} };
      
      var neighborsHtml = "";
      neighbors.forEach(function(nb) {
        var nbId = nb[0];
        var sim = nb[1];
        var nbChunk = chunksById[nbId] || { text: "N/A", metadata: {} };
        
        // Find shared characteristics
        var pMeta = pivotChunk.metadata || {};
        var nMeta = nbChunk.metadata || {};
        
        var sharedKws = (pMeta.keywords || []).filter(k => (nMeta.keywords || []).includes(k));
        var sharedEnts = (pMeta.people || []).filter(e => (nMeta.people || []).includes(e))
          .concat((pMeta.organizations || []).filter(o => (nMeta.organizations || []).includes(o)));
        
        var sharedHeading = pMeta.heading === nMeta.heading && pMeta.heading ? pMeta.heading : "None";
        var sharedSection = pMeta.section === nMeta.section && pMeta.section ? pMeta.section : "None";
        
        neighborsHtml += `
          <div style="background:#fff; border:1px solid var(--border); border-radius:8px; padding:18px; margin-bottom:15px; box-shadow:var(--shadow);">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
              <span style="font-weight:bold; font-family:monospace; color:var(--primary);">${nbId}</span>
              <span class="badge" style="background:var(--primary); font-size:12px;">Similarity: ${sim.toFixed(4)}</span>
            </div>
            <div style="font-size:12.5px; display:grid; grid-template-columns: 1fr 1fr; gap:10px; margin-bottom:10px; background:#f8fafc; padding:10px; border-radius:6px;">
              <div><strong>Shared Keywords:</strong> ${sharedKws.length > 0 ? sharedKws.join(', ') : 'None'}</div>
              <div><strong>Shared Entities:</strong> ${sharedEnts.length > 0 ? sharedEnts.join(', ') : 'None'}</div>
              <div><strong>Shared Heading:</strong> ${sharedHeading}</div>
              <div><strong>Shared Section:</strong> ${sharedSection}</div>
            </div>
            <div class="chunk-text" style="background:#fafafa;">${escapeHtml(nbChunk.text)}</div>
          </div>
        `;
      });
      
      resultsDiv.innerHTML = `
        <div style="background:var(--primary-light); padding:20px; border-radius:8px; border:1px solid var(--primary); margin-bottom:20px;">
          <h3 style="margin-top:0; color:var(--primary);">Pivot Chunk: ${pivotId}</h3>
          <div class="chunk-text">${escapeHtml(pivotChunk.text)}</div>
        </div>
        <h2>Top Nearest Neighbors</h2>
        ${neighborsHtml || '<div style="color:var(--text-muted);">No semantic neighbors found above similarity threshold.</div>'}
      `;
    };

    // 6. Render Cluster Topics List
    var topicsDiv = document.getElementById("topics-list-container");
    topicsDiv.innerHTML = "";
    clusters.forEach(function(cluster, idx) {
      var item = document.createElement("div");
      item.style.padding = "12px";
      item.style.borderBottom = "1px solid var(--border)";
      item.innerHTML = `
        <div style="display:flex; justify-content:space-between; font-size:14px; font-weight:600;">
          <span style="color:var(--primary); font-family:monospace;">${cluster.cluster_id.toUpperCase()}</span>
          <span style="background:var(--primary-light); color:var(--primary); padding:2px 8px; border-radius:4px;">${cluster.topic_summary}</span>
        </div>
        <div style="font-size:12px; color:var(--text-muted); margin-top:4px;">Member Chunk IDs: ${cluster.chunk_ids.join(', ')}</div>
      `;
      topicsDiv.appendChild(item);
    });

    // 7. Search & Filters implementation
    window.applySearchFilters = function() {
      var query = document.getElementById("sf-query").value.toLowerCase();
      var type = document.getElementById("sf-type").value;
      var minSize = parseInt(document.getElementById("sf-minsize").value) || 2;
      
      var resultsDiv = document.getElementById("sf-results");
      resultsDiv.innerHTML = "";
      
      var foundChunks = [];
      clusters.forEach(function(cluster, cIdx) {
        if (cluster.cluster_size < minSize) return;
        
        cluster.chunks.forEach(function(ch) {
          // Apply type filter
          if (type !== "all" && ch.chunk_type.toLowerCase() !== type) return;
          
          // Apply search query filter
          var match = false;
          if (!query) {
            match = true;
          } else {
            var idMatch = ch.chunk_id.toLowerCase().indexOf(query) > -1;
            var textMatch = ch.text.toLowerCase().indexOf(query) > -1;
            var headingMatch = (ch.heading_path || "").toLowerCase().indexOf(query) > -1;
            var keywordsMatch = (ch.metadata.keywords || []).some(k => k.toLowerCase().indexOf(query) > -1);
            var entityMatch = (ch.metadata.people || []).concat(ch.metadata.organizations || []).some(e => e.toLowerCase().indexOf(query) > -1);
            match = idMatch || textMatch || headingMatch || keywordsMatch || entityMatch;
          }
          
          if (match) {
            foundChunks.push({ chunk: ch, clusterId: cluster.cluster_id, topic: cluster.topic_summary });
          }
        });
      });
      
      foundChunks.forEach(function(item) {
        var ch = item.chunk;
        var typeClass = "badge-type-" + ch.chunk_type.toLowerCase();
        
        var card = document.createElement("div");
        card.className = "chunk-card";
        card.innerHTML = `
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
            <span style="font-weight:bold; font-family:monospace;">${ch.chunk_id}</span>
            <div>
              <span class="badge" style="background:var(--primary);">${item.clusterId.toUpperCase()} (${item.topic})</span>
              <span class="badge ${typeClass}">${ch.chunk_type}</span>
              <span class="badge" style="background:#64748b;">PAGE ${ch.page}</span>
            </div>
          </div>
          <div style="font-size:12px; color:var(--text-muted); margin-bottom:8px;"><strong>Heading Path:</strong> ${ch.heading_path}</div>
          <div class="chunk-text">${escapeHtml(ch.text)}</div>
        `;
        resultsDiv.appendChild(card);
      });
      
      if (foundChunks.length === 0) {
        resultsDiv.innerHTML = '<div style="text-align:center; color:var(--text-muted); margin:30px;">No matching semantic chunks found.</div>';
      }
    };
    
    // Default execute
    applySearchFilters();
  </script>
</body>
</html>
"""
        
        # Inject serialized variables into HTML template
        html_content = html_template \
            .replace("/* INJECT_CLUSTERS */", json.dumps(clusters_output, ensure_ascii=False)) \
            .replace("/* INJECT_STATS */", json.dumps(stats_output, ensure_ascii=False)) \
            .replace("/* INJECT_GRAPH */", json.dumps({"nodes": nodes, "edges": edges}, ensure_ascii=False)) \
            .replace("/* INJECT_MATRIX */", json.dumps(similarity_matrix, ensure_ascii=False)) \
            .replace("/* INJECT_NEIGHBORS */", json.dumps(neighbor_lists, ensure_ascii=False))
            
        with open(output_folder / "cluster_inspector.html", "w", encoding="utf-8") as f:
            f.write(html_content)
            
        logger.info(f"Generated Phase 1 Ambiguity Clustering outputs in {output_folder}")
        return stats_output
