#!/usr/bin/env python3
"""
Agent Reports Sync - Saves all agent reports to memory
"""
import os
import sys
from datetime import datetime
from glob import glob

sys.path.insert(0, os.getenv('BRAIN_SRC_DIR', os.path.dirname(os.path.abspath(__file__))))

from respond import save_assistant_response

WORKSPACES = "/root/.openclaw/workspace/agents"
STATE_FILE = os.getenv("BRAIN_DATA_DIR", "./data"/reports_sync_state.json"

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f)

def sync_reports():
    """Sync latest reports from all agents"""
    import json
    state = load_state()
    new_reports = 0
    
    for workspace in os.listdir(WORKSPACES):
        reports_dir = os.path.join(WORKSPACES, workspace, "reports")
        
        if not os.path.isdir(reports_dir):
            continue
        
        # Get latest report
        reports = sorted(glob(os.path.join(reports_dir, "*.md")), key=os.path.getmtime, reverse=True)
        
        if reports:
            latest = reports[0]
            mtime = os.path.getmtime(latest)
            
            # Check if new
            last_mtime = state.get(workspace, 0)
            
            if mtime > last_mtime:
                with open(latest, 'r') as f:
                    content = f.read()[:2000]  # First 2000 chars
                
                # Save to memory
                msg = f"[REPORT-{workspace.upper()}] {os.path.basename(latest)}\n\n{content}"
                save_assistant_response(msg)
                
                state[workspace] = mtime
                new_reports += 1
                print(f"  📄 {workspace}: {os.path.basename(latest)}")
    
    save_state(state)
    
    if new_reports > 0:
        print(f"[REPORTS SYNC] {new_reports} nuevos reportes guardados")
    return new_reports

import json
if __name__ == "__main__":
    sync_reports()
