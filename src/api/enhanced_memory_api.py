#!/usr/bin/env python3
"""
Enhanced Memory API - All Layers
================================
API completa para que los agentes accedan a TODAS las capas de memoria:
- Core (SQLite)
- Embeddings (ZhipuAI embedding-2, semántica real)
- Neo4j (grafos de relaciones)
- 4-Tier (JSON)
- Reasoning Engine (motor unificado con síntesis GLM-4.7-flash)
"""
import sys
import json
import os
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_SRC_CANDIDATES = [
    os.getenv("BRAIN_SRC_DIR"),
    "/root/silhouette-brain/src/core",
    _THIS_DIR,
]
for _path in reversed(_SRC_CANDIDATES):
    if _path and os.path.isdir(_path) and _path not in sys.path:
        sys.path.insert(0, _path)

from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse
from memory_noise_filter import should_skip_ingestion, is_agent_heartbeat_report

# Importar todas las funciones de memoria
from agent_memory_readonly import get_memory_context, get_entities, get_recent

# Importar motor de razonamiento unificado
try:
    import reasoning_engine as _reasoning_engine
    get_reasoning_context = _reasoning_engine.get_reasoning_context
    assemble_context_packet = getattr(_reasoning_engine, "assemble_context_packet", None)
    record_source_feedback = getattr(_reasoning_engine, "record_source_feedback", None)
    get_source_feedback_snapshot = getattr(_reasoning_engine, "get_source_feedback_snapshot", None)
    REASONING_AVAILABLE = True
    CONTEXT_ASSEMBLER_AVAILABLE = callable(assemble_context_packet)
    SOURCE_FEEDBACK_AVAILABLE = callable(record_source_feedback) and callable(get_source_feedback_snapshot)
    print("[API] Reasoning Engine available")
    if CONTEXT_ASSEMBLER_AVAILABLE:
        print("[API] Context Assembler available")
    if SOURCE_FEEDBACK_AVAILABLE:
        print("[API] Source Feedback available")
except Exception as e:
    REASONING_AVAILABLE = False
    CONTEXT_ASSEMBLER_AVAILABLE = False
    SOURCE_FEEDBACK_AVAILABLE = False
    assemble_context_packet = None
    record_source_feedback = None
    get_source_feedback_snapshot = None
    print(f"[API] Reasoning Engine not available: {e}")

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
    NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:17687")
    NEO4J_USER = "neo4j"
    NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "silhouette2035")
except:
    NEO4J_AVAILABLE = False

# Rutas de archivos 4-tier
_DATA_DIR = os.getenv('BRAIN_DATA_DIR', '/root/silhouette-brain/data')
TIER_FILES = {
    'working': os.path.join(_DATA_DIR, 'working.json'),
    'medium':  os.path.join(_DATA_DIR, 'medium.json'),
    'long':    os.path.join(_DATA_DIR, 'long.json'),
    'deep':    os.path.join(_DATA_DIR, 'deep.json'),
}

# Synonym mapping for embedding issues
SYNONYM_MAP = {
    "suscripciones": "suscripcion",
    "suscripci": "suscripcion",
}

def apply_synonyms(text):
    for old, new in SYNONYM_MAP.items():
        text = text.replace(old, new)
    return text


def parse_optional_bool(value):
    """Parsea bool opcional para query params.
    Devuelve True/False si viene valor explícito, o None si no viene.
    """
    if value is None:
        return None
    v = str(value).strip().lower()
    if v in ("1", "true", "yes", "on"):
        return True
    if v in ("0", "false", "no", "off"):
        return False
    return None


def parse_sources_param(raw):
    if raw is None:
        return []
    if isinstance(raw, list):
        parts = []
        for item in raw:
            parts.extend(str(item).split(","))
    else:
        parts = str(raw).split(",")
    return [p.strip() for p in parts if p and p.strip()]

