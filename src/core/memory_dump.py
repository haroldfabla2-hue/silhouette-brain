import os
#!/usr/bin/env python3
"""
Memory Dump Generator
Genera un JSON con el estado actual de la memoria para que los agentes puedan leerlo
sin ejecutar Python
"""
import json
import sys
sys.path.insert(0, os.getenv('BRAIN_SRC_DIR', os.path.dirname(os.path.abspath(__file__))))

from agent_memory_readonly import get_memory_context, get_entities, get_recent
from datetime import datetime

OUTPUT_FILE = "/home/ubuntu/.openclaw/workspace/agents/workspace-silhouette/memory/agent_memory_dump.json"

def generate_memory_dump():
    """Genera un dump completo de la memoria"""
    
    dump = {
        "generated_at": datetime.utcnow().isoformat(),
        "recent": [],
        "entities": [],
        "important_projects": {},
        "context_cache": {}
    }
    
    # 1. Conversaciones recientes (últimas 4h)
    recent = get_recent(hours=4, limit=10)
    dump["recent"] = recent.get("conversations", [])[:5]
    
    # 2. Entidades
    ents = get_entities()
    dump["entities"] = ents.get("entities", [])[:15]
    
    # 3. Proyectos importantes (búsqueda pre-generada)
    projects = [
        "Nanosilhouette", "Silhouette Agency OS", "Brandistry", 
        "Miportafolio", "Blog", "Nexus"
    ]
    for proj in projects:
        result = get_memory_context(proj, limit=2)
        if result.get("found", 0) > 0:
            dump["important_projects"][proj] = {
                "found": result.get("found", 0),
                "latest": result["results"][0]["message"][:300] if result["results"] else ""
            }
    
    # 4. Guardar
    with open(OUTPUT_FILE, "w") as f:
        json.dump(dump, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Memory dump guardado en {OUTPUT_FILE}")
    print(f"   - Recientes: {len(dump['recent'])}")
    print(f"   - Entidades: {len(dump['entities'])}")
    print(f"   - Proyectos: {len(dump['important_projects'])}")
    
    return dump


def get_memory_for_agent():
    """Genera y retorna el dump para inyectar en un agente"""
    dump = generate_memory_dump()
    
    # Generar texto formateado para el agente
    lines = []
    lines.append("## 🧠 CONTEXTO DE MEMORIA (Automático)")
    lines.append(f"_Generado: {dump['generated_at']}_")
    lines.append("")
    
    # Recientes
    if dump["recent"]:
        lines.append("### 📅 Conversaciones Recientes")
        for conv in dump["recent"][:3]:
            lines.append(f"- **{conv['datetime']}** | {conv['speaker']}: {conv['message'][:80]}...")
        lines.append("")
    
    # Entidades
    if dump["entities"]:
        lines.append("### 🏢 Entidades Conocidas")
        for e in dump["entities"][:8]:
            lines.append(f"- {e['name']} ({e['type']})")
        lines.append("")
    
    # Proyectos
    if dump["important_projects"]:
        lines.append("### 📁 Proyectos Activos")
        for name, data in dump["important_projects"].items():
            lines.append(f"**{name}**: {data['latest'][:100]}...")
        lines.append("")
    
    return "\n".join(lines)


if __name__ == "__main__":
    # Generar dump
    generate_memory_dump()
    
    # También mostrar para un agente
    print("\n" + "="*50)
    print("TEXTO PARA AGENTE:")
    print("="*50)
    print(get_memory_for_agent())
