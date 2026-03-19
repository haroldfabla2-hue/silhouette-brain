#!/usr/bin/env python3
"""
Introspection Engine — Motor de autoevaluación cognitiva de Silhouette
Versión mejorada con auto-reflexión y memoria de errores.
"""
import os
import sys
import json
from datetime import datetime
from enum import Enum

base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
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

    # ─────────────────────────────────────────────────────────────────────────────
    # AUTO-REFLEXIÓN: Memoria de errores y correcciones
    # ─────────────────────────────────────────────────────────────────────────────
    
    def _get_mistakes_file(self) -> str:
        """Path al archivo de errores."""
        return os.path.join(_DATA_DIR, 'silhouette_mistakes.json')
    
    def _load_mistakes(self) -> list:
        """Carga la lista de errores."""
        try:
            path = self._get_mistakes_file()
            if os.path.exists(path):
                with open(path) as f:
                    return json.load(f)
        except Exception:
            pass
        return []
    
    def _save_mistakes(self, mistakes: list):
        """Guarda la lista de errores."""
        try:
            os.makedirs(_DATA_DIR, exist_ok=True)
            path = self._get_mistakes_file()
            with open(path, 'w') as f:
                json.dump(mistakes, f, indent=2)
        except Exception:
            pass
    
    def record_mistake(self, context: str, error: str, correction: str) -> dict:
        """
        Registra un error que cometí + la corrección.
        Esto me permite no repetir el mismo error.
        """
        mistakes = self._load_mistakes()
        
        entry = {
            'id': f"mistake_{len(mistakes)}_{int(datetime.now().timestamp())}",
            'timestamp': datetime.now().isoformat(),
            'context': context[:200],
            'error': error[:300],
            'correction': correction[:300],
            'resolved': False
        }
        
        mistakes.append(entry)
        mistakes = mistakes[-50:]
        self._save_mistakes(mistakes)
        
        # También guardar en Brain API
        self._save_to_brain_api(
            f"ERROR: {error} | CORRECCIÓN: {correction} | CONTEXTO: {context[:100]}",
            tags=['error', 'correccion', 'autonomia']
        )
        
        return {'status': 'recorded', 'mistake_id': entry['id']}
    
    def check_past_mistakes(self, context: str, query: str = None) -> list:
        """Busca errores similares en contextos anteriores."""
        mistakes = self._load_mistakes()
        matches = []
        search_text = (context + " " + (query or "")).lower()
        
        for m in mistakes[-20:]:
            error_text = (m.get('error', '') + " " + m.get('context', '')).lower()
            context_words = set(search_text.split())
            error_words = set(error_text.split())
            common = context_words & error_words
            
            # Threshold mínimo de 1 palabra en común
            if len(common) >= 1:
                matches.append({
                    'error': m.get('error'),
                    'correction': m.get('correction'),
                    'timestamp': m.get('timestamp')
                })
        
        return matches[:5]
    
    def record_correction(self, original_response: str, correction: str, user_comment: str = None) -> dict:
        """Registra cuando el usuario me corrige."""
        return self.record_mistake(
            context=user_comment or "Corrección del usuario",
            error=original_response[:300],
            correction=correction[:300]
        )
    
    def auto_reflect_on_action(self, action: str, result: str, query: str = None) -> dict:
        """Después de una acción importante, registra y reflexiona automáticamente."""
        reflection = self.reflect({'action': action, 'result': result})
        
        self._save_to_brain_api(
            f"REFLEXIÓN: {action} → {result[:150]}",
            tags=['reflexion', 'autonomia', 'ciclo_cognitivo']
        )
        
        return reflection
    
    def _save_to_brain_api(self, content: str, tags: list):
        """Guarda en la Brain API para búsqueda semántica."""
        try:
            import urllib.request
            payload = json.dumps({
                'content': content,
                'tags': tags,
                'importance': 0.8
            }).encode('utf-8')
            
            req = urllib.request.Request(
                'http://127.0.0.1:9876/api/memory',
                data=payload,
                headers={'Content-Type': 'application/json'}
            )
            urllib.request.urlopen(req, timeout=5)
        except Exception:
            pass

    # ─────────────────────────────────────────────────────────────────────────────
    # FASE 3: Detección Automática de Correcciones + Auto-Reflexión
    # ─────────────────────────────────────────────────────────────────────────────
    
    # Patrones que indican que el usuario me está corrigiendo
    CORRECTION_PATTERNS = [
        r"no,\s*(es|es\s+que|es\s+para)",
        r"te\s+equivocaste",
        r"no\s+es\s+(correcto|así)",
        r"actually\s*,",
        r"wait,\s*(that's|this)",
        r"wrong",
        r"incorrect",
        r"mejor\s+(dicho|dice)",
        r"quería\s+decir",
        r"me\s+refiero",
        r"olvidaste\s+que",
        r"no\s+entendiste",
        r"eso\s+no\s+es",
    ]
    
    def detect_correction(self, user_message: str, my_previous_response: str = None) -> dict:
        """
        Detecta si el usuario me está corrigiendo.
        Retorna: {'is_correction': bool, 'pattern': str, 'correction_text': str}
        """
        import re
        user_lower = user_message.lower()
        
        for pattern in self.CORRECTION_PATTERNS:
            if re.search(pattern, user_lower, re.IGNORECASE):
                # Extraer la corrección
                match = re.search(pattern, user_lower, re.IGNORECASE)
                start = max(0, match.start() - 50)
                correction_text = user_message[start:match.end() + 100]
                
                return {
                    'is_correction': True,
                    'pattern': pattern,
                    'correction_text': correction_text.strip(),
                    'user_message': user_message,
                    'my_previous_response': my_previous_response
                }
        
        return {'is_correction': False, 'pattern': None}
    
    def auto_process_correction(self, user_message: str, my_previous_response: str = None) -> dict:
        """
        Procesa automáticamente una corrección del usuario.
        Detecta + registra + reflexiona.
        """
        detection = self.detect_correction(user_message, my_previous_response)
        
        if detection['is_correction']:
            # Registrar el error
            result = self.record_mistake(
                context=f"Corrección detectada: {detection['pattern']}",
                error=my_previous_response[:300] if my_previous_response else "Respuesta incorrecta",
                correction=detection['correction_text'][:300]
            )
            
            # Auto-reflexionar
            self.auto_reflect_on_action(
                action=f"Corrección automática detectada",
                result=f"Patrón: {detection['pattern']} | Corrección: {detection['correction_text'][:100]}"
            )
            
            return {'status': 'recorded', 'detection': detection}
        
        return {'status': 'no_correction', 'detection': detection}
    
    def record_lesson_learned(self, category: str, lesson: str, action_taken: str = None) -> dict:
        """
        Registra una lección aprendida (patrón de Claude Code).
        Categorías: skill_gap, friction, knowledge, automation
        """
        VALID_CATEGORIES = ['skill_gap', 'friction', 'knowledge', 'automation']
        if category not in VALID_CATEGORIES:
            category = 'skill_gap'
        
        lessons_file = os.path.join(_DATA_DIR, 'lessons_learned.json')
        
        try:
            if os.path.exists(lessons_file):
                with open(lessons_file) as f:
                    lessons = json.load(f)
            else:
                lessons = []
        except:
            lessons = []
        
        lesson_entry = {
            'id': f"lesson_{len(lessons)}_{int(datetime.now().timestamp())}",
            'timestamp': datetime.now().isoformat(),
            'category': category,
            'lesson': lesson[:500],
            'action_taken': action_taken[:200] if action_taken else None,
            'resolved': False
        }
        
        lessons.append(lesson_entry)
        lessons = lessons[-50:]  # Mantener últimas 50
        
        try:
            with open(lessons_file, 'w') as f:
                json.dump(lessons, f, indent=2)
        except:
            pass
        
        # También guardar en Brain API
        self._save_to_brain_api(
            f"Lección aprendida [{category}]: {lesson}",
            tags=['leccion', 'autonomia', category]
        )
        
        return {'status': 'recorded', 'lesson_id': lesson_entry['id']}
    
    def get_recent_lessons(self, category: str = None, limit: int = 5) -> list:
        """Obtiene lecciones aprendidas recientes."""
        lessons_file = os.path.join(_DATA_DIR, 'lessons_learned.json')
        
        try:
            if os.path.exists(lessons_file):
                with open(lessons_file) as f:
                    lessons = json.load(f)
            else:
                return []
        except:
            return []
        
        if category:
            lessons = [l for l in lessons if l.get('category') == category]
        
        return lessons[-limit:]


_introspection = None

def get_introspection_engine():
    global _introspection
    if _introspection is None:
        _introspection = IntrospectionEngine()
    return _introspection
