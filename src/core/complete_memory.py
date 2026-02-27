#!/usr/bin/env python3
"""
Silhouette Complete Memory System
Full integration with all memory services

Features:
- GraphExtractionService: Extract entities from conversations
- IntrospectionEngine: Monitor thought patterns
- Narrator: Stream of consciousness (lightweight)
- Memory Agents: Dreamer, Curiosity, Janitor (infrequent)
"""
import time
import threading
import re
import hashlib
from datetime import datetime, timezone
from typing import Dict, List, Optional
import json
import os

# Import existing memory system
import sys
sys.path.insert(0, os.getenv('BRAIN_SRC_DIR', os.path.dirname(os.path.abspath(__file__))))
from silhouette_memory import SilhouetteMemory
from memory_agents import MemoryAgents, DreamerService, CuriosityService, SemanticJanitor

class GraphExtractionService:
    """
    Extracts entities from conversations in real-time
    Lightweight version - doesn't use LLM, uses pattern matching
    
    Extracts:
    - Names
    - Projects
    - Companies
    - Technologies
    - Preferences
    """
    
    PATTERNS = {
        'name': [
            r"(?:me llamo|mi nombre es|soy)\s+([A-Za-záéíóúñÁÉÍÓÚÑ]+)",
            r"(?:llámame|call me)\s+([A-Za-záéíóúñÁÉÍÓÚÑ]+)",
            r"my name is\s+([A-Za-z]+)",
        ],
        'project': [
            r"(?:trabajo en|working on|proyecto)\s+([A-Z][a-zA-Z\s]+)",
            r"(?:estoy construyendo|building)\s+([A-Z][a-zA-Z\s]+)",
        ],
        'company': [
            r"(?:empresa|company|trabajo en)\s+([A-Z][a-zA-Z]+)",
        ],
        'tech': [
            r"(?:uso|using|trabajo con)\s+(n8n|React|Python|JavaScript|Node|AI|GPT|Neo4j|Redis)",
        ],
        'preference': [
            r"(?:prefiero|i prefer|me gusta)\s+([^\.]+)",
            r"(?:no me gusta|i don't like)\s+([^\.]+)",
        ]
    }
    
    def __init__(self, memory_system):
        self.memory = memory_system
        self.extracted_count = 0
        
    def extract_from_conversation(self, user_message: str, ai_response: str = "") -> List[Dict]:
        """Extract entities from conversation"""
        entities = []
        
        # Extract names
        for pattern in self.PATTERNS['name']:
            matches = re.finditer(pattern, user_message, re.IGNORECASE)
            for match in matches:
                name = match.group(1).strip()
                if len(name) > 2:
                    entities.append({
                        'type': 'person',
                        'value': name,
                        'source': 'name_mention'
                    })
                    
                    # Store immediately in memory
                    self.memory.add(
                        f"El usuario se llama {name}",
                        importance=0.95,
                        tags=['usuario', 'nombre', name.lower()],
                        tier='WORKING'
                    )
                    self.extracted_count += 1
        
        # Extract projects
        for pattern in self.PATTERNS['project']:
            matches = re.finditer(pattern, user_message, re.IGNORECASE)
            for match in matches:
                project = match.group(1).strip()
                if len(project) > 2:
                    entities.append({
                        'type': 'project',
                        'value': project,
                        'source': 'project_mention'
                    })
        
        # Extract technologies
        for pattern in self.PATTERNS['tech']:
            matches = re.finditer(pattern, user_message, re.IGNORECASE)
            for match in matches:
                tech = match.group(1).strip()
                entities.append({
                    'type': 'technology',
                    'value': tech,
                    'source': 'tech_mention'
                })
                
                # Store tech in memory
                self.memory.add(
                    f"El usuario trabaja con {tech}",
                    importance=0.7,
                    tags=['tecnologia', tech.lower()],
                    tier='MEDIUM'
                )
                self.extracted_count += 1
        
        # Extract preferences
        for pattern in self.PATTERNS['preference']:
            matches = re.finditer(pattern, user_message, re.IGNORECASE)
            for match in matches:
                pref = match.group(1).strip()
                if len(pref) > 3:
                    entities.append({
                        'type': 'preference',
                        'value': pref,
                        'source': 'preference_mention'
                    })
        
        return entities
    
    def get_stats(self) -> Dict:
        return {
            'total_extracted': self.extracted_count
        }


