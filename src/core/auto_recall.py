import os
#!/usr/bin/env python3
"""
Auto Recall - Se ejecuta antes de cada respuesta importante
"""
import sys
sys.path.insert(0, os.getenv('BRAIN_SRC_DIR', os.path.dirname(os.path.abspath(__file__))))

def auto_recall(query: str, mode: str = "default") -> dict:
    """
    Busca contexto relevante ANTES de responder.
    
    Args:
        query: Lo que voy a responder/preguntar
        mode: "default" | "agent" | "quick"
    
    Returns:
        Dict con contexto encontrado
    """
    from agent_memory_readonly import get_memory_context, get_recent
    
    results = {
        'query': query,
        'recent': [],
        'context': [],
        'entities': [],
        'ready': False
    }
    
    # 1. Contexto reciente (últimas 2 horas)
    recent = get_recent(hours=2)
    results['recent'] = recent.get('results', [])[:3]
    
    # 2. Buscar contexto relevante según el query
    if query:
        context = get_memory_context(query)
        results['context'] = context.get('results', [])[:5]
        results['entities'] = context.get('entities', [])
    
    # 3. Determinar si tenemos suficiente contexto
    total_results = len(results['recent']) + len(results['context'])
    results['ready'] = total_results > 0
    
    # Debug
    print(f"\n[AUTO RECALL] Query: {query[:50]}...")
    print(f"  - Recientes: {len(results['recent'])}")
    print(f"  - Contexto: {len(results['context'])}")
    print(f"  - Listo: {results['ready']}")
    
    return results


def get_context_summary(results: dict) -> str:
    """Genera un resumen legible del contexto encontrado"""
    summary = []
    
    if results.get('recent'):
        summary.append("📌 CONtexto RECIENTE:")
        for r in results['recent'][:2]:
            msg = r.get('message', r.get('text', ''))[:100]
            summary.append(f"  • {msg}...")
    
    if results.get('context'):
        summary.append("\n📌 Contexto relacionado:")
        for r in results['context'][:3]:
            msg = r.get('message', r.get('text', ''))[:80]
            summary.append(f"  • {msg}...")
    
    return "\n".join(summary) if summary else "Sin contexto relevante."


if __name__ == "__main__":
    # Test
    query = sys.argv[1] if len(sys.argv) > 1 else "test"
    r = auto_recall(query)
    print(f"\nResumen: {get_context_summary(r)}")
