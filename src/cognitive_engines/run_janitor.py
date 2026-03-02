import os
#!/usr/bin/env python3
"""
Automatic Memory Janitor
Runs periodically to find and resolve contradictions
"""
import sys
sys.path.append(os.getenv('BRAIN_SRC_DIR', '/home/ubuntu/.openclaw/workspace/silhouette-brain/src/core'))
sys.path.insert(0, os.getenv('BRAIN_SRC_DIR', '/home/ubuntu/.openclaw/workspace/silhouette-brain/src'))

from memory_core import get_memory_core
from datetime import datetime

def run_janitor():
    """Run janitor - find and auto-resolve contradictions"""
    core = get_memory_core()
    
    print(f"[{datetime.now().strftime('%H:%M')}] === Janitor ===")
    
    # Find contradictions
    contradictions = core.find_contradictions()
    
    if not contradictions:
        print("No hay contradicciones")
        return
    
    print(f"Encontradas: {len(contradictions)}")
    
    # Cargar entidades una sola vez y hacer lookup por nombre
    entity_by_name = {e['name']: e for e in core.get_entities()}

    resolved = 0
    for c in contradictions:
        # Auto-resolve: majority wins
        if c['positive_count'] > c['negative_count']:
            truth = f"Verdad: mayoría positiva ({c['positive_count']} vs {c['negative_count']})"
        else:
            truth = f"Verdad: mayoría negativa ({c['negative_count']} vs {c['positive_count']})"

        e = entity_by_name.get(c['entity'])
        if e:
            core.verify_entity(e['id'], truth, "Janitor-Auto")
            print(f"  ✅ {c['entity']}: {truth}")
            resolved += 1
    
    print(f"Resueltas: {resolved}")

if __name__ == "__main__":
    run_janitor()