class IntrospectionEngine:
    """
    Monitors thought patterns and cognitive state
    Lightweight version - doesn't run frequently
    
    Tracks:
    - Response patterns
    - Memory access frequency
    - Topic continuity
    """
    
    def __init__(self, memory_system):
        self.memory = memory_system
        self.thoughts: List[Dict] = []
        self.max_thoughts = 50
        self.current_layer = "OPTIMAL"  # OPTIMAL, REFLECTION, IDLE, DREAMING
        
    def record_thought(self, thought: str, context: str = ""):
        """Record a thought pattern"""
        thought_entry = {
            'thought': thought,
            'context': context,
            'timestamp': time.time(),
            'layer': self.current_layer
        }
        
        self.thoughts.append(thought_entry)
        
        # Keep only recent thoughts
        if len(self.thoughts) > self.max_thoughts:
            self.thoughts = self.thoughts[-self.max_thoughts:]
    
    def analyze_context(self, query: str) -> Dict:
        """Analyze current context and return insights"""
        # Check recent thoughts
        recent = self.thoughts[-5:]
        
        # Check memory context
        relevant = self.memory.search(query)
        
        # Determine cognitive layer
        if len(recent) == 0:
            layer = "INITIAL"
        elif any(t['layer'] == 'DREAMING' for t in recent):
            layer = "DREAMING"
        elif len(relevant) > 5:
            layer = "OPTIMAL"
        else:
            layer = "REFLECTION"
        
        self.current_layer = layer
        
        return {
            'layer': layer,
            'recent_thoughts': len(recent),
            'relevant_memories': len(relevant),
            'thought_pattern': [t['thought'][:30] for t in recent[-3:]]
        }
    
    def get_current_layer(self) -> str:
        return self.current_layer


class NarratorService:
    """
    Stream of consciousness - generates narrative summaries
    Lightweight - runs infrequently (every 30 minutes max)
    Uses templates, not generation
    """
    
    def __init__(self, memory_system):
        self.memory = memory_system
        self.last_narrative = None
        self.narrative_cooldown = 1800  # 30 minutes minimum
        self.last_run = 0
        
    def should_run(self) -> bool:
        """Check if enough time has passed"""
        return (time.time() - self.last_run) > self.narrative_cooldown
    
    def generate_narrative(self, force: bool = False) -> Optional[str]:
        """Generate a narrative summary"""
        if not force and not self.should_run():
            return None
        
        self.last_run = time.time()
        
        # Get current state
        stats = self.memory.get_stats()
        working = self.memory.get_working()
        
        # Get recent thoughts (from introspection if available)
        recent_content = [w['content'][:40] for w in working[-5:]]
        
        # Generate simple narrative using templates
        templates = [
            f"Manteniendo {stats['working']} memorias activas en contexto.",
            f"Explorando conexiones entre {stats['graph_nodes']} nodos de conocimiento.",
            f"Consolidando {stats['long']} memorias de largo plazo.",
            f"Monitoreando {stats['graph_edges']} relaciones en el grafo de conocimiento."
        ]
        
        # Pick one based on state
        if stats['working'] > 30:
            narrative = templates[0]
        elif stats['graph_edges'] > 10:
            narrative = templates[1]
        elif stats['long'] > 5:
            narrative = templates[2]
        else:
            narrative = templates[3]
        
        self.last_narrative = narrative
        
        # Store as memory
        self.memory.add(
            f"Narrativa del sistema: {narrative}",
            importance=0.3,
            tags=['sistema', 'narrativa'],
            tier='LONG'
        )
        
        return narrative
    
    def get_status(self) -> Dict:
        return {
            'last_narrative': self.last_narrative,
            'seconds_since_last': time.time() - self.last_run,
            'cooldown': self.narrative_cooldown
        }


