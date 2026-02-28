#!/usr/bin/env python3
"""
Discord Memory Sync V2 - Lee TODOS los agentes
Guarda en JSONL (backup) - NO depende de Neo4j
"""

import json
from pathlib import Path

# Paths - TODOS los agentes
AGENTS_DIR = "/root/.openclaw/agents"
MEMORY_OUTPUT = "/root/.openclaw/workspace/memory_discord"
STATE_FILE = f"{MEMORY_OUTPUT}/.sync_state_v2.json"

def get_all_sessions():
    """Obtiene sesiones de TODOS los agentes"""
    sessions = []
    agents_path = Path(AGENTS_DIR)
    if not agents_path.exists():
        return sessions
    
    for agent_dir in agents_path.iterdir():
        if agent_dir.is_dir():
            sessions_dir = agent_dir / "sessions"
            if sessions_dir.exists():
                for session_file in sessions_dir.glob("*.jsonl"):
                    sessions.append(session_file)
    return sessions

def parse_message(line):
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
                return {"role": role, "content": text, "timestamp": data.get("timestamp", ""), "channel": "discord", "source": "discord"}
    except:
        pass
    return None

def sync():
    """Sincroniza mensajes - solo JSONL (no requiere Neo4j)"""
    Path(MEMORY_OUTPUT).mkdir(parents=True, exist_ok=True)
    
    state = json.loads(Path(STATE_FILE).read_text()) if Path(STATE_FILE).exists() else {}
    messages_saved = 0
    
    for session_file in get_all_sessions():
        file_path = str(session_file)
        last_offset = state.get(file_path, 0)
        
        lines = session_file.read_text().split('\n')
        
        for i, line in enumerate(lines):
            if i <= last_offset or not line.strip():
                continue
            msg = parse_message(line)
            if msg:
                # Guardar en JSONL
                with open(f"{MEMORY_OUTPUT}/discord_messages.jsonl", "a") as f:
                    f.write(json.dumps(msg, ensure_ascii=False) + "\n")
                messages_saved += 1
        
        state[file_path] = len(lines)
    
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)
    
    return messages_saved

if __name__ == "__main__":
    count = sync()
    print(f"Discord V2: {count} mensajes sincronizados")
