import sqlite3
import os
import json
import time

BRAIN_DATA = os.getenv("BRAIN_DATA_DIR", "/root/silhouette-brain/data")
DB_CORE = os.path.join(BRAIN_DATA, "memory_core.db")
DB_MEM = os.path.join(BRAIN_DATA, "memory.db")

if not os.path.exists(DB_MEM):
    print("No memory.db found. Nothing to migrate.")
    exit(0)

conn_mem = sqlite3.connect(DB_MEM)
conn_core = sqlite3.connect(DB_CORE)

# Get nodes from memory.db
nodes = conn_mem.execute("SELECT id, content, timestamp, tags, tier FROM memory_nodes").fetchall()
print(f"Found {len(nodes)} nodes in memory.db")

count = 0
for id_, content, ts, tags_json, tier in nodes:
    # Check if already exists in conversations
    exists = conn_core.execute("SELECT id FROM conversations WHERE message = ? AND timestamp = ?", (content, ts)).fetchone()
    if not exists:
        conn_core.execute(
            "INSERT INTO conversations (id, timestamp, speaker, message, tags) VALUES (?, ?, ?, ?, ?)",
            (id_, ts, "user", content, tags_json)
        )
        count += 1

conn_core.commit()
print(f"Migrated {count} nodes to memory_core.db conversations table.")

conn_mem.close()
conn_core.close()
