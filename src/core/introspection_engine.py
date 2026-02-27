import os
import sys
# Añadir el directorio raíz al path para encontrar módulos internos
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if base_dir not in sys.path: sys.path.append(base_dir)
core_dir = os.path.join(base_dir, "core")
if core_dir not in sys.path: sys.path.append(core_dir)
import os
#!/usr/bin/env python3
"""
Introspection Engine - Fixed
"""
import json
from datetime import datetime
from enum import Enum

class CognitivePhase(Enum):
    INTROSPECTION = "introspection"
    PLANNING = "planning"
    EXECUTION = "execution"
    REFLECTION = "reflection"

class IntrospectionEngine:
    def __init__(self):
        self.current_phase = CognitivePhase.INTROSPECTION
        self.cycle_count = 0
        self.last_reflection = None
        self.load_state()
    
    def load_state(self):
        try:
            with open(os.getenv('BRAIN_DATA_DIR', './data'/introspection_state.json') as f:
                data = json.load(f)
                self.cycle_count = data.get('cycle_count', 0)
                self.last_reflection = data.get('last_reflection')
        except:
            pass
    
    def save_state(self):
        with open(os.getenv('BRAIN_DATA_DIR', './data'/introspection_state.json', 'w') as f:
            json.dump({
                'cycle_count': self.cycle_count,
                'last_reflection': self.last_reflection,
                'last_updated': datetime.now().isoformat()
            }, f)
    
    def introspect(self) -> dict:
        """FASE 1: ¿Qué sé? ¿Qué necesito?"""
        self.current_phase = CognitivePhase.INTROSPECTION
        
        # Get memory directly, not via respond
        try:
            with open(os.getenv('BRAIN_DATA_DIR', './data'/priority_memory.json') as f:
                memory = json.load(f)
                never_forget_count = len(memory.get('never_forget', []))
        except:
            never_forget_count = 0
        
        return {
            'phase': 'INTROSPECTION',
            'cycle': self.cycle_count,
            'memory_items': never_forget_count,
            'questions': [
                '¿Qué sé sobre el tema?',
                '¿Qué necesita Alberto?',
                '¿Cómo está el equipo?'
            ]
        }
    
    def plan(self, context: dict) -> dict:
        """FASE 2: ¿Qué debo hacer?"""
        self.current_phase = CognitivePhase.PLANNING
        
        return {
            'phase': 'PLANNING',
            'suggestions': [
                'Revisar memoria',
                'Consultar reportes de equipo',
                'Preparar respuesta'
            ],
            'recommended': 'Revisar contexto'
        }
    
    def execute(self, action: str) -> dict:
        """FASE 3: Ejecutar"""
        self.current_phase = CognitivePhase.EXECUTION
        return {'phase': 'EXECUTION', 'action': action, 'status': 'done'}
    
    def reflect(self, result: dict) -> dict:
        """FASE 4: Reflexión"""
        self.current_phase = CognitivePhase.REFLECTION
        self.cycle_count += 1
        
        reflection = {
            'phase': 'REFLECTION',
            'action': result.get('action'),
            'count': self.cycle_count
        }
        
        self.last_reflection = reflection
        self.save_state()
        return reflection
    
    def run_cycle(self, query: str = None) -> dict:
        """Ejecuta un ciclo cognitivo completo"""
        intro = self.introspect()
        planning = self.plan(intro)
        
        return {
            'cycle': self.cycle_count,
            'introspection': intro,
            'planning': planning,
            'execution': None,
            'reflection': None
        }


_introspection = None

def get_introspection_engine():
    global _introspection
    if _introspection is None:
        _introspection = IntrospectionEngine()
    return _introspection
