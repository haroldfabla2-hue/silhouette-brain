#!/usr/bin/env python3
"""
Silhouette Memory Integration
Simple API to use memory before responding
"""
import sys
import os
sys.path.insert(0, os.getenv('BRAIN_SRC_DIR', os.path.dirname(os.path.abspath(__file__))))

from complete_memory import CompleteMemorySystem

# Singleton instance
_memory_system = None

def get_memory_system():
    """Get or create memory system instance"""
    global _memory_system
    if _memory_system is None:
        _memory_system = CompleteMemorySystem()
    return _memory_system

def before_response(query: str) -> dict:
    """
    Called before responding - integrates all memory services
    Returns context for better responses
    """
    cms = get_memory_system()
    result = cms.before_responding(query)
    return result

def process_message(user_message: str, context: str = "") -> dict:
    """
    Process a user message - extracts entities and integrates
    """
    cms = get_memory_system()
    return cms.process_conversation(user_message, context)

def add_memory(content: str, importance: float = 0.7, tags: list = None, tier: str = "WORKING") -> str:
    """Add a memory"""
    cms = get_memory_system()
    return cms.memory.add(content, importance, tags or [], tier=tier)

def search_memory(query: str) -> list:
    """Search memory"""
    cms = get_memory_system()
    return cms.memory.search(query)

def get_stats() -> dict:
    """Get memory stats"""
    cms = get_memory_system()
    return cms.memory.get_stats()

# Quick CLI
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Memory Integration CLI")
        print("Usage: python3 memory_integration.py <command> [args]")
        print("Commands: before, process, add, search, stats")
    else:
        cmd = sys.argv[1]
        
        if cmd == "before":
            result = before_response(" ".join(sys.argv[2:]))
            print(f"Layer: {result['cognitive_layer']}")
            print(f"Memories: {len(result['relevant_memories'])}")
            for m in result['relevant_memories'][:3]:
                print(f"  - {m['content'][:50]}...")
        
        elif cmd == "process":
            result = process_message(" ".join(sys.argv[2:]))
            print(f"Entities: {result['entities_extracted']}")
            print(f"Layer: {result['cognitive_layer']}")
        
        elif cmd == "add":
            content = " ".join(sys.argv[2:])
            result = add_memory(content)
            print(f"Added: {result}")
        
        elif cmd == "search":
            results = search_memory(" ".join(sys.argv[2:]))
            print(f"Found: {len(results)}")
            for r in results[:5]:
                print(f"  - {r['content'][:50]}...")
        
        elif cmd == "stats":
            s = get_stats()
            print(f"Working: {s['working']}")
            print(f"Long: {s['long']}")
            print(f"Deep: {s['deep']}")
            print(f"Graph: {s['graph_nodes']} nodes, {s['graph_edges']} edges")
