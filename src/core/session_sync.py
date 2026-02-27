#!/usr/bin/env python3
"""
Session to Memory Sync - OPTIMIZED VERSION
With proper tags and reasonable frequency
"""
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.getenv('BRAIN_SRC_DIR', os.path.dirname(os.path.abspath(__file__))))

from respond import respond_with_context, save_assistant_response

AGENTS_DIR = "/root/.openclaw/agents"
STATE_FILE = os.getenv("BRAIN_DATA_DIR", "./data"/session_sync_state.json"

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    return {"offsets": {}, "last_full_sync": 0}

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f)

def get_all_session_files():
    files = []
    for agent in os.listdir(AGENTS_DIR):
        agent_dir = os.path.join(AGENTS_DIR, agent, "sessions")
        if os.path.isdir(agent_dir):
            for f in os.listdir(agent_dir):
                if f.endswith('.jsonl') and not f.endswith('.lock'):
                    path = os.path.join(agent_dir, f)
                    files.append((path, agent))
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

def sync_all_sessions():
    state = load_state()
    new_messages = 0
    now = datetime.now()
    
    # Only do full sync every 30 minutes (not every minute)
    do_full = (now.timestamp() - state.get("last_full_sync", 0)) > 1800
    
    for path, agent in get_all_session_files():
        filename = os.path.basename(path)
        key = f"{agent}:{filename}"
        
        current_size = os.path.getsize(path)
        last_position = state["offsets"].get(key, 0)
        
        # Skip if no new content
        if current_size <= last_position:
            continue
        
        with open(path, 'r') as f:
            f.seek(last_position)
            new_lines = f.readlines()
        
        for line in new_lines:
            content = extract_content(line)
            
            if content and len(content) > 20:
                # Add tags for organization
                tags = [f"agent:{agent}", "session"]
                if agent == "silhouette":
                    tags = ["silhouette", "conversacion"]
                elif agent == "main":
                    tags = ["main", "sistema"]
                else:
                    tags = [f"agent:{agent}", "trabajo"]
                
                # Store with tags
                msg = f"[{agent.upper()}] {content[:500]}"
                
                try:
                    data = json.loads(line)
                    role = data.get('message', {}).get('role', 'unknown')
                    
                    if role in ['user', 'human']:
                        respond_with_context(msg)
                    else:
                        save_assistant_response(msg)
                    
                    new_messages += 1
                except:
                    pass
        
        state["offsets"][key] = current_size
    
    if do_full:
        state["last_full_sync"] = now.timestamp()
    
    state["last_sync"] = now.isoformat()
    save_state(state)
    
    if new_messages > 0:
        print(f"[SESSION SYNC] {new_messages} mensajes ({'full' if do_full else ' incremental'})")
    return new_messages

if __name__ == "__main__":
    sync_all_sessions()
