#!/usr/bin/env python3
"""
Silhouette Memory Agents
Intelligent services for autonomous memory management

Based on Silhouette-OS:
- Dreamer: Exploration during idle
- Curiosity: Active knowledge discovery  
- MemoryIntegration: Auto-search before responding
"""
import time
import threading
import random
from datetime import datetime, timezone
from typing import List, Dict, Optional
import json

class DreamerService:
    """
    Dreamer: Explores memories during idle periods
    Based on Silhouette-OS dreamerService.ts
    
    Triggered when:
    - System is idle
    - Hippocampus is full (50 memories)
    - Manual trigger
    """
    
    def __init__(self, memory_system):
        self.memory = memory_system
        self.is_dreaming = False
        self.last_dream = None
        self.hippocampus: List[Dict] = []
        self.HIPPOCAMPUS_CAPACITY = 50
        
    def add_to_hippocampus(self, node: Dict):
        """Add memory to hippocampus for dreaming"""
        if len(self.hippocampus) >= self.HIPPOCAMPUS_CAPACITY:
            self.attempt_dream()
        
        self.hippocampus.append(node)
        print(f"[DREAMER] Added to hippocampus: {len(self.hippocampus)}/{self.HIPPOCAMPUS_CAPACITY}")
    
    def attempt_dream(self):
        """Attempt to dream - explore connections between memories"""
        if self.is_dreaming or len(self.hippocampus) < 10:
            return
        
        self.is_dreaming = True
        print("[DREAMER] 🌙 Starting dream cycle...")
        
        try:
            # Find connections between memories in hippocampus
            connections_found = 0
            
            for i, mem1 in enumerate(self.hippocampus[:20]):
                for mem2 in self.hippocampus[i+1:20]:
                    # Check for tag similarity
                    tags1 = set(mem1.get('tags', []))
                    tags2 = set(mem2.get('tags', []))
                    
                    if tags1 & tags2:  # Common tags
                        # Create edge in graph
                        self.memory.neo4j.add_edge(
                            mem1['id'], 
                            mem2['id'], 
                            'DREAMED'
                        )
                        connections_found += 1
            
            # Consolidate important memories to LONG
            for mem in self.hippocampus:
                if mem.get('importance', 0) > 0.8:
                    self.memory.add(
                        mem['content'],
                        mem.get('importance', 0.5),
                        mem.get('tags', []),
                        tier='LONG'
                    )
            
            # Clear hippocampus after dreaming
            self.hippocampus = self.hippocampus[:10]  # Keep recent 10
            
            print(f"[DREAMER] 🌙 Dream complete! Found {connections_found} connections")
            self.last_dream = datetime.now(timezone.utc)
            
        finally:
            self.is_dreaming = False
    
    def start_dreaming_loop(self, interval_seconds: int = 300):
        """Start background dreaming loop"""
        def loop():
            while True:
                time.sleep(interval_seconds)
                if len(self.hippocampus) >= 20:
                    self.attempt_dream()
        
        thread = threading.Thread(target=loop, daemon=True)
        thread.start()
        print("[DREAMER] Dreaming loop started")


class CuriosityService:
    """
    Curiosity: Actively discovers new knowledge
    Based on Silhouette-OS curiosityService.ts
    
    During idle, explores:
    - Related topics to existing memories
    - New trends in stored tags
    - Creates exploration tasks
    """
    
    def __init__(self, memory_system):
        self.memory = memory_system
        self.is_exploring = False
        self.last_exploration = None
        self.exploration_topics: List[str] = []
        
    def add_exploration_topic(self, topic: str):
        """Add topic to exploration queue"""
        if topic not in self.exploration_topics:
            self.exploration_topics.append(topic)
    
    def explore(self):
        """Perform curiosity exploration"""
        if self.is_exploring:
            return
        
        self.is_exploring = True
        print("[CURIOSITY] 🔍 Starting exploration...")
        
        try:
            # Get all tags from memory
            all_tags = set()
            for tier in ['working', 'medium', 'long', 'deep']:
                nodes = getattr(self.memory, f'get_{tier}')()
                for node in nodes:
                    all_tags.update(node.get('tags', []))
            
            # Explore each tag
            for tag in list(all_tags)[:10]:
                # Find related content in memory
                related = self.memory.search(tag)
                
                if len(related) < 3:
                    # Need more info - this could be a gap
                    print(f"[CURIOSITY] 🔍 Gap found: {tag} (only {len(related)} memories)")
            
            self.last_exploration = datetime.now(timezone.utc)
            print(f"[CURIOSITY] 🔍 Exploration complete. Topics: {len(all_tags)}")
            
        finally:
            self.is_exploring = False
    
    def start_curiosity_loop(self, interval_seconds: int = 600):
        """Start background curiosity loop"""
        def loop():
            while True:
                time.sleep(interval_seconds)
                self.explore()
        
        thread = threading.Thread(target=loop, daemon=True)
        thread.start()
        print("[CURIOSITY] Curiosity loop started")