class CompleteMemorySystem:
    """
    Complete memory system with all services
    Optimized for low resource usage
    """
    
    def __init__(self):
        # Core memory
        self.memory = SilhouetteMemory()
        
        # Intelligence services
        self.agents = MemoryAgents(self.memory)
        self.extractor = GraphExtractionService(self.memory)
        self.introspection = IntrospectionEngine(self.memory)
        self.narrator = NarratorService(self.memory)
        
        # Background threads (infrequent)
        self.running = False
        
        print("[COMPLETE MEMORY] All services initialized")
    
    def process_conversation(self, user_message: str, query_context: str = "") -> Dict:
        """Process a conversation - extract, integrate, respond"""
        # 1. Extract entities
        entities = self.extractor.extract_from_conversation(user_message)
        
        # 2. Analyze context
        context = self.introspection.analyze_context(query_context)
        
        # 3. Get relevant memories for response
        memories = self.memory.search(query_context)
        
        # 4. Occasionally generate narrative (every 30 min max)
        narrative = self.narrator.generate_narrative()
        
        return {
            'entities_extracted': len(entities),
            'cognitive_layer': context['layer'],
            'relevant_memories': len(memories),
            'narrative': narrative,
            'stats': self.memory.get_stats()
        }
    
    def before_responding(self, query: str) -> Dict:
        """Called before responding - integrates all services"""
        # Analyze context
        context = self.introspection.analyze_context(query)
        
        # Search memory
        memories = self.memory.search(query)
        
        # Get suggestions
        agents_result = self.agents.before_response(query)
        
        return {
            'query': query,
            'cognitive_layer': context['layer'],
            'relevant_memories': memories,
            'suggestions': agents_result.get('suggestions', []),
            'stats': self.memory.get_stats()
        }
    
    def start_background_services(self):
        """Start infrequent background services"""
        # Dreamer: every 30 minutes
        # Curiosity: every 60 minutes  
        # Janitor: every 24 hours
        self.agents.start_background_agents(
            dream_interval=1800,  # 30 min
            curiosity_interval=3600  # 60 min
        )
        self.running = True
        print("[COMPLETE MEMORY] Background services started (infrequent)")
    
    def run_maintenance(self):
        """Run maintenance - contradictions, cleanup"""
        return self.agents.run_maintenance()
    
    def close(self):
        self.memory.close()


# CLI
if __name__ == "__main__":
    import sys
    
    cms = CompleteMemorySystem()
    
    if len(sys.argv) < 2:
        print("""
╔═══════════════════════════════════════════╗
║   COMPLETE SILHOUETTE MEMORY SYSTEM    ║
║   Full Integration v1.0                ║
╚═══════════════════════════════════════════╝

Services:
- 4-Tier Memory (Working/Medium/Long/Deep)
- GraphExtraction (entity extraction)
- Introspection (thought monitoring)
- Narrator (stream of consciousness)
- Memory Agents (Dreamer/Curiosity/Janitor)

Commands:
  process <message>         - Process conversation
  before <query>           - Before responding
  extract <message>        - Extract entities
  narrative                - Generate narrative
  maintenance              - Run janitor
  stats                    - Full stats
  start                    - Start background services
        """)
    else:
        cmd = sys.argv[1]
        
        if cmd == "process":
            msg = " ".join(sys.argv[2:])
            result = cms.process_conversation(msg, msg)
            print(f"Entities: {result['entities_extracted']}")
            print(f"Layer: {result['cognitive_layer']}")
            print(f"Memories: {result['relevant_memories']}")
        
        elif cmd == "before":
            query = " ".join(sys.argv[2:])
            result = cms.before_responding(query)
            print(f"Layer: {result['cognitive_layer']}")
            print(f"Memories: {len(result['relevant_memories'])}")
        
        elif cmd == "extract":
            msg = " ".join(sys.argv[2:])
            entities = cms.extractor.extract_from_conversation(msg)
            print(f"Extracted: {len(entities)}")
            for e in entities:
                print(f"  [{e['type']}] {e['value']}")
        
        elif cmd == "narrative":
            narr = cms.narrator.generate_narrative(force=True)
            print(f"Narrative: {narr}")
        
        elif cmd == "maintenance":
            result = cms.run_maintenance()
            print(f"Maintenance: {result}")
        
        elif cmd == "stats":
            s = cms.memory.get_stats()
            print(f"Working: {s['working']}")
            print(f"Long: {s['long']}")
            print(f"Deep: {s['deep']}")
            print(f"Graph: {s['graph_nodes']} nodes, {s['graph_edges']} edges")
            print(f"Extracted: {cms.extractor.get_stats()['total_extracted']}")
            print(f"Narrator: {cms.narrator.get_status()}")
        
        elif cmd == "start":
            cms.start_background_services()
            print("Background services started")
    
    cms.close()
