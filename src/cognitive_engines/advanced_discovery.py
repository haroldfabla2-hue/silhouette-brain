import os
#!/usr/bin/env python3
"""
Advanced Memory Discovery System
Based on Small-World Network Theory (Watts & Strogatz)
[COGNITIVE_AUDIT] Silhouette OS - Memory Discovery Active

This implements:
1. Small-World Discovery: Find short paths between distant concepts
2. Weak Tie Discovery: Find unexpected connections
3. Novelty Detection: Find unexplored areas
4. Memory Association: Strengthen connections like synapses
"""
import math
import random
import time
from collections import defaultdict
from typing import List, Dict, Set, Tuple, Optional
import json

class SmallWorldDiscovery:
    """
    Implements Watts-Strogatz small-world network concepts for memory discovery.
    
    Key concepts:
    - Clustering: How connected neighbors are
    - Path length: Shortest distance between nodes
    - Weak ties: Bridges between distant clusters
    """
    
    def __init__(self, memory_system):
        self.memory = memory_system
        self.graph = {}  # node_id -> {neighbor_id: weight}
        self.access_counts = defaultdict(int)
        
    def build_graph_from_memory(self):
        """Build network graph from stored memories"""
        # Get all memories from memory core
        from memory_core import get_memory_core
        core = get_memory_core()
        
        # Get entities and their connections
        entities = core.get_entities()
        
        # Build graph
        for entity in entities:
            node_id = entity['name']
            self.graph[node_id] = {}
            
            # Find related entities via common messages
            related = core.search_context(node_id)
            for rel in related[:10]:
                # Extract entities from related messages
                for other_entity in entities:
                    if other_entity['name'] != node_id:
                        if other_entity['name'].lower() in rel['message'].lower():
                            # Add edge with weight based on similarity
                            if other_entity['name'] not in self.graph[node_id]:
                                self.graph[node_id][other_entity['name']] = 0
                            self.graph[node_id][other_entity['name']] += rel['similarity']
        
        return self.graph
    
    def calculate_clustering_coefficient(self, node: str) -> float:
        """Calculate local clustering coefficient for a node"""
        if node not in self.graph:
            return 0.0
            
        neighbors = set(self.graph[node].keys())
        k = len(neighbors)
        
        if k < 2:
            return 0.0
        
        # Count edges between neighbors
        triangles = 0
        for n1 in neighbors:
            if n1 in self.graph:
                for n2 in neighbors:
                    if n2 in self.graph and n1 != n2:
                        if n2 in self.graph[n1]:
                            triangles += 1
        
        # Clustering coefficient
        max_triangles = k * (k - 1) / 2
        return triangles / max_triangles if max_triangles > 0 else 0.0
    
    def find_shortest_path(self, start: str, end: str) -> Optional[List[str]]:
        """BFS to find shortest path between two nodes"""
        if start not in self.graph:
            return None
            
        visited = {start}
        queue = [(start, [start])]
        
        while queue:
            current, path = queue.pop(0)
            
            if current == end:
                return path
                
            if current not in self.graph:
                continue
                
            for neighbor in self.graph[current].keys():
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, path + [neighbor]))
        
        return None
    
    def find_weak_ties(self, node: str, threshold: float = 0.3) -> List[Dict]:
        """
        Find weak ties - connections to nodes outside your cluster.
        These are valuable for discovering new information.
        """
        if node not in self.graph:
            return []
            
        neighbors = self.graph[node]
        
        # Get clustering of neighbors
        weak_ties = []
        for neighbor, weight in neighbors.items():
            # Low weight = weak tie = potential bridge to other clusters
            if weight < threshold:
                neighbor_clustering = self.calculate_clustering_coefficient(neighbor)
                weak_ties.append({
                    'node': neighbor,
                    'weight': weight,
                    'clustering': neighbor_clustering,
                    'discovery_potential': 1.0 - weight  # Higher potential for lower weight
                })
        
        # Sort by discovery potential
        weak_ties.sort(key=lambda x: x['discovery_potential'], reverse=True)
        return weak_ties[:5]
    
    def discover_bridges(self) -> List[Dict]:
        """Find bridges - nodes that connect different clusters"""
        bridges = []
        
        for node in self.graph.keys():
            if len(self.graph[node]) < 2:
                continue
                
            clustering = self.calculate_clustering_coefficient(node)
            
            # Low clustering + many connections = potential bridge
            if clustering < 0.3 and len(self.graph[node]) > 3:
                bridges.append({
                    'node': node,
                    'clustering': clustering,
                    'connections': len(self.graph[node])
                })
        
        return sorted(bridges, key=lambda x: x['connections'], reverse=True)[:10]


