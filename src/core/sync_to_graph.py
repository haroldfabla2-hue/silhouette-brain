import os
#!/usr/bin/env python3
"""
Sync priority memory to Neo4j graph - FILTERED VERSION
Only syncs truly important items, filters noise
"""
import json
import re
import sys
sys.path.insert(0, os.getenv('BRAIN_SRC_DIR', os.path.dirname(os.path.abspath(__file__))))

from neo4j import GraphDatabase

NOISE_PATTERNS = [
    r'^\[SILHOUETTE\]',
    r'^===',
    r'\{.*\}',
    r'^/root/',
    r'Command exited',
    r'EMBEDDINGS',
]

def is_noise(text):
    for p in NOISE_PATTERNS:
        if re.search(p, text):
            return True
    return False

def sync_to_neo4j():
    with open(os.getenv('BRAIN_DATA_DIR', './data'/priority_memory.json') as f:
        data = json.load(f)
    
    never_forget = [item for item in data.get('never_forget', []) 
                    if not is_noise(item.get('content', '')) and item.get('importance', 0) > 0.4]
    
    if not never_forget:
        print("No clean items to sync")
        return
    
    driver = GraphDatabase.driver('bolt://localhost:17687', auth=('neo4j', 'silhouette2035'))
    
    with driver.session() as s:
        # Clear old Semantic nodes
        s.run("MATCH (n:Semantic) DETACH DELETE n")
        
        # Add filtered NEVER FORGET
        for item in never_forget:
            content = item.get('content', '')[:100]
            importance = item.get('importance', 0.5)
            
            # Extract tags
            entities = item.get('entities', [])
            tags = list(set([label for label, name in entities])) if entities else []
            
            # Determine owner_id from item (default to "default")
            item_owner = item.get('owner_id') or item.get('client_id') or 'default'
            
            # Ensure Client node exists + MERGE Semantic with BELONGS_TO
            s.run("""
                MERGE (c:Client {id: $owner_id})
                SET c.lastSeen = timestamp()
                MERGE (n:Semantic {name: $name})
                SET n.content = $content,
                    n.importance = $importance,
                    n.tags = $tags,
                    n.lastSeen = timestamp()
                MERGE (n)-[:BELONGS_TO]->(c)
            """, name=content[:30], content=content, importance=importance, 
               tags=json.dumps(tags), owner_id=item_owner)
        
        print(f"Synced {len(never_forget)} CLEAN items to Neo4j")
    
    driver.close()

if __name__ == "__main__":
    sync_to_neo4j()


def migrate_existing_nodes_to_default():
    """One-time migration: attach all existing Semantic nodes to Client 'default'.
    
    Use this after deploying the multi-tenant changes to bind orphan nodes.
    """
    driver = GraphDatabase.driver('bolt://localhost:17687', auth=('neo4j', 'silhouette2035'))
    
    with driver.session() as s:
        # Ensure default client exists
        s.run("MERGE (c:Client {id: 'default'}) SET c.name = 'System (default)', c.is_system = true")
        s.run("MERGE (c:Client {id: 'alfonso'}) SET c.name = 'Alfonso Grados'")
        s.run("MERGE (c:Client {id: 'isabella'}) SET c.name = 'Isabella Escudero'")
        
        # Attach orphan Semantic nodes to default
        result = s.run("""
            MATCH (n:Semantic)
            WHERE NOT (n)-[:BELONGS_TO]->(:Client)
            MATCH (c:Client {id: 'default'})
            MERGE (n)-[:BELONGS_TO]->(c)
            RETURN count(n) as migrated
        """)
        record = result.single()
        migrated = record["migrated"] if record else 0
        print(f"Migrated {migrated} orphan Semantic nodes to Client 'default'")
    
    driver.close()


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "migrate":
        migrate_existing_nodes_to_default()
    else:
        sync_to_neo4j()