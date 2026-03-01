#!/usr/bin/env python3
"""
Silhouette Reasoning Engine v1.0
=================================
Motor cognitivo unificado. Combina TODAS las capas de memoria y
opcionalmente sintetiza el contexto con GLM-4.7-flash.

Capas:
  A. Semántica  — ZhipuAI embedding-2 (cosine similarity sobre SQLite)
  B. Reciente   — Conversaciones últimas N horas (SQLite)
  C. Grafo      — Neo4j entity relationships (opcional)
  D. Tiers      — 4-Tier JSON (working/medium/long/deep) (opcional)
  E. Síntesis   — GLM-4.7-flash resume todo en lenguaje natural (opcional)

Endpoint principal: /api/reasoning/context
Integrable en cualquier agente, canal o plugin (OpenClaw, Discord, n8n…).
"""
import os
import sys
import json
import time

# Path setup para imports relativos
_SRC = os.path.dirname(os.path.abspath(__file__))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from memory_noise_filter import is_agent_heartbeat_report, is_operational_runtime_noise

# ---- Configuración -------------------------------------------------------

_DATA_DIR = os.getenv("BRAIN_DATA_DIR", "/root/silhouette-brain/data")
TIER_FILES = {
    "working": os.path.join(_DATA_DIR, "working.json"),
    "medium":  os.path.join(_DATA_DIR, "medium.json"),
    "long":    os.path.join(_DATA_DIR, "long.json"),
    "deep":    os.path.join(_DATA_DIR, "deep.json"),
}

