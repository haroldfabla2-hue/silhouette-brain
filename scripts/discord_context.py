#!/usr/bin/env python3
"""
Discord Context - Consulta memoria durante conversaciones de Discord
"""
import requests
import os

BRAIN_API_URL = os.getenv("BRAIN_API_URL", "http://localhost:9876")

def get_context_for_iris():
    """Obtiene contexto relevante sobre Iris para la conversación"""
    results = []
    
    # Buscar sobre Iris
    r = requests.get(f"{BRAIN_API_URL}/api/memory", 
                    params={"query": "Iris protocolo check-in", "limit": 3}, timeout=10)
    if r.status_code == 200:
        data = r.json()
        results.extend(data.get("results", []))
    
    return results

def search_context(query: str):
    """Busca contexto específico"""
    r = requests.get(f"{BRAIN_API_URL}/api/memory", 
                    params={"query": query, "limit": 5}, timeout=10)
    if r.status_code == 200:
        return r.json().get("results", [])
    return []

if __name__ == "__main__":
    # Test
    print("=== Contexto de Iris ===")
    results = get_context_for_iris()
    for r in results:
        print(f"- {r.get('message', '')[:100]}...")
