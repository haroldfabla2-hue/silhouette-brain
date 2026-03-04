import os
import sys
# Añadir el directorio raíz al path para encontrar módulos internos
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if base_dir not in sys.path: sys.path.append(base_dir)
core_dir = os.path.join(base_dir, "core")
if core_dir not in sys.path: sys.path.append(core_dir)
import os
#!/usr/bin/env python3
"""
Silhouette Memory Core - Full Context Memory System
Industrial Scale with Neo4j Vector Indexes and OpenAI Embeddings
"""
import time
import json
import hashlib
import sqlite3
import numpy as np
from datetime import datetime
from typing import List, Dict, Optional
from pathlib import Path
import sys

# Try to import local embeddings
try:
    from local_embeddings import get_embedding as get_openai_embedding
    EMBEDDINGS_AVAILABLE = True
    print("[EMBEDDINGS] Local fastembed available")
except ImportError:
    EMBEDDINGS_AVAILABLE = False
    print("[EMBEDDINGS] Using simple similarity (no embeddings)")

# Database setup
DB_PATH = os.path.join(os.getenv('BRAIN_DATA_DIR', '/root/silhouette-brain/data'), 'memory_core.db')
Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)

class MemoryCore:
    def find_contradictions(self):
        """Find potential contradictions in memories"""
        cur = self.conn.cursor()
        cur.execute(
            "SELECT * FROM entities WHERE mention_count > 1 ORDER BY mention_count DESC LIMIT 200"
        )
        entities = [dict(row) for row in cur.fetchall()]
        
        contradictions = []
        for entity in entities:
            # Excluir embedding (blob innecesario) y limitar resultados
            cur.execute("""
                SELECT id, timestamp, speaker, message, context, tags FROM conversations
                WHERE message LIKE ?
                ORDER BY timestamp
                LIMIT 200
            """, (f"%{entity['name']}%",))

            messages = [dict(row) for row in cur.fetchall()]
            positive_words = ["good", "great", "love", "like", "best", "excelent", "bien", "mejor", "gusta", "feliz"]
            negative_words = ["bad", "terrible", "hate", "dislike", "worst", "mal", "peor", "odiar", "triste"]
            
            positive_mentions = [m for m in messages if any(w in m["message"].lower() for w in positive_words)]
            negative_mentions = [m for m in messages if any(w in m["message"].lower() for w in negative_words)]
            
            if positive_mentions and negative_mentions:
                contradictions.append({
                    "entity": entity["name"],
                    "positive_count": len(positive_mentions),
                    "negative_count": len(negative_mentions),
                    "positive_examples": [p["message"][:100] for p in positive_mentions[-2:]],
                    "negative_examples": [n["message"][:100] for n in negative_mentions[-2:]],
                    "status": "pending"
                })
        return contradictions

    def verify_entity(self, entity_id, truth, updated_by):
        """Verify an entity resolution"""
        try:
            cur = self.conn.cursor()
            cur.execute("""
                UPDATE entities 
                SET attributes = json_insert(COALESCE(attributes, '{}'), '$.truth', ?),
                    verified = 1
                WHERE id = ?
            """, (truth, entity_id))
            self.conn.commit()
            return True
        except Exception as e:
            print(f"Error verifying entity: {e}")
            return False

    """Full context memory with semantic search (Neo4j + SQLite fallback)"""
    
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()
        
        self.neo4j_driver = None
        self.embedding_dims = int(os.getenv("EMBEDDING_DIMS", "384"))
        
        try:
            from neo4j import GraphDatabase
            self.neo4j_driver = GraphDatabase.driver(
                os.getenv("NEO4J_URI", "bolt://localhost:17687"), 
                auth=(os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD", "silhouette2035"))
            )
            self.neo4j_driver.verify_connectivity()
            print("[MEMORY CORE] ✅ Neo4j connected for Vector Search")
            self._ensure_neo4j_index()
        except Exception as e:
            print(f"[MEMORY CORE] ⚠️ Neo4j Vector Search not available: {e}")
            
        print("[MEMORY CORE] ✅ Initialized")

    def _ensure_neo4j_index(self):
        """Asegura que el índice vectorial en Neo4j exista y tenga la dimensión correcta"""
        if not self.neo4j_driver:
            return
            
        try:
            with self.neo4j_driver.session() as session:
                # 1. Verificar índices existentes
                result = session.run("SHOW INDEXES YIELD name, type, options WHERE type = 'VECTOR'")
                indexes = [record for record in result]
                index_exists = False
                dims_match = False
                
                for idx in indexes:
                    if idx['name'] == 'conversation_embeddings':
                        index_exists = True
                        options = idx['options']
                        # Extraer dimensiones de la configuración del índice
                        if options and 'indexConfig' in options:
                            config = options['indexConfig']
                            # Las claves pueden variar ligeramente entre versiones de Neo4j (ej. 'vector.dimensions' o '`vector.dimensions`')
                            dim_key = next((k for k in config.keys() if 'dimensions' in k), None)
                            if dim_key and config[dim_key] == self.embedding_dims:
                                dims_match = True
                                
                # 2. Si no existe o las dimensiones cambiaron, recrearlo
                if index_exists and not dims_match:
                    print(f"[MEMORY CORE] ⚠️ Dimensions mismatch in Neo4j index. Recreating with {self.embedding_dims} dims...")
                    session.run("DROP INDEX conversation_embeddings")
                    index_exists = False
                    
                if not index_exists:
                    print(f"[MEMORY CORE] 🔨 Creating Neo4j vector index with {self.embedding_dims} dimensions...")
                    session.run(f"CALL db.index.vector.createNodeIndex('conversation_embeddings', 'Conversation', 'embedding', {self.embedding_dims}, 'cosine')")
                    print("[MEMORY CORE] ✅ Neo4j vector index created successfully")
        except Exception as e:
            print(f"[MEMORY CORE] ⚠️ Failed to verify/create Neo4j index: {e}")
    
    def _init_schema(self):
        cur = self.conn.cursor()
        
        # Check if embedding column exists
        cur.execute("PRAGMA table_info(conversations)")
        columns = [row[1] for row in cur.fetchall()]
        if columns and 'embedding' not in columns:
            cur.execute("ALTER TABLE conversations ADD COLUMN embedding BLOB")
            
        # Full conversations table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                timestamp REAL NOT NULL,
                speaker TEXT NOT NULL,
                message TEXT NOT NULL,
                context TEXT,
                embedding BLOB,
                tags TEXT
            )
        """)
        
        # Vector cache
        cur.execute("""
            CREATE TABLE IF NOT EXISTS embeddings (
                id TEXT PRIMARY KEY,
                message_id TEXT,
                embedding BLOB,
                model TEXT,
                created_at INTEGER
            )
        """)
        
        # Entities table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS entities (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                first_mentioned REAL,
                last_mentioned REAL,
                mention_count INTEGER DEFAULT 1,
                verified BOOLEAN DEFAULT 0,
                truth TEXT
            )
        """)
        
        # Contradictions table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS contradictions (
                id TEXT PRIMARY KEY,
                entity_id TEXT,
                memory1_id TEXT,
                memory2_id TEXT,
                conflict TEXT,
                status TEXT DEFAULT 'pending',
                resolution TEXT,
                resolved_by TEXT,
                resolved_at REAL
            )
        """)
        
        cur.execute("CREATE INDEX IF NOT EXISTS idx_conv_time ON conversations(timestamp)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_conv_speaker ON conversations(speaker)")
        self.conn.commit()

    def _normalize_embedding_vector(self, vector: np.ndarray) -> np.ndarray:
        """Normalize any embedding vector to the configured dimensionality."""
        if vector is None:
            return np.zeros(self.embedding_dims, dtype=np.float32)

        v = np.asarray(vector, dtype=np.float32).reshape(-1)
        if v.size == 0:
            return np.zeros(self.embedding_dims, dtype=np.float32)

        if v.size == self.embedding_dims:
            out = v
        elif v.size > self.embedding_dims:
            # If dimensions are divisible (e.g. 1536 -> 384), average buckets.
            if v.size % self.embedding_dims == 0:
                factor = v.size // self.embedding_dims
                out = v.reshape(self.embedding_dims, factor).mean(axis=1)
            else:
                out = v[: self.embedding_dims]
        else:
            out = np.pad(v, (0, self.embedding_dims - v.size), mode="constant")

        norm = np.linalg.norm(out)
        if norm > 0:
            out = out / norm
        return out.astype(np.float32)

    def _normalize_embedding_bytes(self, embedding: bytes) -> Optional[bytes]:
        """Normalize serialized embedding bytes to the configured dimensionality."""
        if not embedding:
            return None
        try:
            vec = np.frombuffer(embedding, dtype=np.float32)
            if vec.size == 0:
                return None
            return self._normalize_embedding_vector(vec).tobytes()
        except Exception:
            return None
    
    def _get_embedding(self, text: str) -> Optional[bytes]:
        """Get embedding for text using OpenAI with SQLite cache"""
        if not EMBEDDINGS_AVAILABLE:
            # Fallback pseudo-embedding
            h = hashlib.sha256(text.encode()).digest()
            emb = [float(b) / 255.0 for b in h] * 64
            return self._normalize_embedding_vector(np.array(emb, dtype=np.float32)).tobytes()
        
        try:
            cur = self.conn.cursor()
            text_hash = hashlib.md5(text.encode()).hexdigest()
            cur.execute("SELECT embedding FROM embeddings WHERE id = ?", (text_hash,))
            row = cur.fetchone()
            
            if row:
                normalized_cached = self._normalize_embedding_bytes(row[0])
                if normalized_cached and normalized_cached != row[0]:
                    cur.execute(
                        "UPDATE embeddings SET embedding = ?, model = ?, created_at = ? WHERE id = ?",
                        (normalized_cached, "fastembed:paraphrase-multilingual-MiniLM-L12-v2", int(time.time()), text_hash),
                    )
                    self.conn.commit()
                return normalized_cached
            
            vector = get_openai_embedding(text)
            normalized_vec = self._normalize_embedding_vector(np.array(vector, dtype=np.float32))
            embedding_bytes = normalized_vec.tobytes()
            
            cur.execute(
                "INSERT OR REPLACE INTO embeddings (id, embedding, model, created_at) VALUES (?, ?, ?, ?)",
                (text_hash, embedding_bytes, "fastembed:paraphrase-multilingual-MiniLM-L12-v2", int(time.time()))
            )
            self.conn.commit()
            return embedding_bytes
        except Exception as e:
            print(f"[EMBEDDINGS] Error: {e}")
            return None
    
    def store_message(self, speaker: str, message: str, context: str = "", tags: List[str] = None) -> str:
        """Store a complete message with embedding in both SQLite and Neo4j"""
        import uuid
        
        msg_id = str(uuid.uuid4())[:16]
        timestamp = time.time()
        
        # Generate embedding
        full_text = f"{speaker}: {message}" if speaker else message
        embedding = self._get_embedding(full_text)
        
        cur = self.conn.cursor()
        cur.execute("""
            INSERT INTO conversations (id, timestamp, speaker, message, context, embedding, tags)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (msg_id, timestamp, speaker, message, context, embedding, json.dumps(tags or [])))
        self.conn.commit()
        
        # Extract entities (basic regex for now, phase 2 handles this better via dreamer)
        self._extract_entities(message, tags or [])
        
        # Sync to Neo4j Vector Index
        if self.neo4j_driver and embedding:
            try:
                emb_array = np.frombuffer(embedding, dtype=np.float32).tolist()
                with self.neo4j_driver.session() as session:
                    session.run("""
                    MERGE (c:Conversation {id: $id})
                    SET c.timestamp = $ts, c.speaker = $speaker, c.message = $msg, 
                        c.context = $ctx, c.tags = $tags, c.embedding = $emb
                    """, id=msg_id, ts=timestamp, speaker=speaker, msg=message, 
                         ctx=context, tags=tags or [], emb=emb_array)
            except Exception as e:
                print(f"[MEMORY CORE] Neo4j sync error: {e}")
                
        return msg_id
    
    def _extract_entities(self, message: str, tags: List[str]):
        """Basic entity extraction fallback"""
        import re
        import uuid
        cur = self.conn.cursor()
        
        names = re.findall(r'\b([A-Z][a-z]+)\b', message)
        for name in names:
            cur.execute("SELECT * FROM entities WHERE name = ? AND type = 'person'", (name,))
            existing = cur.fetchone()
            if existing:
                cur.execute("UPDATE entities SET mention_count = mention_count + 1, last_mentioned = ? WHERE id = ?", (time.time(), existing['id']))
            else:
                cur.execute("INSERT INTO entities (id, name, type, first_mentioned, last_mentioned) VALUES (?, ?, 'person', ?, ?)", (str(uuid.uuid4())[:8], name, time.time(), time.time()))
        
        tech_keywords = ['n8n', 'python', 'react', 'node', 'javascript', 'neo4j', 'redis', 'gpt', 'ai', 'openai', 'docker', 'postgres']
        for tech in tech_keywords:
            if tech.lower() in message.lower():
                cur.execute("SELECT * FROM entities WHERE name = ? AND type = 'tech'", (tech,))
                if not cur.fetchone():
                    cur.execute("INSERT INTO entities (id, name, type, first_mentioned, last_mentioned) VALUES (?, ?, 'tech', ?, ?)", (str(uuid.uuid4())[:8], tech, time.time(), time.time()))
        self.conn.commit()
    
    def search_context(self, query: str, limit: int = 15) -> List[Dict]:
        """Semantic search using Neo4j Vector Index or SQLite Fast Numpy fallback"""
        query_embedding = self._get_embedding(query)
        if not query_embedding:
            return []
            
        emb_array = np.frombuffer(query_embedding, dtype=np.float32).tolist()
        
        # Verify vector is valid and finite
        if sum(abs(x) for x in emb_array) == 0 or not all(np.isfinite(x) for x in emb_array):
            print("[MEMORY CORE] Invalid query vector detected (all zeros or non-finite). Aborting search.")
            return []
        
        # 1. Primary: Neo4j Vector Search (Instant on Millions of rows)
        if self.neo4j_driver:
            try:
                with self.neo4j_driver.session() as session:
                    res = session.run("""
                    CALL db.index.vector.queryNodes('conversation_embeddings', $limit, $emb) YIELD node, score
                    WHERE score > 0.15
                    RETURN node.id as id, node.timestamp as timestamp, node.speaker as speaker, 
                           node.message as message, node.context as context, node.tags as tags, score as similarity
                    """, limit=limit, emb=emb_array)
                    
                    results = []
                    for row in res:
                        results.append({
                            'id': row['id'],
                            'timestamp': row['timestamp'],
                            'speaker': row['speaker'],
                            'message': row['message'],
                            'context': row['context'],
                            'tags': row['tags'] or [],
                            'similarity': row['similarity']
                        })
                    if results:
                        return results
            except Exception as e:
                print(f"[MEMORY CORE] Neo4j search error (falling back to SQLite): {e}")

        # 2. Fallback: SQLite Full Numpy Vector Search (No 50 limit)
        cur = self.conn.cursor()
        cur.execute("SELECT id, timestamp, speaker, message, context, tags, embedding FROM conversations WHERE embedding IS NOT NULL")
        rows = cur.fetchall()
        
        if not rows:
            return []
            
        # Fast numpy matrix multiplication across all vectors
        query_vec = np.array(emb_array, dtype=np.float32)
        query_norm = np.linalg.norm(query_vec)
        if query_norm == 0:
            return []
            
        embeddings = []
        valid_rows = []
        for r in rows:
            if r['embedding']:
                vec = np.frombuffer(r['embedding'], dtype=np.float32)
                if vec.shape[0] != query_vec.shape[0]:
                    vec = self._normalize_embedding_vector(vec)
                embeddings.append(vec)
                valid_rows.append(r)
                    
        if not embeddings:
            return []
            
        emb_matrix = np.vstack(embeddings)
        norms = np.linalg.norm(emb_matrix, axis=1)
        
        # Calculate cosine similarities
        similarities = np.dot(emb_matrix, query_vec) / (norms * query_norm + 1e-10)
        
        results = []
        for idx, sim in enumerate(similarities):
            if sim > 0.15:
                r = valid_rows[idx]
                results.append({
                    'id': r['id'],
                    'timestamp': r['timestamp'],
                    'speaker': r['speaker'],
                    'message': r['message'],
                    'context': r['context'],
                    'tags': json.loads(r['tags']) if r['tags'] else [],
                    'similarity': float(sim)
                })
                
        results.sort(key=lambda x: x['similarity'], reverse=True)
        return results[:limit]
    
    def get_recent_context(self, hours: int = 24, limit: int = 50) -> List[Dict]:
        """Get recent conversation context"""
        cutoff = time.time() - (hours * 3600)
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM conversations WHERE timestamp > ? ORDER BY timestamp DESC LIMIT ?", (cutoff, limit))
        return [dict(row) for row in cur.fetchall()]
    
    def get_entities(self, type_filter: str = None) -> List[Dict]:
        """Get all entities"""
        cur = self.conn.cursor()
        if type_filter:
            cur.execute("SELECT * FROM entities WHERE type = ? ORDER BY mention_count DESC", (type_filter,))
        else:
            cur.execute("SELECT * FROM entities ORDER BY mention_count DESC")
        return [dict(row) for row in cur.fetchall()]
    
    def get_context_summary(self) -> Dict:
        """Get summary of memory context"""
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) as total FROM conversations")
        total = cur.fetchone()['total']
        cur.execute("SELECT COUNT(*) as verified FROM entities WHERE verified = 1")
        verified = cur.fetchone()['verified']
        return {
            'total_conversations': total,
            'verified_entities': verified
        }
    
    def close(self):
        if self.neo4j_driver:
            self.neo4j_driver.close()
        self.conn.close()