NEO4J_URI      = os.getenv("NEO4J_URI",      "bolt://localhost:7687")
NEO4J_USER     = os.getenv("NEO4J_USER",     "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "silhouette2035")


# =========================================================================
# CAPA A — Búsqueda semántica (ZhipuAI embedding-2)
# =========================================================================

def _layer_semantic(query: str, limit: int, min_score: float,
                    filter_heartbeats: bool) -> list:
    """Devuelve lista de {message, speaker, similarity, timestamp}."""
    try:
        from embeddings_wrapper import get_memory_core_embeddings
        data = get_memory_core_embeddings(query, limit * 2)   # pedir más, filtrar abajo
        results = data.get("results", [])
        out = []
        for r in results:
            sim = r.get("similarity", 0.0)
            if sim < min_score:
                continue
            msg = r.get("message", "")
            if filter_heartbeats and is_agent_heartbeat_report(msg):
                continue
            if is_operational_runtime_noise(msg):
                continue
            out.append({
                "message":   msg,
                "speaker":   r.get("speaker", ""),
                "similarity": round(sim, 4),
                "timestamp": r.get("timestamp", 0),
            })
            if len(out) >= limit:
                break
        return out
    except Exception as e:
        return [{"_error": f"semantic layer: {e}"}]


# =========================================================================
# CAPA B — Conversaciones recientes
# =========================================================================

def _layer_recent(hours: int, limit: int, filter_heartbeats: bool) -> list:
    """Devuelve lista de {message, speaker, datetime}."""
    try:
        from agent_memory_readonly import get_recent
        data = get_recent(hours, limit * 2)
        convs = data.get("conversations", [])
        out = []
        for c in convs:
            msg = c.get("message", "")
            if filter_heartbeats and is_agent_heartbeat_report(msg):
                continue
            if is_operational_runtime_noise(msg):
                continue
            out.append({
                "message":  msg,
                "speaker":  c.get("speaker", ""),
                "datetime": c.get("datetime", ""),
            })
            if len(out) >= limit:
                break
        return out
    except Exception as e:
        return [{"_error": f"recent layer: {e}"}]


# =========================================================================
# CAPA C — Grafo Neo4j (relaciones entre entidades)
# =========================================================================

def _layer_graph(query: str, limit: int = 15) -> list:
    """
    Devuelve relaciones relevantes del grafo Neo4j.
    Busca nodos cuyo nombre/contenido coincida con términos del query,
    y retorna sus relaciones (n)-[r]->(m).
    """
    try:
        from neo4j import GraphDatabase
    except ImportError:
        return [{"_error": "neo4j driver no instalado"}]

    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

        # Extraer términos relevantes del query (palabras >3 chars)
        terms = [w for w in query.split() if len(w) > 3]
        search_term = terms[0] if terms else query[:20]

        with driver.session() as session:
            # 1. Relaciones directas donde aparece el término
            result = session.run("""
                MATCH (n)-[r]->(m)
                WHERE toLower(n.name) CONTAINS toLower($term)
                   OR toLower(m.name) CONTAINS toLower($term)
                   OR toLower(n.content) CONTAINS toLower($term)
                RETURN n.name AS from, type(r) AS rel, m.name AS to,
                       n.type AS from_type, m.type AS to_type
                LIMIT $lim
            """, term=search_term, lim=limit)

            rels = []
            for rec in result:
                rels.append({
                    "from":      rec.get("from", "?"),
                    "rel":       rec.get("rel",  "?"),
                    "to":        rec.get("to",   "?"),
                    "from_type": rec.get("from_type"),
                    "to_type":   rec.get("to_type"),
                })

            # 2. Si no hay relaciones, buscar nodos sueltos
            if not rels:
                result2 = session.run("""
                    MATCH (n)
                    WHERE toLower(n.name) CONTAINS toLower($term)
                       OR toLower(n.content) CONTAINS toLower($term)
                    RETURN n.name AS name, labels(n) AS labels,
                           n.importance AS importance
                    ORDER BY n.importance DESC
                    LIMIT $lim
                """, term=search_term, lim=limit)
                for rec in result2:
                    rels.append({
                        "node":       rec.get("name", "?"),
                        "labels":     list(rec.get("labels", [])),
                        "importance": rec.get("importance"),
                    })

        driver.close()
        return rels
    except Exception as e:
        return [{"_error": f"neo4j: {e}"}]


# =========================================================================
# CAPA D — 4-Tier JSON memory
# =========================================================================

def _layer_tiers(tier_filter: str = None) -> dict:
    """Devuelve contenido de los archivos JSON de tier memory."""
    result = {}
    tiers = [tier_filter] if tier_filter else list(TIER_FILES.keys())
    for name in tiers:
        path = TIER_FILES.get(name)
        if path and os.path.exists(path):
            try:
                with open(path) as f:
                    result[name] = json.load(f)
            except Exception:
                result[name] = []
        else:
            result[name] = []
    return result


# =========================================================================
# CAPA E — Síntesis GLM-4.7-flash
# =========================================================================

def _layer_synthesis(query: str, semantic: list, recent: list,
                     graph: list, tiers: dict) -> str:
    """Sintetiza todo el contexto en un párrafo usando GLM-4.7-flash."""
    try:
        from local_embeddings import synthesize_context

        fragments = []

        for r in semantic[:6]:
            if "message" in r:
                who = r.get("speaker", "?")
                sim = int(r.get("similarity", 0) * 100)
                fragments.append(f"[Memoria {sim}%] <{who}> {r['message'][:180]}")

        for c in recent[:4]:
            if "message" in c:
                who = c.get("speaker", "?")
                dt  = c.get("datetime", "")
                fragments.append(f"[Reciente {dt}] <{who}> {c['message'][:180]}")

        for rel in graph[:5]:
            if "_error" not in rel:
                if "rel" in rel:
                    fragments.append(
                        f"[Grafo] {rel.get('from','?')} --{rel.get('rel','?')}--> {rel.get('to','?')}"
                    )
                elif "node" in rel:
                    fragments.append(f"[Grafo nodo] {rel.get('node','?')}")

        # Añadir tier working si tiene items relevantes
        for item in tiers.get("working", [])[:3]:
            if isinstance(item, dict):
                content = item.get("content", item.get("text", ""))
                if content:
                    fragments.append(f"[Working memory] {content[:120]}")

        return synthesize_context(query, fragments)
    except Exception as e:
        return f"[Síntesis no disponible: {e}]"


# =========================================================================
# MOTOR PRINCIPAL
# =========================================================================

def get_reasoning_context(
    query: str,
    sem_limit:        int   = 5,
    rec_limit:        int   = 3,
    hours:            int   = 2,
    min_score:        float = 0.3,
    include_graph:    bool  = False,
    include_tiers:    bool  = False,
    synthesize:       bool  = False,
    filter_heartbeats: bool = True,
    tier_filter:      str   = None,
) -> dict:
    """
    Motor de razonamiento unificado de Silhouette Brain.

    Args:
        query:             Consulta del agente/canal.
        sem_limit:         Máximo de resultados semánticos.
        rec_limit:         Máximo de conversaciones recientes.
        hours:             Ventana de tiempo para "reciente".
        min_score:         Similitud mínima semántica (0-1).
        include_graph:     Si True, incluye relaciones Neo4j.
        include_tiers:     Si True, incluye 4-tier JSON memory.
        synthesize:        Si True, genera síntesis con GLM-4.7-flash.
        filter_heartbeats: Filtra reportes automáticos de agentes.
        tier_filter:       Si se especifica, solo ese tier ('working', etc).

    Returns:
        dict con campos: semantic, recent, graph, tiers, synthesis,
                         formatted_context (listo para inyectar en prompt).
    """
    result: dict = {
        "query":          query,
        "semantic":       [],
        "recent":         [],
        "graph":          [],
        "tiers":          {},
        "synthesis":      "",
        "formatted_context": "",
    }

    # — Capa A: Semántica
    result["semantic"] = _layer_semantic(query, sem_limit, min_score, filter_heartbeats)

    # — Capa B: Reciente
    result["recent"] = _layer_recent(hours, rec_limit, filter_heartbeats)

    # — Capa C: Grafo
    if include_graph:
        result["graph"] = _layer_graph(query)

    # — Capa D: Tiers
    if include_tiers:
        result["tiers"] = _layer_tiers(tier_filter)

    # — Capa E: Síntesis (necesita contexto de capas anteriores)
    if synthesize:
        result["synthesis"] = _layer_synthesis(
            query,
            result["semantic"],
            result["recent"],
            result["graph"],
            result["tiers"],
        )

    # — Formatear contexto listo para inyectar en cualquier prompt
    result["formatted_context"] = _format_for_prompt(result)

    return result


def _format_for_prompt(ctx: dict) -> str:
    """
    Genera el bloque <industrial-memory> listo para prepender a cualquier prompt.
    Formato compatible con OpenClaw, Discord y cualquier agente.
    """
    lines = []

    if ctx.get("synthesis"):
        lines.append("── SÍNTESIS COGNITIVA ──")
        lines.append(ctx["synthesis"])
        lines.append("")

    if ctx.get("recent"):
        lines.append("── CONTEXTO RECIENTE ──")
        for r in ctx["recent"]:
            who = "Alberto" if r.get("speaker") == "user" else r.get("speaker", "?")
            lines.append(f"[{r.get('datetime','')}] <{who}> {r.get('message','')[:150]}")

    if ctx.get("semantic"):
        if lines:
            lines.append("")
        lines.append("── MEMORIA RELEVANTE ──")
        for r in ctx["semantic"]:
            if "_error" not in r:
                pct = int(r.get("similarity", 0) * 100)
                lines.append(f"[{pct}%] {r.get('message','')[:180]}")

    if ctx.get("graph"):
        valid = [r for r in ctx["graph"] if "_error" not in r]
        if valid:
            if lines:
                lines.append("")
            lines.append("── RELACIONES (GRAFO) ──")
            for rel in valid[:8]:
                if "rel" in rel:
                    lines.append(
                        f"{rel.get('from','?')} --{rel.get('rel','?')}--> {rel.get('to','?')}"
                    )
                elif "node" in rel:
                    lines.append(f"[nodo] {rel.get('node','?')}")

    if ctx.get("tiers"):
        tier_items = []
        for tier_name, items in ctx["tiers"].items():
            for item in (items or [])[:2]:
                if isinstance(item, dict):
                    content = item.get("content", item.get("text", ""))
                    if content:
                        tier_items.append(f"[{tier_name}] {content[:120]}")
        if tier_items:
            if lines:
                lines.append("")
            lines.append("── MEMORIA PERMANENTE ──")
            lines.extend(tier_items)

    if not lines:
        return ""

    return f"<industrial-memory>\n" + "\n".join(lines) + "\n</industrial-memory>"


# =========================================================================
# TEST STANDALONE
# =========================================================================

if __name__ == "__main__":
    print("=== Silhouette Reasoning Engine — Test ===\n")
    ctx = get_reasoning_context(
        query="proyectos Alberto Brandistry",
        sem_limit=5,
        rec_limit=3,
        hours=24,
        min_score=0.2,
        include_graph=True,
        include_tiers=True,
        synthesize=True,
    )
    print(f"Semánticos : {len(ctx['semantic'])}")
    print(f"Recientes  : {len(ctx['recent'])}")
    print(f"Grafo      : {len(ctx['graph'])}")
    print(f"Tiers      : {list(ctx['tiers'].keys())}")
    print(f"\nSíntesis:\n{ctx['synthesis']}")
    print(f"\nFormatted context:\n{ctx['formatted_context']}")