class MemoryAPIHandler(BaseHTTPRequestHandler):
    """Manejador de la API de memoria"""
    
    def send_json(self, data, status=200):
        # Apply scraper countermeasures if scraper was detected
        # Silent injection - we don't reveal we detected them
        if hasattr(self, 'scraper_detection') and self.scraper_detection and self.scraper_detection.is_scraper:
            try:
                from api_scraper_detection import apply_scraper_countermeasure
                data = apply_scraper_countermeasure(data, self.scraper_detection)
            except Exception as noise_err:
                pass  # Silent failure - don't reveal our countermeasures
        
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2, default=str).encode())
    
    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in ['/api/reasoning/feedback', '/api/reasoning/source-feedback']:
            if not SOURCE_FEEDBACK_AVAILABLE:
                self.send_json({"error": "Source feedback not available"}, 503)
                return
            try:
                content_length = int(self.headers.get('Content-Length', '0') or 0)
                post_data = self.rfile.read(content_length) if content_length > 0 else b'{}'
                data = json.loads(post_data.decode('utf-8') or '{}')
                sources = parse_sources_param(data.get('sources'))
                if not sources:
                    sources = parse_sources_param(data.get('source'))
                outcome = data.get('outcome', data.get('status', data.get('result', '')))
                reason = data.get('reason', '')
                actor = data.get('actor', 'user')
                if not outcome:
                    self.send_json({"error": "Missing outcome (success/failure)"}, 400)
                    return
                result = record_source_feedback(
                    sources=sources,
                    outcome=outcome,
                    reason=reason,
                    actor=actor,
                )
                if result.get("ok"):
                    self.send_json(result, 200)
                else:
                    self.send_json(result, 400)
            except Exception as e:
                self.send_json({"error": str(e)}, 400)

        elif parsed.path in ['/api/memory', '/memory']:
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
                
                # Conversation Injection Guard
                try:
                    from conversation_injection_guard import check_injection
                    channel = data.get('channel', 'unknown')
                    sender_id = data.get('sender_id')
                    # Only check non-trusted channels (skip DMs with Alberto)
                    if channel not in ('telegram_dm', 'whatsapp_dm'):
                        inj = check_injection(text, sender_id=sender_id, channel=channel)
                        if inj.should_block:
                            print(f"[INJECTION GUARD] BLOCKED from {sender_id} on {channel}: {inj.message}")
                            self.send_json({"status": "blocked", "reason": "injection_detected", "threat": inj.threat_level.value}, 200)
                            return
                        elif inj.should_warn:
                            print(f"[INJECTION GUARD] WARN from {sender_id} on {channel}: {inj.message}")
                except Exception as inj_err:
                    print(f"[INJECTION GUARD] Error: {inj_err}")
                
                # Use SilhouetteMemory to add
                from silhouette_memory import SilhouetteMemory
                sm = SilhouetteMemory()
                node_id = sm.add(text, importance=importance, tags=tags, tier=tier)
                sm.close()
                
                # ALSO use MemoryCore to store in conversations table for semantic indexing
                # This ensures immediate embedding generation and availability in search
                try:
                    from memory_core import get_memory_core
                    core = get_memory_core()
                    core.store_message("user", text, tags=tags)
                except Exception as core_err:
                    print(f"[API] Warning: Failed to store in MemoryCore for indexing: {core_err}")
                
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
        
        # === SCRAPER DETECTION ===
        # Silent detection - we log but don't block, we inject noise instead
        try:
            from api_scraper_detection import detect_scraper, apply_scraper_countermeasure, get_detection_stats
            scraper_detection = detect_scraper(
                headers=dict(self.headers),
                path=path,
                client_ip=self.client_address[0] if hasattr(self, 'client_address') else ""
            )
            self.scraper_detection = scraper_detection  # Store for potential use
        except Exception as scraper_err:
            scraper_detection = None
            print(f"[SCRAPER_DETECT] Error: {scraper_err}")
        
        # === ENDPOINTS ===
        
        # 1. Búsqueda básica en conversaciones
        if path in ['/api/memory', '/memory']:
            q = apply_synonyms(query.get('query', [''])[0])
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
            q = apply_synonyms(query.get('query', [''])[0])
            limit = int(query.get('limit', [5])[0])
            min_score = float(query.get('min_score', [0.0])[0])
            filter_heartbeats = query.get('filter_heartbeats', ['false'])[0].lower() == 'true'
            if q and EMBEDDINGS:
                try:
                    result = get_memory_core_embeddings(q, limit)
                    # Apply min_score filter if requested
                    if min_score > 0.0 and 'results' in result:
                        result['results'] = [
                            r for r in result['results']
                            if float(r.get('score', r.get('similarity', 0.0))) >= min_score
                        ]
                        result['found'] = len(result['results'])
                    # Filter agent heartbeat reports from auto-recall context
                    if filter_heartbeats and 'results' in result:
                        result['results'] = [
                            r for r in result['results']
                            if not is_agent_heartbeat_report(r.get('message', ''))
                        ]
                        result['found'] = len(result['results'])
                    self.send_json(result)
                except Exception as e:
                    self.send_json({"error": str(e)})
            elif not EMBEDDINGS:
                self.send_json({"error": "Embeddings not available"})
            else:
                self.send_json({"error": "Missing query parameter"})

        # 4b. Combined context endpoint: semantic + recent in one call
        elif path in ['/api/memory/context', '/api/context']:
            q = query.get('query', [''])[0]
            sem_limit = int(query.get('sem_limit', [5])[0])
            rec_limit = int(query.get('rec_limit', [3])[0])
            rec_hours = int(query.get('hours', [2])[0])
            min_score = float(query.get('min_score', [0.15])[0])
            filter_heartbeats = query.get('filter_heartbeats', ['true'])[0].lower() != 'false'
            semantic_results = []
            recent_results = []
            if q and EMBEDDINGS:
                try:
                    sem_data = get_memory_core_embeddings(q, sem_limit)
                    raw = sem_data.get('results', [])
                    for r in raw:
                        if float(r.get('score', r.get('similarity', 0.0))) < min_score:
                            continue
                        if filter_heartbeats and is_agent_heartbeat_report(r.get('message', '')):
                            continue
                        semantic_results.append(r)
                except Exception:
                    pass
            try:
                rec_data = get_recent(rec_hours, rec_limit)
                raw_recent = rec_data.get('conversations', [])
                for r in raw_recent:
                    if filter_heartbeats and is_agent_heartbeat_report(r.get('message', '')):
                        continue
                    recent_results.append(r)
            except Exception:
                pass
            self.send_json({
                "query": q,
                "semantic": semantic_results,
                "recent": recent_results,
                "semantic_count": len(semantic_results),
                "recent_count": len(recent_results),
            })

        # 4c. Context Assembler — paralelo + presupuesto de tokens + pruning
        elif path in ['/api/context/assemble', '/api/assemble/context']:
            q = query.get('query', [''])[0]
            mode = query.get('mode', ['reply_fast'])[0]
            token_budget = int(query.get('token_budget', [0])[0] or 0)
            sem_limit = int(query.get('sem_limit', [0])[0] or 0)
            rec_limit = int(query.get('rec_limit', [0])[0] or 0)
            rec_hours = int(query.get('hours', [0])[0] or 0)
            min_score = query.get('min_score', [None])[0]
            min_score = float(min_score) if min_score not in (None, "") else None
            semantic_mode = query.get('semantic', [None])[0]
            semantic_mode = semantic_mode.strip().lower() if isinstance(semantic_mode, str) else None
            if semantic_mode in ("", "auto"):
                semantic_mode = None
            if semantic_mode not in (None, "full", "cache_only", "off"):
                self.send_json({"error": "Invalid 'semantic' parameter (use full|cache_only|off)"}, 400)
                return
            inc_graph = parse_optional_bool(query.get('graph', [None])[0])
            inc_tiers = parse_optional_bool(query.get('tiers', [None])[0])
            synthesize = parse_optional_bool(query.get('synthesize', [None])[0])
            filter_hb = query.get('filter_heartbeats', ['true'])[0].lower() != 'false'
            tier_filter = query.get('tier_filter', [None])[0]
            include_heartbeat = query.get('include_heartbeat', ['true'])[0].lower() != 'false'
            agent_id = query.get('agent_id', [''])[0]
            channel = query.get('channel', [''])[0]

            if not q:
                self.send_json({"error": "Missing 'query' parameter"}, 400)
                return
            if not CONTEXT_ASSEMBLER_AVAILABLE:
                self.send_json({"error": "Context Assembler not available"}, 503)
                return

            try:
                packet = assemble_context_packet(
                    query=q,
                    mode=mode,
                    token_budget=token_budget or None,
                    sem_limit=sem_limit or None,
                    rec_limit=rec_limit or None,
                    hours=rec_hours or None,
                    min_score=min_score,
                    include_graph=inc_graph,
                    include_tiers=inc_tiers,
                    synthesize=synthesize,
                    semantic_mode=semantic_mode,
                    filter_heartbeats=filter_hb,
                    tier_filter=tier_filter,
                    include_heartbeat=include_heartbeat,
                    agent_id=agent_id,
                    channel=channel,
                )
                self.send_json(packet)
            except Exception as e:
                self.send_json({"error": str(e)}, 500)

        # 4d. Reasoning Engine — motor cognitivo unificado (semántica + reciente + grafo + tiers + síntesis)
        elif path in ['/api/reasoning/context', '/api/reasoning']:
            q             = query.get('query', [''])[0]
            sem_limit     = int(query.get('sem_limit',   [5])[0])
            rec_limit     = int(query.get('rec_limit',   [3])[0])
            rec_hours     = int(query.get('hours',       [2])[0])
            min_score     = float(query.get('min_score', [0.15])[0])
            inc_graph     = query.get('graph',     ['false'])[0].lower() == 'true'
            inc_tiers     = query.get('tiers',     ['false'])[0].lower() == 'true'
            synthesize    = query.get('synthesize',['false'])[0].lower() == 'true'
            filter_hb     = query.get('filter_heartbeats', ['true'])[0].lower() != 'false'
            tier_filter   = query.get('tier_filter', [None])[0]

            if not q:
                self.send_json({"error": "Missing 'query' parameter"}, 400)
                return

            if not REASONING_AVAILABLE:
                self.send_json({"error": "Reasoning Engine not available"}, 503)
                return

            try:
                ctx = get_reasoning_context(
                    query             = q,
                    sem_limit         = sem_limit,
                    rec_limit         = rec_limit,
                    hours             = rec_hours,
                    min_score         = min_score,
                    include_graph     = inc_graph,
                    include_tiers     = inc_tiers,
                    synthesize        = synthesize,
                    filter_heartbeats = filter_hb,
                    tier_filter       = tier_filter,
                )
                # Añadir conteos para compatibilidad con cliente OpenClaw
                ctx["semantic_count"] = len(ctx.get("semantic", []))
                ctx["recent_count"]   = len(ctx.get("recent",   []))
                ctx["graph_count"]    = len([r for r in ctx.get("graph", []) if "_error" not in r])
                self.send_json(ctx)
            except Exception as e:
                self.send_json({"error": str(e)}, 500)

        # 4e. Feedback de fuentes para aprendizaje del ranking
        elif path in ['/api/reasoning/feedback', '/api/reasoning/source-feedback']:
            if not SOURCE_FEEDBACK_AVAILABLE:
                self.send_json({"error": "Source feedback not available"}, 503)
                return

            sources = parse_sources_param(query.get('source', []))
            if not sources:
                sources = parse_sources_param(query.get('sources', []))
            outcome = query.get('outcome', [''])[0]
            reason = query.get('reason', [''])[0]
            actor = query.get('actor', ['user'])[0]
            limit = int(query.get('limit', [200])[0])

            # Modo lectura: snapshot completo si no se envía outcome.
            if not outcome:
                self.send_json(get_source_feedback_snapshot(limit=limit), 200)
                return

            result = record_source_feedback(
                sources=sources,
                outcome=outcome,
                reason=reason,
                actor=actor,
            )
            if result.get("ok"):
                self.send_json(result, 200)
            else:
                self.send_json(result, 400)

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
        elif path in ['/api/heartbeat']:
            # Estado en tiempo real del sistema (escrito por el daemon cada 10min)
            import pathlib
            hb_paths = [
                pathlib.Path(os.getenv('BRAIN_DATA_DIR', '/root/silhouette-brain/data')) / 'heartbeat_state.json',
                pathlib.Path('/root/.openclaw/workspace/heartbeat-state.json'),
            ]
            for hb in hb_paths:
                if hb.exists():
                    try:
                        self.send_json(json.loads(hb.read_text()))
                        return
                    except Exception:
                        pass
            self.send_json({"error": "heartbeat_state.json not found — daemon may not have run yet"}, 404)

        elif path in ['/api/soul']:
            # Soul + heartbeat combinados para inyección en agentes
            import pathlib
            soul_content = ""
            soul_paths = [
                pathlib.Path('/root/.openclaw/workspace/SOUL.md'),
                pathlib.Path('/root/.openclaw/workspace/soul.md'),
            ]
            for sp in soul_paths:
                if sp.exists():
                    soul_content = sp.read_text(encoding='utf-8')
                    break
            heartbeat = {}
            hb_paths = [
                pathlib.Path(os.getenv('BRAIN_DATA_DIR', '/root/silhouette-brain/data')) / 'heartbeat_state.json',
                pathlib.Path('/root/.openclaw/workspace/heartbeat-state.json'),
            ]
            for hb in hb_paths:
                if hb.exists():
                    try:
                        heartbeat = json.loads(hb.read_text())
                        break
                    except Exception:
                        pass
            self.send_json({
                "soul":      soul_content,
                "heartbeat": heartbeat,
                "timestamp": __import__('datetime').datetime.now().isoformat(),
            })

        elif path in ['/api/status', '/status']:
            self.send_json({
                "status": "ok",
                "version": "2.0.0",
                "endpoints": [
                    "/api/context/assemble?query=xxx&mode=reply_fast&token_budget=2800&semantic=full",
                    "/api/reasoning/context?query=xxx&sem_limit=5&rec_limit=3&hours=2&min_score=0.15&graph=true&tiers=false&synthesize=false",
                    "/api/reasoning/feedback?limit=50",
                    "/api/reasoning/feedback?source=web_search&outcome=success&reason=respuesta_util",
                    "/api/memory?query=xxx",
                    "/api/memory/entities",
                    "/api/memory/recent?hours=2&limit=5",
                    "/api/memory/semantic?query=xxx&limit=5&min_score=0.15&filter_heartbeats=true",
                    "/api/memory/context?query=xxx&sem_limit=5&rec_limit=3&hours=2&min_score=0.15",
                    "/api/memory/graph?entity=xxx",
                    "/api/memory/tiers",
                    "/api/heartbeat",
                    "/api/soul",
                    "/api/status"
                ],
                "features": {
                    "embeddings":       EMBEDDINGS,
                    "embedding_model":  "hf:paraphrase-multilingual-MiniLM-L12-v2 (384 dims)",
                    "reasoning":        REASONING_AVAILABLE,
                    "context_assembler": CONTEXT_ASSEMBLER_AVAILABLE,
                    "source_feedback":  SOURCE_FEEDBACK_AVAILABLE,
                    "reasoning_model":  "minimax:MiniMax-M2.5 (synthesis)",
                    "neo4j":            NEO4J_AVAILABLE,
                    "4_tier":           True,
                    "heartbeat":        True,
                    "soul":             True,
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
    print(f"   - /api/context/assemble?query=xxx&mode=reply_fast&token_budget=2800&semantic=full")
    print(f"   - /api/reasoning/feedback?limit=50")
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