class MemoryIntegration:
    """
    MemoryIntegration: Automatic memory lookup before responding
    Based on Silhouette-OS introspectionEngine.ts
    
    Called before every response to:
    - Check relevant memories
    - Suggest related information
    - Maintain context continuity
    """
    
    def __init__(self, memory_system):
        self.memory = memory_system
        self.context_window: List[Dict] = []
        self.MAX_CONTEXT = 10
        
    def before_responding(self, query: str, user_id: str = None) -> Dict:
        """
        Called before responding - searches memory and returns context
        Returns: {
            'relevant_memories': [...],
            'suggestions': [...],
            'context': [...]
        }
        """
        # Search memory for relevant information
        results = self.memory.search(query)
        
        # Get working memory
        working = self.memory.get_working()
        
        # Add to context window
        context_entry = {
            'query': query,
            'timestamp': time.time(),
            'relevant_count': len(results)
        }
        self.context_window.append(context_entry)
        
        # Keep only recent context
        if len(self.context_window) > self.MAX_CONTEXT:
            self.context_window = self.context_window[-self.MAX_CONTEXT:]
        
        # Suggest related memories based on tags in results
        suggestions = []
        for r in results[:5]:
            suggestions.extend([
                {'id': n['id'], 'content': n['content'][:50]}
                for n in self.memory.search(r.get('tags', [''])[0])
                if n.get('id') != r.get('id')
            ][:2])
        
        return {
            'relevant_memories': results[:5],
            'suggestions': suggestions[:5],
            'context': self.context_window[-3:],
            'stats': self.memory.get_stats()
        }
    
    def get_context_summary(self) -> str:
        """Get summary of recent context"""
        if not self.context_window:
            return "No recent context"
        
        recent = self.context_window[-3:]
        summary = []
        for c in recent:
            summary.append(f"- {c['query'][:40]}... ({c['relevant_count']} memories)")
        
        return "\n".join(summary)


class SemanticJanitor:
    """
    SemanticJanitor: Detects contradictions and manages memory health
    Based on Silhouette-OS memory maintenance
    
    Functions:
    - Detect contradictory memories
    - Merge duplicate memories
    - Clean up stale data
    """
    
    def __init__(self, memory_system):
        self.memory = memory_system
    
    def find_contradictions(self) -> List[Dict]:
        """Find potentially contradictory memories"""
        contradictions = []
        
        # Get all LONG/DEEP memories
        long_memories = self.memory.get_long()
        
        # Simple contradiction detection (same tags, opposite sentiments)
        for i, mem1 in enumerate(long_memories):
            for mem2 in long_memories[i+1:]:
                # Check if same topic (tags overlap)
                tags1 = set(mem1.get('tags', []))
                tags2 = set(mem2.get('tags', []))
                
                common = tags1 & tags2
                if common:
                    # Check for contradictory keywords
                    positive = ['good', 'great', 'love', 'best', 'excelent', 'bien', 'mejor', 'gustar']
                    negative = ['bad', 'terrible', 'hate', 'worst', 'mal', 'peor', 'odiar']
                    
                    content1 = mem1.get('content', '').lower()
                    content2 = mem2.get('content', '').lower()
                    
                    has_pos = any(p in content1 for p in positive)
                    has_neg = any(n in content2 for n in negative)
                    
                    if (has_pos and has_neg) or (any(n in content1 for n in negative) and any(p in content2 for p in positive)):
                        contradictions.append({
                            'memory1': mem1['id'],
                            'memory2': mem2['id'],
                            'topic': list(common)[0],
                            'conflict': f"Opposing views on {list(common)[0]}"
                        })
        
        return contradictions
    
    def clean_stale_memories(self):
        """Remove or archive very old low-importance memories"""
        now = time.time()
        threshold = 30 * 24 * 60 * 60  # 30 days
        
        cleaned = 0
        for node in self.memory.get_long():
            age = now - node.get('timestamp', 0)
            importance = node.get('importance', 0)
            
            if age > threshold and importance < 0.3:
                # Could move to archive instead of delete
                cleaned += 1
        
        print(f"[JANITOR] Cleaned {cleaned} stale memories")
        return cleaned
    
    def run_maintenance(self):
        """Run full maintenance cycle"""
        print("[JANITOR] 🧹 Running maintenance...")
        
        contradictions = self.find_contradictions()
        if contradictions:
            print(f"[JANITOR] ⚠️ Found {len(contradictions)} potential contradictions")
            for c in contradictions[:3]:
                print(f"  - {c['conflict']}")
        
        cleaned = self.clean_stale_memories()
        
        return {
            'contradictions': len(contradictions),
            'cleaned': cleaned
        }


class MemoryAgents:
    """
    Unified Memory Agents System
    Combines all memory intelligence services
    """
    
    def __init__(self, memory_system):
        self.memory = memory_system
        
        # Initialize services
        self.dreamer = DreamerService(memory_system)
        self.curiosity = CuriosityService(memory_system)
        self.integration = MemoryIntegration(memory_system)
        self.janitor = SemanticJanitor(memory_system)
        
        print("[MEMORY AGENTS] All agents initialized")
    
    def before_response(self, query: str, user_id: str = None) -> Dict:
        """Automatically called before responding"""
        return self.integration.before_responding(query, user_id)
    
    def start_background_agents(self, dream_interval: int = 300, curiosity_interval: int = 600):
        """Start background exploration"""
        self.dreamer.start_dreaming_loop(dream_interval)
        self.curiosity.start_curiosity_loop(curiosity_interval)
        print("[MEMORY AGENTS] Background agents started")
    
    def run_maintenance(self):
        """Run memory maintenance"""
        return self.janitor.run_maintenance()


if __name__ == "__main__":
    # Test the agents
    from silhouette_memory import SilhouetteMemory
    
    memory = SilhouetteMemory()
    agents = MemoryAgents(memory)
    
    # Test before responding
    print("\n=== Testing Memory Integration ===")
    result = agents.before_response("Alberto")
    print(f"Relevant memories: {len(result['relevant_memories'])}")
    print(f"Suggestions: {len(result['suggestions'])}")
    
    # Test maintenance
    print("\n=== Testing Janitor ===")
    maintenance = agents.run_maintenance()
    print(f"Maintenance result: {maintenance}")
    
    memory.close()
