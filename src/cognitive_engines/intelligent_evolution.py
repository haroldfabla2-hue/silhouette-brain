#!/usr/bin/env python3
import os
import sys
# Añadir el directorio raíz al path para encontrar módulos internos
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if base_dir not in sys.path: sys.path.append(base_dir)
core_dir = os.path.join(base_dir, "core")
if core_dir not in sys.path: sys.path.append(core_dir)
"""
Intelligent Evolution System v2
Integrates: Introspection + Memory + Feedback + Self-Analysis + Repo Sync
"""
import json
import os
from datetime import datetime

class IntelligentEvolution:
    """
    Sistema de evolución inteligente que:
    1. Analiza patrones de errores/feedback
    2. Propone mejoras ROOT CAUSE
    3. Evalúa riesgo de cambios
    4. Sincroniza con repositorio
    5. Pide confirmación para cambios complejos
    """
    
    def __init__(self):
        self.evolution_path = '/root/silhouette-brain'
        self.public_repo_path = '/root/silhouette-claw-repo/silhouette-claw'
        self.private_repo_path = '/root/silhouette-system-state'
        self.load_intelligence()
    
    def load_intelligence(self):
        """Carga inteligencia acumulada"""
        try:
            with open(f'{self.evolution_path}/data/evolution_intelligence.json') as f:
                self.intel = json.load(f)
        except:
            self.intel = {
                'patterns': {},      # Patrones de errores
                'root_causes': {},   # Causas raíz identificadas
                'solutions': {},     # Soluciones aplicadas
                'risk_history': {},  # Historial de riesgo
                'evolution_log': []   # Log de evoluciones
            }
    
    def save_intelligence(self):
        """Guarda inteligencia"""
        with open(f'{self.evolution_path}/data/evolution_intelligence.json', 'w') as f:
            json.dump(self.intel, f, indent=2)
    
    def analyze_feedback_patterns(self, feedback: str) -> dict:
        """
        Analiza feedback para identificar:
        - Tipo de problema
        - Si es recurrente
        - Causa raíz
        - Solución propuesta
        """
        feedback_lower = feedback.lower()
        
        analysis = {
            'feedback': feedback,
            'timestamp': datetime.now().isoformat(),
            'type': self.classify_feedback(feedback),
            'is_recurring': False,
            'root_cause': None,
            'proposed_fix': None,
            'risk_level': 'low',
            'requires_approval': False
        }
        
        # Verificar si es recurrente
        for pattern in self.intel.get('patterns', {}):
            if pattern in feedback_lower:
                analysis['is_recurring'] = True
                analysis['root_cause'] = self.intel['patterns'][pattern].get('root_cause')
                analysis['proposed_fix'] = self.intel['patterns'][pattern].get('solution')
        
        # Clasificar riesgo
        risk_indicators = {
            'critical': ['seguridad', 'credencial', 'password', 'token', 'api key'],
            'high': ['memoria', 'comportamiento', 'personalidad', 'alucinar'],
            'medium': ['script', 'función', 'código'],
            'low': ['documentación', 'comentario', 'docs']
        }
        
        for level, indicators in risk_indicators.items():
            if any(ind in feedback_lower for ind in indicators):
                analysis['risk_level'] = level
                break
        
        # Determinar si requiere aprobación
        if analysis['risk_level'] in ['critical', 'high']:
            analysis['requires_approval'] = True
        
        return analysis
    
    def classify_feedback(self, feedback: str) -> str:
        """Clasifica el tipo de feedback"""
        f = feedback.lower()
        
        if 'error' in f or 'fallo' in f or 'bug' in f:
            return 'bug'
        elif 'mejorar' in f or 'podrías' in f:
            return 'improvement'
        elif 'bien' in f or 'perfecto' in f or 'excelente' in f:
            return 'success'
        elif 'nunca' in f or 'siempre' in f:
            return 'rule'
        else:
            return 'general'
    
    def identify_root_cause(self, feedback: str, analysis: dict) -> dict:
        """
        Identifica la causa raíz (no el síntoma)
        """
        root_cause = {
            'identified': False,
            'cause': None,
            'fix_type': None,
            'files_affected': [],
            'complexity': 'simple'
        }
        
        f = feedback.lower()
        
        # Análisis de causa raíz
        if 'voz' in f or 'audio' in f or 'tts' in f:
            root_cause = {
                'identified': True,
                'cause': 'Falta de enforcement de voz default en sistema TTS',
                'fix_type': 'config_update',
                'files_affected': ['TOOLS.md', 'SOUL.md'],
                'complexity': 'simple'
            }
        
        elif 'memoria' in f and ('olvidas' in f or 'no recuerdas' in f):
            root_cause = {
                'identified': True,
                'cause': 'Session sync no está capturando mensajes correctamente',
                'fix_type': 'integration_fix',
                'files_affected': ['session_sync.py', 'respond.py'],
                'complexity': 'medium'
            }
        
        elif 'alucinar' in f:
            root_cause = {
                'identified': True,
                'cause': 'Falta de verificación automática de facts',
                'fix_type': 'new_feature',
                'files_affected': ['introspection_engine.py'],
                'complexity': 'complex'
            }
            root_cause['requires_approval'] = True
        
        return root_cause
    
    def generate_evolution(self, feedback: str) -> dict:
        """
        Genera una evolución basada en feedback
        """
        # Analizar
        analysis = self.analyze_feedback_patterns(feedback)
        
        # Identificar causa raíz
        root_cause = self.identify_root_cause(feedback, analysis)
        
        # Determinar riesgo
        if root_cause.get('complexity') == 'complex':
            risk = 'high'
            requires_approval = True
        elif analysis.get('risk_level') in ['critical', 'high']:
            risk = analysis['risk_level']
            requires_approval = True
        else:
            risk = 'low'
            requires_approval = root_cause.get('requires_approval', False)
        
        evolution = {
            'id': f"EVOLUTION-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
            'feedback': feedback,
            'analysis': analysis,
            'root_cause': root_cause,
            'risk': risk,
            'requires_approval': requires_approval,
            'status': 'pending_review' if requires_approval else 'ready',
            'timestamp': datetime.now().isoformat()
        }
        
        # Guardar en inteligencia
        self.intel['evolution_log'].append(evolution)
        self.save_intelligence()
        
        return evolution
    
    def sync_from_repo(self) -> dict:
        """
        Sincroniza cambios del repositorio
        """
        import subprocess
        
        result = {
            'status': 'unknown',
            'changes': [],
            'applied': False
        }
        
        try:
            # Pull latest
            subprocess.run(['git', 'pull'], cwd=self.repo_path, capture_output=True)
            
            # Check for changes
            diff = subprocess.run(['git', 'diff', '--name-only'], 
                               cwd=self.repo_path, capture_output=True, text=True)
            
            result['changes'] = diff.stdout.strip().split('\n')
            result['status'] = 'synced'
            
            # Check if version changed
            version_file = f'{self.repo_path}/VERSION.md'
            if os.path.exists(version_file):
                with open(version_file) as f:
                    result['new_version'] = f.read().split('\n')[0]
            
        except Exception as e:
            result['status'] = 'error'
            result['error'] = str(e)
        
        return result
    
    def get_intelligence_summary(self) -> str:
        """Resumen de inteligencia"""
        patterns = len(self.intel.get('patterns', {}))
        evolutions = len(self.intel.get('evolution_log', []))
        root_causes = len(self.intel.get('root_causes', {}))
        
        return f"""
=== INTELLIGENT EVOLUTION ===

Patrones identificados: {patterns}
Causas raíz: {root_causes}
Evoluciones: {evolutions}

Última evolución:
"""
    
    def run_self_analysis(self) -> dict:
        """
        Auto-análisis para identificar oportunidades de mejora
        """
        from respond import respond_with_context
        
        # Consultar memoria sobre errores/feedbacks recientes
        context = respond_with_context("error problema mejora")
        
        analysis = {
            'timestamp': datetime.now().isoformat(),
            'context_found': len(context.get('relevant', [])),
            'opportunities': [],
            'recommendations': []
        }
        
        # Analizar patrones
        if self.intel.get('patterns'):
            recurring = [p for p, v in self.intel['patterns'].items() 
                       if v.get('count', 0) > 2]
            if recurring:
                analysis['opportunities'].append({
                    'type': 'recurring_patterns',
                    'items': recurring,
                    'action': 'Revisar patrones recurrentes'
                })
        
        return analysis


# Singleton
_intelligent_evolution = None

def get_intelligent_evolution():
    global _intelligent_evolution
    if _intelligent_evolution is None:
        _intelligent_evolution = IntelligentEvolution()
    return _intelligent_evolution


if __name__ == "__main__":
    ie = get_intelligent_evolution()
    print(ie.get_intelligence_summary())
    
    # Test with example feedback
    evo = ie.generate_evolution("Dejaste de usar la voz correcta para los audios")
    print(f"\nEvolución generada: {evo['id']}")
    print(f"Riesgo: {evo['risk']}")
    print(f"Requiere aprobación: {evo['requires_approval']}")
    print(f"Causa raíz: {evo['root_cause']}")
