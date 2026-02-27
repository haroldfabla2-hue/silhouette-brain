import os
#!/usr/bin/env python3
"""
Enhanced Memory Core with Real Embeddings
Uses OpenAI text-embedding-3-small for semantic search
"""
import sqlite3
import json
import hashlib
import time
import numpy as np
from datetime import datetime
from typing import List, Dict, Optional
import sys
sys.path.insert(0, os.getenv('BRAIN_SRC_DIR', os.path.dirname(os.path.abspath(__file__))))
from memory_noise_filter import (
    is_operational_runtime_noise,
    is_runtime_diagnostic_query,
    should_skip_ingestion,
)

# Try to import OpenAI embeddings, fall back to simple if not available
try:
    from openai_embeddings import get_openai_embedding, cosine_similarity
    EMBEDDINGS_AVAILABLE = True
    print("[EMBEDDINGS] OpenAI embeddings available")
except ImportError:
    EMBEDDINGS_AVAILABLE = False
    print("[EMBEDDINGS] Using simple similarity (no OpenAI)")

DB_PATH = os.getenv('BRAIN_DATA_DIR', './data'/memory_core.db'

class MemoryCore:
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_db()
    
    def _init_db(self):
        """Initialize database with embeddings table"""
        # Check if embeddings column exists
        cursor = self.conn.cursor()
        cursor.execute("PRAGMA table_info(conversations)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'embedding' not in columns:
            cursor.execute("ALTER TABLE conversations ADD COLUMN embedding BLOB")
            self.conn.commit()
            print("[MEMORY] Added embedding column")
        
        # Create vector index table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS embeddings (
                id TEXT PRIMARY KEY,
                message_id TEXT,
                embedding BLOB,
                model TEXT,
                created_at INTEGER
            )
        """)
        self.conn.commit()
    
    def _get_embedding(self, text: str) -> Optional[bytes]:
        """Get embedding for text using OpenAI or return None"""
        if not EMBEDDINGS_AVAILABLE:
            return None
        
        try:
            # Check cache first
            cursor = self.conn.cursor()
            text_hash = hashlib.md5(text.encode()).hexdigest()
            cursor.execute("SELECT embedding FROM embeddings WHERE id = ?", (text_hash,))
            row = cursor.fetchone()
            
            if row:
                return row[0]
            
            # Generate new embedding
            vector = get_openai_embedding(text)
            embedding_bytes = np.array(vector, dtype=np.float32).tobytes()
            
            # Cache it
            cursor.execute(
                "INSERT OR REPLACE INTO embeddings (id, embedding, model, created_at) VALUES (?, ?, ?, ?)",
                (text_hash, embedding_bytes, 'text-embedding-3-small', int(time.time()))
            )
            self.conn.commit()
            
            return embedding_bytes
        except Exception as e:
            print(f"[EMBEDDINGS] Error: {e}")
            return None
    
    def _cosine_similarity(self, emb1: bytes, emb2: bytes) -> float:
        """Calculate cosine similarity between two embeddings"""
        try:
            vec1 = np.frombuffer(emb1, dtype=np.float32)
            vec2 = np.frombuffer(emb2, dtype=np.float32)
            
            dot = np.dot(vec1, vec2)
            norm1 = np.linalg.norm(vec1)
            norm2 = np.linalg.norm(vec2)
            
            if norm1 == 0 or norm2 == 0:
                return 0
            
            return float(dot / (norm1 * norm2))
        except:
            return 0
    
    def store_message(self, speaker: str, message: str, context: str = None, tags: List[str] = None) -> Optional[str]:
        """Store a message with embedding"""
        if should_skip_ingestion(message):
            print("[MEMORY] Skipped runtime operational noise")
            return None

        msg_id = hashlib.md5(f"{message}{time.time()}".encode()).hexdigest()[:16]
        timestamp = int(time.time())
        
        # Get embedding
        embedding = self._get_embedding(message)
        
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO conversations (id, timestamp, speaker, message, context, embedding, tags)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (msg_id, timestamp, speaker, message, context, embedding, json.dumps(tags or [])))
        
        self.conn.commit()
        return msg_id
    
    def search_context(self, query: str, limit: int = 5) -> List[Dict]:
        """Search using semantic embeddings"""
        cursor = self.conn.cursor()
        allow_runtime_noise = is_runtime_diagnostic_query(query)
        
        # Get embedding for query
        query_embedding = self._get_embedding(query)
        
        if query_embedding:
            # Use vector similarity
            cursor.execute("""
                SELECT id, timestamp, speaker, message, context, tags, embedding
                FROM conversations
                WHERE embedding IS NOT NULL
                ORDER BY timestamp DESC
                LIMIT 50
            """)
            
            results = []
            for row in cursor.fetchall():
                if row[6]:  # embedding
                    similarity = self._cosine_similarity(query_embedding, row[6])
                    if similarity > 0.1:  # Threshold
                        results.append({
                            'id': row[0],
                            'timestamp': row[1],
                            'speaker': row[2],
                            'message': row[3],
                            'context': row[4],
                            'tags': json.loads(row[5]) if row[5] else [],
                            'similarity': similarity
                        })
            
            if not allow_runtime_noise:
                results = [
                    item for item in results
                    if not is_operational_runtime_noise(item.get('message', ''))
                ]

            # Sort by similarity
            results.sort(key=lambda x: x['similarity'], reverse=True)
            return results[:limit]
        else:
            # Fallback to simple search
            sql_limit = max(limit * 4, limit)
            cursor.execute("""
                SELECT id, timestamp, speaker, message, context, tags
                FROM conversations
                WHERE message LIKE ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (f"%{query}%", sql_limit))

            fallback_results = [dict(row) for row in cursor.fetchall()]
            if not allow_runtime_noise:
                fallback_results = [
                    item for item in fallback_results
                    if not is_operational_runtime_noise(item.get('message', ''))
                ]
            return fallback_results[:limit]
    
    def get_entities(self) -> List[Dict]:
        """Get all entities"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT name, type, mention_count FROM entities ORDER BY mention_count DESC")
        return [{'name': row[0], 'type': row[1], 'mention_count': row[2]} for row in cursor.fetchall()]
    
    def get_recent_context(self, hours: int = 24, limit: int = 50) -> List[Dict]:
        """Get recent memories"""
        cursor = self.conn.cursor()
        cutoff = int(time.time()) - (hours * 3600)
        cursor.execute("""
            SELECT id, timestamp, speaker, message, context
            FROM conversations
            WHERE timestamp > ?
            ORDER BY timestamp DESC
            LIMIT ?
        """, (cutoff, limit))
        return [dict(row) for row in cursor.fetchall()]


# Singleton
_memory_core = None

def get_memory_core():
    global _memory_core
    if _memory_core is None:
        _memory_core = MemoryCore()
    return _memory_core


if __name__ == "__main__":
    # Test
    core = get_memory_core()
    
    print("\n=== Testing Semantic Search ===")
    
    # Store test messages
    core.store_message("user", "Alberto es vegetariano y le gusta la pizza")
    core.store_message("user", "Beto trabaja en Brandistry con n8n")
    core.store_message("user", "El proyecto de automation usa Neo4j")
    
    # Search with semantic query
    results = core.search_context("qué come Alberto")
    print(f"\nQuery: 'qué come Alberto'")
    for r in results:
        print(f"  - {r['message'][:50]}... (sim: {r.get('similarity', 'N/A')})")
    
    results = core.search_context("proyecto de automation")
    print(f"\nQuery: 'proyecto de automation'")
    for r in results:
        print(f"  - {r['message'][:50]}... (sim: {r.get('similarity', 'N/A')})")
