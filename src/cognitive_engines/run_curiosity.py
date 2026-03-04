#!/usr/bin/env python3
import os
"""
Automatic Curiosity Discovery
Runs every 30 minutes to find gaps and novel connections
"""
import sys
sys.path.append(os.getenv("BRAIN_SRC_DIR", "/root/silhouette-brain/src/core"))
sys.path.insert(0, os.getenv("BRAIN_SRC_DIR_FALLBACK", "/root/silhouette-brain/src"))

from advanced_discovery import CuriosityDiscovery, MemoryAssociation
from silhouette_memory import SilhouetteMemory
from datetime import datetime
import json

def run_curiosity():
    """Run curiosity discovery and store in memory"""
    print(f"[{datetime.now().strftime('%H:%M')}] === Curiosity ===")
    
    try:
        memory = SilhouetteMemory()
        curiosity = CuriosityDiscovery(memory)
        
        # Find gaps
        gaps = curiosity.find_information_gaps()
        print(f"Found {len(gaps)} gaps")
        
        # Get novel connections
        ma = MemoryAssociation()
        from memory_core import get_memory_core
        core = get_memory_core()
        entities = core.get_entities()
        entity_names = [e['name'] for e in entities[:20]]
        novel = ma.find_novel_connections(entity_names)
        
        # Store in memory
        discovery = {
            "type": "curiosity_discovery",
            "gaps": [{"entity": g['entity'], "potential": g['discovery_potential']} for g in gaps[:5]],
            "novel": [{"from": n['from'], "to": n['to']} for n in novel[:3]]
        }
        
        memory.add(json.dumps(discovery), tags=["curiosity", "auto", "discovery"])
        
        print(f"✅ Stored in memory")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    run_curiosity()
