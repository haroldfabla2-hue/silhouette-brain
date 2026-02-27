import os
#!/usr/bin/env python3
"""
Context Awareness System
Se ejecuta ANTES de cualquier tarea para obtener contexto relevante
"""
import sys
sys.path.insert(0, os.getenv('BRAIN_SRC_DIR', os.path.dirname(os.path.abspath(__file__))))

def get_context_for_task(agent: str, task_type: str) -> dict:
    """
    Obtiene contexto relevante antes de ejecutar una tarea.
    Se debe llamar ANTES de cualquier acción.
    """
    from respond import respond_with_context
    from biomimetic_memory import get_biomimetic_memory
    
    biomimetic = get_biomimetic_memory()
    
    context = {
        'agent': agent,
        'task_type': task_type,
        'priority_context': [],
        'related_context': [],
        'never_forget': []
    }
    
    # 1. Get NEVER FORGET (siempre presente)
    for item in biomimetic.priority.get('never_forget', []):
        context['never_forget'].append({
            'content': item['content'],
            'tags': item.get('tags', [])
        })
    
    # 2. Get relevant context based on agent/task
    queries = {
        'roger': ['oportunidades', 'freelance', 'remoteok', 'linkedin'],
        'cami': ['research', 'mercado', 'tech', 'empresas'],
        'rick': ['código', 'github', 'proyectos', 'brandistry'],
        'rose': ['análisis', 'métricas', 'competidores'],
        'jack': ['planificación', 'roadmap', 'tareas'],
        'larry': ['social media', 'twitter', 'linkedin', 'contenido'],
        'flocky': ['github', 'ci cd', 'commits', 'issues']
    }
    
    for q in queries.get(agent, [agent]):
        result = respond_with_context(q)
        for r in result.get('relevant', [])[:3]:
            if r.get('type') == 'semantic':
                context['related_context'].append({
                    'query': q,
                    'content': r['message'][:150],
                    'similarity': r.get('similarity', 0)
                })
    
    return context


def format_context_for_agent(agent: str, task: str) -> str:
    """Formatea el contexto para pasarlo al agente"""
    ctx = get_context_for_task(agent, task)
    
    prompt = f"=== CONTEXTO DE MEMORIA ===\n"
    
    if ctx['never_forget']:
        prompt += "\n⭐ COSAS IMPORTANTES (NEVER FORGET):\n"
        for item in ctx['never_forget']:
            prompt += f"  - {item['content']}\n"
    
    if ctx['related_context']:
        prompt += "\n📚 CONTEXTO RELACIONADO:\n"
        for item in ctx['related_context'][:5]:
            prompt += f"  [{item['query']}] {item['content']}...\n"
    
    prompt += "\n=== FIN CONTEXTO ===\n"
    
    return prompt


if __name__ == "__main__":
    # Test
    for agent in ['roger', 'rick', 'cami']:
        print(f"\n=== {agent.upper()} ===")
        ctx = get_context_for_task(agent, 'cycle')
        
        print(f"Never forget: {len(ctx['never_forget'])}")
        print(f"Related: {len(ctx['related_context'])}")
        
        # Show context
        print(format_context_for_agent(agent, 'test'))
