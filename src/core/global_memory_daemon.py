#!/usr/bin/env python3
"""
Global Memory Sync Daemon (Definitive Root Solution)
====================================================
Sincroniza dinámicamente CUALQUIER canal (Discord, Slack, Telegram, etc.) 
y las sesiones de CUALQUIER agente hacia el sistema de Memoria de 4 Capas 
(SilhouetteAutoMemory -> SQLite -> Neo4j via Dreamer).

Beneficios:
- Escala a futuros canales automáticamente sin tocar código.
- Desacoplado de OpenClaw.
- Mantiene el estado (offsets) para no duplicar datos.
- Prepara los datos para que el motor "Dreamer" los lleve al Grafo (Neo4j).
"""

import json
import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv("/home/ubuntu/.openclaw/workspace/silhouette-brain/.env")

# Inyectar path del cerebro para usar la memoria nativa
BRAIN_SRC_DIR = os.getenv('BRAIN_SRC_DIR', '/home/ubuntu/.openclaw/workspace/silhouette-brain/src/core')
sys.path.insert(0, BRAIN_SRC_DIR)

# Intentar importar la memoria automática de 4 capas
try:
    from auto_memory import SilhouetteAutoMemory
    memory_system = SilhouetteAutoMemory()
    HAS_MEMORY = True
    print("✅ [GLOBAL SYNC] Conectado exitosamente al Sistema de Memoria de Silhouette.")
except Exception as e:
    print(f"⚠️ [GLOBAL SYNC] Error conectando a SilhouetteAutoMemory: {e}")
    HAS_MEMORY = False
    memory_system = None

# Rutas base a monitorizar
OPENCLAW_WORKSPACE = Path("/home/ubuntu/.openclaw/workspace")
OPENCLAW_AGENTS = Path("/home/ubuntu/.openclaw/agents")
STATE_FILE = Path(os.getenv("BRAIN_DATA_DIR", "/home/ubuntu/.openclaw/workspace/silhouette-brain/data")) / "global_sync_state.json"

def get_all_target_files():
    """Descubre dinámicamente todos los archivos de sesión y canales."""
    target_files = []
    
    # 1. Escanear todos los canales en workspace (ej. memory_discord, memory_slack)
    if OPENCLAW_WORKSPACE.exists():
        for channel_dir in OPENCLAW_WORKSPACE.glob("memory_*"):
            if channel_dir.is_dir():
                for jsonl_file in channel_dir.glob("*.jsonl"):
                    channel_name = channel_dir.name.replace("memory_", "")
                    target_files.append((jsonl_file, f"channel_{channel_name}"))

    # 2. Escanear todas las sesiones de agentes (ej. agents/main/sessions/*.jsonl)
    if OPENCLAW_AGENTS.exists():
        for agent_dir in OPENCLAW_AGENTS.iterdir():
            sessions_dir = agent_dir / "sessions"
            if sessions_dir.is_dir():
                for jsonl_file in sessions_dir.glob("*.jsonl"):
                    if not jsonl_file.name.endswith(".lock"):
                        target_files.append((jsonl_file, f"agent_{agent_dir.name}"))

    # 3. Sesiones multi-agente globales
    multi_agent_dir = OPENCLAW_WORKSPACE / "multi-agent"
    if multi_agent_dir.exists():
        for jsonl_file in multi_agent_dir.glob("*.jsonl"):
            target_files.append((jsonl_file, "multi_agent_session"))

    return target_files

def parse_message(line):
    """Parsea el formato mixto de logs de OpenClaw."""
    try:
        data = json.loads(line)
        # Filtrar eventos del sistema que no son mensajes
        if data.get("type") in ["session", "model_change", "tool_call", "tool_result"]:
            return None
            
        # Algunos archivos guardan el msg directo, otros lo anidan en 'message'
        msg_data = data.get("message", data)
        role = msg_data.get("role", "unknown")
        content_parts = msg_data.get("content", [])
        
        text = ""
        if isinstance(content_parts, list):
            texts = []
            for part in content_parts:
                if isinstance(part, dict) and part.get("type") == "text":
                    texts.append(part.get("text", ""))
            text = " ".join(texts)
        elif isinstance(content_parts, str):
            text = content_parts
            
        if role and text and len(text.strip()) > 0:
            return {
                "role": role, 
                "content": text[:1000], # Incrementado límite para mejor contexto semántico
                "source": data.get("channel", data.get("source", "openclaw"))
            }
    except:
        pass
    return None

def run_sync_cycle(state):
    """Ejecuta un ciclo completo de sincronización."""
    files_to_process = get_all_target_files()
    total_new_messages = 0
    
    for file_path, source_tag in files_to_process:
        path_str = str(file_path)
        last_offset = state.get(path_str, 0)
        
        if not file_path.exists():
            continue
            
        try:
            # Leer todas las líneas (se asume que son archivos rotativos manejables)
            content = file_path.read_text(encoding='utf-8')
            lines = content.split('\n')
            
            new_lines_count = 0
            
            for i, line in enumerate(lines):
                # Saltar las líneas ya procesadas
                if i < last_offset or not line.strip():
                    continue
                    
                msg = parse_message(line)
                if msg and HAS_MEMORY:
                    try:
                        # Inyectar en Memoria de 4 Capas
                        tags = ["global-sync", source_tag, msg["source"]]
                        # Limpiar tags vacíos o repetidos
                        tags = list(set([t for t in tags if t]))
                        
                        memory_system.process_message(
                            speaker=msg["role"],
                            message=msg["content"],
                            tags=tags
                        )
                        new_lines_count += 1
                        total_new_messages += 1
                    except Exception as mem_err:
                        print(f"⚠️ [GLOBAL SYNC] Error insertando en memoria: {mem_err}")
            
            # Actualizar offset
            state[path_str] = len(lines)
            
            if new_lines_count > 0:
                print(f"📥 [GLOBAL SYNC] {new_lines_count} mensajes nuevos de {source_tag}")
                
        except Exception as file_err:
            print(f"⚠️ [GLOBAL SYNC] Error leyendo archivo {path_str}: {file_err}")

    return total_new_messages

def daemon_mode():
    """Bucle infinito del Daemon."""
    print("🚀 [GLOBAL SYNC DAEMON] Iniciando...")
    
    # Asegurar directorio de datos
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    while True:
        try:
            # Cargar estado
            state = {}
            if STATE_FILE.exists():
                with open(STATE_FILE, "r") as f:
                    state = json.load(f)
            
            # Ejecutar ciclo
            new_msgs = run_sync_cycle(state)
            
            # Guardar estado
            with open(STATE_FILE, "w") as f:
                json.dump(state, f)
                
            if new_msgs > 0:
                print(f"✅ [GLOBAL SYNC] Ciclo completado. {new_msgs} nuevos recuerdos integrados para el Grafo/Neo4j.")
                
            # Esperar antes del siguiente ciclo
            time.sleep(120)
            
        except KeyboardInterrupt:
            print("\n🛑 [GLOBAL SYNC DAEMON] Detenido por el usuario.")
            break
        except Exception as e:
            print(f"💥 [GLOBAL SYNC ERROR FATAL] {e}")
            time.sleep(60) # Backoff en caso de error grave

if __name__ == "__main__":
    daemon_mode()
