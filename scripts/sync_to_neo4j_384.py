import sqlite3
import numpy as np
from neo4j import GraphDatabase
import os

DB_PATH = os.path.join(os.getenv('BRAIN_DATA_DIR', '/root/silhouette-brain/data'), 'memory_core.db')
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:17687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "changeme")

conn = sqlite3.connect(DB_PATH)
driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

# Get 384-dim embeddings
rows = conn.execute("SELECT id, timestamp, speaker, message, context, tags, embedding FROM conversations WHERE length(embedding) == 1536").fetchall()
print(f"Found {len(rows)} messages with 384-dim embeddings.")

def push_batch(batch):
    with driver.session() as session:
        session.run("""
        UNWIND $data as row
        MERGE (c:Conversation {id: row.id})
        SET c.timestamp = row.ts, c.speaker = row.speaker, c.message = row.msg,
            c.context = row.ctx, c.tags = row.tags, c.embedding = row.emb
        """, data=batch)

batch = []
count = 0
for r in rows:
    emb_array = np.frombuffer(r[6], dtype=np.float32).tolist()
    batch.append({
        "id": r[0], "ts": r[1], "speaker": r[2], "msg": r[3],
        "ctx": r[4], "tags": r[5], "emb": emb_array
    })
    if len(batch) >= 100:
        push_batch(batch)
        count += len(batch)
        if count % 1000 == 0:
            print(f"Pushed {count} nodes to Neo4j...")
        batch = []

if batch:
    push_batch(batch)
    count += len(batch)

print(f"Sync complete. Pushed {count} nodes to Neo4j.")
driver.close()
conn.close()
