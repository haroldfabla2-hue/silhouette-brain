#!/usr/bin/env python3
"""
Self-Memory Registry - Registro automático de pensamientos, decisiones y resultados
========================================================================
Este script registra automáticamente:
1. Pensamientos internos
2. Decisiones de coordinación
3. Resultados de ciclos de agentes
4. Insights

Todo se guarda en la Brain API con embeddings automáticos.
"""

import json
import os
import sys
import urllib.request
import urllib.parse
from datetime import datetime
from pathlib import Path

# Configuración
BRAIN_API = os.getenv("BRAIN_API_URL", "http://127.0.0.1:9876")
BRAIN_DATA = Path(os.getenv("BRAIN_DATA_DIR", "/root/silhouette-brain/data"))

# Archivo de estado
STATE_FILE = BRAIN_DATA / "self_memory_registry.json"


def save_to_brain(content: str, tags: list, importance: float = 0.7) -> bool:
    """Guarda contenido en la Brain API."""
    try:
        payload = json.dumps({
            "content": content,
            "tags": tags,
            "importance": importance
        }).encode('utf-8')
        
        req = urllib.request.Request(
            f"{BRAIN_API}/api/memory",
            data=payload,
            headers={"Content-Type": "application/json"}
        )
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception as e:
        print(f"[self_memory] Error guardando: {e}")
        return False


def load_state() -> dict:
    """Carga el estado anterior."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except:
            return {"decisions": [], "insights": [], "agent_results": []}
    return {"decisions": [], "insights": [], "agent_results": []}


def save_state(state: dict):
    """Guarda el estado."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def register_decision(decision: str, reason: str, agent: str = None):
    """Registra una decisión de coordinación."""
    state = load_state()
    
    entry = {
        "timestamp": datetime.now().isoformat(),
        "decision": decision,
        "reason": reason,
        "agent": agent
    }
    
    state["decisions"].append(entry)
    
    # Guardar en Brain API
    content = f"DECISIÓN: {decision} | Razón: {reason}"
    if agent:
        content += f" | Agente: {agent}"
    
    save_to_brain(content, tags=["decision", "coordinacion", "silhouette"], importance=0.8)
    
    # Mantener solo últimos 50
    state["decisions"] = state["decisions"][-50:]
    save_state(state)
    print(f"[self_memory] Decisión registrada: {decision[:50]}...")


def register_insight(insight: str, source: str = "heartbeat"):
    """Registra un insight o pensamiento."""
    state = load_state()
    
    entry = {
        "timestamp": datetime.now().isoformat(),
        "insight": insight,
        "source": source
    }
    
    state["insights"].append(entry)
    
    # Guardar en Brain API
    save_to_brain(
        f"INSIGHT ({source}): {insight}",
        tags=["insight", "pensamiento", "silhouette"],
        importance=0.7
    )
    
    # Mantener solo últimos 50
    state["insights"] = state["insights"][-50:]
    save_state(state)
    print(f"[self_memory] Insight registrado: {insight[:50]}...")


def register_agent_result(agent: str, task: str, result: str, status: str):
    """Registra el resultado de un ciclo de agente."""
    state = load_state()
    
    entry = {
        "timestamp": datetime.now().isoformat(),
        "agent": agent,
        "task": task,
        "result": result[:200] if len(result) > 200 else result,
        "status": status
    }
    
    state["agent_results"].append(entry)
    
    # Guardar en Brain API
    save_to_brain(
        f"AGENTE {agent.upper()}: {task} → {status} | Resultado: {result[:100]}",
        tags=["agente", "resultado", agent, "silhouette"],
        importance=0.8
    )
    
    # Mantener solo últimos 50
    state["agent_results"] = state["agent_results"][-50:]
    save_state(state)
    print(f"[self_memory] Resultado de {agent}: {task[:30]}... ({status})")


def auto_discovery():
    """
    Auto-descubrimiento: detecta y registra automáticamente:
    - Sesiones recientes de agentes
    - Reportes generados
    - patterns en la actividad
    """
    from pathlib import Path
    
    # Buscar reportes de agentes
    reports_dir = Path("/root/.openclaw/workspace/agents")
    if reports_dir.exists():
        for agent_dir in reports_dir.iterdir():
            if agent_dir.is_dir():
                # Tomar el reporte más reciente
                report_files = sorted(agent_dir.glob("reports/*.md"), key=lambda x: x.stat().st_mtime, reverse=True)
                if report_files:
                    latest = report_files[0]
                    mtime = datetime.fromtimestamp(latest.stat().st_mtime)
                    
                    # Si es reciente (última hora)
                    if (datetime.now() - mtime).total_seconds() < 3600:
                        content = latest.read_text()[:300]
                        save_to_brain(
                            f"REPORTE {agent_dir.name.upper()}: {content}",
                            tags=["reporte", agent_dir.name, "auto"],
                            importance=0.6
                        )
    
    print("[self_memory] Auto-discovery completado")


# CLI
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: self_memory.py <command> [args]")
        print("Commands:")
        print("  decision <decision> <reason> [agent]")
        print("  insight <insight> [source]")
        print("  agent <agent> <task> <result> <status>")
        print("  auto-discovery")
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    if cmd == "decision":
        decision = sys.argv[2]
        reason = sys.argv[3] if len(sys.argv) > 3 else ""
        agent = sys.argv[4] if len(sys.argv) > 4 else None
        register_decision(decision, reason, agent)
    
    elif cmd == "insight":
        insight = sys.argv[2]
        source = sys.argv[3] if len(sys.argv) > 3 else "manual"
        register_insight(insight, source)
    
    elif cmd == "agent":
        agent = sys.argv[2]
        task = sys.argv[3]
        result = sys.argv[4]
        status = sys.argv[5] if len(sys.argv) > 5 else "unknown"
        register_agent_result(agent, task, result, status)
    
    elif cmd == "auto-discovery":
        auto_discovery()
    
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
