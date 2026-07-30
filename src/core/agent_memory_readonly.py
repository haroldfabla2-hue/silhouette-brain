import os
import sys

# Multi-tenant client whitelist
try:
    from clients_config import get_view_scope, get_client_config, is_system_owner
except Exception:
    get_view_scope = lambda x: [x]
    get_client_config = lambda x: {}
    is_system_owner = lambda x: False
# Añadir el directorio raíz al path para encontrar módulos internos
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if base_dir not in sys.path: sys.path.append(base_dir)
core_dir = os.path.join(base_dir, "core")
if core_dir not in sys.path: sys.path.append(core_dir)
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

MEMORY_DB = os.path.join(os.getenv("BRAIN_DATA_DIR", "/home/ubuntu/.openclaw/workspace/silhouette-brain/data"), "memory_core.db")
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

def get_memory_context(query: str, limit: int = 5, owner_id: str = None):
    """
    Buscar en Neo4j (primario) con fallback a SQLite
    
    Args:
        query: search query
        limit: max results
        owner_id: REQUIRED for multi-tenant. Returns only data visible to this client.
    """
    if owner_id is None:
        return {"error": "owner_id required", "results": []}
    
    # Determine view scope (which owners this client can see)
    view_scope = get_view_scope(owner_id)
    
    r = _get_redis()
    cache_key = _cache_key(f"{owner_id}:{query}", limit)
    
    # 1. Verificar cache
    if r:
        try:
            cached = r.get(cache_key)
            if cached:
                print(f"[MEMORY CACHE] ✅ Hit: {query[:30]}...")
                return json.loads(cached)
        except:
            pass
    
    # 2. Query a Neo4j (primario)
    neo4j_results = search_neo4j(query, limit, owner_id=owner_id)
    if neo4j_results and not isinstance(neo4j_results, dict):
        print(f"[MEMORY] ✅ Neo4j: {len(neo4j_results)} results for: {query[:30]}...")
        return {"source": "neo4j", "results": neo4j_results}
    
    # 3. Fallback a SQLite
    conn = _get_connection()
    if not conn:
        return {"error": "Memory DB not found"}
    
    try:
        cursor = conn.cursor()
        fetch_limit = max(limit * 4, limit)
        allow_runtime_noise = is_runtime_diagnostic_query(query)
        # Búsqueda optimizada con LIMIT
        # Build dynamic IN clause for view_scope
        scope_placeholders = ",".join("?" for _ in view_scope)
        cursor.execute(f"""
            SELECT id, timestamp, speaker, substr(message, 1, 500) as msg
            FROM conversations 
            WHERE message LIKE ?
            AND owner_id IN ({scope_placeholders})
            ORDER BY timestamp DESC 
            LIMIT ?
        """, (f'%{query}%', *view_scope, fetch_limit))
        
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

def get_recent(hours: int = 12, limit: int = 10, owner_id: str = None):
    """Obtener conversaciones recientes - optimizado
    
    Args:
        owner_id: REQUIRED for multi-tenant. Returns only data visible to this client.
    """
    import time
    
    if owner_id is None:
        return {"error": "owner_id required", "conversations": []}
    
    view_scope = get_view_scope(owner_id)
    
    r = _get_redis()
    cache_key = f"memory:recent:{owner_id}:{hours}:{limit}"
    
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
        
        scope_placeholders = ",".join("?" for _ in view_scope)
        cursor.execute(f"""
            SELECT id, timestamp, speaker, substr(message, 1, 300) as msg
            FROM conversations 
            WHERE timestamp > ?
            AND owner_id IN ({scope_placeholders})
            ORDER BY timestamp DESC 
            LIMIT ?
        """, (cutoff, *view_scope, fetch_limit))
        
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

# === NEO4J SEARCH ===
def search_neo4j(query: str, limit: int = 5, owner_id: str = None):
    """Buscar en Neo4j con filtro multi-tenant.
    
    Args:
        query: search term
        limit: max results
        owner_id: REQUIRED. Filter by Client via BELONGS_TO relation.
    """
    if owner_id is None:
        return {"error": "owner_id required", "results": []}
    
    view_scope = get_view_scope(owner_id)
    
    try:
        from neo4j import GraphDatabase
        import os
        
        NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:17687")
        NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
        NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "silhouette2035")
        
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        
        with driver.session() as session:
            result = session.run("""
                MATCH (n:Semantic)-[:BELONGS_TO]->(c:Client)
                WHERE n.content CONTAINS $search_term
                AND c.id IN $scope
                RETURN n.content, n.importance, n.tags, c.id as owner
                ORDER BY n.importance DESC
                LIMIT $limit_num
            """, search_term=query, limit_num=limit, scope=view_scope)
            
            nodes = []
            for record in result:
                nodes.append({
                    "content": record[0],
                    "importance": record[1],
                    "tags": record[2],
                    "owner": record[3]
                })
        
        driver.close()
        return nodes
    except Exception as e:
        return {"error": str(e)}