class CuriosityDiscovery:
    """
    Active knowledge discovery based on:
    - Information entropy
    - Novelty detection
    - Gap analysis
    """
    
    def __init__(self, memory_system):
        self.memory = memory_system
        self.exploration_history = []
        
    def calculate_entropy(self, entity_name: str) -> float:
        """Calculate entropy (uncertainty) about an entity"""
        from memory_core import get_memory_core
        core = get_memory_core()
        
        # Get all mentions
        mentions = core.search_context(entity_name)
        
        if not mentions:
            return 1.0  # Maximum entropy = completely unknown
        
        # Calculate diversity of contexts
        contexts = [m['message'] for m in mentions]
        
        if len(contexts) < 2:
            return 0.5  # Some information
        
        # Simple entropy: variety of contexts
        unique_words = set()
        for ctx in contexts:
            unique_words.update(ctx.lower().split())
        
        # More unique words = higher entropy = more to discover
        return min(1.0, len(unique_words) / (len(contexts) * 10))
    
    def find_information_gaps(self) -> List[Dict]:
        """Find topics with high potential for discovery"""
        from memory_core import get_memory_core
        core = get_memory_core()
        
        entities = core.get_entities()
        
        gaps = []
        for entity in entities:
            if entity['mention_count'] < 3:  # Low coverage
                entropy = self.calculate_entropy(entity['name'])
                gaps.append({
                    'entity': entity['name'],
                    'type': entity['type'],
                    'mentions': entity['mention_count'],
                    'entropy': entropy,
                    'discovery_potential': entropy * (1.0 / (entity['mention_count'] + 1))
                })
        
        # Sort by discovery potential
        gaps.sort(key=lambda x: x['discovery_potential'], reverse=True)
        return gaps[:10]
    
    def suggest_exploration(self) -> List[Dict]:
        """Suggest topics to explore based on gaps and weak ties"""
        gaps = self.find_information_gaps()
        
        suggestions = []
        for gap in gaps[:5]:
            suggestions.append({
                'topic': gap['entity'],
                'type': 'information_gap',
                'reason': f"Only {gap['mentions']} mentions, {gap['entropy']:.2f} entropy",
                'action': f"Explore more about {gap['entity']}"
            })
        
        return suggestions


