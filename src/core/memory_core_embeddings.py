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
import bisect
import re
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

# Usar ZhipuAI embeddings (embedding-2, 1024 dims). Fallback a búsqueda simple.
try:
    from local_embeddings import get_embedding as get_openai_embedding, cosine_similarity
    EMBEDDINGS_AVAILABLE = True
    print("[EMBEDDINGS] ZhipuAI embedding-2 available")
except Exception as _zhipu_err:
    try:
        from openai_embeddings import get_openai_embedding, cosine_similarity
        EMBEDDINGS_AVAILABLE = True
        print("[EMBEDDINGS] OpenAI embeddings available (fallback)")
    except ImportError:
        EMBEDDINGS_AVAILABLE = False
        print(f"[EMBEDDINGS] Using simple similarity (no ZhipuAI/OpenAI): {_zhipu_err}")

DB_PATH = os.path.join(os.getenv('BRAIN_DATA_DIR', '/root/silhouette-brain/data'), 'memory_core.db')
EMBEDDING_DIMS = int(os.getenv("EMBEDDING_DIMS", "384"))
TOKEN_RE = re.compile(r"[a-z0-9@._-]{3,}", re.IGNORECASE)
SEMANTIC_STOPWORDS = {
    "para", "como", "con", "sin", "por", "del", "las", "los", "que", "una", "uno",
    "unos", "unas", "sobre", "desde", "hasta", "donde", "cuando", "estado", "actual",
    "quiero", "saber", "tengo", "tiene", "tienen", "esto", "esta", "este", "estos",
    "estas", "about", "with", "from", "that", "this", "what", "when", "where", "your",
}
TOOL_NOISE_HINTS = (
    "<<<external_untrusted_content",
    "\"status\": \"error\"",
    "successfully wrote",
    "session synced",
    "web fetch failed",
    "current time:",
    "[cron:",
    "(no output)",
)

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
        # Índice crítico para traer contexto reciente sin escanear toda la tabla.
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_conversations_emb_ts
            ON conversations(timestamp DESC)
            WHERE embedding IS NOT NULL
        """)
        self.conn.commit()

    def _normalize_vector(self, vector: np.ndarray) -> np.ndarray:
        """Normalize any embedding vector to EMBEDDING_DIMS."""
        v = np.asarray(vector, dtype=np.float32).reshape(-1)
        if v.size == 0:
            return np.zeros(EMBEDDING_DIMS, dtype=np.float32)

        if v.size == EMBEDDING_DIMS:
            out = v
        elif v.size > EMBEDDING_DIMS:
            if v.size % EMBEDDING_DIMS == 0:
                factor = v.size // EMBEDDING_DIMS
                out = v.reshape(EMBEDDING_DIMS, factor).mean(axis=1)
            else:
                out = v[:EMBEDDING_DIMS]
        else:
            out = np.pad(v, (0, EMBEDDING_DIMS - v.size), mode='constant')

        norm = np.linalg.norm(out)
        if norm > 0:
            out = out / norm
        return out.astype(np.float32)

    def _normalize_embedding_bytes(self, embedding: bytes) -> Optional[bytes]:
        if not embedding:
            return None
        try:
            vec = np.frombuffer(embedding, dtype=np.float32)
            if vec.size == 0:
                return None
            return self._normalize_vector(vec).tobytes()
        except Exception:
            return None
    
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
                normalized_cached = self._normalize_embedding_bytes(row[0])
                if normalized_cached and normalized_cached != row[0]:
                    cursor.execute(
                        "UPDATE embeddings SET embedding = ?, model = ?, created_at = ? WHERE id = ?",
                        (normalized_cached, os.getenv("EMBEDDING_MODEL", "fastembed:paraphrase-multilingual-MiniLM-L12-v2"), int(time.time()), text_hash),
                    )
                    self.conn.commit()
                return normalized_cached
            
            # Generate new embedding
            vector = get_openai_embedding(text)
            embedding_bytes = self._normalize_vector(np.array(vector, dtype=np.float32)).tobytes()
            
            # Cache it
            cursor.execute(
                "INSERT OR REPLACE INTO embeddings (id, embedding, model, created_at) VALUES (?, ?, ?, ?)",
                (text_hash, embedding_bytes, os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"), int(time.time()))
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

            if vec1.shape != vec2.shape:
                vec1 = self._normalize_vector(vec1)
                vec2 = self._normalize_vector(vec2)

            dot = np.dot(vec1, vec2)
            norm1 = np.linalg.norm(vec1)
            norm2 = np.linalg.norm(vec2)

            if norm1 == 0 or norm2 == 0:
                return 0

            return float(dot / (norm1 * norm2))
        except:
            return 0

    def _extract_query_terms(self, query: str) -> List[str]:
        lowered = (query or "").lower()
        terms = []
        for match in TOKEN_RE.findall(lowered):
            token = match.strip().lower()
            if len(token) < 3:
                continue
            if token in SEMANTIC_STOPWORDS:
                continue
            if token not in terms:
                terms.append(token)
        return terms

    def _lexical_match_score(self, query: str, query_terms: List[str], message: str) -> float:
        text = (message or "").lower()
        if not text:
            return 0.0
        score = 0.0
        q = (query or "").strip().lower()
        if q and len(q) >= 4 and q in text:
            score += 0.20
        if query_terms:
            hits = sum(1 for term in query_terms if term in text)
            ratio = hits / float(len(query_terms))
            score += ratio * 0.30
            if hits > 0:
                score += min(0.08, 0.02 * hits)
        return min(score, 0.45)

    def _tool_noise_penalty(self, speaker: str, message: str, allow_runtime_noise: bool) -> float:
        if allow_runtime_noise:
            return 0.0
        msg = (message or "").strip().lower()
        if not msg:
            return 0.0
        penalty = 0.0
        spk = (speaker or "").strip().lower()
        if spk == "toolresult":
            penalty += 0.08
            if msg.startswith("{") or msg.startswith("["):
                penalty += 0.05
        if any(hint in msg for hint in TOOL_NOISE_HINTS):
            penalty += 0.08
        if len(msg) > 600 and (msg.startswith("{") or msg.startswith("[")):
            penalty += 0.06
        return min(penalty, 0.22)

    def _recency_bonus(self, timestamp: int) -> float:
        if not timestamp:
            return 0.0
        age_days = max(0.0, (time.time() - float(timestamp)) / 86400.0)
        if age_days <= 3:
            return 0.03
        if age_days <= 14:
            return 0.015
        return 0.0
    
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
        """
        Búsqueda semántica acotada para producción:
        - conserva embeddings (no degrada a texto salvo fallo real),
        - limita carga de CPU con scan/time budget,
        - reconstruye contexto narrativo local sin O(N*M).
        """
        cursor = self.conn.cursor()
        allow_runtime_noise = is_runtime_diagnostic_query(query)
        
        query_embedding_bytes = self._get_embedding(query)
        if not query_embedding_bytes:
            return self._fallback_search(query, limit, allow_runtime_noise)

        query_vec = self._normalize_vector(np.frombuffer(query_embedding_bytes, dtype=np.float32))
        norm_q = np.linalg.norm(query_vec)
        if norm_q == 0:
            return self._fallback_search(query, limit, allow_runtime_noise)

        start_ts = time.time()
        time_budget_ms = max(1500, int(os.getenv("SEMANTIC_TIME_BUDGET_MS", "9000")))
        max_scan_cap = max(2000, int(os.getenv("SEMANTIC_SCAN_LIMIT", "9000")))
        scan_limit = min(max_scan_cap, max(3000, int(limit) * 1200))
        score_threshold = float(os.getenv("SEMANTIC_SCORE_THRESHOLD", "0.20"))
        neighbor_window_sec = max(600, int(os.getenv("SEMANTIC_NEIGHBOR_WINDOW_SEC", "7200")))
        neighbor_cap = max(limit * 8, int(os.getenv("SEMANTIC_NEIGHBOR_CAP", "60")))
        candidate_pool = max(limit * 8, 24)
        longtail_enabled = os.getenv("SEMANTIC_LONGTAIL_ENABLED", "1").strip().lower() not in ("0", "false", "no", "off")
        longtail_days = max(7, int(os.getenv("SEMANTIC_LONGTAIL_DAYS", "45")))
        raw_longtail_fraction = float(os.getenv("SEMANTIC_LONGTAIL_FRACTION", "0.30"))
        longtail_fraction = min(0.60, max(0.0, raw_longtail_fraction))

        def over_budget() -> bool:
            return (time.time() - start_ts) * 1000.0 >= float(time_budget_ms)

        query_terms = self._extract_query_terms(query)

        # Recuperación híbrida: reciente + largo plazo, sin apagar semántica.
        recent_limit = scan_limit
        longtail_limit = 0
        if longtail_enabled:
            longtail_limit = int(scan_limit * longtail_fraction)
            longtail_limit = min(max(0, longtail_limit), max(0, scan_limit // 2))
            recent_limit = max(1000, scan_limit - longtail_limit)

        cursor.execute("""
            SELECT id, timestamp, speaker, message, context, tags, embedding
            FROM conversations
            WHERE embedding IS NOT NULL
            ORDER BY timestamp DESC
            LIMIT ?
        """, (recent_limit,))
        rows = cursor.fetchall()

        if longtail_enabled and longtail_limit > 0 and not over_budget():
            cutoff_ts = int(time.time()) - (longtail_days * 86400)
            cursor.execute("""
                SELECT id, timestamp, speaker, message, context, tags, embedding
                FROM conversations
                WHERE embedding IS NOT NULL AND timestamp < ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (cutoff_ts, longtail_limit))
            old_rows = cursor.fetchall()
            if old_rows:
                known_ids = {r[0] for r in rows}
                for r in old_rows:
                    if r[0] not in known_ids:
                        rows.append(r)

        # Priorizar candidatos con match léxico explícito para evitar que
        # consultas de entidad ("UnityIris", "CRM", etc.) queden fuera por timeout.
        if query_terms and not over_budget():
            lexical_limit = max(80, limit * 24)
            where_parts = ["LOWER(message) LIKE ?"]
            lexical_params = [f"%{(query or '').strip().lower()}%"]
            for term in query_terms[:6]:
                where_parts.append("LOWER(message) LIKE ?")
                lexical_params.append(f"%{term}%")
            lexical_params.append(lexical_limit)
            cursor.execute(f"""
                SELECT id, timestamp, speaker, message, context, tags, embedding
                FROM conversations
                WHERE {' OR '.join(where_parts)}
                ORDER BY timestamp DESC
                LIMIT ?
            """, lexical_params)
            lexical_rows = cursor.fetchall()
            if lexical_rows:
                known_ids = {r[0] for r in rows}
                prioritized = [r for r in lexical_rows if r[0] not in known_ids]
                if prioritized:
                    rows = prioritized + rows

        if not rows:
            return []

        all_messages = []
        vectors = []

        for row in rows:
            if over_budget():
                break
            try:
                target_bytes = row[6]
                if not target_bytes:
                    continue

                target_vec = self._normalize_vector(np.frombuffer(target_bytes, dtype=np.float32))
                if not np.isfinite(target_vec).all():
                    continue

                msg = {
                    'id': row[0],
                    'timestamp': int(row[1] or 0),
                    'speaker': row[2],
                    'message': row[3],
                    'context': row[4],
                    'tags': json.loads(row[5]) if row[5] else [],
                    'similarity': 0.0,
                }
                all_messages.append(msg)
                vectors.append(target_vec)
            except Exception:
                continue

        if not all_messages or not vectors:
            return self._fallback_search(query, limit, allow_runtime_noise)

        emb_matrix = np.vstack(vectors).astype(np.float32, copy=False)
        norms = np.linalg.norm(emb_matrix, axis=1)
        similarities = np.dot(emb_matrix, query_vec) / (norms * norm_q + 1e-10)

        for idx, sim in enumerate(similarities):
            msg = all_messages[idx]
            raw_similarity = float(sim)
            message_text = msg.get("message", "")
            lexical_score = self._lexical_match_score(query, query_terms, message_text)
            tool_penalty = self._tool_noise_penalty(msg.get("speaker", ""), message_text, allow_runtime_noise)
            recency_bonus = self._recency_bonus(int(msg.get("timestamp", 0) or 0))
            short_penalty = 0.0
            stripped = (message_text or "").strip()
            if stripped:
                lowered = stripped.lower()
                has_term = any(term in lowered for term in query_terms) if query_terms else False
                if not has_term:
                    if len(stripped) < 18:
                        short_penalty = 0.12
                    elif len(stripped) < 36:
                        short_penalty = 0.07
            final_score = raw_similarity + lexical_score + recency_bonus - tool_penalty - short_penalty
            msg["similarity"] = raw_similarity
            msg["score"] = float(final_score)
            msg["lexical"] = float(lexical_score)

        matches = [m for m in all_messages if m.get("score", m["similarity"]) >= score_threshold]
        if matches:
            matches.sort(key=lambda x: (x.get("score", x["similarity"]), x["similarity"]), reverse=True)
            matches = matches[:candidate_pool]
        else:
            matches = sorted(
                all_messages,
                key=lambda x: (x.get("score", x["similarity"]), x["similarity"]),
                reverse=True,
            )[:max(limit * 3, 12)]

        # --- Reconstrucción de contexto narrativo acotada ---
        timeline = sorted(all_messages, key=lambda x: x["timestamp"])
        timeline_ts = [m["timestamp"] for m in timeline]
        final_context = {}
        seed_limit = max(limit * 4, 12)
        for match in matches[:seed_limit]:
            if over_budget() or len(final_context) >= neighbor_cap:
                break
            mid = match.get("id")
            if mid:
                final_context[mid] = match

            ts = int(match.get("timestamp", 0))
            left = bisect.bisect_left(timeline_ts, ts - neighbor_window_sec)
            right = bisect.bisect_right(timeline_ts, ts + neighbor_window_sec)
            for other in timeline[left:right]:
                oid = other.get("id")
                if not oid or oid in final_context:
                    continue
                enriched = dict(other)
                own_score = float(other.get("score", other.get("similarity", 0.0)))
                seed_score = float(match.get("score", match.get("similarity", 0.0)))
                enriched["score"] = max(own_score * 0.6, seed_score * 0.35)
                final_context[oid] = enriched
                if len(final_context) >= neighbor_cap:
                    break

        # Convertir a lista y limpiar ruido
        results = list(final_context.values())
        if not allow_runtime_noise:
            results = [r for r in results if not is_operational_runtime_noise(r.get('message', ''))]

        # Ordenar por score híbrido (semántica + léxico + recencia - ruido)
        results.sort(
            key=lambda x: (
                float(x.get("score", x.get("similarity", 0.0))),
                float(x.get("similarity", 0.0)),
                int(x.get("timestamp", 0) or 0),
            ),
            reverse=True,
        )

        # Quitar duplicados casi idénticos de output operativo
        deduped: List[Dict] = []
        seen = set()
        for row in results:
            msg = (row.get("message") or "").strip().lower()
            key = ((row.get("speaker") or "").strip().lower(), re.sub(r"\s+", " ", msg[:180]))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(row)
            if len(deduped) >= limit * 2:
                break

        return deduped

    def _fallback_search(self, query: str, limit: int, allow_runtime_noise: bool) -> List[Dict]:
        """Búsqueda por texto simple si fallan los embeddings"""
        cursor = self.conn.cursor()
        sql_limit = max(limit * 4, 40)
        query_terms = self._extract_query_terms(query)
        where_parts = ["LOWER(message) LIKE ?"]
        params = [f"%{(query or '').lower()}%"]
        for term in query_terms[:5]:
            where_parts.append("LOWER(message) LIKE ?")
            params.append(f"%{term}%")
        params.append(sql_limit)

        cursor.execute(f"""
            SELECT id, timestamp, speaker, message, context, tags
            FROM conversations
            WHERE {' OR '.join(where_parts)}
            ORDER BY timestamp DESC
            LIMIT ?
        """, params)
        
        res = [dict(row) for row in cursor.fetchall()]
        if not allow_runtime_noise:
            res = [r for r in res if not is_operational_runtime_noise(r.get('message', ''))]
        for row in res:
            lexical = self._lexical_match_score(query, query_terms, row.get("message", ""))
            recency = self._recency_bonus(int(row.get("timestamp", 0) or 0))
            penalty = self._tool_noise_penalty(row.get("speaker", ""), row.get("message", ""), allow_runtime_noise)
            row["score"] = lexical + recency - penalty
            row["similarity"] = float(row.get("similarity", 0.0))
        res.sort(
            key=lambda x: (
                float(x.get("score", 0.0)),
                int(x.get("timestamp", 0) or 0),
            ),
            reverse=True,
        )
        return res[:limit]
    
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
