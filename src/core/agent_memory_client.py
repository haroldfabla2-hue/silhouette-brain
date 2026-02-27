#!/usr/bin/env python3
import os
import sys
# Añadir el directorio raíz al path para encontrar módulos internos
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if base_dir not in sys.path: sys.path.append(base_dir)
core_dir = os.path.join(base_dir, "core")
if core_dir not in sys.path: sys.path.append(core_dir)
"""
Agent Memory Client - Optimizado para agentes
============================================
Los agentes usan esto para consultar memoria sin saturar:
- Solo 3 resultados por query
- Cache de 5 minutos
- Semantic search cuando es necesario
"""
import requests
import time

# Configuración
API_URL = "http://localhost:9876"
CACHE_TTL = 300  # 5 minutos
_cache = {}

# LÍMITES ÓPTIMOS (ajustar según necesidad)
LIMITS = {
    'context': 10,      # Resultados de contexto
    'entities': 15,     # Entidades
    'recent': 10        # Recientes
}

def _get_cache(key):
    """Obtiene del cache si está vigente"""
    if key in _cache:
        if time.time() - _cache[key]['time'] < CACHE_TTL:
            return _cache[key]['data']
    return None

def _set_cache(key, data):
    """Guarda en cache"""
    _cache[key] = {'data': data, 'time': time.time()}

def get_context(task_description, limit=LIMITS["context"]):
    """
    Obtiene contexto relevante para una tarea
    Optimizado: solo 3 resultados, cache 5 min
    """
    cache_key = f"context:{task_description[:50]}"
    
    # Ver cache
    cached = _get_cache(cache_key)
    if cached:
        return cached
    
    # Query a API
    try:
        r = requests.get(f"{API_URL}/api/memory/semantic", 
                         params={'query': task_description, 'limit': limit},
                         timeout=5)
        if r.status_code == 200:
            data = r.json()
            _set_cache(cache_key, data)
            return data
    except:
        pass
    
    # Fallback a búsqueda básica
    try:
        r = requests.get(f"{API_URL}/api/memory",
                         params={'query': task_description, 'limit': limit},
                         timeout=5)
        if r.status_code == 200:
            data = r.json()
            _set_cache(cache_key, data)
            return data
    except:
        pass
    
    return {'error': 'No se pudo obtener contexto'}

def get_entities(limit=LIMITS["entities"]):
    """Obtiene entidades - cache 5 min"""
    cache_key = "entities"
    
    cached = _get_cache(cache_key)
    if cached:
        return cached
    
    try:
        r = requests.get(f"{API_URL}/api/memory/entities", 
                         params={'limit': limit}, timeout=5)
        if r.status_code == 200:
            data = r.json()
            _set_cache(cache_key, data)
            return data
    except:
        pass
    
    return {'error': 'No se pudieron obtener entidades'}

def get_recent(hours=2, limit=LIMITS["recent"]):
    """Obtiene conversaciones recientes - cache 5 min"""
    cache_key = f"recent:{hours}"
    
    cached = _get_cache(cache_key)
    if cached:
        return cached
    
    try:
        r = requests.get(f"{API_URL}/api/memory/recent",
                        params={'hours': hours, 'limit': limit}, timeout=5)
        if r.status_code == 200:
            data = r.json()
            _set_cache(cache_key, data)
            return data
    except:
        pass
    
    return {'error': 'No se pudieron obtener recientes'}

def get_entity_info(entity_name):
    """Obtiene info de una entidad específica"""
    cache_key = f"entity:{entity_name}"
    
    cached = _get_cache(cache_key)
    if cached:
        return cached
    
    try:
        r = requests.get(f"{API_URL}/api/memory",
                         params={'query': entity_name, 'limit': 2}, timeout=5)
        if r.status_code == 200:
            data = r.json()
            _set_cache(cache_key, data)
            return data
    except:
        pass
    
    return {'error': 'No se pudo obtener info de entidad'}

def check_memory_before_task(task):
    """
    Helper principal: llama esto al INICIO de cada tarea
    Returns contexto optimizado
    """
    context = get_context(task, limit=3)
    entities = get_entities(limit=5)
    recent = get_recent(hours=2, limit=3)
    
    return {
        'context': context,
        'entities': entities,
        'recent': recent,
        'ready': True
    }

# Ejemplo de uso:
# from agent_memory import check_memory_before_task, get_entity_info
# 
# # 1. Al inicio de tarea
# mem = check_memory_before_task("actualizar blog de Brandistry")
# print(f"Tengo {len(mem.get('context',{}).get('results',[]))} resultados de contexto")
#
# # 2. Durante tarea larga (si necesita más info)
# info = get_entity_info("Brandistry")
#
# # 3. Al finalizar (opcional - guardar resultado)
# # El reporte ya se guarda automáticamente
