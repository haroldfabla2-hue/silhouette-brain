import os
#!/usr/bin/env python3
"""
Silhouette Memory System v3.0 - Full Implementation
Complete replica of Silhouette-OS Memory System

Tiers:
- WORKING: Redis (fast cache)
- MEDIUM: SQLite (frequent access)
- LONG: SQLite (persistent)
- DEEP: SQLite (semantic - with embeddings)
"""
import json
import time
import uuid
import re
import hashlib
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict, field
from enum import Enum
import sqlite3

try:
    import redis
    REDIS_AVAILABLE = True
except:
    REDIS_AVAILABLE = False

try:
    from neo4j import GraphDatabase
    NEO4J_AVAILABLE = True
except:
    NEO4J_AVAILABLE = False

# Config
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "silhouette2035"
REDIS_HOST = "localhost"
REDIS_PORT = 6379

DB_PATH = os.getenv("BRAIN_DATA_DIR", "./data"/memory.db"
Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)

MAX_WORKING = 50
WORKING_TTL = 1800

class MemoryTier(Enum):
    WORKING = "WORKING"
    MEDIUM = "MEDIUM"
    LONG = "LONG"
    DEEP = "DEEP"

@dataclass
class MemoryNode:
    id: str
    content: str
    timestamp: float
    tier: str
    importance: float
    tags: List[str] = field(default_factory=list)
    owner_id: Optional[str] = None
    access_count: int = 0
    last_access: float = 0
    embedding: Optional[List[float]] = None
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'MemoryNode':
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

class Neo4jHandler:
    """Graph relationships"""
    def __init__(self):
        self.driver = None
        if NEO4J_AVAILABLE:
            try:
                self.driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
                self.driver.verify_connectivity()
                print("[NEO4J] ✅ Connected")
                self._init_schema()
            except Exception as e:
                print(f"[NEO4J] ❌ {e}")
    
    def _init_schema(self):
        if not self.driver:
            return
        with self.driver.session() as s:
            try:
                s.run("CREATE INDEX memory_id IF NOT EXISTS FOR (m:Memory) ON (m.id)")
                s.run("CREATE INDEX memory_tier IF NOT EXISTS FOR (m:Memory) ON (m.tier)")
            except:
                pass
    
    def add_node(self, node: MemoryNode):
        if not self.driver:
            return
        with self.driver.session() as s:
            s.run("""
                MERGE (m:Memory {id: $id})
                SET m.content = $content, m.timestamp = $timestamp,
                    m.tier = $tier, m.importance = $importance,
                    m.access_count = $access_count
            """, id=node.id, content=node.content, timestamp=node.timestamp,
                tier=node.tier, importance=node.importance, access_count=node.access_count)
            
            for tag in node.tags:
                s.run("""
                    MERGE (t:Tag {name: $tag})
                    WITH t
                    MATCH (m:Memory {id: $id})
                    MERGE (m)-[:TAGGED]->(t)
                """, id=node.id, tag=tag)
    
    def add_edge(self, from_id: str, to_id: str, rel_type: str):
        if not self.driver:
            return
        with self.driver.session() as s:
            s.run("""
                MATCH (a:Memory {id: $from_id}), (b:Memory {id: $to_id})
                MERGE (a)-[r:RELATED {type: $rel_type}]->(b)
            """, from_id=from_id, to_id=to_id, rel_type=rel_type)
    
    def find_by_tag(self, tag: str) -> List[Dict]:
        if not self.driver:
            return []
        with self.driver.session() as s:
            r = s.run("""
                MATCH (m:Memory)-[:TAGGED]->(t:Tag {name: $tag})
                RETURN m.id as id, m.content as content, m.tier as tier
                LIMIT 20
            """, tag=tag)
            return [dict(x) for x in r]
    
    def get_graph(self) -> Dict:
        if not self.driver:
            return {"nodes": [], "edges": []}
        with self.driver.session() as s:
            nodes = list(s.run("MATCH (m:Memory) RETURN m.id as id, m.content as label, m.tier as tier LIMIT 100"))
            edges = list(s.run("MATCH (a:Memory)-[r:RELATED]->(b:Memory) RETURN a.id as source, b.id as target LIMIT 200"))
            return {
                "nodes": [{"id": x["id"], "label": x["label"], "tier": x["tier"]} for x in nodes],
                "edges": [{"source": x["source"], "target": x["target"]} for x in edges]
            }
    
    def close(self):
        if self.driver:
            self.driver.close()

