#!/usr/bin/env python3
import os
import sys
# Añadir el directorio raíz al path para encontrar módulos internos
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if base_dir not in sys.path: sys.path.append(base_dir)
core_dir = os.path.join(base_dir, "core")
if core_dir not in sys.path: sys.path.append(core_dir)
"""
Smart Task Flow - After completion, I verify and assign next
"""
import requests
from datetime import datetime

API_KEY = "5998956bd378b210adf4d9907876b414"
TOKEN = "ATTA5265b7adab6bca47d729308071db452dcae4119d3bd2b82604f147f6447d8c0b0D84EB7C"
BOARD_ID = "698b618d53e6bf940183872d"

def check_completed():
    """Check completed tasks and decide next steps"""
    
    print(f"[{datetime.now().strftime('%H:%M')}] === VERIFICANDO TAREAS COMPLETADAS ===\n")
    
    # Get lists
    r = requests.get(f"https://api.trello.com/1/boards/{BOARD_ID}/lists",
                    params={"key": API_KEY, "token": TOKEN})
    lists = {l['name']: l['id'] for l in r.json()}
    
    # Get cards
    r2 = requests.get(f"https://api.trello.com/1/boards/{BOARD_ID}/cards",
                    params={"key": API_KEY, "token": TOKEN})
    cards = r2.json()
    
    # Check "Hecho" for newly completed tasks
    done_list = lists.get("✅ Hecho", "")
    if done_list:
        done_cards = [c for c in cards if c['idList'] == done_list]
        
        print(f"✅ Completadas: {len(done_cards)}")
        
        # MY DECISIONS for each completed task
        for card in done_cards:
            name = card['name']
            print(f"\n📋 Análisis: {name[:50]}")
            
            # Decision logic based on what I know
            if "Rick" in name and "Nexus" in name:
                print("   💡 DECISIÓN: Verificar calidad")
                print("   → Si está bien: Asignar siguiente proyecto")
                print("   → Si no: Devolver con correcciones")
                print("   → Siguiente: Silhouette Workflow Creator")
            
            elif "Roger" in name and "oportunidades" in name:
                print("   💡 DECISIÓN: Revisar leads encontrados")
                print("   → Si son buenos: Asignar a Cami para investigar")
                print("   → Si no: Nueva tarea de búsqueda")
            
            elif "Larry" in name:
                print("   💡 DECISIÓN: Verificar engagement")
                print("   → Si está bien: Asignar más contenido")
                print("   → Ajustar estrategia si no funciona")
    
    # Check pending to identify gaps
    print("\n=== IDENTIFICANDO GAPS ===")
    
    # Get my agent lists
    agents = ["Roger", "Cami", "Rick", "Larry", "Rose", "Jack"]
    
    for agent in agents:
        list_name = f"📋 {agent}"
        if list_name in lists:
            agent_cards = [c for c in cards if c['idList'] == lists[list_name]]
            if not agent_cards:
                print(f"⚠️ {agent} NO tiene tareas - asignar!")
                
                # Auto-assign based on what I know
                if agent == "Rick":
                    print(f"   → Asignar: Silhouette Workflow Creator")
                elif agent == "Roger":
                    print(f"   → Asignar: Buscar más oportunidades")
                elif agent == "Larry":
                    print(f"   → Asignar: Más contenido para leads")

if __name__ == "__main__":
    check_completed()
