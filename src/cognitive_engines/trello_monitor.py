#!/usr/bin/env python3
"""
Trello Monitor - Revisa tareas cada 30 min
"""
import requests
import os
from datetime import datetime

API_KEY = "5998956bd378b210adf4d9907876b414"
TOKEN = "ATTA5265b7adab6bca47d729308071db452dcae4119d3bd2b82604f147f6447d8c0b0D84EB7C"
BOARD_ID = "698b618d53e6bf940183872d"

def check_trello():
    """Check Trello for tasks and agent progress"""
    print(f"[{datetime.now().strftime('%H:%M')}] Checking Trello...")
    
    # Get lists
    r = requests.get(f"https://api.trello.com/1/boards/{BOARD_ID}/lists",
                    params={"key": API_KEY, "token": TOKEN})
    
    if r.status_code != 200:
        print(f"Error getting lists: {r.status_code}")
        return
    
    lists = {l['name']: l['id'] for l in r.json()}
    
    # Get cards
    r2 = requests.get(f"https://api.trello.com/1/boards/{BOARD_ID}/cards",
                     params={"key": API_KEY, "token": TOKEN})
    
    if r2.status_code != 200:
        print(f"Error getting cards: {r2.status_code}")
        return
    
    cards = r2.json()
    
    # Check each agent's list
    agents = ["Roger", "Cami", "Rick", "Larry", "Rose", "Jack"]
    
    print("\n=== TRELLO STATUS ===")
    for agent in agents:
        list_name = f"📋 {agent}"
        if list_name in lists:
            agent_cards = [c for c in cards if c['idList'] == lists[list_name]]
            print(f"{agent}: {len(agent_cards)} tareas pendientes")
    
    # Check "En Proceso"
    if "🔄 En Proceso" in lists:
        proceso_cards = [c for c in cards if c['idList'] == lists["🔄 En Proceso"]]
        print(f"\n🔄 En Proceso: {len(proceso_cards)} tareas")
    
    # Check "Hecho"
    if "✅ Hecho" in lists:
        done_cards = [c for c in cards if c['idList'] == lists["✅ Hecho"]]
        print(f"✅ Completadas: {len(done_cards)} tareas")
    
    print("=== END ===")

if __name__ == "__main__":
    check_trello()
