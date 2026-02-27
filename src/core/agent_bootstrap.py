"""
Agente Bootstrap - Memoria Automática
====================================
Este script se ejecuta automáticamente cuando un agente inicia.

Uso:
    # Al inicio del agente, importar y ejecutar:
    from agent_bootstrap import init_agent
    init_agent("nombre_del_agente", "tarea_a_realizar")

Esto:
1. Busca contexto relevante en memoria
2. Muestra entidades conocidas
3. Proporciona contexto para la tarea
"""
import sys
import os

# Añadir path de memoria
sys.path.insert(0, os.getenv('BRAIN_SRC_DIR', os.path.dirname(os.path.abspath(__file__))))

from agent_memory_readonly import get_memory_context, get_entities, get_recent

AGENT_COLOR = {
    "rick": "🔴",
    "cami": "🔵",
    "roger": "🦅",
    "jack": "📋",
    "rose": "📊",
    "larry": "🐦",
    "flocky": "🐙"
}

def init_agent(agent_name: str, task: str = ""):
    """
    Inicializa el agente con contexto de memoria.
    DEBE ejecutarse al inicio de cualquier tarea.
    """
    emoji = AGENT_COLOR.get(agent_name.lower(), "🤖")
    
    print(f"\n{'='*50}")
    print(f"{emoji} [AGENTE: {agent_name.upper()}] INICIANDO")
    print(f"{'='*50}")
    
    # 1. Contexto reciente
    print(f"\n📅 CONTEXTO RECIENTE (últimas 24h):")
    recent = get_recent(hours=24)
    if recent.get('found', 0) > 0:
        for conv in recent.get('conversations', [])[:5]:
            print(f"  - {conv['datetime']}: {conv['speaker']}: {conv['message'][:80]}...")
    else:
        print("  (sin contexto reciente)")
    
    # 2. Si hay tarea, buscar contexto relevante
    if task:
        print(f"\n🔍 BUSCANDO CONTEXTO PARA: {task}")
        result = get_memory_context(task)
        if result.get('found', 0) > 0:
            print(f"  ✅ {result.get('found', 0)} resultados encontrados:")
            for r in result.get('results', [])[:3]:
                print(f"     - {r['message'][:100]}...")
        else:
            print(f"  ⚠️ No se encontró contexto específico")
    
    # 3. Entidades conocidas
    print(f"\n🏢 ENTIDADES CONOCIDAS:")
    ents = get_entities()
    if ents.get('total', 0) > 0:
        for e in ents.get('entities', [])[:10]:
            print(f"  - {e['name']} ({e['type']}) - {e['mentions']} menciones")
    else:
        print("  (sin entidades)")
    
    print(f"\n{'='*50}")
    print(f"✅ Contexto cargado. Lista para trabajar.")
    print(f"{'='*50}\n")
    
    return {
        "recent": recent,
        "entities": ents
    }

# ============================================
# USO EN AGENTES:
# ============================================
#
# Al inicio de cualquier tarea:
#
# from agent_bootstrap import init_agent
#
# # Ejemplo para Rick:
# context = init_agent("rick", "traducir componentes")
#
# # Para Flocky:
# context = init_agent("flocky", "github commits")
#
# ============================================
