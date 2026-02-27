#!/usr/bin/env python3
"""
Silhouette Auto-Integration
Automatically stores every conversation and retrieves context before responding
"""
import sys
import os
sys.path.insert(0, os.getenv('BRAIN_SRC_DIR', os.path.dirname(os.path.abspath(__file__))))

from memory_core import get_memory_core
from silhouette_memory import SilhouetteMemory

class SilhouetteAutoMemory:
    """
    Auto-integrated memory system
    Called automatically for every message
    """
    
    def __init__(self):
        # Full conversation storage
        self.core = get_memory_core()
        
        # 4-tier memory (Silhouette-OS style)
        self.memory = SilhouetteMemory()
        
        print("[AUTO MEMORY] ✅ Integrated")
    
    def process_message(self, speaker: str, message: str, tags: list = None) -> dict:
        """
        Called for EVERY message
        1. Store in memory_core (full conversation)
        2. Extract entities
        3. Add to 4-tier memory if important
        """
        # Store full conversation
        msg_id = self.core.store_message(speaker, message, tags=tags or [])
        
        # Add important info to 4-tier memory
        if speaker == "user":
            # Check if important enough for long-term memory
            important_keywords = ['nombre', 'trabajo', 'proyecto', 'empresa', 'prefiero', 'importante', 
                               'name', 'work', 'project', 'company', 'prefer', 'important']
            
            if any(kw in message.lower() for kw in important_keywords):
                self.memory.add(
                    message,
                    importance=0.8,
                    tags=tags or ['conversacion'],
                    tier='LONG'
                )
        
        return {'stored': msg_id}
    
    def before_responding(self, query: str) -> dict:
        """
        Called BEFORE responding
        1. Search context in memory_core
        2. Get entities
        3. Check for contradictions
        4. Get 4-tier memory context
        """
        # Semantic search in full conversations
        context_results = self.core.search_context(query, limit=10)
        
        # Get entities
        entities = self.core.get_entities()
        
        # Check for verified truth about entities
        verified_truths = []
        for entity in entities[:5]:
            truth = self.core.get_verified_truth(entity['name'])
            if truth:
                verified_truths.append(truth)
        
        # Get recent context
        recent = self.core.get_recent_context(hours=24, limit=20)
        
        # Get 4-tier memory context
        working = self.memory.get_working()
        
        return {
            'query': query,
            'context_results': context_results[:5],
            'entities': entities[:10],
            'verified_truths': verified_truths,
            'recent_count': len(recent),
            'working_memory': working[:3]
        }
    
    def store_agent_report(self, agent_name: str, report: str, status: str = "completed") -> str:
        """Store agent reports in memory"""
        return self.core.store_message(
            speaker=f"agent:{agent_name}",
            message=report,
            tags=['agent', agent_name, status]
        )
    
    def get_team_context(self) -> dict:
        """Get all context about the team"""
        # Recent conversations
        recent = self.core.get_recent_context(hours=168, limit=100)  # Last week
        
        # All entities
        entities = self.core.get_entities()
        
        # Get user-related entities
        user_entities = [e for e in entities if e.get('type') == 'person']
        tech_entities = [e for e in entities if e.get('type') == 'tech']
        
        return {
            'recent_conversations': len(recent),
            'total_entities': len(entities),
            'people': [e['name'] for e in user_entities[:10]],
            'tech': [e['name'] for e in tech_entities[:10]]
        }
    
    def find_contradictions(self) -> list:
        """Find and return contradictions for resolution"""
        return self.core.find_contradictions()
    
    def get_stats(self) -> dict:
        """Get memory stats"""
        core_stats = self.core.get_context_summary()
        memory_stats = self.memory.get_stats()
        
        return {
            'conversations': core_stats['total_conversations'],
            'entities': len(self.core.get_entities()),
            'verified': core_stats['verified_entities'],
            'contradictions': core_stats['pending_contradictions'],
            'working_memory': memory_stats['working'],
            'long_memory': memory_stats['long'],
            'graph_nodes': memory_stats['graph_nodes']
        }


# Singleton
_auto_memory = None

def get_auto_memory() -> SilhouetteAutoMemory:
    global _auto_memory
    if _auto_memory is None:
        _auto_memory = SilhouetteAutoMemory()
    return _auto_memory

# Easy CLI
if __name__ == "__main__":
    am = get_auto_memory()
    
    import sys
    if len(sys.argv) < 2:
        print("Auto Memory CLI")
        print("Commands: process, before, agent, team, stats, contradictions")
    else:
        cmd = sys.argv[1]
        
        if cmd == "process":
            # process user "message"
            speaker = sys.argv[2] if len(sys.argv) > 2 else "user"
            message = " ".join(sys.argv[3:])
            result = am.process_message(speaker, message)
            print(f"Stored: {result['stored']}")
        
        elif cmd == "before":
            query = " ".join(sys.argv[2:])
            result = am.before_responding(query)
            print(f"Context: {len(result['context_results'])} results")
            print(f"Entities: {len(result['entities'])}")
            for r in result['context_results'][:3]:
                print(f"  - [{r['speaker']}] {r['message'][:40]}...")
        
        elif cmd == "agent":
            agent = sys.argv[2]
            report = " ".join(sys.argv[3:])
            result = am.store_agent_report(agent, report)
            print(f"Agent report stored: {result}")
        
        elif cmd == "team":
            context = am.get_team_context()
            print(f"Team context:")
            print(f"  Conversations: {context['recent_conversations']}")
            print(f"  People: {', '.join(context['people'])}")
            print(f"  Tech: {', '.join(context['tech'])}")
        
        elif cmd == "stats":
            stats = am.get_stats()
            print(f"Memory Stats:")
            print(f"  Conversations: {stats['conversations']}")
            print(f"  Entities: {stats['entities']}")
            print(f"  Verified: {stats['verified']}")
            print(f"  Working: {stats['working_memory']}")
            print(f"  Long: {stats['long_memory']}")
            print(f"  Graph: {stats['graph_nodes']}")
        
        elif cmd == "contradictions":
            contra = am.find_contradictions()
            print(f"Contradictions found: {len(contra)}")
            for c in contra:
                print(f"  - {c['entity']}: {c['positive_count']} positive, {c['negative_count']} negative")
