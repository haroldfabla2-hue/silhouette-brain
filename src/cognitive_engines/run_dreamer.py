import os
#!/usr/bin/env python3
"""
Dreamer Algorithm - Memory Consolidation During "Sleep"
Based on Watts-Strogatz small-world network formation

This simulates the memory consolidation process that happens during sleep:
1. Memory Activation: Reactivate recent memories
2. Association Formation: Create new connections between related memories
3. Synaptic Pruning: Remove weak connections
4. Shortcut Creation: Create long-range bridges for efficient recall
5. Memory Transfer: Move important episodic memories to semantic (permanent) storage
"""
import random
import time
import json
from datetime import datetime, timedelta
from collections import defaultdict

class Dreamer:
    """
    Implements memory consolidation during simulated sleep cycles.
    Based on:
    - Hebbian learning: "Neurons that fire together, wire together"
    - Synaptic pruning: Remove unused connections
    - Watts-Strogatz: Create shortcuts for efficient memory retrieval
    """
    
    def __init__(self):
        self.associations = defaultdict(lambda: defaultdict(float))
        self.dream_log = []
        
    def load_dream_state(self):
        """Load previous dream state"""
        try:
            with open(os.getenv('BRAIN_DATA_DIR', './data'/dream_state.json', 'r') as f:
                data = json.load(f)
                self.associations = defaultdict(lambda: defaultdict(float), 
                    {k: defaultdict(float, v) for k, v in data.get('associations', {}).items()})
                self.dream_log = data.get('dream_log', [])
        except:
            pass
    
    def save_dream_state(self):
        """Save dream state"""
        data = {
            'associations': dict(self.associations),
            'dream_log': self.dream_log[-100:]  # Keep last 100 dreams
        }
        with open(os.getenv('BRAIN_DATA_DIR', './data'/dream_state.json', 'w') as f:
            json.dump(data, f)
    
    def activate_memories(self, memory_core):
        """Reactivate recent memories (like during REM sleep)"""
        from memory_core import get_memory_core
        core = memory_core or get_memory_core()
        
        # Get recent conversations (last 24 hours)
        recent = core.get_recent_context(hours=24, limit=50)
        
        activated = []
        for mem in recent:
            # Simulate memory activation
            activated.append({
                'id': mem.get('id'),
                'message': mem.get('message', '')[:100],
                'activation_strength': random.uniform(0.5, 1.0)
            })
        
        return activated
    
    def form_associations(self, memories):
        """Form new associations between activated memories (Hebbian learning)"""
        new_associations = []
        
        # Group by common entities/words
        memory_texts = {m['id']: m.get('message', '').lower() for m in memories}
        
        for i, mem1 in enumerate(memories):
            for mem2 in memories[i+1:]:
                # Check for common words/entities
                text1 = memory_texts.get(mem1['id'], '')
                text2 = memory_texts.get(mem2['id'], '')
                
                common_words = set(text1.split()) & set(text2.split())
                
                if len(common_words) > 2:
                    # Form association based on commonality
                    strength = min(1.0, len(common_words) / 10)
                    
                    # Hebbian: strengthen existing or create new
                    key = tuple(sorted([mem1['id'], mem2['id']]))
                    current = self.associations[key[0]][key[1]]
                    self.associations[key[0]][key[1]] = min(1.0, current + strength * 0.2)
                    
                    new_associations.append({
                        'from': mem1['id'][:20],
                        'to': mem2['id'][:20],
                        'strength': strength,
                        'common_words': list(common_words)[:5]
                    })
        
        return new_associations
    
    def synaptic_pruning(self):
        """Remove weak associations (synaptic pruning)"""
        pruned = []
        
        for node1 in list(self.associations.keys()):
            for node2 in list(self.associations[node1].keys()):
                strength = self.associations[node1][node2]
                
                # Prune weak connections
                if strength < 0.1:
                    del self.associations[node1][node2]
                    pruned.append(f"{node1[:10]}->{node2[:10]}")
        
        # Clean up empty dicts
        self.associations = {k: v for k, v in self.associations.items() if v}
        
        return pruned
    
    def create_shortcuts(self, memory_core):
        """Create long-range shortcuts for efficient recall (Watts-Strogatz)"""
        from memory_core import get_memory_core
        core = memory_core or get_memory_core()
        
        shortcuts = []
        
        # Get high-frequency entities (hubs)
        entities = core.get_entities()
        hubs = sorted(entities, key=lambda x: x.get('mention_count', 0), reverse=True)[:20]
        
        # Get low-frequency entities (periphery)
        periphery = [e for e in entities if e.get('mention_count', 0) < 3]
        
        # Create shortcuts from periphery to hubs
        for entity in periphery[:10]:
            if hubs:
                hub = random.choice(hubs[:5])  # Connect to top hub
                key = tuple(sorted([entity['name'], hub['name']]))
                
                # Create weak shortcut (0.2-0.4 strength)
                strength = random.uniform(0.2, 0.4)
                
                # Ensure keys exist
                if key[0] not in self.associations:
                    self.associations[key[0]] = defaultdict(float)
                if key[1] not in self.associations:
                    self.associations[key[1]] = defaultdict(float)
                    
                self.associations[key[0]][key[1]] = strength
                
                shortcuts.append({
                    'from': entity['name'],
                    'to': hub['name'],
                    'type': 'shortcut',
                    'strength': strength
                })
        
        return shortcuts
    
    def consolidate_to_permanent(self, memory_core):
        """Move important episodic memories to semantic (permanent) storage"""
        from memory_core import get_memory_core
        core = memory_core or get_memory_core()
        
        # Get high-importance memories (frequently accessed)
        recent = core.get_recent_context(hours=72, limit=100)
        
        consolidated = []
        
        # Find entities with high mention counts that should be permanent
        entities = core.get_entities()
        important = [e for e in entities if e.get('mention_count', 0) >= 5]
        
        # Store in Neo4j as semantic memory
        try:
            from neo4j import GraphDatabase
            driver = GraphDatabase.driver('bolt://localhost:17687', 
                                        auth=('neo4j', 'silhouette2035'))
            
            with driver.session() as session:
                for entity in important[:20]:
                    # Check if already exists
                    result = session.run(
                        "MERGE (n:Semantic {name: $name}) "
                        "SET n.lastConsolidated = timestamp(), "
                        "n.consolidationCount = coalesce(n.consolidationCount, 0) + 1",
                        name=entity['name']
                    )
                    
                    # Create relationships to other semantic memories
                    for other in important[:10]:
                        if other['name'] != entity['name']:
                            session.run(
                                "MATCH (a:Semantic {name: $a}), (b:Semantic {name: $b}) "
                                "MERGE (a)-[:ASSOCIATED]->(b)",
                                a=entity['name'], b=other['name']
                            )
                    
                    consolidated.append(entity['name'])
            
            driver.close()
        except Exception as e:
            print(f"Neo4j consolidation error: {e}")
        
        return consolidated
    
    def dream_cycle(self):
        """Complete dream consolidation cycle"""
        print("[DREAMER] 🌙 Starting dream cycle...")
        
        self.load_dream_state()
        
        # Step 1: Activate memories
        print("[DREAMER] 📖 Activating recent memories...")
        memories = self.activate_memories(None)
        print(f"[DREAMER]   Activated {len(memories)} memories")
        
        # Step 2: Form associations (Hebbian learning)
        print("[DREAMER] 🔗 Forming associations...")
        associations = self.form_associations(memories)
        print(f"[DREAMER]   Created {len(associations)} new associations")
        
        # Step 3: Synaptic pruning
        print("[DREAMER] ✂️ Synaptic pruning...")
        pruned = self.synaptic_pruning()
        print(f"[DREAMER]   Pruned {len(pruned)} weak connections")
        
        # Step 4: Create shortcuts
        print("[DREAMER] ➡️ Creating shortcuts...")
        shortcuts = self.create_shortcuts(None)
        print(f"[DREAMER]   Created {len(shortcuts)} shortcuts")
        
        # Step 5: Consolidate to permanent
        print("[DREAMER] 💾 Consolidating to permanent storage...")
        consolidated = self.consolidate_to_permanent(None)
        print(f"[DREAMER]   Consolidated {len(consolidated)} entities")
        
        # Save state
        self.save_dream_state()
        
        # Log dream
        self.dream_log.append({
            'timestamp': datetime.now().isoformat(),
            'memories_activated': len(memories),
            'associations_formed': len(associations),
            'pruned': len(pruned),
            'shortcuts_created': len(shortcuts),
            'consolidated': len(consolidated)
        })
        
        return {
            'status': 'completed',
            'memories_activated': len(memories),
            'associations': len(associations),
            'pruned': len(pruned),
            'shortcuts': len(shortcuts),
            'consolidated': len(consolidated)
        }


if __name__ == "__main__":
    print("=== DREAMER - Memory Consolidation ===")
    dreamer = Dreamer()
    result = dreamer.dream_cycle()
    print(f"\n✅ Dream cycle complete: {result}")
