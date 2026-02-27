"""
SILHOUETTE MEMORY OS - Python Implementation
========================================
Port from TypeScript to Python of Silhouette-OS memory system
"""

import redis
import json
import time
import hashlib
from typing import List, Dict, Any

class SilhouetteMemoryOS:
    """
    Unified Memory System with ALL Silhouette-OS features:
    1. ContinuumMemory (4-tier)
    2. Identity Re-Perspectiver
    3. CuriosityService
    4. Anti-Recursion
    """
    
    def __init__(self):
        self.redis = redis.Redis(host='localhost', port=6379, decode_responses=True)
        self.working = []  # L1: RAM
        print("[MEMORY OS] ✅ Initialized")
    
    def before_responding(self, user_message: str) -> Dict:
        """Hook: ANTES de cada respuesta"""
        
        # 1. Identity Re-Perspectiver
        transformed = self._transform_identity(user_message)
        
        # 2. Anti-Recursion check
        if self._is_loop_pattern(transformed):
            return {"blocked": True, "reason": "loop_pattern"}
        
        # 3. Add to working memory
        node_id = self._add_memory(transformed, importance=0.6)
        
        # 4. Track for curiosity
        self._track_topics(transformed)
        
        # 5. Detect gaps
        gaps = self._detect_gaps()
        
        return {
            "transformed": transformed,
            "node_id": node_id,
            "gaps": gaps,
            "status": "ready"
        }
    
    def after_responding(self, assistant_message: str) -> Dict:
        """Hook: DESPUÉS de cada respuesta"""
        
        # Check for loop patterns
        if self._is_loop_pattern(assistant_message):
            return {"blocked": True}
        
        # Save
        node_id = self._add_memory(assistant_message, importance=0.7)
        
        # Promote memories
        self._tick()
        
        return {"node_id": node_id, "status": "saved"}
    
    def _transform_identity(self, text: str) -> str:
        """Identity Re-Perspectiver: 1st person -> 3rd person"""
        transforms = [
            ("yo soy ", "El usuario se identifica como "),
            ("me llamo ", "El usuario indica que se llama "),
            ("mi nombre es ", "El usuario indica que su nombre es "),
            ("puedes llamarme ", "El usuario prefiere ser llamado "),
            ("llamame ", "El usuario desea ser llamado "),
            ("mi apodo es ", "El apodo del usuario es "),
        ]
        
        result = text
        for old, new in transforms:
            result = result.replace(old, new)
            result = result.replace(old.title(), new)
        
        return result
    
    def _is_loop_pattern(self, text: str) -> bool:
        """Anti-Recursion: Detect loop patterns"""
        patterns = [
            "I'm committing this to memory",
            "Storing memory: Storing memory",
            "memory that is identical to itself",
        ]
        
        text_lower = text.lower()
        return any(p.lower() in text_lower for p in patterns)
    
    def _add_memory(self, content: str, importance: float) -> str:
        """Add to working memory"""
        node_id = hashlib.md5(content.encode()).hexdigest()[:12]
        
        node = {
            "id": node_id,
            "content": content,
            "importance": importance,
            "timestamp": time.time(),
            "access_count": 0
        }
        
        self.working.append(node)
        
        # Auto-save to Redis
        key = f"memory:working:{node_id}"
        self.redis.setex(key, 86400 * 7, json.dumps(node))
        
        return node_id
    
    def _track_topics(self, text: str):
        """Track topic frequency for curiosity"""
        words = text.lower().split()
        
        for word in words:
            if len(word) > 4:
                key = f"topic:{word}"
                count = self.redis.incr(key)
                self.redis.expire(key, 86400 * 7)
    
    def _detect_gaps(self) -> List[Dict]:
        """Detect knowledge gaps (Curiosity)"""
        gaps = []
        
        # Find topics mentioned 3+ times without depth
        topics = self.redis.keys("topic:*")
        
        for topic_key in topics:
            count = int(self.redis.get(topic_key) or 0)
            if count >= 3:
                topic = topic_key.replace("topic:", "")
                gaps.append({
                    "topic": topic,
                    "count": count,
                    "priority": count / 10
                })
        
        return gaps[:10]
    
    def _tick(self):
        """Tick: Promote memories between tiers"""
        now = time.time()
        
        to_promote = []
        
        for node in self.working[:]:
            age_ms = (now - node["timestamp"]) * 1000
            
            # 15 minutes = 900000ms
            if age_ms > 900000 or node["access_count"] > 10 or node["importance"] >= 0.95:
                to_promote.append(node)
        
        for node in to_promote:
            if node["importance"] >= 0.7:
                # Promote to LONG
                key = f"memory:long:{node['id']}"
                self.redis.setex(key, 86400 * 30, json.dumps(node))
            
            self.working.remove(node)
            print(f"[MEMORY] ⬆️ Promoted: {node['id']}")

# Auto-initialize
memory_os = SilhouetteMemoryOS()

def before_response(message):
    return memory_os.before_responding(message)

def after_response(message):
    return memory_os.after_responding(message)
