#!/usr/bin/env python3
import os
import sys
# Añadir el directorio raíz al path para encontrar módulos internos
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if base_dir not in sys.path: sys.path.append(base_dir)
core_dir = os.path.join(base_dir, "core")
if core_dir not in sys.path: sys.path.append(core_dir)
"""
Self-Evolution Engine
Based on Silhouette Agency OS
Monitors performance, generates improvements, creates PRs
"""
import json
import os
from datetime import datetime
from enum import Enum

class EvolutionLevel(Enum):
    LOW = "low"          # Docs, comments
    MEDIUM = "medium"   # Scripts sin impacto
    HIGH = "high"       # Comportamiento, memoria
    CRITICAL = "critical"  # Seguridad

class SelfEvolution:
    """
    Sistema de auto-evolución basado en feedback
    """
    
    def __init__(self):
        self.metrics = {
            'feedback_positive': 0,
            'feedback_negative': 0,
            'changes_proposed': 0,
            'changes_approved': 0,
            'changes_rejected': 0
        }
        self.load_state()
    
    def load_state(self):
        """Carga estado de evoluación"""
        try:
            with open(os.getenv('BRAIN_DATA_DIR', './data'/evolution_state.json') as f:
                data = json.load(f)
                self.metrics = data.get('metrics', self.metrics)
        except:
            pass
    
    def save_state(self):
        """Guarda estado"""
        with open(os.getenv('BRAIN_DATA_DIR', './data'/evolution_state.json', 'w') as f:
            json.dump({
                'metrics': self.metrics,
                'last_update': datetime.now().isoformat()
            }, f)
    
    def receive_feedback(self, feedback: str, is_positive: bool = True) -> dict:
        """Recibe feedback de Alberto"""
        if is_positive:
            self.metrics['feedback_positive'] += 1
        else:
            self.metrics['feedback_negative'] += 1
        
        # Clasificar feedback
        category = self.classify_feedback(feedback)
        
        self.save_state()
        
        return {
            'feedback': feedback,
            'type': 'positive' if is_positive else 'negative',
            'category': category,
            'metrics': self.metrics
        }
    
    def classify_feedback(self, feedback: str) -> str:
        """Clasifica el tipo de feedback"""
        feedback = feedback.lower()
        
        if any(x in feedback for x in ['error', 'fallo', 'incorrecto', 'mal']):
            return 'error'
        elif any(x in feedback for x in ['bien', 'perfecto', 'excelente', 'good']):
            return 'success'
        elif any(x in feedback for x in ['mejorar', 'podrías', 'deberías']):
            return 'improvement'
        else:
            return 'general'
    
    def analyze(self) -> dict:
        """Analiza patrones de feedback"""
        analysis = {
            'timestamp': datetime.now().isoformat(),
            'metrics': self.metrics,
            'issues': [],
            'suggestions': []
        }
        
        # Analizar errores recurrentes
        if self.metrics['feedback_negative'] > 5:
            analysis['issues'].append({
                'type': 'recurring_errors',
                'count': self.metrics['feedback_negative'],
                'action': 'Revisar patrones de errores'
            })
        
        # Calcular ratio de éxito
        total = self.metrics['feedback_positive'] + self.metrics['feedback_negative']
        if total > 0:
            ratio = self.metrics['feedback_positive'] / total
            analysis['success_ratio'] = ratio
            
            if ratio < 0.7:
                analysis['suggestions'].append({
                    'priority': 'HIGH',
                    'suggestion': 'Bajo ratio de éxito - revisar metodología'
                })
        
        return analysis
    
    def generate_proposal(self, issue: dict) -> dict:
        """Genera propuesta de mejora"""
        self.metrics['changes_proposed'] += 1
        self.save_state()
        
        proposal = {
            'id': f"EVOLUTION-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
            'issue': issue.get('type'),
            'description': issue.get('action'),
            'level': self.determine_level(issue),
            'timestamp': datetime.now().isoformat(),
            'status': 'pending_review',
            'requires_approval': True
        }
        
        # Guardar propuesta
        self.save_proposal(proposal)
        
        return proposal
    
    def determine_level(self, issue: dict) -> str:
        """Determina nivel de cambio"""
        issue_type = issue.get('type', '')
        
        if 'seguridad' in issue_type or 'credencial' in issue_type:
            return EvolutionLevel.CRITICAL.value
        elif 'memoria' in issue_type or 'comportamiento' in issue_type:
            return EvolutionLevel.HIGH.value
        else:
            return EvolutionLevel.MEDIUM.value
    
    def save_proposal(self, proposal: dict):
        """Guarda propuesta para revisión"""
        proposals_dir = os.getenv('BRAIN_DATA_DIR', './data'/proposals'
        os.makedirs(proposals_dir, exist_ok=True)
        
        with open(f"{proposals_dir}/{proposal['id']}.json", 'w') as f:
            json.dump(proposal, f, indent=2)
    
    def get_pending_proposals(self) -> list:
        """Obtiene propuestas pendientes"""
        proposals_dir = os.getenv('BRAIN_DATA_DIR', './data'/proposals'
        
        if not os.path.exists(proposals_dir):
            return []
        
        pending = []
        for f in os.listdir(proposals_dir):
            if f.endswith('.json'):
                with open(f"{proposals_dir}/{f}") as fp:
                    data = json.load(fp)
                    if data.get('status') == 'pending_review':
                        pending.append(data)
        
        return pending
    
    def approve_proposal(self, proposal_id: str) -> dict:
        """Aprueba una propuesta"""
        proposals_dir = os.getenv('BRAIN_DATA_DIR', './data'/proposals'
        filepath = f"{proposals_dir}/{proposal_id}.json"
        
        if not os.path.exists(filepath):
            return {'error': 'Proposal not found'}
        
        with open(filepath) as f:
            proposal = json.load(f)
        
        proposal['status'] = 'approved'
        proposal['approved_at'] = datetime.now().isoformat()
        
        with open(filepath, 'w') as f:
            json.dump(proposal, f, indent=2)
        
        self.metrics['changes_approved'] += 1
        self.save_state()
        
        return {'status': 'approved', 'proposal': proposal}
    
    def reject_proposal(self, proposal_id: str, reason: str = None) -> dict:
        """Rechaza una propuesta"""
        proposals_dir = os.getenv('BRAIN_DATA_DIR', './data'/proposals'
        filepath = f"{proposals_dir}/{proposal_id}.json"
        
        if not os.path.exists(filepath):
            return {'error': 'Proposal not found'}
        
        with open(filepath) as f:
            proposal = json.load(f)
        
        proposal['status'] = 'rejected'
        proposal['rejected_at'] = datetime.now().isoformat()
        proposal['reject_reason'] = reason
        
        with open(filepath, 'w') as f:
            json.dump(proposal, f, indent=2)
        
        self.metrics['changes_rejected'] += 1
        self.save_state()
        
        return {'status': 'rejected', 'proposal': proposal}
    
    def get_summary(self) -> str:
        """Resumen de evolución"""
        return f"""
=== SELF-EVOLUTION SUMMARY ===

Métricas:
- Feedback Positivo: {self.metrics['feedback_positive']}
- Feedback Negativo: {self.metrics['feedback_negative']}
- Cambios Propuestos: {self.metrics['changes_proposed']}
- Cambios Aprobados: {self.metrics['changes_approved']}
- Cambios Rechazados: {self.metrics['changes_rejected']}

Propuestas Pendientes: {len(self.get_pending_proposals())}
"""


# Singleton
_evolution = None

def get_self_evolution():
    global _evolution
    if _evolution is None:
        _evolution = SelfEvolution()
    return _evolution


if __name__ == "__main__":
    evo = get_self_evolution()
    print(evo.get_summary())
