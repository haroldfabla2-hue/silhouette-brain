#!/usr/bin/env python3
import os
import sys
# Añadir el directorio raíz al path para encontrar módulos internos
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if base_dir not in sys.path: sys.path.append(base_dir)
core_dir = os.path.join(base_dir, "core")
if core_dir not in sys.path: sys.path.append(core_dir)
"""
Agent Reminders - Send reminders to agents about their Trello tasks
"""
from datetime import datetime

import requests

API_KEY = os.getenv("TRELLO_API_KEY", "")
TOKEN = os.getenv("TRELLO_TOKEN", "")
BOARD_ID = os.getenv("TRELLO_BOARD_ID", "")


def check_and_remind():
    """Check Trello and send reminders for pending tasks"""
    if not API_KEY or not TOKEN or not BOARD_ID:
        print("TRELLO_API_KEY / TRELLO_TOKEN / TRELLO_BOARD_ID no configurados — omitiendo check")
        return

    print(f"[{datetime.now().strftime('%H:%M')}] Checking tasks...")
    
    # Get lists
    r = requests.get(f"https://api.trello.com/1/boards/{BOARD_ID}/lists",
                    params={"key": API_KEY, "token": TOKEN})
    lists = {l['name']: l['id'] for l in r.json()}
    
    # Get cards
    r2 = requests.get(f"https://api.trello.com/1/boards/{BOARD_ID}/cards",
                     params={"key": API_KEY, "token": TOKEN})
    cards = r2.json()
    
    # Check each agent
    agents = ["Roger", "Cami", "Rick", "Larry", "Rose", "Jack"]
    
    reminders = []
    
    for agent in agents:
        list_name = f"📋 {agent}"
        if list_name in lists:
            agent_cards = [c for c in cards if c['idList'] == lists[list_name]]
            if agent_cards:
                task = agent_cards[0]['name'][:60]
                reminders.append(f"{agent}: {task}")
    
    if reminders:
        print("\n⚠️ Tareas pendientes:")
        for r in reminders:
            print(f"   {r}")
        
        # Save for me to see
        with open('/tmp/agent_reminders.txt', 'w') as f:
            f.write("=== TAREAS PENDIENTES ===\n")
            for r in reminders:
                f.write(f"- {r}\n")
    else:
        print("✅ Todas las tareas completadas!")
        
        # Save empty state
        with open('/tmp/agent_reminders.txt', 'w') as f:
            f.write("=== TODAS LAS TAREAS COMPLETADAS ===\n")
    
    return len(reminders)

if __name__ == "__main__":
    check_and_remind()