class MemoryAssociation:
    """
    Brain-like synapse system:
    - Strengthen connections through access
    - Form new associations
    - Prune weak connections
    """
    
    def __init__(self):
        self.associations = defaultdict(lambda: defaultdict(float))
        self.load_associations()
    
    def load_associations(self):
        """Load associations from storage"""
        try:
            with open(os.getenv('BRAIN_DATA_DIR', './data'/associations.json', 'r') as f:
                self.associations = defaultdict(lambda: defaultdict(float), json.load(f))
        except:
            pass
    
    def save_associations(self):
        """Save associations to storage"""
        with open(os.getenv('BRAIN_DATA_DIR', './data'/associations.json', 'w') as f:
            json.dump(dict(self.associations), f)
    
    def strengthen(self, entity1: str, entity2: str, amount: float = 0.1):
        """Strengthen association between two entities"""
        self.associations[entity1][entity2] += amount
        self.associations[entity2][entity1] += amount
        self.save_associations()
    
    def get_associations(self, entity: str) -> List[Tuple[str, float]]:
        """Get all associations for an entity, sorted by strength"""
        if entity not in self.associations:
            return []
        
        assocs = [(e, w) for e, w in self.associations[entity].items()]
        return sorted(assocs, key=lambda x: x[1], reverse=True)
    
    def find_novel_connections(self, entities: List[str]) -> List[Dict]:
        """Find unexpected connections between entities"""
        novel = []
        
        for i, e1 in enumerate(entities):
            for e2 in entities[i+1:]:
                strength = self.associations[e1].get(e2, 0)
                
                # Low strength but both exist = novel connection
                if 0 < strength < 0.3:
                    # Calculate combined potential
                    potential = (0.3 - strength) * 2
                    novel.append({
                        'from': e1,
                        'to': e2,
                        'strength': strength,
                        'potential': potential,
                        'suggestion': f"Explore connection between {e1} and {e2}"
                    })
        
        return sorted(novel, key=lambda x: x['potential'], reverse=True)[:10]


class AdvancedMemoryDiscovery:
    """Complete discovery system combining all algorithms"""
    
    def __init__(self):
        self.small_world = None
        self.curiosity = None
        self.association = MemoryAssociation()
    
    def run_discovery(self) -> Dict:
        """Run complete discovery cycle"""
        results = {
            'timestamp': time.time(),
            'discoveries': []
        }
        
        # 1. Build small world graph
        from silhouette_memory import SilhouetteMemory
        memory = SilhouetteMemory()
        self.small_world = SmallWorldDiscovery(memory)
        graph = self.small_world.build_graph_from_memory()
        
        results['discoveries'].append({
            'type': 'graph_built',
            'nodes': len(graph)
        })
        
        # 2. Find weak ties
        if graph:
            # Pick a random node to analyze
            node = random.choice(list(graph.keys()))
            weak_ties = self.small_world.find_weak_ties(node)
            
            results['discoveries'].append({
                'type': 'weak_ties',
                'node': node,
                'ties': weak_ties
            })
            
            # 3. Find bridges (FIXED: method name was wrong)
            bridges = self.small_world.discover_bridges()
            results['discoveries'].append({
                'type': 'bridges',
                'bridges': bridges[:5]
            })
        
        # 4. Curiosity exploration
        self.curiosity = CuriosityDiscovery(memory)
        suggestions = self.curiosity.suggest_exploration()
        results['discoveries'].append({
            'type': 'exploration_suggestions',
            'suggestions': suggestions
        })
        
        # 5. Novel connections
        from memory_core import get_memory_core
        core = get_memory_core()
        entities = core.get_entities()
        entity_names = [e['name'] for e in entities[:20]]
        
        novel = self.association.find_novel_connections(entity_names)
        results['discoveries'].append({
            'type': 'novel_connections',
            'connections': novel
        })
        
        return results


# CLI
if __name__ == "__main__":
    import sys
    
    amd = AdvancedMemoryDiscovery()
    
    if len(sys.argv) < 2:
        print("""
╔═══════════════════════════════════════════╗
║   ADVANCED MEMORY DISCOVERY            ║
║   Small-World + Curiosity + Association  ║
╚═══════════════════════════════════════════╝

Commands:
  discover      - Run full discovery cycle
  weak_ties    - Find weak ties for random node
  bridges      - Find bridging nodes
  curiosity   - Information gap analysis
  associations - Novel connections
        """)
    else:
        cmd = sys.argv[1]
        
        if cmd == "discover":
            results = amd.run_discovery()
            print(json.dumps(results, indent=2))
        
        elif cmd == "weak_ties":
            from silhouette_memory import SilhouetteMemory
            sw = SmallWorldDiscovery(SilhouetteMemory())
            sw.build_graph_from_memory()
            if sw.graph:
                node = random.choice(list(sw.graph.keys()))
                ties = sw.find_weak_ties(node)
                print(f"Weak ties for '{node}':")
                for t in ties:
                    print(f"  - {t}")
        
        elif cmd == "curiosity":
            from silhouette_memory import SilhouetteMemory
            cd = CuriosityDiscovery(SilhouetteMemory())
            gaps = cd.find_information_gaps()
            print("Information gaps:")
            for g in gaps:
                print(f"  - {g['entity']}: {g['discovery_potential']:.2f}")
