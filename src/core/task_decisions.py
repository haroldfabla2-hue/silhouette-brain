#!/usr/bin/env python3
"""
Smart Task Decisions - Analizo y decido qué hacer
"""
import requests
from datetime import datetime

API_KEY = "5998956bd378b210adf4d9907876b414"
TOKEN = "ATTA5265b7adab6bca47d729308071db452dcae4119d3bd2b82604f147f6447d8c0b0D84EB7C"

def analyze_and_decide():
    """Analizar estado y tomar decisiones"""
    
    print(f"[{datetime.now().strftime('%H:%M')}] === ANÁLISIS DE DECISIONES ===\n")
    
    # Get Trello state
    r = requests.get("https://api.trello.com/1/boards/698b618d53e6bf940183872d/cards",
                    params={"key": API_KEY, "token": TOKEN})
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
