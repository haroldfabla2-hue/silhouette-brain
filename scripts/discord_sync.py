#!/usr/bin/env python3
"""
Discord Memory Sync V2 - Versión Producción
Sincroniza conversaciones de TODOS los agentes a JSONL + Brain API
"""

import json
import os
import sys
import logging
from pathlib import Path
from datetime import datetime
import time
import traceback

# ============== CONFIGURACIÓN ==============
AGENTS_DIR = os.getenv("OPENCLAW_AGENTS_DIR", "/root/.openclaw/agents")
MEMORY_OUTPUT = os.getenv("MEMORY_OUTPUT_DIR", "/root/.openclaw/workspace/memory_discord")
STATE_FILE = f"{MEMORY_OUTPUT}/.sync_state_v2.json"
BRAIN_API_URL = os.getenv("BRAIN_API_URL", "http://localhost:9876")

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============== FUNCIONES ==============

def get_all_sessions():
    """Obtiene sesiones de TODOS los agentes"""
    sessions = []
    agents_path = Path(AGENTS_DIR)
    
    if not agents_path.exists():
        logger.info(f"Directorio de agentes no encontrado: {agents_path}")
        return sessions
    
    for agent_dir in agents_path.iterdir():
        if agent_dir.is_dir() and not agent_dir.name.startswith('.'):
            sessions_dir = agent_dir / "sessions"
            if sessions_dir.exists():
                for session_file in sessions_dir.glob("*.jsonl"):
                    sessions.append({
                        "path": session_file,
                        "agent": agent_dir.name
                    })
    
    logger.info(f"Encontradas {len(sessions)} sesiones de agentes")
    return sessions

def parse_message(line):
    """Parsea mensaje del formato OpenClaw JSONL"""
    try:
        data = json.loads(line)
        if data.get("type") == "message":
            msg_data = data.get("message", {})
            role = msg_data.get("role")
            content_parts = msg_data.get("content", [])
            
            text = ""
            if isinstance(content_parts, list):
                for part in content_parts:
                    if isinstance(part, dict) and part.get("type") == "text":
                        text = part.get("text", "")[:500]
                        break
            
            if role and text:
                return {
                    "role": role,
                    "content": text,
                    "timestamp": data.get("timestamp", ""),
                    "channel": "discord",
                    "source": "discord"
                }
    except json.JSONDecodeError as e:
        logger.debug(f"JSON decode error: {e}")
    except Exception as e:
        logger.error(f"Error parseando mensaje: {e}")
    return None

def check_brain_api():
    """Verifica si Brain API está disponible"""
    try:
        import requests
        response = requests.get(f"{BRAIN_API_URL}/api/status", timeout=5)
        return response.status_code in [200, 201]
    except:
        return False

def send_to_brain_api(messages):
    """Envía mensajes al Brain API"""
    try:
        import requests
        for msg in messages:
            response = requests.post(
                f"{BRAIN_API_URL}/api/memory",
                json={
                    "text": msg.get("content", "")[:500],
                    "importance": 0.7,
                    "tier": "MEDIUM"
                },
                timeout=30
            )
            if response.status_code not in [200, 201]:
                logger.debug(f"Error: {response.text}")
                return False
        return True
    except Exception as e:
        logger.debug(f"Brain API error: {e}")
        return False

def sync():
    """Sincroniza mensajes de Discord"""
    
    # Crear directorio de salida
    Path(MEMORY_OUTPUT).mkdir(parents=True, exist_ok=True)
    
    # Cargar estado
    state = {}
    if Path(STATE_FILE).exists():
        try:
            state = json.loads(Path(STATE_FILE).read_text())
        except:
            state = {}
    
    # Verificar Brain API
    brain_available = check_brain_api()
    logger.info(f"Brain API: {'✅ Disponible' if brain_available else '❌ No disponible'}")
    
    messages_saved = 0
    messages_to_brain = []
    
    # Procesar sesiones
    for session in get_all_sessions():
        session_file = session["path"]
        agent_name = session["agent"]
        file_path = str(session_file)
        
        last_offset = state.get(file_path, 0)
        
        try:
            lines = session_file.read_text().split('\n')
        except Exception as e:
            logger.error(f"Error leyendo {file_path}: {e}")
            continue
        
        new_count = 0
        for i, line in enumerate(lines):
            if i <= last_offset or not line.strip():
                continue
            
            msg = parse_message(line)
            if msg:
                msg["agent"] = agent_name
                
                # Guardar en JSONL
                with open(f"{MEMORY_OUTPUT}/discord_messages.jsonl", "a") as f:
                    f.write(json.dumps(msg, ensure_ascii=False) + "\n")
                
                # Guardar para Brain API
                messages_to_brain.append(msg)
                messages_saved += 1
                new_count += 1
        
        state[file_path] = len(lines)
        
        if new_count > 0:
            logger.info(f"  {agent_name}: {new_count} nuevos mensajes")
    
    # Guardar estado
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)
    
    # Enviar a Brain API si está disponible
    if brain_available and messages_to_brain:
        if send_to_brain_api(messages_to_brain):
            logger.info(f"✅ Enviados {len(messages_to_brain)} mensajes a Brain API")
        else:
            logger.info("❌ Error enviando a Brain API")
    
    return messages_saved

# ============== MAIN ==============
if __name__ == "__main__":
    logger.info("=" * 50)
    logger.info("Discord Memory Sync V2 - Producción")
    logger.info("=" * 50)
    
    try:
        start_time = time.time()
        count = sync()
        elapsed = time.time() - start_time
        
        logger.info(f"🎯 Total: {count} mensajes sincronizados en {elapsed:.2f}s")
        print(f"Discord V2: {count} mensajes sincronizados")
        
    except Exception as e:
        logger.error(f"Error fatal: {e}")
        traceback.print_exc()
        sys.exit(1)
