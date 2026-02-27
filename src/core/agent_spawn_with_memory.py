#!/usr/bin/env python3
"""
Agent Spawner con Memoria Automática
Wrapper para sessions_spawn que incluye contexto de memoria
"""
import sys
sys.path.insert(0, os.getenv('BRAIN_SRC_DIR', os.path.dirname(os.path.abspath(__file__))))

from agent_memory_readonly import get_memory_context, get_entities, get_recent

AGENT_COLOR = {
    "rick": "🔴",
    "cami": "🔵", 
    "roger": "🦅",
    "jack": "📋",
    "rose": "📊",
    "larry": "🐦",
    "flocky": "🐙",
    "silhouette": "🎯"
}

def get_agent_context(agent_name: str, task: str = "") -> str:
    """
    Genera un resumen de contexto para el agente.
    Se incluye automáticamente cuando se spawnea.
    """
    emoji = AGENT_COLOR.get(agent_name.lower(), "🤖")
    
    context_lines = []
    context_lines.append(f"\n{emoji} **CONTEXTO DE MEMORIA** - Agent: {agent_name}")
    context_lines.append("="*50)
    
    # 1. Contexto muy reciente (últimas 2 horas)
    recent = get_recent(hours=2)
    if recent.get('found', 0) > 0:
        context_lines.append(f"\n📅 ÚLTIMAS CONVERSACIONES:")
        for conv in recent.get('conversations', [])[:3]:
            context_lines.append(f"  • {conv['datetime']} | {conv['speaker']}: {conv['message'][:60]}...")
    
    # 2. Contexto específico de la tarea
    if task:
        result = get_memory_context(task)
        if result.get('found', 0) > 0:
            context_lines.append(f"\n🔍 CONTEXTO RELEVANTE PARA '{task}':")
            for r in result.get('results', [])[:3]:
                msg = r.get('message', r.get('text', ''))[:150]
                context_lines.append(f"  → {msg}...")
    
    # 3. Entidades clave
    ents = get_entities()
    if ents.get('total', 0) > 0:
        context_lines.append(f"\n🏢 ENTIDADES IMPORTANTES:")
        for e in ents.get('entities', [])[:5]:
            context_lines.append(f"  • {e['name']} ({e['type']})")
    
    context_lines.append("="*50 + "\n")
    
    return "\n".join(context_lines)


def spawn_with_memory(agent_id: str, task: str, model: str = None) -> dict:
    """
    Wrapper para spawnear agente con contexto automático de memoria.
    
    Uso:
        from agent_spawn_with_memory import spawn_with_memory
        
        result = spawn_with_memory("rick", "actualizar blog i18n")
    """
    from sessions_spawn import sessions_spawn
    
    # Obtener contexto de memoria dinámica
    context = get_agent_context(agent_id, task)
    
    # Obtener dump estático (sin ejecutar Python en el agente)
    try:
        from memory_dump import get_memory_for_agent
        dump = get_memory_for_agent()
    except:
        dump = "(Memory dump no disponible)"
    
    # Crear prompt con contexto
    full_task = f"""{context}

---

## 🧠 CONTEXTO DE MEMORIA (Dump Automático)
{dump}

---

## 🎯 TAREA ASIGNADA:

{task}

---

**IMPORTANTE:** 
- El contexto de arriba es tu memoria. úsalo para mantener continuidad.
- NO necesitas ejecutar Python - toda la info ya está aquí.
- Si necesitas más contexto, está en: /root/.openclaw/workspace/agents/workspace-silhouette/memory/agent_memory_dump.json
"""


# ============================================
# Alternativa: Función para ejecutar DENTRO del agente
# ============================================
def inject_memory_context():
    """
    Si el agente ya está corriendo, puede llamar esto para obtener contexto.
    """
    import os
    
    # Obtener agent_id del environment o argumento
    agent_id = os.environ.get('AGENT_ID', 'unknown')
    task = os.environ.get('AGENT_TASK', '')
    
    return get_agent_context(agent_id, task)


if __name__ == "__main__":
    # Test
    print(get_agent_context("rick", "blog"))
