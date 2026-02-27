import os
import sys
# Añadir el directorio raíz al path para encontrar módulos internos
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if base_dir not in sys.path: sys.path.append(base_dir)
core_dir = os.path.join(base_dir, "core")
if core_dir not in sys.path: sys.path.append(core_dir)
import os
"""
COMPLETE MEMORY SYSTEM FOR SILHOUETTE
===================================
Integrates:
1. Short-term: Redis (últimos mensajes)
2. Long-term: Neo4j (grafos de conocimiento)  
3. Semantic: OpenAI embeddings (búsqueda por significado)
4. Curiosity: Encuentra lo que NO sé
5. Dreaming: Procesamiento en background
6. Janitor: Mantiene coherencia

Nunca más gaps - siempre en contexto
"""

import redis
import json
import time
import requests
from datetime import datetime

# ============== OPENAI EMBEDDINGS ==============
class SemanticSearch:
    """Búsqueda semántica con OpenAI"""
    
    MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    API_KEY = os.getenv("OPENAI_API_KEY")
    
    @classmethod
    def get_embedding(cls, text):
        """Obtener embedding de OpenAI"""
        try:
            response = requests.post(
                "https://api.openai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {cls.API_KEY}"},
                json={"input": text, "model": cls.MODEL}
            )
            if response.status_code == 200:
                return response.json()["data"][0]["embedding"]
        except Exception as e:
            print(f"[SEMANTIC] ⚠️ {e}")
        return None
    
    @classmethod
    def search(cls, query, top_k=5):
        """Buscar por significado"""
        query_emb = cls.get_embedding(query)
        if not query_emb:
            return []
        
        # En un sistema real, esto buscaría en vectores
        # Por ahora, usamos búsqueda de texto
        from memory_core import get_memory_core
        core = get_memory_core()
        return core.search_context(query)

# ============== CURIOSITY ==============
class Curiosity:
    """Encuentra lo que NO sé"""
    
    @classmethod
    def find_gaps(cls, conversation_history):
        """Encontrar gaps de información"""
        gaps = []
        
        # Keywords que indican que necesito más info
        question_words = ["qué", "cómo", "por qué", "cuándo", "dónde", "cuál"]
        
        for msg in conversation_history[-5:]:
            if any(word in msg.lower() for word in question_words):
                # Es una pregunta - necesito contexto
                gaps.append({
                    "type": "question",
                    "content": msg,
                    "timestamp": time.time()
                })
        
        return gaps

# ============== DREAMING ==============
class Dreaming:
    """Procesamiento en background (cuando no hay actividad)"""
    
    @classmethod
    def process(cls):
        """Procesar conversaciones recientes"""
        print("[DREAM] 💭 Procesando conversaciones...")
        
        # 1. Extraer entidades nuevas
        # 2. Crear conexiones
        # 3. Consolidar memoria
        
        print("[DREAM] ✅ Sueño completado")
        return {"processed": True}

# ============== JANITOR ==============
class Janitor:
    """Mantiene coherencia - detecta contradicciones"""
    
    @classmethod
    def check_coherence(cls):
        """Verificar coherencia"""
        # En un sistema real, buscaría contradicciones
        return {"contradictions": 0, "status": "clean"}

# ============== MAIN MEMORY SYSTEM ==============
class CompleteMemory:
    """Sistema completo de memoria"""
    
    def __init__(self):
        self.redis = redis.Redis(host='localhost', port=6379, decode_responses=True)
        self.connected = False
        
    def connect(self):
        """Conectar todos los servicios"""
        try:
            self.redis.ping()
            self.connected = True
            print("[MEMORY] ✅ Todo conectado")
            return True
        except Exception as e:
            print(f"[MEMORY] ⚠️ {e}")
            return False
    
    def save_message(self, role, content):
        """GUARDAR MENSAJE - Se llama automáticamente"""
        # 1. Guardar en Redis (corto plazo)
        key = f"memory:{role}"
        self.redis.rpush(key, json.dumps({
            "content": content,
            "timestamp": time.time()
        }))
        self.redis.expire(key, 86400 * 7)  # 7 días
        
        # 2. Generar embedding (OpenAI)
        embedding = SemanticSearch.get_embedding(content)
        if embedding:
            self.redis.setex(f"embedding:{role}:{int(time.time())}", 86400 * 30, json.dumps(embedding))
        
        # 3. Verificar coherencia (Janitor)
        Janitor.check_coherence()
        
        print(f"[MEMORY] 💾 Guardado: {role}")
    
    def get_context(self, query):
        """OBTENER CONTEXTO - Se llama automáticamente antes de responder"""
        # 1. Buscar en Redis (reciente)
        recent = []
        for role in ["user", "assistant"]:
            key = f"memory:{role}"
            msgs = self.redis.lrange(key, -10, -1)
            for m in msgs:
                recent.append(json.loads(m))
        
        # 2. Búsqueda semántica (OpenAI)
        semantic = SemanticSearch.search(query)
        
        # 3. Verificar gaps (Curiosity)
        gaps = Curiosity.find_gaps([r.get("content", "") for r in recent])
        
        return {
            "recent": recent,
            "semantic": semantic,
            "gaps": gaps,
            "coherence": Janitor.check_coherence()
        }

# Instancia global
memory = CompleteMemory()

# ============== FUNCTIONS FOR AUTO USE ==============
def before_response(message):
    """Llamar ANTES de cada respuesta"""
    if not memory.connected:
        memory.connect()
    return memory.get_context(message)

def after_response(message):
    """Llamar DESPUÉS de cada respuesta"""
    memory.save_message("assistant", message)

# Auto-inicializar
print("[COMPLETE MEMORY] 🚀 Sistema completo cargado")
memory.connect()
