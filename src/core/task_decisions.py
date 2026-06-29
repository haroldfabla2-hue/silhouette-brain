#!/usr/bin/env python3
import os
import sys
# Añadir el directorio raíz al path para encontrar módulos internos
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if base_dir not in sys.path: sys.path.append(base_dir)
core_dir = os.path.join(base_dir, "core")
if core_dir not in sys.path: sys.path.append(core_dir)
"""
Smart Task Decisions - Analizo y decido qué hacer
"""
from datetime import datetime

import requests

API_KEY = os.getenv("TRELLO_API_KEY", "")
TOKEN = os.getenv("TRELLO_TOKEN", "")
BOARD_ID = os.getenv("TRELLO_BOARD_ID", "")


def analyze_and_decide():
    """Analizar estado y tomar decisiones"""
    if not API_KEY or not TOKEN or not BOARD_ID:
        print("TRELLO_API_KEY / TRELLO_TOKEN / TRELLO_BOARD_ID no configurados — omitiendo check")
        return

    print(f"[{datetime.now().strftime('%H:%M')}] === ANÁLISIS DE DECISIONES ===\n")

    r = requests.get(
        f"https://api.trello.com/1/boards/{BOARD_ID}/cards",
        params={"key": API_KEY, "token": TOKEN},
    )
    cards = r.json()
    
    # Count by status
    done = [c for c in cards if "Hecho" in c.get("listName", "")]
    pending = [c for c in cards if "📋" in c.get("listName", "")]
    proceso = [c for c in cards if "Proceso" in c.get("listName", "")]
    
    print(f"📊 Estado:")
    print(f"   ✅ Completadas: {len(done)}")
    print(f"   🔄 En proceso: {len(proceso)}")
    print(f"   ⏳ Pendientes: {len(pending)}")
    
    # MY DECISIONS based on what I know
    print(f"\n🧠 MIS DECISIONES:")
    
    # Decision 1: If Rick is done with Nexus, assign landing page
    rick_tasks = [c for c in pending if "Rick" in c["name"]]
    if rick_tasks:
        print(f"   ⚠️ Rick tiene {len(rick_tasks)} tareas - completar antes de asignar más")
    
    # Decision 2: Roger should keep searching
    roger_tasks = [c for c in pending if "Roger" in c["name"]]
    if not roger_tasks:
        print(f"   💡 Roger necesita nueva tarea - buscar oportunidades freelance")
    
    # Decision 3: Content is critical while building
    larry_tasks = [c for c in pending if "Larry" in c["name"]]
    if not larry_tasks:
        print(f"   💡 Larry debería crear contenido - generar ожидае leads")
    
    # Decision 4: Check if we need more research
    cami_tasks = [c for c in pending if "Cami" in c["name"]]
    if not cami_tasks:
        print(f"   💡 Cami podría investigar nuevos nichos")
    
    print(f"\n=== ACCIONES TOMADAS ===")
    
    # Save decision log
    with open('/tmp/task_decisions.txt', 'w') as f:
        f.write(f"=== DECISIONES {datetime.now().strftime('%Y-%m-%d %H:%M')} ===\n")
        f.write(f"Pendientes: {len(pending)}\n")
        f.write(f"Completadas: {len(done)}\n")
        f.write(f"\nDecisiones:\n")
        f.write("- Revisar progreso regularmente\n")
        f.write("- Asignar nuevas tareas según resultados\n")

if __name__ == "__main__":
    analyze_and_decide()