class RedisHandler:
    """Working memory cache"""
    def __init__(self):
        self.client = None
        if REDIS_AVAILABLE:
            try:
                self.client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, decode_responses=True)
                self.client.ping()
                print("[REDIS] ✅ Connected")
            except Exception as e:
                print(f"[REDIS] ❌ {e}")
    
    def set_node(self, node: MemoryNode, ttl: int = WORKING_TTL):
        if not self.client:
            return
        key = f"memory:working:{node.id}"
        self.client.setex(key, ttl, json.dumps(node.to_dict()))
    
    def get_node(self, node_id: str) -> Optional[MemoryNode]:
        if not self.client:
            return None
        key = f"memory:working:{node_id}"
        data = self.client.get(key)
        return MemoryNode.from_dict(json.loads(data)) if data else None
    
    def delete_node(self, node_id: str):
        if not self.client:
            return
        self.client.delete(f"memory:working:{node_id}")
    
    def get_all_working(self) -> List[MemoryNode]:
        if not self.client:
            return []
        nodes = []
        for key in self.client.scan_iter("memory:working:*"):
            data = self.client.get(key)
            if data:
                nodes.append(MemoryNode.from_dict(json.loads(data)))
        return nodes
    
    def working_count(self) -> int:
        if not self.client:
            return 0
        return sum(1 for _ in self.client.scan_iter("memory:working:*"))

