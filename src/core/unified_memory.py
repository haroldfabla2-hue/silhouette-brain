import os
"""
UNIFIED MEMORY SYSTEM - Using existing Redis & Neo4j
=================================================
This integrates with the same infrastructure as Silhouette-OS
"""
import sys
import redis
from neo4j import GraphDatabase

sys.path.insert(0, os.getenv('BRAIN_SRC_DIR', os.path.dirname(os.path.abspath(__file__))))

class UnifiedMemory:
    def __init__(self):
        self.redis_client = None
        self.neo4j_driver = None
        self.connected = False
        
    def connect(self):
        """Connect to Redis and Neo4j (same as Silhouette-OS uses)"""
        try:
            # Connect to Redis (already running on port 6379)
            self.redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)
            self.redis_client.ping()
            print("[MEMORY] ✅ Redis connected")
        except Exception as e:
            print(f"[MEMORY] ❌ Redis error: {e}")
        
        try:
            # Connect to Neo4j (already running on port 17687)
            self.neo4j_driver = GraphDatabase.driver(
                "bolt://localhost:17687",
                auth=("neo4j", os.getenv("NEO4J_PASSWORD", "silhouette2035"))
            )
            self.neo4j_driver.verify_connectivity()
            print("[MEMORY] ✅ Neo4j connected")
        except Exception as e:
            print(f"[MEMORY] ❌ Neo4j error: {e}")
        
        self.connected = True
        return True
    
    def before_responding(self, user_message):
        """ANTES DE CADA RESPUESTA - Buscar contexto automáticamente"""
        if not self.connected:
            self.connect()
        
        # 1. Guardar mensaje en Redis (corto plazo)
        self._save_to_redis(user_message, "user")
        
        # 2. Buscar en Neo4j (largo plazo)
        context = self._search_neo4j(user_message)
        
        # 3. Actualizar memoria reciente
        self._update_recent(user_message)
        
        return context
    
    def after_responding(self, agent_message):
        """DESPUÉS DE CADA RESPUESTA"""
        # Guardar en Redis
        self._save_to_redis(agent_message, "assistant")
        
        # Persistir a Neo4j (largo plazo)
        self._save_to_neo4j(agent_message)
    
    def _save_to_redis(self, message, role):
        """Guardar en Redis (corto plazo)"""
        try:
            import time
            # Guardar últimos 100 mensajes
            key = f"silhouette:messages:{role}"
            self.redis_client.rpush(key, message)
            self.redis_client.expire(key, 86400 * 7)  # 7 días
            # Mantener solo los últimos 100
            self.redis_client.ltrim(key, -100, -1)
            print(f"[MEMORY] 💾 Redis: {role}")
        except Exception as e:
            print(f"[MEMORY] ⚠️ Redis save: {e}")
    
    def _search_neo4j(self, query):
        """Buscar en Neo4j (largo plazo)"""
        try:
            with self.neo4j_driver.session() as session:
                # Buscar entidades relacionadas con la query
                result = session.run("""
                    MATCH (m:Message)
                    WHERE m.content CONTAINS $query
                    RETURN m.content as content, m.role as role
                    ORDER BY m.timestamp DESC
                    LIMIT 10
                """, query=query)
                
                return [dict(record) for record in result]
        except Exception as e:
            print(f"[MEMORY] ⚠️ Neo4j search: {e}")
            return []
    
    def _save_to_neo4j(self, message):
        """Persistir mensaje a Neo4j"""
        try:
            import time
            with self.neo4j_driver.session() as session:
                session.run("""
                    CREATE (m:Message {
                        content: $content,
                        role: $role,
                        timestamp: $timestamp
                    })
                """, content=message, role="assistant", timestamp=int(time.time()))
                print(f"[MEMORY] 💾 Neo4j: saved")
        except Exception as e:
            print(f"[MEMORY] ⚠️ Neo4j save: {e}")
    
    def _update_recent(self, query):
        """Actualizar contexto reciente"""
        try:
            # Guardar última query para contexto
            self.redis_client.set("silhouette:last_query", query, ex=3600)
        except:
            pass
    
    def get_full_context(self):
        """Obtener TODO el contexto disponible"""
        context = {
            "recent_messages": [],
            "long_term": [],
            "last_query": None
        }
        
        try:
            # Get recent from Redis
            for role in ["user", "assistant"]:
                key = f"silhouette:messages:{role}"
                messages = self.redis_client.lrange(key, -10, -1)
                context["recent_messages"].extend(messages)
        except:
            pass
        
        try:
            # Get last query
            context["last_query"] = self.redis_client.get("silhouette:last_query")
        except:
            pass
        
        return context

# Global instance
memory = UnifiedMemory()

def before_responding(message):
    """Llamar ANTES de cada respuesta"""
    return memory.before_responding(message)

def after_responding(message):
    """Llamar DESPUÉS de cada respuesta"""
    memory.after_responding(message)

def get_context():
    """Obtener contexto completo"""
    return memory.get_full_context()

# Auto-connect
print("[MEMORY] 🚀 Sistema de memoria unificada cargado")
memory.connect()
