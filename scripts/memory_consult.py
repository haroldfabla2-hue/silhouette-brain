#!/usr/bin/env python3
"""
Memory Consult - Busca en la memoria de silhouette-brain
"""
import requests
import sys
import os

BRAIN_API_URL = os.getenv("BRAIN_API_URL", "http://localhost:9876")

def search_memory(query: str, limit: int = 5):
    """Busca en la memoria"""
    try:
        response = requests.get(
            f"{BRAIN_API_URL}/api/memory/semantic",
            params={"query": query, "limit": limit},
            timeout=10
        )
        if response.status_code == 200:
            return response.json()
        return None
    except Exception as e:
        print(f"Error: {e}")
        return None

def get_recent(channel: str = None, limit: int = 10):
    """Obtiene mensajes recientes"""
    try:
        params = {"limit": limit}
        if channel:
            params["channel"] = channel
            
        response = requests.get(
            f"{BRAIN_API_URL}/api/memory/recent",
            params=params,
            timeout=10
        )
        if response.status_code == 200:
            return response.json()
        return None
    except Exception as e:
        print(f"Error: {e}")
        return None

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: memory_consult.py <query>")
        sys.exit(1)
    
    query = " ".join(sys.argv[1:])
    results = search_memory(query)
    
    if results:
        print(f"=== Resultados para: '{query}' ===")
        for i, r in enumerate(results.get("results", [])[:5]):
            print(f"\n{i+1}. {r.get('text', '')[:150]}...")
    else:
        print("No se encontraron resultados")
