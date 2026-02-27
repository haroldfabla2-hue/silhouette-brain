import os
#!/usr/bin/env python3
"""
UNIFIED RESPONSE SYSTEM v6
Includes: Memory + Introspection + Real-Time Evolution + Self-Awareness
"""
import sys
sys.path.insert(0, os.getenv('BRAIN_SRC_DIR', os.path.dirname(os.path.abspath(__file__))))
from memory_noise_filter import should_skip_ingestion

def respond_with_context(query: str) -> dict:
    """Mi flujo completo ANTES de responder"""
    
    # === FASE 1: SELF-EVOLUTION (Real-time) ===
    from real_time_evolution import get_real_time_evolution
    rte = get_real_time_evolution()
    evolution = rte.run_continuous_loop()
    
    # === FASE 2: INTROSPECTION ===
    from introspection_engine import get_introspection_engine
    intro = get_introspection_engine()
    intro_data = intro.run_cycle(query)
    
    # === FASE 3: MEMORY ===
    from context_engine import get_complete_context
    memory = get_complete_context(query)
    
    # === FASE 4: EQUIPO ===
    from ceo_communication import get_ceo_communication
    ceo = get_ceo_communication()
    team_reports = ceo.get_summary()
    
    return {
        'query': query,
        
        # Self-Evolution
        'evolution': {
            'status': evolution['status'],
            'opportunities': evolution['opportunities'],
            'self_knowledge': evolution['self_analysis'].get('capabilities', [])
        },
        
        # Introspection
        'introspection': intro_data,
        
        # Memory
        'memory': {
            'never_forget': len(memory.get('level_1_never_forget', [])),
            'team': len(memory.get('level_2_team', [])),
            'projects': len(memory.get('level_3_projects', []))
        },
        
        # Team
        'team_reports': team_reports[:200],
        
        'ready': True
    }


def save_assistant_response(response: str, source: str = 'silhouette:session'):
    """Guarda mi respuesta + aprende"""
    from memory_core_embeddings import get_memory_core
    from enhanced_memory import get_enhanced_memory

    if should_skip_ingestion(response):
        return {'stored': False, 'id': None, 'reason': 'runtime_operational_noise'}

    core = get_memory_core()
    memory = get_enhanced_memory()

    # Guardar en memoria
    msg_id = core.store_message("assistant", response)
    if msg_id:
        memory.process('assistant', response, source)
        return {'stored': True, 'id': msg_id}

    return {'stored': False, 'id': None, 'reason': 'runtime_operational_noise'}


def analyze_feedback_realtime(feedback: str):
    """Analiza feedback en tiempo real"""
    from real_time_evolution import get_real_time_evolution
    rte = get_real_time_evolution()
    return rte.real_time_feedback_analysis(feedback)


if __name__ == "__main__":
    r = respond_with_context("test")
    print(f"Evolution: {r['evolution']['status']}")
    print(f"Introspection: {r['introspection']['introspection']['phase']}")
    print(f"Memory: {r['memory']}")
