#!/usr/bin/env python3
"""
Enhanced Memory API - All Layers
================================
API completa para que los agentes accedan a TODAS las capas de memoria:
- Core (SQLite)
- Embeddings (búsqueda semántica)
- Neo4j (grafos)
- 4-Tier (JSON)
"""
import sys
import json
import os
sys.path.insert(0, os.getenv('BRAIN_SRC_DIR', os.path.dirname(os.path.abspath(__file__))))

from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse
from memory_noise_filter import should_skip_ingestion

# Importar todas las funciones de memoria
from agent_memory_readonly import get_memory_context, get_entities, get_recent

# Intentar importar embeddings
try:
    from embeddings_wrapper import get_memory_core_embeddings
    EMBEDDINGS = True
    print("[API] Embeddings available")
except Exception as e:
    EMBEDDINGS = False
    print(f"[API] Embeddings not available: {e}")

# Intentar importar Neo4j
try:
    from neo4j import GraphDatabase
    NEO4J_AVAILABLE = True
    NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    NEO4J_USER = "neo4j"
    NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "neo4j_password")
except:
    NEO4J_AVAILABLE = False

# Rutas de archivos 4-tier
TIER_FILES = {
    'working': os.getenv('BRAIN_DATA_DIR', './data/working.json',
    'medium': os.getenv('BRAIN_DATA_DIR', './data/medium.json',
    'long': os.getenv('BRAIN_DATA_DIR', './data/long.json',
    'deep': os.getenv('BRAIN_DATA_DIR', './data/deep.json')
}

class MemoryAPIHandler(BaseHTTPRequestHandler):
    """Manejador de la API de memoria"""
    
    def send_json(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2, default=str).encode())
    
    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in ['/api/memory', '/memory']:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            try:
                data = json.loads(post_data.decode('utf-8'))
                text = data.get('text', '')
                importance = data.get('importance', 0.5)
                tags = data.get('tags', [])
                tier = data.get('tier', 'WORKING')
                if should_skip_ingestion(text):
                    self.send_json({"status": "blocked", "reason": "runtime_operational_noise"}, 200)
                    return
                
                # Use SilhouetteMemory to add
                from silhouette_memory import SilhouetteMemory
                sm = SilhouetteMemory()
                node_id = sm.add(text, importance=importance, tags=tags, tier=tier)
                sm.close()
                
                if node_id:
                    self.send_json({"status": "ok", "id": node_id}, 201)
                else:
                    self.send_json({"status": "blocked", "reason": "loop detected"}, 200)
            except Exception as e:
                self.send_json({"error": str(e)}, 400)
        else:
            self.send_json({"error": "Endpoint not found"}, 404)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)
        
        # === ENDPOINTS ===
        
        # 1. Búsqueda básica en conversaciones
        if path in ['/api/memory', '/memory']:
            q = query.get('query', [''])[0]
            limit = int(query.get('limit', [10])[0])
            if q:
                result = get_memory_context(q, limit)
                self.send_json(result)
            else:
                self.send_json({"error": "Missing query parameter"})
        
        # 2. Entidades
        elif path in ['/api/memory/entities', '/entities', '/api/entities']:
            etype = query.get('type', [None])[0]
            limit = int(query.get('limit', [20])[0])
            result = get_entities(etype, limit)
            self.send_json(result)
        
        # 3. Conversaciones recientes
        elif path in ['/api/memory/recent', '/recent']:
            hours = int(query.get('hours', [24])[0])
            limit = int(query.get('limit', [20])[0])
            result = get_recent(hours, limit)
            self.send_json(result)
        
        # 4. Búsqueda con EMBEDDINGS (semántica)
        elif path in ['/api/memory/semantic', '/semantic', '/api/semantic']:
            q = query.get('query', [''])[0]
            limit = int(query.get('limit', [5])[0])
            if q and EMBEDDINGS:
                try:
                    result = get_memory_core_embeddings(q, limit)
                    self.send_json(result)
                except Exception as e:
                    self.send_json({"error": str(e)})
            elif not EMBEDDINGS:
                self.send_json({"error": "Embeddings not available"})
            else:
                self.send_json({"error": "Missing query parameter"})
        
        # 5. Neo4j - Grafo de relaciones
        elif path in ['/api/memory/graph', '/graph', '/api/graph']:
            entity = query.get('entity', [None])[0]
            if NEO4J_AVAILABLE:
                try:
                    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
                    with driver.session() as session:
                        if entity:
                            result = session.run("""
                                MATCH (n)-[r]->(m) 
                                WHERE n.name CONTAINS $entity OR m.name CONTAINS $entity
                                RETURN n.name, type(r), m.name LIMIT 20
                            """, entity=entity)
                        else:
                            result = session.run("MATCH (n) RETURN n.name, labels(n) LIMIT 20")
                        data = [{"n": r[0], "rel": r[1], "m": r[2]} for r in result]
                    driver.close()
                    self.send_json({"graph": data, "available": True})
                except Exception as e:
                    self.send_json({"graph": [], "available": False, "error": str(e)})
            else:
                self.send_json({"graph": [], "available": False, "error": "Neo4j not available"})
        
        # 6. 4-Tier Memory
        elif path in ['/api/memory/tiers', '/tiers', '/api/tiers']:
            tier_name = query.get('tier', [None])[0]
            result = {}
            
            if tier_name and tier_name in TIER_FILES:
                # Solicitar tier específico
                if os.path.exists(TIER_FILES[tier_name]):
                    with open(TIER_FILES[tier_name]) as f:
                        result[tier_name] = json.load(f)
                else:
                    result[tier_name] = []
            else:
                # Todos los tiers
                for name, path in TIER_FILES.items():
                    if os.path.exists(path):
                        with open(path) as f:
                            result[name] = json.load(f)
                    else:
                        result[name] = []
            
            self.send_json({"tiers": result, "available_tiers": list(TIER_FILES.keys())})
        
        # 7. Estado de la API
        elif path in ['/api/status', '/status']:
            self.send_json({
                "status": "ok",
                "endpoints": [
                    "/api/memory?query=xxx",
                    "/api/memory/entities",
                    "/api/memory/recent",
                    "/api/memory/semantic?query=xxx",
                    "/api/memory/graph?entity=xxx",
                    "/api/memory/tiers",
                    "/api/status"
                ],
                "features": {
                    "embeddings": EMBEDDINGS,
                    "neo4j": NEO4J_AVAILABLE,
                    "4_tier": True
                }
            })
        
        # 404
        else:
            self.send_json({"error": "Endpoint not found. Use /api/status to see available endpoints"}, 404)
    
    def log_message(self, format, *args):
        print(f"[API] {args[0]}")

class ReuseAddressServer(HTTPServer):
    allow_reuse_address = True

def run_api(port=9876):
    server = ReuseAddressServer(('0.0.0.0', port), MemoryAPIHandler)
    print(f"🚀 Enhanced Memory API running on port {port}")
    print(f"   Endpoints:")
    print(f"   - /api/memory?query=xxx")
    print(f"   - /api/memory/entities")
    print(f"   - /api/memory/recent")
    print(f"   - /api/memory/semantic?query=xxx")
    print(f"   - /api/memory/graph?entity=xxx")
    print(f"   - /api/memory/tiers")
    print(f"   - /api/status")
    server.serve_forever()

if __name__ == "__main__":
    run_api()
