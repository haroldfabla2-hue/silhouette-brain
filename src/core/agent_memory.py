import os
import sys
# Añadir el directorio raíz al path para encontrar módulos internos
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if base_dir not in sys.path: sys.path.append(base_dir)
core_dir = os.path.join(base_dir, "core")
if core_dir not in sys.path: sys.path.append(core_dir)
"""
Agente Memory Access - Para que los subagentes puedan acceder a la memoria de Silhouette
"""
import sqlite3
import os

MEMORY_DB = os.path.join(os.getenv("BRAIN_DATA_DIR", "./data"), "memory_core.db")

def get_memory_context(query: str, limit: int = 10):
    """Buscar en la memoria de Silhouette"""
    if not os.path.exists(MEMORY_DB):
        return {"error": "Memory DB not found"}
    
    try:
        conn = sqlite3.connect(MEMORY_DB)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT datetime(timestamp, 'unixepoch') as ts, speaker, substr(message, 1, 500) as msg
            FROM conversations 
            WHERE message LIKE ? OR speaker = ?
            ORDER BY timestamp DESC LIMIT ?
        """, (f'%{query}%', query, limit))
        
        results = []
        for row in cursor.fetchall():
            results.append({
                "timestamp": row[0],
                "speaker": row[1],
                "message": row[2]
            })
        
        conn.close()
        return {"query": query, "results": results, "count": len(results)}
    except Exception as e:
        return {"error": str(e)}

def get_recent_context(hours: int = 24, limit: int = 20):
    """Obtener contexto reciente"""
    if not os.path.exists(MEMORY_DB):
        return {"error": "Memory DB not found"}
    
    try:
        conn = sqlite3.connect(MEMORY_DB)
        cursor = conn.cursor()
        
        cursor.execute(f"""
            SELECT datetime(timestamp, 'unixepoch') as ts, speaker, substr(message, 1, 300) as msg
            FROM conversations 
            WHERE timestamp > strftime('%s', 'now', '-{hours} hours')
            ORDER BY timestamp DESC LIMIT {limit}
        """)
        
        results = []
        for row in cursor.fetchall():
            results.append({
                "timestamp": row[0],
                "speaker": row[1],
                "message": row[2]
            })
        
        conn.close()
        return {"hours": hours, "results": results, "count": len(results)}
    except Exception as e:
        return {"error": str(e)}

# Para usar en agentes:
# from agent_memory import get_memory_context, get_recent_context
# 
# # Buscar algo específico
# result = get_memory_context("proyecto blog")
# print(result)
#
# # Ver contexto reciente
# recent = get_recent_context(hours=24)
# print(recent)
