#!/usr/bin/env python3
"""
Agent Reminders - Send reminders to agents about their Trello tasks
"""
import requests
from datetime import datetime

API_KEY = "5998956bd378b210adf4d9907876b414"
TOKEN = "ATTA5265b7adab6bca47d729308071db452dcae4119d3bd2b82604f147f6447d8c0b0D84EB7C"
BOARD_ID = "698b618d53e6bf940183872d"

def check_and_remind():
    """Check Trello and send reminders for pending tasks"""
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