# Singleton instance
_core = None

def get_memory_core() -> MemoryCore:
    global _core
    if _core is None:
        _core = MemoryCore()
    return _core

if __name__ == "__main__":
    core = get_memory_core()
    
    print("\n=== Testing Industrial Semantic Search ===")
    core.store_message("user", "El proyecto de automation usa Neo4j y Redis para escalar", tags=['tech'])
    
    start = time.time()
    results = core.search_context("qué tecnología usa el proyecto de automation?", limit=5)
    elapsed = (time.time() - start) * 1000
    
    print(f"\nSearch completed in {elapsed:.2f}ms")
    for r in results:
        print(f"  [{r['speaker']}] {r['message'][:80]}... (sim: {r.get('similarity', 0):.2f})")
    
    core.close()

    def find_contradictions(self):
        """Find potential contradictions in memories"""
        cur = self.conn.cursor()
        cur.execute(
            "SELECT * FROM entities WHERE mention_count > 1 ORDER BY mention_count DESC LIMIT 200"
        )
        entities = [dict(row) for row in cur.fetchall()]
        
        contradictions = []
        for entity in entities:
            # Excluir embedding (blob innecesario) y limitar resultados
            cur.execute("""
                SELECT id, timestamp, speaker, message, context, tags FROM conversations
                WHERE message LIKE ?
                ORDER BY timestamp
                LIMIT 200
            """, (f"%{entity['name']}%",))

            messages = [dict(row) for row in cur.fetchall()]
            positive_words = ['good', 'great', 'love', 'like', 'best', 'excelent', 'bien', 'mejor', 'gusta', 'feliz']
            negative_words = ['bad', 'terrible', 'hate', 'dislike', 'worst', 'mal', 'peor', 'odiar', 'triste']
            
            positive_mentions = [m for m in messages if any(w in m['message'].lower() for w in positive_words)]
            negative_mentions = [m for m in messages if any(w in m['message'].lower() for w in negative_words)]
            
            if positive_mentions and negative_mentions:
                contradictions.append({
                    'entity': entity['name'],
                    'positive_count': len(positive_mentions),
                    'negative_count': len(negative_mentions),
                    'positive_examples': [p['message'][:100] for p in positive_mentions[-2:]],
                    'negative_examples': [n['message'][:100] for n in negative_mentions[-2:]],
                    'status': 'pending'
                })
        return contradictions

    def verify_entity(self, entity_id, truth, updated_by):
        """Verify an entity resolution"""
        try:
            cur = self.conn.cursor()
            cur.execute("""
                UPDATE entities 
                SET attributes = json_insert(COALESCE(attributes, '{}'), '$.truth', ?),
                    verified = 1
                WHERE id = ?
            """, (truth, entity_id))
            self.conn.commit()
            return True
        except Exception as e:
            print(f"Error verifying entity: {e}")
            return False

    def find_contradictions(self):
        """Find potential contradictions in memories"""
        cur = self.conn.cursor()
        cur.execute(
            "SELECT * FROM entities WHERE mention_count > 1 ORDER BY mention_count DESC LIMIT 200"
        )
        entities = [dict(row) for row in cur.fetchall()]
        
        contradictions = []
        for entity in entities:
            # Excluir embedding (blob innecesario) y limitar resultados
            cur.execute("""
                SELECT id, timestamp, speaker, message, context, tags FROM conversations
                WHERE message LIKE ?
                ORDER BY timestamp
                LIMIT 200
            """, (f"%{entity['name']}%",))

            messages = [dict(row) for row in cur.fetchall()]
            positive_words = ['good', 'great', 'love', 'like', 'best', 'excelent', 'bien', 'mejor', 'gusta', 'feliz']
            negative_words = ['bad', 'terrible', 'hate', 'dislike', 'worst', 'mal', 'peor', 'odiar', 'triste']
            
            positive_mentions = [m for m in messages if any(w in m['message'].lower() for w in positive_words)]
            negative_mentions = [m for m in messages if any(w in m['message'].lower() for w in negative_words)]
            
            if positive_mentions and negative_mentions:
                contradictions.append({
                    'entity': entity['name'],
                    'positive_count': len(positive_mentions),
                    'negative_count': len(negative_mentions),
                    'positive_examples': [p['message'][:100] for p in positive_mentions[-2:]],
                    'negative_examples': [n['message'][:100] for n in negative_mentions[-2:]],
                    'status': 'pending'
                })
        return contradictions

    def verify_entity(self, entity_id, truth, updated_by):
        """Verify an entity resolution"""
        try:
            cur = self.conn.cursor()
            cur.execute("""
                UPDATE entities 
                SET attributes = json_insert(COALESCE(attributes, '{}'), '$.truth', ?),
                    verified = 1
                WHERE id = ?
            """, (truth, entity_id))
            self.conn.commit()
            return True
        except Exception as e:
            print(f"Error verifying entity: {e}")
            return False
