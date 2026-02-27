"""
Agente Memory Access - OPTIMIZED VERSION
========================================
- Redis cache para consultas repetidas
- Límites por defecto
- Búsqueda optimizada
"""
import sqlite3
import os
import json
import hashlib
from datetime import datetime
from memory_noise_filter import is_operational_runtime_noise, is_runtime_diagnostic_query

# Intentar importar Redis
try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

MEMORY_DB = os.getenv("BRAIN_DATA_DIR", "./data"/memory_core.db"
REDIS_HOST = "localhost"
REDIS_PORT = 6379
CACHE_TTL = 300  # 5 minutos

def _get_redis():
    """Obtiene cliente Redis"""
    if not REDIS_AVAILABLE:
        return None
    try:
        return redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    except:
        return None

def _get_connection():
    if not os.path.exists(MEMORY_DB):
        return None
    conn = sqlite3.connect(MEMORY_DB)
    conn.row_factory = sqlite3.Row
    return conn

def _cache_key(query, limit):
    """Genera clave de cache"""
    return f"memory:search:{hashlib.md5(f'{query}:{limit}'.encode()).hexdigest()}"

def get_memory_context(query: str, limit: int = 5):
    """
    Buscar en conversaciones - OPTIMIZADO con cache Redis
    """
    r = _get_redis()
    cache_key = _cache_key(query, limit)
    
    # 1. Verificar cache
    if r:
        try:
            cached = r.get(cache_key)
            if cached:
                print(f"[MEMORY CACHE] ✅ Hit: {query[:30]}...")
                return json.loads(cached)
        except:
            pass
    
    # 2. Query a DB
    conn = _get_connection()
    if not conn:
        return {"error": "Memory DB not found"}
    
    try:
        cursor = conn.cursor()
        fetch_limit = max(limit * 4, limit)
        allow_runtime_noise = is_runtime_diagnostic_query(query)
        # Búsqueda optimizada con LIMIT
        cursor.execute("""
            SELECT id, timestamp, speaker, substr(message, 1, 500) as msg
            FROM conversations 
            WHERE message LIKE ? 
            ORDER BY timestamp DESC 
            LIMIT ?
        """, (f'%{query}%', fetch_limit))
        
        results = []
        for row in cursor.fetchall():
            if not allow_runtime_noise and is_operational_runtime_noise(row["msg"]):
                continue
            results.append({
                "id": row["id"],
                "timestamp": row["timestamp"],
                "datetime": datetime.fromtimestamp(row["timestamp"]).strftime("%Y-%m-%d %H:%M"),
                "speaker": row["speaker"],
                "message": row["msg"]
            })
            if len(results) >= limit:
                break
        
        conn.close()
        
        response = {"query": query, "found": len(results), "results": results}
        
        # 3. Guardar en cache
        if r:
            try:
                r.setex(cache_key, CACHE_TTL, json.dumps(response))
                print(f"[MEMORY CACHE] 💾 Guardado: {query[:30]}...")
            except:
                pass
        
        return response
        
    except Exception as e:
        return {"error": str(e)}

def get_entities(entity_type: str = None, limit: int = 10):
    """Obtener entidades - con cache"""
    r = _get_redis()
    cache_key = f"memory:entities:{entity_type or 'all'}:{limit}"
    
    # Cache
    if r:
        try:
            cached = r.get(cache_key)
            if cached:
                return json.loads(cached)
        except:
            pass
    
    conn = _get_connection()
    if not conn:
        return {"error": "Memory DB not found"}
    
    try:
        cursor = conn.cursor()
        if entity_type:
            cursor.execute("""
                SELECT name, type, mention_count, truth 
                FROM entities 
                WHERE type = ? 
                ORDER BY mention_count DESC 
                LIMIT ?
            """, (entity_type, limit))
        else:
            cursor.execute("""
                SELECT name, type, mention_count, truth 
                FROM entities 
                ORDER BY mention_count DESC 
                LIMIT ?
            """, (limit,))
        
        results = []
        for row in cursor.fetchall():
            results.append({
                "name": row[0],
                "type": row[1],
                "mentions": row[2],
                "truth": row[3]
            })
        
        conn.close()
        
        response = {"total": len(results), "entities": results}
        
        if r:
            try:
                r.setex(cache_key, CACHE_TTL, json.dumps(response))
            except:
                pass
        
        return response
        
    except Exception as e:
        return {"error": str(e)}

def get_recent(hours: int = 12, limit: int = 10):
    """Obtener conversaciones recientes - optimizado"""
    import time
    
    r = _get_redis()
    cache_key = f"memory:recent:{hours}:{limit}"
    
    if r:
        try:
            cached = r.get(cache_key)
            if cached:
                return json.loads(cached)
        except:
            pass
    
    conn = _get_connection()
    if not conn:
        return {"error": "Memory DB not found"}
    
    try:
        cursor = conn.cursor()
        cutoff = time.time() - (hours * 3600)
        fetch_limit = max(limit * 4, limit)
        
        cursor.execute("""
            SELECT id, timestamp, speaker, substr(message, 1, 300) as msg
            FROM conversations 
            WHERE timestamp > ?
            ORDER BY timestamp DESC 
            LIMIT ?
        """, (cutoff, fetch_limit))
        
        results = []
        for row in cursor.fetchall():
            if is_operational_runtime_noise(row[3]):
                continue
            results.append({
                "id": row[0],
                "datetime": datetime.fromtimestamp(row[1]).strftime("%Y-%m-%d %H:%M"),
                "speaker": row[2],
                "message": row[3]
            })
            if len(results) >= limit:
                break
        
        conn.close()
        
        response = {"hours": hours, "found": len(results), "conversations": results}
        
        if r:
            try:
                r.setex(cache_key, CACHE_TTL, json.dumps(response))
            except:
                pass
        
        return response
        
    except Exception as e:
        return {"error": str(e)}

def invalidate_cache():
    """Limpia cache cuando hay nuevos mensajes"""
    r = _get_redis()
    if r:
        try:
            # Limpiar solo claves de memoria
            for key in r.keys("memory:*"):
                r.delete(key)
            print("[MEMORY CACHE] 🗑️ Cache invalidada")
        except:
            pass
