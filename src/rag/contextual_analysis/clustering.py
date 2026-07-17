import logging
from typing import List, Dict, Tuple, Any

logger = logging.getLogger("pipeline")

class LouvainClusterer:
    """
    Runs Louvain modularity optimization over the similarity graph to partition
    Knowledge Objects into coarse groups.
    """

    def __init__(self, nodes: List[str], edges: List[Tuple[str, str, float]]):
        self.nodes = nodes
        self.edges = edges

    def get_clusters(self) -> List[List[str]]:
        # Build adjacency list with weights
        adj = {node: {} for node in self.nodes}
        k = {node: 0.0 for node in self.nodes}
        m = 0.0
        
        for u, v, w in self.edges:
            if u in adj and v in adj:
                adj[u][v] = w
                adj[v][u] = w
                k[u] += w
                k[v] += w
                m += w

        if m == 0:
            # If no edges, group isolated nodes individually
            return [[node] for node in self.nodes]

        communities = {node: node for node in self.nodes}
        c_tot = {node: k[node] for node in self.nodes}
        
        improved = True
        iterations = 0
        while improved and iterations < 15:
            improved = False
            iterations += 1
            for u in self.nodes:
                current_comm = communities[u]
                best_comm = current_comm
                best_gain = 0.0
                
                # Links from u to neighbor communities
                comm_links = {}
                for v, w in adj[u].items():
                    comm_v = communities[v]
                    comm_links[comm_v] = comm_links.get(comm_v, 0.0) + w
                
                k_u = k[u]
                
                # Remove u from current community temporarily
                c_tot[current_comm] -= k_u
                
                for comm, k_u_in in comm_links.items():
                    # Modularity gain formula
                    gain = k_u_in / m - (c_tot[comm] * k_u) / (2.0 * m * m)
                    if gain > best_gain:
                        best_gain = gain
                        best_comm = comm
                
                # Insert u into best community
                communities[u] = best_comm
                c_tot[best_comm] += k_u
                
                if best_comm != current_comm:
                    improved = True

        # Group nodes
        groups = {}
        for node, comm in communities.items():
            if comm not in groups:
                groups[comm] = []
            groups[comm].append(node)
            
        cluster_list = list(groups.values())
        
        # Build community node lookup
        node_to_comm = {}
        for c_idx, comm in enumerate(cluster_list):
            for node in comm:
                node_to_comm[node] = c_idx
                
        # Find connection strength between communities
        comm_adj = {i: {} for i in range(len(cluster_list))}
        for u, v, w in self.edges:
            if u in node_to_comm and v in node_to_comm:
                c1 = node_to_comm[u]
                c2 = node_to_comm[v]
                if c1 != c2:
                    comm_adj[c1][c2] = comm_adj[c1].get(c2, 0.0) + w
                    comm_adj[c2][c1] = comm_adj[c2].get(c1, 0.0) + w

        # Merge clusters with high connectivity or very small size
        merged_clusters = {i: set(cluster_list[i]) for i in range(len(cluster_list))}
        
        # Scan small clusters and merge them
        for i, nodes_set in list(merged_clusters.items()):
            if len(nodes_set) < 4:
                # Find neighbor community with highest cumulative weight
                best_neighbor = None
                best_w = 0.0
                for neighbor, weight in comm_adj[i].items():
                    if neighbor in merged_clusters and neighbor != i:
                        if weight > best_w:
                            best_w = weight
                            best_neighbor = neighbor
                            
                # If a strong neighbor is found, merge
                if best_neighbor is not None and best_w > 0.5:
                    merged_clusters[best_neighbor].update(nodes_set)
                    merged_clusters.pop(i)
                    # Update adjacency mapping for merged community
                    for k, v_w in comm_adj[i].items():
                        if k != best_neighbor:
                            comm_adj[best_neighbor][k] = comm_adj[best_neighbor].get(k, 0.0) + v_w
                            
        return [list(s) for s in merged_clusters.values()]
