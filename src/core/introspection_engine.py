#!/usr/bin/env python3
"""
Introspection Engine — Motor de autoevaluación cognitiva de Silhouette
"""
import os
import sys
import json
from datetime import datetime
from enum import Enum

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if base_dir not in sys.path:
    sys.path.append(base_dir)
core_dir = os.path.join(base_dir, "core")
if core_dir not in sys.path:
    sys.path.append(core_dir)

_DATA_DIR = os.getenv('BRAIN_DATA_DIR', os.path.join(base_dir, 'data'))


class CognitivePhase(Enum):
    INTROSPECTION = "introspection"
    PLANNING      = "planning"
    EXECUTION     = "execution"
    REFLECTION    = "reflection"


class IntrospectionEngine:
    def __init__(self):
        self.current_phase = CognitivePhase.INTROSPECTION
        self.cycle_count   = 0
        self.last_reflection = None
        self.load_state()

    def load_state(self):
        try:
            path = os.path.join(_DATA_DIR, 'introspection_state.json')
            with open(path) as f:
                data = json.load(f)
                self.cycle_count     = data.get('cycle_count', 0)
                self.last_reflection = data.get('last_reflection')
        except Exception:
            pass

    def save_state(self):
        try:
            os.makedirs(_DATA_DIR, exist_ok=True)
            path = os.path.join(_DATA_DIR, 'introspection_state.json')
            with open(path, 'w') as f:
                json.dump({
                    'cycle_count':    self.cycle_count,
                    'last_reflection': self.last_reflection,
                    'last_updated':   datetime.now().isoformat()
                }, f, indent=2)
        except Exception:
            pass

    def introspect(self) -> dict:
        """FASE 1: ¿Qué sé? ¿Qué necesito?"""
        self.current_phase = CognitivePhase.INTROSPECTION

        never_forget_count = 0
        memory_summary     = {}
        try:
            path = os.path.join(_DATA_DIR, 'priority_memory.json')
            with open(path) as f:
                memory = json.load(f)
                never_forget_count = len(memory.get('never_forget', []))
                memory_summary = {
                    'never_forget': never_forget_count,
                    'important':    len(memory.get('important', [])),
                }
        except Exception:
            pass

        # Métricas del daemon
        daemon_state = {}
        try:
            path = os.path.join(_DATA_DIR, 'unified_daemon_state.json')
            with open(path) as f:
                ds = json.load(f)
                daemon_state = {
                    'run_counts': ds.get('task_run_count', {}),
                    'err_counts': ds.get('task_err_count', {}),
                    'updated_at': ds.get('updated_at'),
                }
        except Exception:
            pass

        return {
            'phase':        'INTROSPECTION',
            'cycle':        self.cycle_count,
            'memory':       memory_summary,
            'daemon':       daemon_state,
            'timestamp':    datetime.now().isoformat(),
            'questions': [
                '¿Qué sé sobre el tema actual?',
                '¿Hay gaps de información que debería investigar?',
                '¿Qué necesita Alberto ahora mismo?',
                '¿Qué sistemas están degradados y debo reparar?',
            ]
        }

    def plan(self, context: dict) -> dict:
        """FASE 2: ¿Qué debo hacer?"""
        self.current_phase = CognitivePhase.PLANNING

        errs = context.get('daemon', {}).get('err_counts', {})
        suggestions = []
        for task, count in errs.items():
            if count > 0:
                suggestions.append(f'Reparar tarea {task} ({count} errores acumulados)')
        suggestions += ['Revisar memoria para contexto del usuario', 'Preparar respuesta proactiva']

        return {
            'phase':       'PLANNING',
            'suggestions': suggestions,
            'recommended': suggestions[0] if suggestions else 'Revisar contexto',
        }

    def execute(self, action: str) -> dict:
        """FASE 3: Ejecutar"""
        self.current_phase = CognitivePhase.EXECUTION
        return {'phase': 'EXECUTION', 'action': action, 'status': 'done'}

    def reflect(self, result: dict) -> dict:
        """FASE 4: Reflexión"""
        self.current_phase = CognitivePhase.REFLECTION
        self.cycle_count  += 1
        reflection = {
            'phase':  'REFLECTION',
            'action': result.get('action'),
            'count':  self.cycle_count,
            'ts':     datetime.now().isoformat(),
        }
        self.last_reflection = reflection
        self.save_state()
        return reflection

    def run_cycle(self, query: str = None) -> dict:
        """Ejecuta un ciclo cognitivo completo."""
        intro    = self.introspect()
        planning = self.plan(intro)
        return {
            'cycle':         self.cycle_count,
            'introspection': intro,
            'planning':      planning,
            'execution':     None,
            'reflection':    None,
        }


_introspection = None

def get_introspection_engine():
    global _introspection
    if _introspection is None:
        _introspection = IntrospectionEngine()
    return _introspection