class SQLiteHandler:
    """Long-term memory storage (MEDIUM + LONG + DEEP)"""
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()
        print("[SQLite] ✅ Connected")
    
    def _init_schema(self):
        cur = self.conn.cursor()
        
        # Memory table with vector support
        cur.execute("""
            CREATE TABLE IF NOT EXISTS memory_nodes (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                timestamp REAL NOT NULL,
                tier TEXT NOT NULL,
                importance REAL NOT NULL,
                tags TEXT,
                owner_id TEXT,
                access_count INTEGER DEFAULT 0,
                last_access REAL,
                embedding BLOB
            )
        """)
        
        # Indexes
        cur.execute("CREATE INDEX IF NOT EXISTS idx_memory_tier ON memory_nodes(tier)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_memory_importance ON memory_nodes(importance DESC)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_memory_content ON memory_nodes(content)")
        
        self.conn.commit()
    
    def add_node(self, node: MemoryNode, embedding: bytes = None):
        cur = self.conn.cursor()
        cur.execute("""
            INSERT OR REPLACE INTO memory_nodes 
            (id, content, timestamp, tier, importance, tags, owner_id, access_count, last_access, embedding)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (node.id, node.content, node.timestamp, node.tier, node.importance,
              json.dumps(node.tags), node.owner_id, node.access_count, node.last_access, embedding))
        self.conn.commit()
    
    def get_by_tier(self, tier: str) -> List[MemoryNode]:
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM memory_nodes WHERE tier = ?", (tier,))
        rows = cur.fetchall()
        return [self._row_to_node(r) for r in rows]
    
    def get_by_id(self, node_id: str) -> Optional[MemoryNode]:
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM memory_nodes WHERE id = ?", (node_id,))
        row = cur.fetchone()
        return self._row_to_node(row) if row else None
    
    def _row_to_node(self, row) -> MemoryNode:
        return MemoryNode(
            id=row['id'],
            content=row['content'],
            timestamp=row['timestamp'],
            tier=row['tier'],
            importance=row['importance'],
            tags=json.loads(row['tags']) if row['tags'] else [],
            owner_id=row['owner_id'],
            access_count=row['access_count'],
            last_access=row['last_access'] or 0
        )
    
    def search(self, query: str, limit: int = 20) -> List[Dict]:
        cur = self.conn.cursor()
        cur.execute("""
            SELECT id, content, tier, importance
            FROM memory_nodes
            WHERE content LIKE ?
            ORDER BY importance DESC
            LIMIT ?
        """, (f"%{query}%", limit))
        return [{"id": r[0], "content": r[1], "tier": r[2], "importance": r[3]} for r in cur.fetchall()]
    
    def count(self, tier: str = None) -> int:
        cur = self.conn.cursor()
        if tier:
            cur.execute("SELECT COUNT(*) FROM memory_nodes WHERE tier = ?", (tier,))
        else:
            cur.execute("SELECT COUNT(*) FROM memory_nodes")
        return cur.fetchone()[0]
    
    def close(self):
        self.conn.close()

class SilhouetteMemory:
    """
    Full Silhouette Memory System v3.0
    Based on Silhouette-OS Continuum Memory Architecture
    
    Tiers:
    - WORKING: Redis (fast cache, 50 nodes max, 30min TTL)
    - MEDIUM: SQLite (frequent access)
    - LONG: SQLite (persistent storage)
    - DEEP: SQLite (semantic with embeddings)
    """
    
    LOOP_PATTERNS = [
        "I'm committing this to memory",
        "Storing memory: Storing memory",
        "memory that is identical to itself"
    ]
    
    IDENTITY_TRANSFORMS = [
        (re.compile(r"^yo soy ([a-záéíóúñ]+)", re.I), r"El usuario se identifica como \1"),
        (re.compile(r"^mi nombre es ([a-záéíóúñ]+)", re.I), r"El usuario indica que su nombre es \1"),
        (re.compile(r"^me llamo ([a-záéíóúñ]+)", re.I), r"El usuario indica que se llama \1"),
        (re.compile(r"prefiero que me llam(es|en) ([a-záéíóúñ]+)", re.I), r"El usuario prefiere ser llamado \2"),
        (re.compile(r"puedes llamarme ([a-záéíóúñ]+)", re.I), r"El usuario prefiere ser llamado \1"),
        (re.compile(r"^soy ([a-záéíóúñ]+)", re.I), r"El usuario indica que es \1"),
    ]
    
    def __init__(self):
        self.neo4j = Neo4jHandler()
        self.redis = RedisHandler()
        self.sqlite = SQLiteHandler()
        print("[MEMORY] Full system initialized")
    
    def _check_loop(self, content: str) -> bool:
        c = content.lower()
        return any(p.lower() in c for p in self.LOOP_PATTERNS)
    
    def _transform_identity(self, content: str) -> str:
        for pattern, repl in self.IDENTITY_TRANSFORMS:
            content = pattern.sub(repl, content)
        return content
    
    def _generate_embedding(self, content: str) -> bytes:
        """Generate simple embedding for semantic search"""
        h = hashlib.sha256(content.encode()).digest()
        # Create pseudo-embedding
        emb = [float(b) / 255.0 for b in h] * 64
        return bytes([int(x * 255) for x in emb[:256]])
    
    def add(self, content: str, importance: float = 0.5, tags: List[str] = None, 
            owner_id: str = None, tier: str = "WORKING") -> Optional[str]:
        """Add memory node"""
        if self._check_loop(content):
            print(f"[MEMORY] Blocked (loop): {content[:30]}...")
            return None
        
        content = self._transform_identity(content)
        
        now = time.time()
        node = MemoryNode(
            id=str(uuid.uuid4())[:8],
            content=content,
            timestamp=now,
            tier=tier,
            importance=importance,
            tags=tags or [],
            owner_id=owner_id,
            access_count=1,
            last_access=now
        )
        
        # Generate embedding for DEEP tier
        embedding = self._generate_embedding(content) if tier in ["LONG", "DEEP"] else None
        
        # Save based on tier
        if tier == "WORKING":
            self.redis.set_node(node)
        
        # Always save to SQLite (MEDIUM/LONG/DEEP)
        self.sqlite.add_node(node, embedding)
        
        # Add to Neo4j graph
        self.neo4j.add_node(node)
        
        # Connect to related by tags
        for tag in node.tags:
            related = self.neo4j.find_by_tag(tag)
            for r in related[:3]:
                if r.get('id') != node.id:
                    self.neo4j.add_edge(node.id, r['id'], 'RELATED')
        
        # Check working limit
        if self.redis.working_count() > MAX_WORKING:
            self._demote_oldest()
        
        print(f"[MEMORY] ✅ Added to {tier}: {content[:40]}...")
        return node.id
    
    def _demote_oldest(self):
        working = self.redis.get_all_working()
        if working:
            oldest = min(working, key=lambda n: n.timestamp)
            self.redis.delete_node(oldest.id)
            oldest.tier = "LONG"
            embedding = self._generate_embedding(oldest.content)
            self.sqlite.add_node(oldest, embedding)
            print(f"[MEMORY] Demoted {oldest.id} to LONG")
    
    def access(self, node_id: str) -> Optional[MemoryNode]:
        """Access and update node"""
        node = self.redis.get_node(node_id)
        if node:
            node.access_count += 1
            node.last_access = time.time()
            self.redis.set_node(node)
            self.neo4j.add_node(node)
            return node
        
        # Check SQLite
        node = self.sqlite.get_by_id(node_id)
        if node:
            node.access_count += 1
            self.sqlite.add_node(node)
            return node
        return None
    
    def search(self, query: str) -> List[Dict]:
        """Search all tiers"""
        results = []
        
        # Search working (Redis)
        for n in self.redis.get_all_working():
            if query.lower() in n.content.lower():
                results.append({"id": n.id, "content": n.content, "tier": n.tier, "importance": n.importance})
        
        # Search SQLite
        results.extend(self.sqlite.search(query))
        
        # Search by tags in Neo4j
        for tag in query.lower().split():
            if len(tag) > 2:
                results.extend(self.neo4j.find_by_tag(tag))
        
        return results
    
    def get_working(self) -> List[Dict]:
        return [n.to_dict() for n in self.redis.get_all_working()]
    
    def get_medium(self) -> List[Dict]:
        return [n.to_dict() for n in self.sqlite.get_by_tier("MEDIUM")]
    
    def get_long(self) -> List[Dict]:
        return [n.to_dict() for n in self.sqlite.get_by_tier("LONG")]
    
    def get_deep(self) -> List[Dict]:
        return [n.to_dict() for n in self.sqlite.get_by_tier("DEEP")]
    
    def get_stats(self) -> Dict:
        graph = self.neo4j.get_graph()
        return {
            "working": self.redis.working_count(),
            "working_max": MAX_WORKING,
            "medium": self.sqlite.count("MEDIUM"),
            "long": self.sqlite.count("LONG"),
            "deep": self.sqlite.count("DEEP"),
            "graph_nodes": len(graph.get("nodes", [])),
            "graph_edges": len(graph.get("edges", []))
        }
    
    def close(self):
        self.neo4j.close()
        self.sqlite.close()

if __name__ == "__main__":
    import sys
    m = SilhouetteMemory()
    
    if len(sys.argv) < 2:
        print("""
╔═══════════════════════════════════════════╗
║   SILHOUETTE MEMORY SYSTEM v3.0        ║
║   Full Implementation                   ║
║   (Neo4j + Redis + SQLite)             ║
╚═══════════════════════════════════════════╝

Commands:
  add <content> [--tier WORKING|MEDIUM|LONG|DEEP] [--importance 0.5] [--tags tag1,tag2]
  search <query>
  working
  medium
  long
  deep
  stats
  graph
        """)
    else:
        cmd = sys.argv[1]
        if cmd == "add":
            content = " ".join(sys.argv[2:])
            tier = "WORKING"
            importance = 0.5
            tags = []
            
            if "--tier" in sys.argv:
                tier = sys.argv[sys.argv.index("--tier")+1]
            if "--importance" in sys.argv:
                importance = float(sys.argv[sys.argv.index("--importance")+1])
            if "--tags" in sys.argv:
                tags = sys.argv[sys.argv.index("--tags")+1].split(",")
            
            m.add(content, importance, tags, tier=tier)
        
        elif cmd == "search":
            for r in m.search(" ".join(sys.argv[2:])):
                print(f"[{r['tier']}] {r['content'][:60]}...")
        
        elif cmd == "working":
            for n in m.get_working():
                print(f"{n['id']}: {n['content'][:50]}")
        
        elif cmd == "medium":
            for n in m.get_medium():
                print(f"{n['id']}: {n['content'][:50]}")
        
        elif cmd == "long":
            for n in m.get_long():
                print(f"{n['id']}: {n['content'][:50]}")
        
        elif cmd == "deep":
            for n in m.get_deep():
                print(f"{n['id']}: {n['content'][:50]}")
        
        elif cmd == "stats":
            s = m.get_stats()
            print(f"📊 Working: {s['working']}/{s['working_max']}")
            print(f"📊 Medium: {s['medium']}")
            print(f"📊 Long: {s['long']}")
            print(f"📊 Deep: {s['deep']}")
            print(f"📊 Graph: {s['graph_nodes']} nodes, {s['graph_edges']} edges")
        
        elif cmd == "graph":
            g = m.neo4j.get_graph()
            print(f"Graph: {len(g['nodes'])} nodes, {len(g['edges'])} edges")
    
    m.close()
