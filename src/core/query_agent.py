#!/usr/bin/env python3
import os
import sys
# Añadir el directorio raíz al path para encontrar módulos internos
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if base_dir not in sys.path: sys.path.append(base_dir)
core_dir = os.path.join(base_dir, "core")
if core_dir not in sys.path: sys.path.append(core_dir)
"""
Query Agent System
Permite a Silhouette (CEO) consultar directamente a cualquier agente
"""
import subprocess
import json
from datetime import datetime

class AgentQuerier:
    """Consultar agentes directamente"""
    
    AGENTS = {
        'roger': {'role': 'Scout', 'prompt': 'Busca oportunidades freelance'},
        'cami': {'role': 'Researcher', 'prompt': 'Investiga temas'},
        'rick': {'role': 'Coder', 'prompt': 'Revisa código'},
        'rose': {'role': 'Analyst', 'prompt': 'Analiza métricas'},
        'jack': {'role': 'Planner', 'prompt': 'Organiza tareas'},
        'larry': {'role': 'Social', 'prompt': 'Crea contenido social'},
        'flocky': {'role': 'GitHub', 'prompt': 'Revisa repos'}
    }
    
    def query(self, agent: str, question: str = None) -> dict:
        """Consulta a un agente directamente"""
        
        if agent not in self.AGENTS:
            return {'error': f'Agente {agent} no encontrado'}
        
        # Get latest report from agent
        report = self.get_latest_report(agent)
        
        return {
            'agent': agent,
            'role': self.AGENTS[agent]['role'],
            'report': report,
            'timestamp': datetime.now().isoformat()
        }
    
    def get_latest_report(self, agent: str) -> str:
        """Obtiene el último reporte del agente"""
        import os
        report_dir = f"/root/.openclaw/workspace/agents/workspace-{agent}/reports"
        
        if not os.path.exists(report_dir):
            return "No hay reportes"
        
        # Get most recent report
        reports = sorted([f for f in os.listdir(report_dir) if f.endswith('.md')])
        
        if not reports:
            return "No hay reportes"
        
        latest = reports[-1]
        with open(f"{report_dir}/{latest}", 'r') as f:
            return f.read()[:1000]  # First 1000 chars
    
    def query_all(self) -> dict:
        """Consulta a todos los agentes"""
        return {agent: self.query(agent) for agent in self.AGENTS}


_querier = None

def get_agent_querier():
    global _querier
    if _querier is None:
        _querier = AgentQuerier()
    return _querier


if __name__ == "__main__":
    q = get_agent_querier()
    
    # Query Flocky
    result = q.query('flocky')
    print(f"=== FLOCKY ({result['role']}) ===")
    print(result['report'][:500])
    print()
    
    # Query all
    print("=== ALL AGENTS ===")
    all_results = q.query_all()
    for agent, data in all_results.items():
        status = "✅" if data.get('report') != "No hay reportes" else "⚠️"
        print(f"{status} {agent}: {data.get('role', 'N/A')}")
