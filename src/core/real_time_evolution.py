#!/usr/bin/env python3
import os
import sys
# Añadir el directorio raíz al path para encontrar módulos internos
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if base_dir not in sys.path: sys.path.append(base_dir)
core_dir = os.path.join(base_dir, "core")
if core_dir not in sys.path: sys.path.append(core_dir)
"""
REAL-TIME SELF-EVOLUTION SYSTEM
Integrated with Memory + Introspection + Context Awareness

Based on research:
- Feedback loops (OpenAI Cookbook)
- Meta-cognition (Arxiv papers)
- Continuous self-improvement (EvoAgentX)
"""
import json
import os
from datetime import datetime

class RealTimeEvolution:
    """
    Sistema de evolución en tiempo real
    Integrado con mi memoria y autoconciencia
    """
    
    def __init__(self):
        self.evolution_path = os.getenv('BRAIN_DATA_DIR', './data')
        self.load_evolution_memory()
    
    def load_evolution_memory(self):
        """Carga mi memoria de evolución"""
        try:
            with open(f'{self.evolution_path}/evolution_memory.json') as f:
                self.evo_memory = json.load(f)
        except:
            self.evo_memory = {
                'self_knowledge': {},
                'code_awareness': {},
                'patterns': {},
                'learnings': [],
                'reflections': [],
                'real_time_analysis': []
            }
    
    def save_evolution_memory(self):
        """Guarda mi memoria de evolución"""
        with open(f'{self.evolution_path}/evolution_memory.json', 'w') as f:
            json.dump(self.evo_memory, f, indent=2)
    
    def classify_feedback(self, feedback: str) -> str:
        """Clasifica tipo de feedback"""
        f = feedback.lower()
        if any(x in f for x in ['error', 'fallo', 'bug', 'incorrecto']):
            return 'bug_fix'
        elif any(x in f for x in ['mejorar', 'podrías', 'deberías']):
            return 'improvement'
        elif any(x in f for x in ['bien', 'perfecto', 'excelente']):
            return 'positive'
        elif any(x in f for x in ['nunca', 'siempre', 'recuerda']):
            return 'rule'
        else:
            return 'general'
    
    def analyze_self(self) -> dict:
        """ANÁLISIS DE MÍ MISMA (Meta-cognición)"""
        try:
            with open(f'{self.evolution_path}/priority_memory.json') as f:
                memory = json.load(f)
                never_forget = memory.get('never_forget', [])
        except:
            never_forget = []
        
        self_analysis = {
            'timestamp': datetime.now().isoformat(),
            'memory_items': len(never_forget),
            'capabilities': [
                'Memoria biomimética 4 niveles',
                'Introspection Engine',
                'CEO Communication',
                'Query Agent System',
                'Self-Evolution (Real-Time)',
                'Context Awareness'
            ],
            'known_limitations': [
                'Dependo de OpenAI para embeddings',
                'No puedo ejecutar código sin approval',
                'Sesiones aisladas de agentes'
            ],
            'current_strengths': [],
            'areas_to_improve': []
        }
        
        patterns = self.evo_memory.get('patterns', {})
        for pattern_name, data in patterns.items():
            if data.get('count', 0) > 3:
                self_analysis['areas_to_improve'].append(pattern_name)
            if data.get('success_count', 0) > 5:
                self_analysis['current_strengths'].append(pattern_name)
        
        reflection = {
            'type': 'self_analysis',
            'data': self_analysis,
            'timestamp': datetime.now().isoformat()
        }
        self.evo_memory['self_knowledge'] = self_analysis
        self.evo_memory['reflections'].append(reflection)
        self.save_evolution_memory()
        
        return self_analysis
    
    def real_time_feedback_analysis(self, feedback: str, context: str = None) -> dict:
        """ANÁLISIS EN TIEMPO REAL"""
        feedback_lower = feedback.lower()
        
        analysis = {
            'timestamp': datetime.now().isoformat(),
            'feedback': feedback,
            'context': context,
            'type': self.classify_feedback(feedback),
            'root_cause': None,
            'pattern_detected': False,
            'learned': False,
            'action_taken': None
        }
        
        patterns = self.evo_memory.get('patterns', {})
        
        for pattern_name, pattern_data in patterns.items():
            if pattern_name in feedback_lower:
                analysis['pattern_detected'] = True
                pattern_data['count'] = pattern_data.get('count', 0) + 1
                pattern_data['last_seen'] = datetime.now().isoformat()
                analysis['learned'] = True
                analysis['action_taken'] = f"Patrón '{pattern_name}' reconocido"
        
        if not analysis['pattern_detected']:
            new_pattern = self.create_pattern(feedback)
            if new_pattern:
                analysis['learned'] = True
                analysis['action_taken'] = f"Nuevo patrón: {new_pattern['name']}"
        
        self.evo_memory['real_time_analysis'].append(analysis)
        self.evo_memory['real_time_analysis'] = self.evo_memory['real_time_analysis'][-50:]
        self.save_evolution_memory()
        
        return analysis
    
    def create_pattern(self, feedback: str) -> dict:
        """Crea nuevo patrón de aprendizaje"""
        f = feedback.lower()
        
        if 'voz' in f or 'audio' in f or 'tts' in f:
            pattern = {'name': 'tts_voice', 'type': 'behavior', 'count': 1, 'solution': 'es-ES-Chirp3-HD-Aoede'}
        elif 'memoria' in f or 'recuerda' in f:
            pattern = {'name': 'memory_recall', 'type': 'memory', 'count': 1, 'solution': 'Consultar memoria antes'}
        elif 'alucinar' in f:
            pattern = {'name': 'hallucination_prevention', 'type': 'behavior', 'count': 1, 'solution': 'Verificar facts'}
        else:
            pattern = None
        
        if pattern:
            self.evo_memory['patterns'][pattern['name']] = pattern
        
        return pattern
    
    def get_self_awareness(self) -> dict:
        """MI AUTOCONCIENCIA ACTUAL"""
        return {
            'timestamp': datetime.now().isoformat(),
            'patterns_learned': len(self.evo_memory.get('patterns', {})),
            'reflections': len(self.evo_memory.get('reflections', [])),
            'recent_analyses': len(self.evo_memory.get('real_time_analysis', [])),
            'self_knowledge': self.evo_memory.get('self_knowledge', {}),
            'patterns': self.evo_memory.get('patterns', {})
        }
    
    def run_continuous_loop(self):
        """EJECUTA EL LOOP CONTINUO"""
        self_analysis = self.analyze_self()
        
        opportunities = []
        patterns = self.evo_memory.get('patterns', {})
        for name, data in patterns.items():
            if data.get('count', 0) > 2:
                opportunities.append({'pattern': name, 'occurrences': data.get('count'), 'status': 'mastered'})
        
        return {'self_analysis': self_analysis, 'opportunities': opportunities, 'status': 'continuously_evolving'}


_real_time_evolution = None

def get_real_time_evolution():
    global _real_time_evolution
    if _real_time_evolution is None:
        _real_time_evolution = RealTimeEvolution()
    return _real_time_evolution

if __name__ == "__main__":
    print("=== REAL-TIME SELF-EVOLUTION ===\n")
    
    rte = get_real_time_evolution()
    
    print("1. Feedback analysis...")
    result = rte.real_time_feedback_analysis("Dejaste de usar la voz correcta para los audios")
    print(f"   Tipo: {result['type']} | Patrón: {result['pattern_detected']} | Acción: {result['action_taken']}")
    
    print("\n2. Self-awareness...")
    aw = rte.get_self_awareness()
    print(f"   Patrones: {aw['patterns_learned']} | Reflexiones: {aw['reflections']}")
    
    print("\n3. Continuous loop...")
    loop = rte.run_continuous_loop()
    print(f"   Estado: {loop['status']}")
    
    print("\n✅ Evolution real-time!")
