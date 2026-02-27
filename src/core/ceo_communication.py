#!/usr/bin/env python3
import os
import sys
# Añadir el directorio raíz al path para encontrar módulos internos
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if base_dir not in sys.path: sys.path.append(base_dir)
core_dir = os.path.join(base_dir, "core")
if core_dir not in sys.path: sys.path.append(core_dir)
"""
CEO Communication System v2
Integrates with query_agent for complete team awareness
"""
import os
import json
from datetime import datetime
from query_agent import get_agent_querier

class CEOCommunication:
    """Sistema de comunicación CEO-Agentes"""
    
    AGENTS = ['roger', 'cami', 'rick', 'rose', 'jack', 'larry', 'flocky']
    
    def __init__(self):
        self.querier = get_agent_querier()
    
    def get_agent_report(self, agent: str) -> dict:
        """Obtiene reporte de un agente"""
        return self.querier.query(agent)
    
    def get_all_reports(self) -> dict:
        """Obtiene todos los reportes"""
        return self.querier.query_all()
    
    def get_summary(self) -> str:
        """Resumen de todos los agentes"""
        reports = self.querier.query_all()
        
        summary = "=== 📊 REPORTE DE EQUIPO ===\n\n"
        
        for agent in self.AGENTS:
            data = reports.get(agent, {})
            role = data.get('role', 'N/A')
            report = data.get('report', 'No hay reporte')
            
            if report and report != "No hay reportes":
                summary += f"✅ **{agent.upper()}** ({role})\n"
                summary += f"   {report[:150]}...\n\n"
            else:
                summary += f"⚠️ **{agent.upper()}** ({role}) - Sin reporte\n\n"
        
        return summary


_ceo_comm = None

def get_ceo_communication():
    global _ceo_comm
    if _ceo_comm is None:
        _ceo_comm = CEOCommunication()
    return _ceo_comm


if __name__ == "__main__":
    ceo = get_ceo_communication()
    print(ceo.get_summary())
