import os
#!/usr/bin/env python3
"""
Ultimate Context Engine v2
Busca en TODOS los niveles de memoria antes de CADA respuesta
"""
import sys
sys.path.insert(0, os.getenv('BRAIN_SRC_DIR', os.path.dirname(os.path.abspath(__file__))))

def get_complete_context(query: str, team_context: str = None) -> dict:
    """
    Obtiene contexto COMPLETO de todos los niveles de memoria
    Se debe llamar ANTES de cada respuesta
    """
    from memory_core_embeddings import get_memory_core
    from enhanced_memory import get_enhanced_memory
    
    context = {
        'query': query,
        'level_1_never_forget': [],    # Mi alma/inconsciente
        'level_2_team': [],              # Equipo de agentes
        'level_3_projects': [],          # Proyectos
        'level_4_recent': [],           # Conversaciones recientes
        'level_5_embeddings': [],        # Búsqueda semántica
        'summary': '',
        'ready_for_response': False
    }
    
    # Load all memory systems
    memory = get_enhanced_memory()
    core = get_memory_core()
    
    # === LEVEL 1: NEVER FORGET (Mi alma) ===
    for item in memory.never_forget[-10:]:
        context['level_1_never_forget'].append({
            'type': '⭐ ALMA',
            'content': item['content'],
            'importance': item.get('importance', 0)
        })
    
    # === LEVEL 2: EQUIPO ===
    # Buscar info del equipo
    team_results = core.search_context('Roger Cami Rick Rose Jack Larry Flocky equipo', limit=5)
    context['level_2_team'] = [
        {'type': '🤖 EQUIPO', 'content': r['message'][:150]} 
        for r in team_results
    ]
    
    # === LEVEL 3: PROYECTOS ===
    project_results = core.search_context('Brandistry Nexus Silhouette proyecto', limit=5)
    context['level_3_projects'] = [
        {'type': '🏢 PROYECTO', 'content': r['message'][:150]} 
        for r in project_results
    ]
    
    # === LEVEL 4: RECIENTE ===
    recent = core.search_context(query, limit=5)
    context['level_4_recent'] = [
        {'type': '📅 RECIENTE', 'content': r['message'][:150]} 
        for r in recent
    ]
    
    # === LEVEL 5: EMBEDDINGS (búsqueda semántica) ===
    all_results = core.search_context(query, limit=10)
    context['level_5_embeddings'] = [
        {'type': '🔍 SEMÁNTICO', 'content': r['message'][:150], 'score': r.get('similarity', 0)}
        for r in all_results
    ]
    
    # === GENERAR RESUMEN PARA RESPUESTA ===
    summary_parts = []
    
    if context['level_1_never_forget']:
        summary_parts.append("⭐ REGLAS: " + context['level_1_never_forget'][0]['content'][:100])
    
    if team_context or context['level_2_team']:
        summary_parts.append("🤖 EQUIPO: Contexto del equipo disponible")
    
    if context['level_3_projects']:
        summary_parts.append("🏢 PROYECTOS: " + context['level_3_projects'][0]['content'][:80])
    
    if context['level_4_recent']:
        summary_parts.append("📍 CONTEXTO: " + context['level_4_recent'][0]['content'][:80])
    
    context['summary'] = " | ".join(summary_parts)
    context['ready_for_response'] = True
    
    return context


def format_context_for_response(query: str) -> str:
    """Formatea el contexto completo para usar en mi respuesta"""
    ctx = get_complete_context(query)
    
    prompt = f"""
=== CONTEXTO COMPLETO PARA RESponder ===
Query: {query}

{ctx['summary']}

---
Nivel 1 (ALMA):
"""
    for item in ctx['level_1_never_forget'][:3]:
        prompt += f"- {item['content'][:100]}\n"
    
    prompt += "\nNivel 2 (EQUIPO):\n"
    for item in ctx['level_2_team'][:2]:
        prompt += f"- {item['content'][:80]}\n"
    
    prompt += "\nNivel 3 (PROYECTOS):\n"
    for item in ctx['level_3_projects'][:2]:
        prompt += f"- {item['content'][:80]}\n"
    
    return prompt


# Test
if __name__ == "__main__":
    print("=== TEST CONTEXT ENGINE ===")
    ctx = get_complete_context("Alberto me pregunta sobre Brandistry")
    
    print(f"\nQuery: {ctx['query']}")
    print(f"Ready: {ctx['ready_for_response']}")
    print(f"\nNivel 1 (ALMA): {len(ctx['level_1_never_forget'])} items")
    print(f"Nivel 2 (EQUIPO): {len(ctx['level_2_team'])} items")
    print(f"Nivel 3 (PROYECTOS): {len(ctx['level_3_projects'])} items")
    print(f"Nivel 5 (SEMÁNTICO): {len(ctx['level_5_embeddings'])} items")
    print(f"\nResumen: {ctx['summary'][:150]}...")
