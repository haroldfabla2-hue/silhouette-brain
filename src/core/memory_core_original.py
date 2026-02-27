import os
#!/usr/bin/env python3
"""
Silhouette Memory Core - Full Context Memory System
Real storage of complete conversations with semantic search
"""
import time
import json
import hashlib
import sqlite3
import threading
from datetime import datetime, timezone
from typing import List, Dict, Optional
from pathlib import Path

# Database setup
DB_PATH = os.getenv("BRAIN_DATA_DIR", "./data"/memory_core.db"
Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)

class MemoryCore:
    """Full context memory with semantic search"""
    
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()
        print("[MEMORY CORE] ✅ Initialized")
    
    def _init_schema(self):
        cur = self.conn.cursor()
        
        # Full conversations table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                timestamp REAL NOT NULL,
                speaker TEXT NOT NULL,  -- 'user' or 'assistant'
                message TEXT NOT NULL,
                context TEXT,  -- related context
                embedding BLOB,
                tags TEXT  -- auto-extracted tags
            )
        """)
        
        # Entities table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS entities (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT NOT NULL,  -- person, project, company, tech, preference
                first_mentioned REAL,
                last_mentioned REAL,
                mention_count INTEGER DEFAULT 1,
                verified BOOLEAN DEFAULT 0,  -- verified by team
                truth TEXT  -- verified truth
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
                status TEXT DEFAULT 'pending',  -- pending, investigating, resolved
                resolution TEXT,
                resolved_by TEXT,
                resolved_at REAL
            )
        """)
        
        # Context relationships
        cur.execute("""
            CREATE TABLE IF NOT EXISTS context_links (
                id TEXT PRIMARY KEY,
                from_conversation TEXT,
                to_conversation TEXT,
                link_type TEXT,  -- similar, contradicts, relates, follows
                strength REAL DEFAULT 0.5
            )
        """)
        
        # Indexes
        cur.execute("CREATE INDEX IF NOT EXISTS idx_conv_time ON conversations(timestamp)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_conv_speaker ON conversations(speaker)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(type)")
        
        self.conn.commit()
    
    def _generate_embedding(self, text: str) -> bytes:
        """Generate simple embedding for semantic search"""
        # Simple hash-based embedding
        h = hashlib.sha256(text.encode()).digest()
        # Create pseudo-embedding
        emb = [float(b) / 255.0 for b in h] * 64
        return bytes([int(x * 255) for x in emb[:256]])
    
    def _simple_similarity(self, text1: str, text2: str) -> float:
        """Calculate simple text similarity"""
        # Word overlap
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1 & words2
        union = words1 | words2
        
        return len(intersection) / len(union)
    
    def store_message(self, speaker: str, message: str, context: str = "", tags: List[str] = None) -> str:
        """Store a complete message"""
        import uuid
        
        msg_id = str(uuid.uuid4())[:12]
        timestamp = time.time()
        
        # Generate embedding
        full_text = f"{speaker}: {message}"
        embedding = self._generate_embedding(full_text)
        
        cur = self.conn.cursor()
        cur.execute("""
            INSERT INTO conversations (id, timestamp, speaker, message, context, embedding, tags)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (msg_id, timestamp, speaker, message, context, embedding, json.dumps(tags or [])))
        
        self.conn.commit()
        
        # Extract and store entities
        self._extract_entities(message, tags or [])
        
        return msg_id
    
    def _extract_entities(self, message: str, tags: List[str]):
        """Extract entities from message"""
        import re
        import uuid
        
        cur = self.conn.cursor()
        
        # Extract names (capitalized words)
        names = re.findall(r'\b([A-Z][a-z]+)\b', message)
        
        for name in names:
            # Check if exists
            cur.execute("SELECT * FROM entities WHERE name = ? AND type = 'person'", (name,))
            existing = cur.fetchone()
            
            if existing:
                # Update mention count
                cur.execute("""
                    UPDATE entities SET 
                        mention_count = mention_count + 1,
                        last_mentioned = ?
                    WHERE id = ?
                """, (time.time(), existing['id']))
            else:
                # Create new entity
                entity_id = str(uuid.uuid4())[:8]
                cur.execute("""
                    INSERT INTO entities (id, name, type, first_mentioned, last_mentioned)
                    VALUES (?, ?, 'person', ?, ?)
                """, (entity_id, name, time.time(), time.time()))
        
        # Extract technologies
        tech_keywords = ['n8n', 'python', 'react', 'node', 'javascript', 'neo4j', 'redis', 
                       'gpt', 'ai', 'openai', 'docker', 'postgres', 'mongodb']
        
        for tech in tech_keywords:
            if tech.lower() in message.lower():
                cur.execute("SELECT * FROM entities WHERE name = ? AND type = 'tech'", (tech,))
                if not cur.fetchone():
                    entity_id = str(uuid.uuid4())[:8]
                    cur.execute("""
                        INSERT INTO entities (id, name, type, first_mentioned, last_mentioned)
                        VALUES (?, ?, 'tech', ?, ?)
                    """, (entity_id, tech, time.time(), time.time()))
        
        self.conn.commit()
    
    def search_context(self, query: str, limit: int = 10) -> List[Dict]:
        """Semantic search in conversation history"""
        cur = self.conn.cursor()
        
        # Get all recent conversations
        cur.execute("""
            SELECT * FROM conversations 
            ORDER BY timestamp DESC 
            LIMIT 100
        """)
        
        conversations = [dict(row) for row in cur.fetchall()]
        
        # Calculate similarity
        results = []
        for conv in conversations:
            # Check message content
            message = conv['message']
            similarity = self._simple_similarity(query, message)
            
            if similarity > 0.1:  # Threshold
                results.append({
                    'id': conv['id'],
                    'timestamp': conv['timestamp'],
                    'speaker': conv['speaker'],
                    'message': conv['message'][:200],
                    'similarity': similarity,
                    'tags': json.loads(conv['tags']) if conv['tags'] else []
                })
        
        # Sort by similarity and return top results
        results.sort(key=lambda x: x['similarity'], reverse=True)
        return results[:limit]
    
    def get_recent_context(self, hours: int = 24, limit: int = 50) -> List[Dict]:
        """Get recent conversation context"""
        import time
        cutoff = time.time() - (hours * 3600)
        
        cur = self.conn.cursor()
        cur.execute("""
            SELECT * FROM conversations 
            WHERE timestamp > ?
            ORDER BY timestamp DESC
            LIMIT ?
        """, (cutoff, limit))
        
        return [dict(row) for row in cur.fetchall()]
    
    def get_entities(self, type_filter: str = None) -> List[Dict]:
        """Get all entities"""
        cur = self.conn.cursor()
        
        if type_filter:
            cur.execute("SELECT * FROM entities WHERE type = ? ORDER BY mention_count DESC", (type_filter,))
        else:
            cur.execute("SELECT * FROM entities ORDER BY mention_count DESC")
        
        return [dict(row) for row in cur.fetchall()]
    
    def verify_entity(self, entity_id: str, truth: str, verified_by: str):
        """Mark entity as verified with truth"""
        cur = self.conn.cursor()
        cur.execute("""
            UPDATE entities SET 
                verified = 1,
                truth = ?,
                mention_count = mention_count + 1
            WHERE id = ?
        """, (truth, entity_id))
        self.conn.commit()
    
    def find_contradictions(self) -> List[Dict]:
        """Find potential contradictions in memories"""
        cur = self.conn.cursor()
        
        # Get entities with multiple mentions
        cur.execute("SELECT * FROM entities WHERE mention_count > 1")
        entities = [dict(row) for row in cur.fetchall()]
        
        contradictions = []
        
        for entity in entities:
            # Get all messages mentioning this entity
            cur.execute("""
                SELECT * FROM conversations 
                WHERE message LIKE ?
                ORDER BY timestamp
            """, (f"%{entity['name']}%",))
            
            messages = [dict(row) for row in cur.fetchall()]
            
            # Check for sentiment contradictions
            positive_words = ['good', 'great', 'love', 'like', 'best', 'excelent', 'bien', 'mejor', 'gusta', 'feliz']
            negative_words = ['bad', 'terrible', 'hate', 'dislike', 'worst', 'mal', 'peor', 'odiar', 'triste']
            
            positive_mentions = []
            negative_mentions = []
            
            for msg in messages:
                msg_lower = msg['message'].lower()
                if any(w in msg_lower for w in positive_words):
                    positive_mentions.append(msg)
                if any(w in msg_lower for w in negative_words):
                    negative_mentions.append(msg)
            
            # Found contradiction
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
    
    def resolve_contradiction(self, contradiction_id: str, resolution: str, resolved_by: str):
        """Resolve a contradiction with truth"""
        cur = self.conn.cursor()
        cur.execute("""
            UPDATE contradictions SET 
                status = 'resolved',
                resolution = ?,
                resolved_by = ?,
                resolved_at = ?
            WHERE id = ?
        """, (resolution, resolved_by, time.time(), contradiction_id))
        self.conn.commit()
    
    def get_verified_truth(self, entity_name: str) -> Optional[Dict]:
        """Get verified truth for an entity"""
        cur = self.conn.cursor()
        cur.execute("""
            SELECT * FROM entities 
            WHERE name = ? AND verified = 1
        """, (entity_name,))
        
        row = cur.fetchone()
        return dict(row) if row else None
    
    def get_context_summary(self) -> Dict:
        """Get summary of memory context"""
        cur = self.conn.cursor()
        
        # Counts
        cur.execute("SELECT COUNT(*) as total FROM conversations")
        total = cur.fetchone()['total']
        
        cur.execute("SELECT COUNT(*) as verified FROM entities WHERE verified = 1")
        verified = cur.fetchone()['verified']
        
        cur.execute("SELECT COUNT(*) as pending FROM contradictions WHERE status = 'pending'")
        pending = cur.fetchone()['pending']
        
        # Recent speakers
        cur.execute("""
            SELECT speaker, COUNT(*) as count 
            FROM conversations 
            WHERE timestamp > ?
            GROUP BY speaker
        """, (time.time() - 86400,))  # Last 24 hours
        recent = [dict(row) for row in cur.fetchall()]
        
        return {
            'total_conversations': total,
            'verified_entities': verified,
            'pending_contradictions': pending,
            'recent_activity': recent
        }
    
    def close(self):
        self.conn.close()


# Singleton instance
_core = None

def get_memory_core() -> MemoryCore:
    global _core
    if _core is None:
        _core = MemoryCore()
    return _core

# Quick test
if __name__ == "__main__":
    core = get_memory_core()
    
    # Store test messages
    print("Testing memory store...")
    core.store_message("user", "Me llamo Alberto y trabajo en Brandistry usando n8n", tags=['persona', 'empresa', 'tech'])
    core.store_message("assistant", "Entendido Alberto! Voy a ayudarte con Brandistry", tags=['confirmacion'])
    core.store_message("user", "También uso Neo4j para el CRM", tags=['tech'])
    
    # Test search
    print("\nSearching for 'Alberto':")
    results = core.search_context("Alberto")
    for r in results:
        print(f"  [{r['speaker']}] {r['message'][:60]}... (sim: {r['similarity']:.2f})")
    
    # Test entities
    print("\nEntities:")
    entities = core.get_entities()
    for e in entities:
        print(f"  - {e['name']} ({e['type']}): {e['mention_count']} menciones")
    
    # Summary
    print("\nContext summary:")
    summary = core.get_context_summary()
    print(f"  Total: {summary['total_conversations']} conversaciones")
    print(f"  Verificadas: {summary['verified_entities']} entidades")
    
    core.close()
