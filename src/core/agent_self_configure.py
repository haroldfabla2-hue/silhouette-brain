#!/usr/bin/env python3
import os
import sys
import requests
import glob

def setup():
    print("🚀 Iniciando Auto-Configuración de Memoria Silhouette...")
    
    # 1. Verificar API
    try:
        r = requests.get("http://localhost:9876/api/status", timeout=2)
        if r.status_code == 200:
            print("✅ Brain API detectada y activa.")
        else:
            print("⚠️ Brain API respondió con error. ¿Está docker-compose arriba?")
    except:
        print("❌ No se pudo conectar con Brain API (localhost:9876).")
        return

    # 2. Localizar SOUL.md o archivos de configuración
    # Buscamos en el directorio actual y uno arriba (típico de OpenClaw)
    potential_paths = [
        "SOUL.md", 
        "../SOUL.md", 
        "../../SOUL.md",
        "AGENTS.md",
        "../AGENTS.md"
    ]
    
    soul_file = None
    for p in potential_paths:
        if os.path.exists(p):
            soul_file = p
            break
    
    if not soul_file:
        print("🔍 No se encontró SOUL.md. Por favor, introduce la ruta manual o ignora este paso.")
    else:
        print(f"📖 Archivo de identidad encontrado: {soul_file}")
        
        with open(soul_file, 'r') as f:
            content = f.read()
            
        if "SILHOUETTE BRAIN" in content:
            print("ℹ️ La directiva de memoria ya existe en este archivo.")
        else:
            directive = """
---
## 🧠 Sistema de Memoria (Silhouette Brain)
Posees una infraestructura cognitiva independiente (Brain API) en http://localhost:9876.
- **Protocolo:** ANTES de responder, DEBES consultar `http://localhost:9876/api/memory/semantic?query=tema`.
- **Relaciones:** Usa `/api/memory/graph?entity=x` para entender conexiones complejas.
- **Acción:** Adapta tu personalidad a los recuerdos recuperados.
"""
            with open(soul_file, 'a') as f:
                f.write(directive)
            print(f"✅ Directiva cognitiva inyectada en {soul_file}")

    # 3. Inyectar herramientas en TOOLS.md si existe
    tools_file = None
    for p in ["TOOLS.md", "../TOOLS.md", "../../TOOLS.md"]:
        if os.path.exists(p):
            tools_file = p
            break
            
    if tools_file:
        with open(tools_file, 'r') as f:
            t_content = f.read()
        if "Brain API" not in t_content:
            t_directive = """
### 🧠 Herramientas de Memoria Profunda
- **Contexto:** `curl -s "http://localhost:9876/api/memory/semantic?query=..."`
- **Entidades:** `curl -s "http://localhost:9876/api/memory/entities"`
- **Grafo:** `curl -s "http://localhost:9876/api/memory/graph?entity=..."`
"""
            with open(tools_file, 'a') as f:
                f.write(t_directive)
            print(f"✅ Herramientas inyectadas en {tools_file}")

    print("\n✨ Proceso de integración completado. ¡Ahora eres más inteligente!")

if __name__ == "__main__":
    setup()
