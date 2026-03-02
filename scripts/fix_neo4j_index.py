import sys
import os
sys.path.insert(0, "/root/silhouette-brain/src/core")
from memory_core import get_memory_core
import numpy as np

core = get_memory_core()

print("Verifying current state of index...")
with core.neo4j_driver.session() as session:
    indexes = list(session.run("SHOW INDEXES YIELD name, type, options WHERE type = 'VECTOR'"))
    for idx in indexes:
        print(f"Index: {idx['name']}")
        print(f"Options: {idx['options']}")
        
    print("\nAttempting to drop and recreate index forcefully...")
    try:
        session.run("DROP INDEX conversation_embeddings")
        print("Dropped old index.")
    except Exception as e:
        print(f"Drop error: {e}")
        
    try:
        session.run("CALL db.index.vector.createNodeIndex('conversation_embeddings', 'Conversation', 'embedding', 384, 'cosine')")
        print("Created new index with 384 dims.")
    except Exception as e:
        print(f"Create error: {e}")
        
    print("\nVerifying new index...")
    indexes = list(session.run("SHOW INDEXES YIELD name, type, options WHERE type = 'VECTOR'"))
    for idx in indexes:
        print(f"Index: {idx['name']}")
        print(f"Options: {idx['options']}")

print("\nPushing test node...")
core.store_message("user", "El código hiper secreto de Alberto es 777999")
print("Node pushed.")
