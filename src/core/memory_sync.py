import os
#!/usr/bin/env python3
"""
Memory Sync - Sincroniza ambas memorias al 100%
"""
import sys
sys.path.insert(0, os.getenv('BRAIN_SRC_DIR', os.path.dirname(os.path.abspath(__file__))))

from memory_core import get_memory_core
from silhouette_memory import SilhouetteMemory
from datetime import datetime

def sync():
    """Sincroniza ambas memorias"""
    print(f"[{datetime.now().strftime('%H:%M')}] Sincronizando...")
    
    core = get_memory_core()
    permanent = SilhouetteMemory()
    
    # Get native entities
    native = core.get_entities()
    
    # Add to permanent if not exists
    for entity in native:
        name = entity.get('name', '')
        etype = entity.get('type', 'unknown')
        
        # Check if exists in permanent
        existing = permanent.search(name)
        if not existing:
            permanent.add(f"Entity from native: {name}", tags=[etype, "sync"])
    
    print(f"Sincronizado: {len(native)} entidades")
    return True

if __name__ == "__main__":
    sync()
