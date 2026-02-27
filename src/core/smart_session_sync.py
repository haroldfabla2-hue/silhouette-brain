#!/usr/bin/env python3
"""
Smart Session Sync - ULTRA OPTIMIZED
====================================
- Sync en grupos de 20 mensajes
- Sin límite de rondas (procesa todo)
- Minimiza uso de memoria
"""
import json
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.getenv('BRAIN_SRC_DIR', os.path.dirname(os.path.abspath(__file__))))

from respond import respond_with_context, save_assistant_response
from agent_memory_readonly import invalidate_cache
from memory_noise_filter import should_skip_ingestion

AGENTS_DIR = "/root/.openclaw/agents"
STATE_FILE = os.getenv("BRAIN_DATA_DIR", "./data"/smart_sync_state.json"
BATCH_SIZE = 20  # Grupo de 20 mensajes

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        except:
            return {"offsets": {}, "last_sync": 0}
    return {"offsets": {}, "last_sync": 0}

def save_state(state):
    with open(STATE_FILE + '.tmp', 'w') as f:
        json.dump(state, f)
    os.replace(STATE_FILE + '.tmp', STATE_FILE)

def get_all_session_files():
    files = []
    for agent in os.listdir(AGENTS_DIR):
        agent_dir = os.path.join(AGENTS_DIR, agent, "sessions")
        if os.path.isdir(agent_dir):
            for f in os.listdir(agent_dir):
                if f.endswith('.jsonl') and not f.endswith('.lock'):
                    path = os.path.join(agent_dir, f)
                    files.append((path, agent, f))
    return files

def extract_content(line):
    try:
        data = json.loads(line)
        if data.get('type') == 'session' or data.get('type') == 'model_change':
            return None
        msg = data.get('message', {})
        content = msg.get('content', [])
        if isinstance(content, list):
            texts = []
            for block in content:
                if isinstance(block, dict):
                    text = block.get('text', '')
                    if text:
                        texts.append(text)
            return ' '.join(texts) if texts else None
        return content if isinstance(content, str) else None
    except:
        return None

def process_message(line, agent):
    """Procesa un mensaje individual"""
    content = extract_content(line)
    if not content or len(content) < 20:
        return False
    
    msg = f"[{agent.upper()}] {content[:500]}"
    if should_skip_ingestion(msg):
        return False
    
    try:
        data = json.loads(line)
        role = data.get('message', {}).get('role', 'unknown')
        
        if role in ['user', 'human']:
            respond_with_context(msg)
        else:
            save_assistant_response(msg)
        
        return True
    except:
        return False

def sync_sessions():
    """Sincroniza en grupos de 20 sin límite de rondas"""
    state = load_state()
    total_new = 0
    now = datetime.now()
    
    # Continuar hasta que no haya más mensajes pendientes
    while True:
        processed_this_batch = 0
        more_data = False
        
        for path, agent, filename in get_all_session_files():
            key = f"{agent}:{filename}"
            current_size = os.path.getsize(path)
            
            # Inicializar offset si no existe
            if key not in state["offsets"]:
                state["offsets"][key] = 0
            
            last_pos = state["offsets"][key]
            
            if current_size <= last_pos:
                continue
            
            more_data = True  # Hay datos pendientes
            
            with open(path, 'r') as f:
                f.seek(last_pos)
                new_lines = f.readlines()
            
            for line in new_lines:
                # Procesar en grupos de 20
                if processed_this_batch >= BATCH_SIZE:
                    # Guardar posición actual
                    if key not in state["offsets"]:
                        state["offsets"][key] = 0
                    state["offsets"][key] += len(line.encode('utf-8'))
                    save_state(state)
                    print(f"[SYNC] Grupo de {BATCH_SIZE} completado. Continuando en próxima ejecución...")
                    print(f"[SYNC] Total procesado hasta ahora: {total_new}")
                    state["last_sync"] = now.timestamp()
                    save_state(state)
                    return total_new
                
                if process_message(line, agent):
                    processed_this_batch += 1
                    total_new += 1
                
                # Actualizar offset después de cada mensaje
                if key not in state["offsets"]:
                    state["offsets"][key] = 0
                state["offsets"][key] += len(line.encode('utf-8'))
            
            # Archivo terminado - actualizar offset final
            state["offsets"][key] = current_size
        
        # Si procesó menos del batch size, terminamos
        if processed_this_batch < BATCH_SIZE:
            break
        
        # Si no hay más datos, terminamos
        if not more_data:
            break
    
    state["last_sync"] = now.timestamp()
    state["last_sync_time"] = now.isoformat()
    save_state(state)
    
    # Invalidar cache de memoria
    if total_new > 0:
        invalidate_cache()
    
    print(f"[SYNC] ✅ Total: {total_new} mensajes sincronizados")
    return total_new

if __name__ == "__main__":
    sync_sessions()
