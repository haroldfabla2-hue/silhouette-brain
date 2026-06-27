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
import subprocess
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from pathlib import Path

# Path setup para imports relativos
_SRC = os.path.dirname(os.path.abspath(__file__))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from memory_noise_filter import is_agent_heartbeat_report, is_operational_runtime_noise

# Para auto-reflexión y memoria de errores
try:
    from introspection_engine import get_introspection_engine
    _INTROSPECTION = get_introspection_engine()
except Exception:
    _INTROSPECTION = None

# ---- Configuración -------------------------------------------------------

_DATA_DIR = os.getenv("BRAIN_DATA_DIR", "/root/silhouette-brain/data")
TIER_FILES = {
    "working": os.path.join(_DATA_DIR, "working.json"),
    "medium":  os.path.join(_DATA_DIR, "medium.json"),
    "long":    os.path.join(_DATA_DIR, "long.json"),
    "deep":    os.path.join(_DATA_DIR, "deep.json"),
}

NEO4J_URI      = os.getenv("NEO4J_URI",      "bolt://localhost:17687")
NEO4J_USER     = os.getenv("NEO4J_USER",     "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "changeme")

_SEMANTIC_CACHE = {}
_SEMANTIC_CACHE_TTL_SEC = 180
_SEMANTIC_TOP_SCORE_MIN = max(0.0, min(float(os.getenv("SEMANTIC_TOP_SCORE_MIN", "0.60")), 1.0))
_SEMANTIC_SCORE_GAP_MIN = max(0.0, min(float(os.getenv("SEMANTIC_SCORE_GAP_MIN", "0.05")), 1.0))


def _env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return str(raw).strip().lower() not in ("0", "false", "no", "off")


def _env_int(name: str, default: int, floor: int = 0) -> int:
    try:
        return max(floor, int(os.getenv(name, str(default))))
    except Exception:
        return max(floor, int(default))


def _env_float(name: str, default: float, floor: float = 0.0, ceil: float = 1.0) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except Exception:
        value = float(default)
    return max(floor, min(value, ceil))


# Regla operativa: si no sabe, primero investiga profundo; pregunta solo al final.
_INVESTIGATE_BEFORE_ASK = _env_flag("REASONING_INVESTIGATE_BEFORE_ASK", True)
_DEEP_INVESTIGATION_SEM_LIMIT = _env_int("REASONING_DEEP_SEM_LIMIT", 12, floor=8)
_DEEP_INVESTIGATION_REC_LIMIT = _env_int("REASONING_DEEP_REC_LIMIT", 8, floor=4)
_DEEP_INVESTIGATION_HOURS = _env_int("REASONING_DEEP_HOURS", 48, floor=12)
_DEEP_INVESTIGATION_MIN_SCORE = _env_float("REASONING_DEEP_MIN_SCORE", 0.10, floor=0.0, ceil=1.0)
_DEEP_INVESTIGATION_DEADLINE_SEC = max(4.0, _env_float("REASONING_DEEP_DEADLINE_SEC", 10.0, floor=1.0, ceil=60.0))
_SOURCE_CAP_TTL_SEC = _env_int("REASONING_SOURCE_CAP_TTL_SEC", 1800, floor=60)
_SOURCE_CAP_CACHE = {"ts": 0.0, "caps": {}, "skills": []}
_SOURCE_FEEDBACK_FILE = Path(os.getenv("BRAIN_DATA_DIR", _DATA_DIR)) / "source_feedback.json"
_SOURCE_FEEDBACK_TTL_SEC = _env_int("REASONING_SOURCE_FEEDBACK_TTL_SEC", 300, floor=30)
_SOURCE_FEEDBACK_CACHE = {"ts": 0.0, "data": {}}


# =========================================================================
# Context Assembler profiles (budget + prioridades)
# =========================================================================

CONTEXT_ASSEMBLER_PROFILES = {
    "reply_fast": {
        "token_budget": 2800,
        "deadline_sec": 8.0,
        "max_parallel": 3,
        "sem_limit": 6,
        "rec_limit": 4,
        "hours": 6,
        "min_score": 0.15,
        "include_graph": False,
        "include_tiers": False,
        "synthesize": False,
        "semantic_mode": "full",
        "alloc": {
            "immediate": 0.25,
            "system": 0.12,
            "recent": 0.26,
            "memory": 0.30,
            "graph": 0.04,
            "tiers": 0.03,
            "synthesis": 0.00,
        },
    },
    "reply_deep": {
        "token_budget": 4200,
        "deadline_sec": 15.0,
        "max_parallel": 4,
        "sem_limit": 8,
        "rec_limit": 5,
        "hours": 12,
        "min_score": 0.15,
        "include_graph": True,
        "include_tiers": True,
        "synthesize": False,
        "semantic_mode": "full",
        "alloc": {
            "immediate": 0.18,
            "system": 0.10,
            "recent": 0.22,
            "memory": 0.28,
            "graph": 0.12,
            "tiers": 0.10,
            "synthesis": 0.00,
        },
    },
    "discovery": {
        "token_budget": 3600,
        "deadline_sec": 15.0,
        "max_parallel": 4,
        "sem_limit": 8,
        "rec_limit": 4,
        "hours": 24,
        "min_score": 0.10,
        "include_graph": True,
        "include_tiers": True,
        "synthesize": False,
        "semantic_mode": "full",
        "alloc": {
            "immediate": 0.14,
            "system": 0.12,
            "recent": 0.20,
            "memory": 0.28,
            "graph": 0.16,
            "tiers": 0.10,
            "synthesis": 0.00,
        },
    },
}


# =========================================================================
# CAPA A — Búsqueda semántica (ZhipuAI embedding-2)
# =========================================================================

def _semantic_cache_key(query: str, limit: int, min_score: float,
                        filter_heartbeats: bool) -> tuple:
    return (
        query.strip().lower(),
        int(limit),
        round(float(min_score), 3),
        bool(filter_heartbeats),
    )


def _semantic_cache_lookup(query: str, limit: int, min_score: float,
                           filter_heartbeats: bool):
    cache_key = _semantic_cache_key(query, limit, min_score, filter_heartbeats)
    cached = _SEMANTIC_CACHE.get(cache_key)
    now = time.time()
    if cached and (now - cached.get("ts", 0)) <= _SEMANTIC_CACHE_TTL_SEC:
        return True, cached.get("data", [])
    return False, []


def _semantic_rank_value(item: dict) -> float:
    try:
        raw = float(item.get("score", item.get("similarity", 0.0)) or 0.0)
        return max(0.0, min(raw, 1.0))
    except Exception:
        return 0.0


def _sort_and_dedupe_semantic(items: list, limit: int) -> list:
    # Orden estricto por score para que la evidencia más fuerte quede primero.
    ranked = sorted(
        [x for x in items if isinstance(x, dict) and "_error" not in x],
        key=lambda x: (
            _semantic_rank_value(x),
            float(x.get("similarity", 0.0) or 0.0),
            float(x.get("timestamp", 0.0) or 0.0),
        ),
        reverse=True,
    )
    out = []
    seen = set()
    for row in ranked:
        msg_key = (row.get("message", "") or "").strip().lower()
        if msg_key and msg_key in seen:
            continue
        if msg_key:
            seen.add(msg_key)
        out.append(row)
        if len(out) >= max(1, int(limit)):
            break
    return out


def _semantic_confidence_meta(semantic_items: list) -> dict:
    valid = [x for x in (semantic_items or []) if isinstance(x, dict) and "_error" not in x]
    ranked = sorted(valid, key=_semantic_rank_value, reverse=True)

    top_score = _semantic_rank_value(ranked[0]) if ranked else 0.0
    second_score = _semantic_rank_value(ranked[1]) if len(ranked) > 1 else None
    gap = (top_score - second_score) if second_score is not None else None

    reasons = []
    needs_confirmation = False

    if not ranked:
        needs_confirmation = True
        reasons.append("no_semantic_evidence")
    else:
        if top_score < _SEMANTIC_TOP_SCORE_MIN:
            needs_confirmation = True
            reasons.append("low_top_score")
        if gap is not None and gap < _SEMANTIC_SCORE_GAP_MIN:
            needs_confirmation = True
            reasons.append("small_score_gap")

    return {
        "has_semantic": bool(ranked),
        "top_score": round(top_score, 4),
        "second_score": round(second_score, 4) if second_score is not None else None,
        "score_gap": round(gap, 4) if gap is not None else None,
        "needs_confirmation": needs_confirmation,
        "reasons": reasons,
        "thresholds": {
            "min_top_score": _SEMANTIC_TOP_SCORE_MIN,
            "min_score_gap": _SEMANTIC_SCORE_GAP_MIN,
        },
    }


def _humanize_sources(sources: list) -> str:
    if not isinstance(sources, list) or not sources:
        return ""
    label_map = {
        "workspace_digital": "workspace digital",
        "google_workspace": "Google Workspace",
        "notebook_intel": "Notebook Intel",
        "web_search": "web search",
        "gmail_monitor": "Gmail monitor",
    }
    labels = [label_map.get(str(s), str(s).replace("_", " ")) for s in sources[:4]]
    return ", ".join(labels)


def _research_policy_line(investigation_pass: dict = None) -> str:
    investigation_pass = investigation_pass if isinstance(investigation_pass, dict) else {}
    source_plan = investigation_pass.get("source_plan", {}) if isinstance(investigation_pass.get("source_plan"), dict) else {}
    external_sources_text = _humanize_sources(source_plan.get("external", []))
    if external_sources_text:
        return (
            "Regla de evidencia: prioriza siempre la memoria con score mas alto; "
            "si hay duda, investiga primero memoria/sistema y luego fuentes externas "
            f"({external_sources_text}); solo despues pregunta."
        )
    return (
        "Regla de evidencia: prioriza siempre la memoria con score mas alto; "
        "si hay duda, investiga primero en memoria y sistema, y solo luego pregunta."
    )


def _semantic_uncertainty_lines(semantic_items: list, investigation_pass: dict = None) -> list:
    meta = _semantic_confidence_meta(semantic_items)
    investigation_pass = investigation_pass if isinstance(investigation_pass, dict) else {}
    deep_triggered = bool(investigation_pass.get("triggered"))
    deep_external = bool(investigation_pass.get("external_research_required"))
    source_plan = investigation_pass.get("source_plan", {}) if isinstance(investigation_pass.get("source_plan"), dict) else {}
    external_sources_text = _humanize_sources(source_plan.get("external", []))
    lines = []
    if "no_semantic_evidence" in meta["reasons"]:
        lines.append(
            "ALERTA INCERTIDUMBRE: no hay evidencia semantica suficiente; evita afirmar y pide confirmacion."
        )
    if "low_top_score" in meta["reasons"]:
        lines.append(
            f"ALERTA INCERTIDUMBRE: score tope bajo ({int(meta['top_score']*100)}%); responde con cautela y pregunta."
        )
    if "small_score_gap" in meta["reasons"] and meta.get("score_gap") is not None:
        lines.append(
            f"ALERTA INCERTIDUMBRE: evidencia competida (gap {int(meta['score_gap']*100)} pts); no concluyas sin confirmar."
        )
    if meta["needs_confirmation"]:
        if deep_triggered:
            external_hint = f" ({external_sources_text})" if external_sources_text else ""
            lines.append(
                "INSTRUCCION: ya hiciste investigacion profunda interna; si aun hay duda, investiga fuentes externas"
                + external_hint
                + " y solo despues pregunta verificacion."
            )
        elif deep_external:
            external_hint = f" ({external_sources_text})" if external_sources_text else ""
            lines.append(
                "INSTRUCCION: antes de preguntar, investiga en multiples fuentes (memoria interna + fuentes externas"
                + external_hint
                + ")."
            )
        else:
            lines.append(
                "INSTRUCCION: antes de preguntar, ejecuta investigacion profunda en memoria/sistema; si persiste la duda, formula una pregunta de verificacion explicita."
            )
    return lines


def _layer_semantic(query: str, limit: int, min_score: float,
                    filter_heartbeats: bool) -> list:
    """Devuelve lista de {message, speaker, similarity, timestamp}."""
    cache_hit, cached_data = _semantic_cache_lookup(query, limit, min_score, filter_heartbeats)
    if cache_hit:
        return cached_data

    try:
        from embeddings_wrapper import get_memory_core_embeddings
        data = get_memory_core_embeddings(query, limit * 2)   # pedir más, filtrar abajo
        results = data.get("results", [])
        now = time.time()
        cache_key = _semantic_cache_key(query, limit, min_score, filter_heartbeats)
        out = []
        for r in results:
            try:
                sim = float(r.get("similarity", 0.0) or 0.0)
            except Exception:
                sim = 0.0
            sim = max(0.0, min(sim, 1.0))
            try:
                score = float(r.get("score", sim) or sim)
            except Exception:
                score = sim
            score = max(0.0, min(score, 1.0))
            if score < min_score:
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
                "score": round(score, 4),
                "timestamp": r.get("timestamp", 0),
            })
        out = _sort_and_dedupe_semantic(out, limit)
        _SEMANTIC_CACHE[cache_key] = {"ts": now, "data": out}
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
                    RETURN coalesce(n.name, n.content, "?") AS name, labels(n) AS labels,
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
                score_pct = int(_semantic_rank_value(r) * 100)
                fragments.append(f"[Memoria score={score_pct}%] <{who}> {r['message'][:180]}")

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
# Deep Investigation Helpers
# =========================================================================

def _collect_layers_with_deadline(
    query: str,
    sem_limit: int,
    rec_limit: int,
    hours: int,
    min_score: float,
    include_graph: bool,
    include_tiers: bool,
    include_heartbeat: bool,
    semantic_mode: str,
    filter_heartbeats: bool,
    tier_filter: str,
    deadline_sec: float,
    max_parallel: int = 4,
) -> dict:
    start = time.time()
    source_errors = {}
    timed_out_sources = []
    skipped_sources = []
    semantic_cache_hit = False

    semantic = []
    recent = []
    graph = []
    tiers = {}
    heartbeat = {}

    semantic_mode = str(semantic_mode or "full").strip().lower()
    if semantic_mode not in ("full", "cache_only", "off"):
        semantic_mode = "full"

    pool = ThreadPoolExecutor(max_workers=max(1, int(max_parallel)))
    try:
        futures = {
            "recent": pool.submit(_layer_recent, hours, rec_limit, filter_heartbeats),
        }
        if semantic_mode == "full":
            futures["semantic"] = pool.submit(
                _layer_semantic,
                query,
                sem_limit,
                min_score,
                filter_heartbeats,
            )
        elif semantic_mode == "cache_only":
            semantic_cache_hit, semantic = _semantic_cache_lookup(
                query,
                sem_limit,
                min_score,
                filter_heartbeats,
            )
            if not semantic_cache_hit:
                skipped_sources.append("semantic_cache_miss")
        else:
            skipped_sources.append("semantic_off")

        if include_graph:
            futures["graph"] = pool.submit(_layer_graph, query)
        if include_tiers:
            futures["tiers"] = pool.submit(_layer_tiers, tier_filter)
        if include_heartbeat:
            futures["heartbeat"] = pool.submit(_load_heartbeat_snapshot)

        for src, fut in futures.items():
            remaining = max(0.05, float(deadline_sec) - (time.time() - start))
            try:
                data = fut.result(timeout=remaining)
            except FuturesTimeoutError:
                timed_out_sources.append(src)
                data = {} if src in ("tiers", "heartbeat") else []
            except Exception as e:
                source_errors[src] = str(e)
                data = {} if src in ("tiers", "heartbeat") else []

            if src == "semantic":
                semantic = data if isinstance(data, list) else []
            elif src == "recent":
                recent = data if isinstance(data, list) else []
            elif src == "graph":
                graph = data if isinstance(data, list) else []
            elif src == "tiers":
                tiers = data if isinstance(data, dict) else {}
            elif src == "heartbeat":
                heartbeat = data if isinstance(data, dict) else {}
    finally:
        pool.shutdown(wait=False, cancel_futures=True)

    return {
        "semantic": semantic,
        "recent": recent,
        "graph": graph,
        "tiers": tiers,
        "heartbeat": heartbeat,
        "semantic_cache_hit": semantic_cache_hit,
        "timed_out_sources": timed_out_sources,
        "skipped_sources": skipped_sources,
        "errors": source_errors,
        "elapsed_ms": int((time.time() - start) * 1000),
    }


def _merge_recent(primary: list, extra: list, limit: int) -> list:
    seen = set()
    out = []
    for row in list(primary or []) + list(extra or []):
        if not isinstance(row, dict) or "_error" in row:
            continue
        key = (
            str(row.get("speaker", "")).strip().lower(),
            str(row.get("datetime", "")).strip().lower(),
            str(row.get("message", "")).strip().lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
        if len(out) >= max(1, int(limit)):
            break
    return out


def _merge_graph(primary: list, extra: list, limit: int = 15) -> list:
    seen = set()
    out = []
    for row in list(primary or []) + list(extra or []):
        if not isinstance(row, dict) or "_error" in row:
            continue
        if "rel" in row:
            key = (
                "rel",
                str(row.get("from", "")).strip().lower(),
                str(row.get("rel", "")).strip().lower(),
                str(row.get("to", "")).strip().lower(),
            )
        else:
            key = ("node", str(row.get("node", "")).strip().lower())
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
        if len(out) >= max(1, int(limit)):
            break
    return out


def _tier_item_key(item) -> str:
    if isinstance(item, dict):
        content = item.get("content", item.get("text", ""))
        if content:
            return str(content).strip().lower()
        try:
            return json.dumps(item, ensure_ascii=False, sort_keys=True)
        except Exception:
            return str(item).strip().lower()
    return str(item).strip().lower()


def _merge_tiers(primary: dict, extra: dict) -> dict:
    out = {}
    all_tiers = set(list((primary or {}).keys()) + list((extra or {}).keys()))
    for tier_name in all_tiers:
        seen = set()
        merged_items = []
        for bucket in ((primary or {}).get(tier_name, []), (extra or {}).get(tier_name, [])):
            if not isinstance(bucket, list):
                continue
            for item in bucket:
                key = _tier_item_key(item)
                if key in seen:
                    continue
                seen.add(key)
                merged_items.append(item)
        out[tier_name] = merged_items
    return out


def _read_openclaw_eligible_skills(timeout_sec: int = 6) -> list:
    cmd = ["openclaw", "skills", "check", "--json"]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=max(2, int(timeout_sec)),
            check=False,
        )
        if proc.returncode != 0:
            return []
        payload = json.loads(proc.stdout or "{}")
        eligible = payload.get("eligible", [])
        if isinstance(eligible, list):
            return [str(x).strip() for x in eligible if str(x).strip()]
        return []
    except Exception:
        return []


def _normalize_feedback_table(raw: dict) -> dict:
    table = {}
    if not isinstance(raw, dict):
        return table
    for source, rec in raw.items():
        if not isinstance(source, str) or not source.strip():
            continue
        if not isinstance(rec, dict):
            continue
        try:
            success = max(0, int(rec.get("success", 0)))
        except Exception:
            success = 0
        try:
            failure = max(0, int(rec.get("failure", 0)))
        except Exception:
            failure = 0
        table[source.strip()] = {
            "success": success,
            "failure": failure,
            "last_outcome": str(rec.get("last_outcome", "") or ""),
            "updated_at": str(rec.get("updated_at", "") or ""),
        }
    return table


def _load_source_feedback(force_refresh: bool = False) -> dict:
    now = time.time()
    if not force_refresh and (now - float(_SOURCE_FEEDBACK_CACHE.get("ts", 0.0))) <= _SOURCE_FEEDBACK_TTL_SEC:
        cached = _SOURCE_FEEDBACK_CACHE.get("data", {})
        if isinstance(cached, dict):
            return dict(cached)

    table = {}
    try:
        if _SOURCE_FEEDBACK_FILE.exists():
            raw = json.loads(_SOURCE_FEEDBACK_FILE.read_text(encoding="utf-8"))
            table = _normalize_feedback_table(raw)
    except Exception:
        table = {}

    _SOURCE_FEEDBACK_CACHE["ts"] = now
    _SOURCE_FEEDBACK_CACHE["data"] = dict(table)
    return table


def _save_source_feedback(table: dict) -> None:
    safe = _normalize_feedback_table(table)
    try:
        _SOURCE_FEEDBACK_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = _SOURCE_FEEDBACK_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(safe, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(_SOURCE_FEEDBACK_FILE)
        _SOURCE_FEEDBACK_CACHE["ts"] = time.time()
        _SOURCE_FEEDBACK_CACHE["data"] = dict(safe)
    except Exception:
        pass


def _feedback_multiplier(source: str, feedback: dict) -> float:
    rec = (feedback or {}).get(source, {})
    success = int(rec.get("success", 0) or 0)
    failure = int(rec.get("failure", 0) or 0)
    # Suavizado bayesiano: prior uniforme.
    posterior = (success + 1.0) / (success + failure + 2.0)
    return 0.85 + (posterior * 0.30)  # ~0.85..1.15


def _update_source_feedback(sources: list, success: bool, reason: str = "") -> dict:
    sources = [str(s).strip() for s in (sources or []) if str(s).strip()]
    if not sources:
        return {"updated": False, "sources": []}

    table = _load_source_feedback(force_refresh=True)
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    outcome = "success" if success else "failure"

    for source in sources:
        rec = table.get(source, {"success": 0, "failure": 0})
        if success:
            rec["success"] = int(rec.get("success", 0) or 0) + 1
        else:
            rec["failure"] = int(rec.get("failure", 0) or 0) + 1
        rec["last_outcome"] = f"{outcome}:{reason}"[:120]
        rec["updated_at"] = now_iso
        table[source] = rec

    _save_source_feedback(table)
    return {"updated": True, "sources": sources, "outcome": outcome, "reason": reason}


def _parse_feedback_outcome(outcome) -> bool:
    if isinstance(outcome, bool):
        return outcome
    val = str(outcome or "").strip().lower()
    if val in ("1", "true", "ok", "success", "resolved", "positive", "up"):
        return True
    if val in ("0", "false", "fail", "failure", "error", "bad", "negative", "down", "uncertain"):
        return False
    raise ValueError("outcome invalido (usa success/failure o true/false)")


def get_source_feedback_snapshot(limit: int = 200) -> dict:
    table = _load_source_feedback(force_refresh=True)
    rows = []
    for source, rec in table.items():
        success = int(rec.get("success", 0) or 0)
        failure = int(rec.get("failure", 0) or 0)
        total = success + failure
        success_rate = round((success / total), 4) if total > 0 else 0.0
        rows.append(
            {
                "source": source,
                "success": success,
                "failure": failure,
                "total": total,
                "success_rate": success_rate,
                "feedback_multiplier": round(_feedback_multiplier(source, table), 4),
                "last_outcome": rec.get("last_outcome", ""),
                "updated_at": rec.get("updated_at", ""),
            }
        )
    rows.sort(key=lambda x: (x["total"], x["feedback_multiplier"], x["success_rate"]), reverse=True)
    if int(limit) > 0:
        rows = rows[: int(limit)]
    return {
        "file": str(_SOURCE_FEEDBACK_FILE),
        "count": len(rows),
        "rows": rows,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def record_source_feedback(sources, outcome, reason: str = "", actor: str = "user") -> dict:
    if isinstance(sources, str):
        normalized = [s.strip() for s in sources.split(",") if s.strip()]
    elif isinstance(sources, list):
        normalized = [str(s).strip() for s in sources if str(s).strip()]
    else:
        normalized = []
    if not normalized:
        return {"ok": False, "error": "sources vacio"}
    try:
        success = _parse_feedback_outcome(outcome)
    except ValueError as e:
        return {"ok": False, "error": str(e)}

    actor = str(actor or "user").strip()[:32]
    reason = str(reason or "").strip()
    tagged_reason = f"{actor}:{reason}" if reason else actor
    update = _update_source_feedback(normalized, success=success, reason=tagged_reason)
    snapshot = get_source_feedback_snapshot(limit=200)
    touched = [x for x in snapshot.get("rows", []) if x.get("source") in normalized]
    return {
        "ok": True,
        "update": update,
        "touched": touched,
        "snapshot_count": snapshot.get("count", 0),
    }


def _detect_source_capabilities() -> dict:
    now = time.time()
    if (now - float(_SOURCE_CAP_CACHE.get("ts", 0.0))) <= _SOURCE_CAP_TTL_SEC:
        cached = _SOURCE_CAP_CACHE.get("caps", {})
        if isinstance(cached, dict) and cached:
            return dict(cached)

    workspace_candidates = [
        Path("/root/.openclaw/workspace"),
        Path("/root/.openclaw/workspace-silhouette"),
        Path("/root/.openclaw/workspace-main"),
    ]
    skills = _read_openclaw_eligible_skills(timeout_sec=6)
    skill_set = set(skills)

    caps = {
        "internal_memory": True,
        "system_heartbeat": True,
        "workspace_digital": any(p.exists() for p in workspace_candidates),
        "google_workspace": "google-workspace" in skill_set,
        "notebook_intel": "silhouette-notebook-intel" in skill_set,
        "gmail_monitor": "gmail-monitor" in skill_set,
        # No hay skill dedicada llamada web-search; se infiere por rutas de investigación listas.
        "web_search": any(s in skill_set for s in ("gemini", "coding-agent", "silhouette-notebook-intel")),
    }

    _SOURCE_CAP_CACHE["ts"] = now
    _SOURCE_CAP_CACHE["caps"] = dict(caps)
    _SOURCE_CAP_CACHE["skills"] = sorted(skill_set)
    return caps


def _infer_research_signals(query: str, confidence: dict) -> dict:
    q = (query or "").strip().lower()
    reasons = set()

    if confidence.get("needs_confirmation"):
        reasons.add("uncertain_answer")
    if "no_semantic_evidence" in (confidence.get("reasons") or []):
        reasons.add("no_internal_evidence")
    if "small_score_gap" in (confidence.get("reasons") or []):
        reasons.add("conflicting_internal_memories")
    if "low_top_score" in (confidence.get("reasons") or []):
        reasons.add("weak_internal_signal")

    workspace_terms = [
        "workspace", "repositorio", "repo", "archivo", "log", "sistema", "daemon", "deploy", "n8n",
    ]
    google_terms = [
        "google", "drive", "docs", "doc", "sheet", "sheets", "gmail", "correo", "calendar", "calendario", "meet",
    ]
    web_terms = [
        "actual", "hoy", "latest", "reciente", "noticia", "precio", "mercado", "competencia", "investiga",
    ]

    if any(t in q for t in workspace_terms):
        reasons.add("workspace_context")
    if any(t in q for t in google_terms):
        reasons.add("google_workspace_context")
    if any(t in q for t in web_terms):
        reasons.add("requires_fresh_external_data")
    if len(q.split()) >= 8:
        reasons.add("complex_query")

    return {"reasons": sorted(reasons)}


def _select_research_sources(query: str, confidence: dict, caps: dict, feedback: dict = None) -> dict:
    signals = _infer_research_signals(query, confidence)
    reasons = set(signals.get("reasons", []))
    feedback = feedback if isinstance(feedback, dict) else _load_source_feedback()

    internal = ["semantic", "recent", "graph", "tiers", "heartbeat"]
    candidate_scores = {}
    rationale = {}
    q = (query or "").lower()
    is_workspace = "workspace_context" in reasons
    is_google = "google_workspace_context" in reasons
    needs_fresh = "requires_fresh_external_data" in reasons
    is_complex = "complex_query" in reasons
    is_uncertain = "uncertain_answer" in reasons
    is_conflict = "conflicting_internal_memories" in reasons
    weak_or_empty = bool({"no_internal_evidence", "weak_internal_signal"} & reasons)

    def add_candidate(source: str, score: float, why: str):
        if not source:
            return
        candidate_scores[source] = float(candidate_scores.get(source, 0.0)) + float(score)
        rationale.setdefault(source, []).append(why)

    # Prioridad por pertinencia de la duda.
    if caps.get("workspace_digital") and is_workspace:
        add_candidate("workspace_digital", 1.00, "contexto operativo/proyecto")

    if caps.get("google_workspace") and (is_google or ("proyecto" in q and is_uncertain)):
        add_candidate("google_workspace", 1.00, "documentos/correos/calendario")

    if caps.get("notebook_intel") and (is_conflict or (is_complex and (is_workspace or is_google))):
        add_candidate("notebook_intel", 0.90, "consolidar fuentes y contraste")

    if caps.get("web_search") and (needs_fresh or weak_or_empty or (is_uncertain and not (is_workspace or is_google))):
        add_candidate("web_search", 1.10 if needs_fresh else 0.85, "evidencia externa actualizada")

    if caps.get("gmail_monitor") and any(t in (query or "").lower() for t in ("correo", "mail", "gmail", "inbox")):
        add_candidate("gmail_monitor", 1.20, "consulta de correo")

    # Ranking aprendido por feedback histórico.
    ranked = []
    for src, base_score in candidate_scores.items():
        mult = _feedback_multiplier(src, feedback)
        weighted = round(base_score * mult, 4)
        ranked.append(
            {
                "source": src,
                "base_score": round(base_score, 4),
                "feedback_multiplier": round(mult, 4),
                "weighted_score": weighted,
                "rationale": rationale.get(src, []),
            }
        )
    ranked.sort(key=lambda x: x["weighted_score"], reverse=True)

    # Umbral para no abrir demasiadas fuentes de bajo valor.
    external = [x["source"] for x in ranked if x["weighted_score"] >= 0.60][:5]

    return {
        "internal": internal,
        "external": external,
        "signals": sorted(reasons),
        "ranked_external": ranked,
    }


def _maybe_run_deep_investigation(
    query: str,
    semantic: list,
    recent: list,
    graph: list,
    tiers: dict,
    heartbeat: dict,
    sem_limit: int,
    rec_limit: int,
    hours: int,
    min_score: float,
    filter_heartbeats: bool,
    tier_filter: str,
    base_deadline_sec: float,
    max_parallel: int,
    include_external_sources: bool = True,
) -> dict:
    initial_meta = _semantic_confidence_meta(semantic)
    feedback = _load_source_feedback()
    source_caps = _detect_source_capabilities()
    source_plan = _select_research_sources(query, initial_meta, source_caps, feedback=feedback)
    if not include_external_sources:
        source_plan["external"] = []
        source_plan["ranked_external"] = []
    report = {
        "enabled": bool(_INVESTIGATE_BEFORE_ASK),
        "triggered": False,
        "initial_confidence": initial_meta,
        "final_confidence": initial_meta,
        "external_research_required": bool(source_plan.get("external")),
        "source_capabilities": source_caps,
        "source_plan": source_plan,
        "sources_policy": {
            "internal": source_plan.get("internal", []),
            "external": source_plan.get("external", []),
        },
    }

    if not _INVESTIGATE_BEFORE_ASK:
        report["skipped_reason"] = "disabled_by_env"
        return {
            "semantic": semantic,
            "recent": recent,
            "graph": graph,
            "tiers": tiers,
            "heartbeat": heartbeat,
            "investigation_pass": report,
        }

    if not initial_meta.get("needs_confirmation"):
        report["skipped_reason"] = "confidence_sufficient"
        return {
            "semantic": semantic,
            "recent": recent,
            "graph": graph,
            "tiers": tiers,
            "heartbeat": heartbeat,
            "investigation_pass": report,
        }

    deep_sem_limit = max(int(sem_limit or 0), _DEEP_INVESTIGATION_SEM_LIMIT)
    deep_rec_limit = max(int(rec_limit or 0), _DEEP_INVESTIGATION_REC_LIMIT)
    deep_hours = max(int(hours or 0), _DEEP_INVESTIGATION_HOURS)
    deep_min_score = min(float(min_score if min_score is not None else _DEEP_INVESTIGATION_MIN_SCORE), _DEEP_INVESTIGATION_MIN_SCORE)
    deep_deadline_sec = max(float(base_deadline_sec or 0.0), _DEEP_INVESTIGATION_DEADLINE_SEC)

    deep = _collect_layers_with_deadline(
        query=query,
        sem_limit=deep_sem_limit,
        rec_limit=deep_rec_limit,
        hours=deep_hours,
        min_score=deep_min_score,
        include_graph=True,
        include_tiers=True,
        include_heartbeat=True,
        semantic_mode="full",
        filter_heartbeats=filter_heartbeats,
        tier_filter=tier_filter,
        deadline_sec=deep_deadline_sec,
        max_parallel=max(4, int(max_parallel or 1)),
    )

    merged_semantic = _sort_and_dedupe_semantic(
        list(semantic or []) + list(deep.get("semantic", []) or []),
        deep_sem_limit,
    )
    merged_recent = _merge_recent(recent, deep.get("recent", []), deep_rec_limit)
    merged_graph = _merge_graph(graph, deep.get("graph", []), limit=18)
    merged_tiers = _merge_tiers(tiers or {}, deep.get("tiers", {}) or {})
    merged_heartbeat = heartbeat if isinstance(heartbeat, dict) and heartbeat else deep.get("heartbeat", {})

    final_meta = _semantic_confidence_meta(merged_semantic)
    improved = bool(
        (not final_meta.get("needs_confirmation"))
        or (float(final_meta.get("top_score", 0.0) or 0.0) - float(initial_meta.get("top_score", 0.0) or 0.0) >= 0.10)
        or (
            float(final_meta.get("score_gap", 0.0) or 0.0) - float(initial_meta.get("score_gap", 0.0) or 0.0) >= 0.05
        )
    )
    feedback_update = _update_source_feedback(
        sources=source_plan.get("internal", []),
        success=improved,
        reason="deep_pass_improved" if improved else "deep_pass_uncertain",
    )
    report.update(
        {
            "triggered": True,
            "query": query,
            "params": {
                "sem_limit": deep_sem_limit,
                "rec_limit": deep_rec_limit,
                "hours": deep_hours,
                "min_score": deep_min_score,
                "deadline_sec": deep_deadline_sec,
            },
            "source_plan": source_plan,
            "deep_sources": {
                "timed_out_sources": deep.get("timed_out_sources", []),
                "skipped_sources": deep.get("skipped_sources", []),
                "errors": deep.get("errors", {}),
                "elapsed_ms": deep.get("elapsed_ms", 0),
            },
            "counts_after": {
                "semantic": len([x for x in merged_semantic if isinstance(x, dict) and "_error" not in x]),
                "recent": len([x for x in merged_recent if isinstance(x, dict) and "_error" not in x]),
                "graph": len([x for x in merged_graph if isinstance(x, dict) and "_error" not in x]),
            },
            "final_confidence": final_meta,
            "still_uncertain": bool(final_meta.get("needs_confirmation")),
            "learning_feedback": feedback_update,
        }
    )

    return {
        "semantic": merged_semantic,
        "recent": merged_recent,
        "graph": merged_graph,
        "tiers": merged_tiers,
        "heartbeat": merged_heartbeat if isinstance(merged_heartbeat, dict) else {},
        "investigation_pass": report,
    }


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
        "heartbeat":      {},
        "investigation_pass": {},
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

    # — Capa Sistema: heartbeat snapshot
    result["heartbeat"] = _load_heartbeat_snapshot()

    # — Regla anti-alucinación: antes de preguntar, investigar profundo.
    deep = _maybe_run_deep_investigation(
        query=query,
        semantic=result["semantic"],
        recent=result["recent"],
        graph=result["graph"],
        tiers=result["tiers"],
        heartbeat=result["heartbeat"],
        sem_limit=sem_limit,
        rec_limit=rec_limit,
        hours=hours,
        min_score=min_score,
        filter_heartbeats=filter_heartbeats,
        tier_filter=tier_filter,
        base_deadline_sec=CONTEXT_ASSEMBLER_PROFILES["reply_deep"]["deadline_sec"],
        max_parallel=CONTEXT_ASSEMBLER_PROFILES["reply_deep"]["max_parallel"],
        include_external_sources=True,
    )
    result["semantic"] = deep.get("semantic", result["semantic"])
    result["recent"] = deep.get("recent", result["recent"])
    result["graph"] = deep.get("graph", result["graph"])
    result["tiers"] = deep.get("tiers", result["tiers"])
    result["heartbeat"] = deep.get("heartbeat", result["heartbeat"])
    result["investigation_pass"] = deep.get("investigation_pass", {})

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
    result["semantic_confidence"] = _semantic_confidence_meta(result.get("semantic", []))

    # — Auto-reflexión: buscar errores similares antes de responder
    result["past_mistakes"] = _load_past_mistakes(query)
    
    # — Cargar lecciones aprendidas
    result["lessons_learned"] = _load_lessons_learned(query)

    return result


def _load_lessons_learned(query: str) -> list:
    """Carga lecciones aprendidas del IntrospectionEngine."""
    global _INTROSPECTION
    if _INTROSPECTION is None:
        try:
            from introspection_engine import get_introspection_engine
            _INTROSPECTION = get_introspection_engine()
        except Exception:
            return []
    
    try:
        return _INTROSPECTION.get_recent_lessons(limit=3)
    except Exception:
        return []


def _load_past_mistakes(query: str) -> list:
    """Carga errores similares del IntrospectionEngine antes de responder."""
    global _INTROSPECTION
    if _INTROSPECTION is None:
        try:
            from introspection_engine import get_introspection_engine
            _INTROSPECTION = get_introspection_engine()
        except Exception:
            return []
    
    try:
        return _INTROSPECTION.check_past_mistakes(context=query, query=query)
    except Exception:
        return []


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

    system_lines = _heartbeat_to_lines(ctx.get("heartbeat", {}))
    if system_lines:
        if lines:
            lines.append("")
        lines.append("── ESTADO DEL SISTEMA ──")
        lines.extend(system_lines[:5])

    semantic_valid = [r for r in (ctx.get("semantic") or []) if "_error" not in r]
    investigation_pass = ctx.get("investigation_pass", {}) if isinstance(ctx.get("investigation_pass"), dict) else {}
    uncertainty_lines = _semantic_uncertainty_lines(semantic_valid, investigation_pass)
    if semantic_valid or uncertainty_lines:
        if lines:
            lines.append("")
        lines.append("── MEMORIA RELEVANTE ──")
        lines.append(_research_policy_line(investigation_pass))
        if investigation_pass.get("triggered"):
            final_meta = investigation_pass.get("final_confidence", {})
            still_uncertain = bool(final_meta.get("needs_confirmation"))
            status = "pendiente confirmar" if still_uncertain else "resuelta tras investigar"
            lines.append(f"[Investigacion profunda] Estado: {status}")
            selected_external = _humanize_sources(
                (investigation_pass.get("source_plan", {}) or {}).get("external", [])
                if isinstance(investigation_pass.get("source_plan"), dict) else []
            )
            if selected_external:
                lines.append(f"[Investigacion profunda] Fuentes externas sugeridas: {selected_external}")
        lines.extend(uncertainty_lines)
        for r in semantic_valid:
            score_pct = int(_semantic_rank_value(r) * 100)
            sim_pct = int(float(r.get("similarity", 0.0) or 0.0) * 100)
            lines.append(f"[score={score_pct}% | sim={sim_pct}%] {r.get('message','')[:180]}")

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

    # — Errores anteriores para evitar repetir
    past_mistakes = ctx.get("past_mistakes", [])
    if past_mistakes:
        if lines:
            lines.append("")
        lines.append("── ERRORES ANTERIORES (EVITAR) ──")
        for m in past_mistakes[:3]:
            error_msg = (m.get('error') or '').strip()
            correction_msg = (m.get('correction') or '').strip()
            if error_msg:
                lines.append(f"⚠️ ERROR: {error_msg[:100]}")
            if correction_msg:
                lines.append(f"   CORRECCIÓN: {correction_msg[:100]}")

    # — Lecciones aprendidas
    lessons = ctx.get("lessons_learned", [])
    if lessons:
        if lines:
            lines.append("")
        lines.append("── LECCIONES APRENDIDAS ──")
        for l in lessons[:3]:
            cat = l.get('category', 'general')
            lesson = l.get('lesson', '')[:80]
            lines.append(f"📚 [{cat}] {lesson}")

    if not lines:
        return ""

    return f"<industrial-memory>\n" + "\n".join(lines) + "\n</industrial-memory>"


# =========================================================================
# Context Assembler (presupuesto + pruning + ejecución paralela)
# =========================================================================

def _estimate_tokens(text: str) -> int:
    """Estimación rápida de tokens (aprox 4 chars/token)."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def _trim_line_to_budget(text: str, max_tokens: int) -> str:
    if max_tokens <= 0:
        return ""
    max_chars = max_tokens * 4
    if len(text) <= max_chars:
        return text
    suffix = "..."
    cut = max(0, max_chars - len(suffix))
    return text[:cut] + suffix


def _apply_budget(lines: list, budget_tokens: int, always_keep: bool = False):
    """
    Conserva líneas hasta llenar presupuesto.
    Si always_keep=True y no cabe nada, conserva una versión truncada de la primera línea.
    """
    if budget_tokens <= 0:
        return [], 0, len(lines)

    kept = []
    used = 0
    dropped = 0

    for idx, line in enumerate(lines):
        token_cost = _estimate_tokens(line) + 1  # +1 por separadores/saltos
        if used + token_cost <= budget_tokens:
            kept.append(line)
            used += token_cost
            continue

        # Si es obligatorio mantener algo, intenta truncar la primera línea
        if always_keep and idx == 0 and not kept:
            remaining = max(4, budget_tokens - used - 1)
            trimmed = _trim_line_to_budget(line, remaining)
            if trimmed:
                kept.append(trimmed)
                used += _estimate_tokens(trimmed) + 1
            continue

        dropped += 1

    return kept, used, dropped


def _load_heartbeat_snapshot() -> dict:
    hb_paths = [
        Path(os.getenv("BRAIN_DATA_DIR", _DATA_DIR)) / "heartbeat_state.json",
        Path("/root/.openclaw/workspace/heartbeat-state.json"),
    ]
    for hb in hb_paths:
        if hb.exists():
            try:
                return json.loads(hb.read_text(encoding="utf-8"))
            except Exception:
                continue
    return {}


def _heartbeat_to_lines(heartbeat: dict) -> list:
    if not isinstance(heartbeat, dict) or not heartbeat:
        return []

    lines = []
    energia = heartbeat.get("energia")
    timestamp = heartbeat.get("timestamp") or heartbeat.get("timestamp_peru")
    servicios = heartbeat.get("servicios", {}) if isinstance(heartbeat.get("servicios"), dict) else {}
    memoria = heartbeat.get("memoria", {}) if isinstance(heartbeat.get("memoria"), dict) else {}
    pendientes = heartbeat.get("pendientes", [])
    proactive = heartbeat.get("proactive_signal")
    proactive_reason = heartbeat.get("proactive_reason")

    if timestamp:
        lines.append(f"Heartbeat: {timestamp}")
    if energia is not None:
        lines.append(f"Energia sistema: {energia}")
    if servicios:
        svc = " | ".join(f"{k}={v}" for k, v in servicios.items())
        lines.append(f"Servicios: {svc}")
    if memoria:
        convs = memoria.get("conversaciones", "?")
        coverage = memoria.get("cobertura_emb", "?")
        lines.append(f"Memoria: {convs} conversaciones ({coverage} embeddings)")
    if proactive and proactive_reason:
        lines.append(f"Senal proactiva: {proactive_reason}")
    if isinstance(pendientes, list) and pendientes:
        for p in pendientes[:3]:
            lines.append(f"Pendiente: {str(p)[:180]}")

    return lines


def assemble_context_packet(
    query: str,
    mode: str = "reply_fast",
    token_budget: int = None,
    sem_limit: int = None,
    rec_limit: int = None,
    hours: int = None,
    min_score: float = None,
    include_graph=None,
    include_tiers=None,
    synthesize=None,
    semantic_mode: str = None,
    filter_heartbeats: bool = True,
    tier_filter: str = None,
    include_heartbeat: bool = True,
    agent_id: str = "",
    channel: str = "",
) -> dict:
    """
    Ensambla contexto con:
      - llamadas paralelas por capa
      - presupuesto estricto por prioridad
      - pruning de secciones de menor valor
    """
    if not query:
        return {
            "query": query,
            "mode": mode,
            "formatted_context": "",
            "semantic": [],
            "recent": [],
            "graph": [],
            "tiers": {},
            "synthesis": "",
            "heartbeat": {},
            "investigation_pass": {
                "enabled": bool(_INVESTIGATE_BEFORE_ASK),
                "triggered": False,
                "initial_confidence": _semantic_confidence_meta([]),
                "final_confidence": _semantic_confidence_meta([]),
                "external_research_required": True,
                "sources_policy": {
                    "internal": ["semantic", "recent", "graph", "tiers", "heartbeat"],
                    "external": ["workspace_digital", "google_workspace", "web_search"],
                },
            },
            "context_packet": {
                "token_budget": token_budget or 0,
                "token_estimate": 0,
                "sections": {},
                "timed_out_sources": [],
                "skipped_sources": [],
                "errors": {},
            },
            "semantic_count": 0,
            "recent_count": 0,
            "graph_count": 0,
        }

    profile_name = mode if mode in CONTEXT_ASSEMBLER_PROFILES else "reply_fast"
    profile = CONTEXT_ASSEMBLER_PROFILES[profile_name]

    token_budget = int(token_budget or profile["token_budget"])
    deadline_sec = float(profile["deadline_sec"])
    max_parallel = int(profile["max_parallel"])
    sem_limit = int(sem_limit or profile["sem_limit"])
    rec_limit = int(rec_limit or profile["rec_limit"])
    hours = int(hours or profile["hours"])
    min_score = float(min_score if min_score is not None else profile["min_score"])
    include_graph = profile["include_graph"] if include_graph is None else bool(include_graph)
    include_tiers = profile["include_tiers"] if include_tiers is None else bool(include_tiers)
    synthesize = profile["synthesize"] if synthesize is None else bool(synthesize)
    semantic_mode = (
        semantic_mode
        if semantic_mode is not None
        else profile.get("semantic_mode", "full")
    )
    semantic_mode = str(semantic_mode).strip().lower()
    if semantic_mode not in ("full", "cache_only", "off"):
        semantic_mode = profile.get("semantic_mode", "full")

    # ---- fan-out paralelo ------------------------------------------------
    start = time.time()
    initial = _collect_layers_with_deadline(
        query=query,
        sem_limit=sem_limit,
        rec_limit=rec_limit,
        hours=hours,
        min_score=min_score,
        include_graph=include_graph,
        include_tiers=include_tiers,
        include_heartbeat=include_heartbeat,
        semantic_mode=semantic_mode,
        filter_heartbeats=filter_heartbeats,
        tier_filter=tier_filter,
        deadline_sec=deadline_sec,
        max_parallel=max_parallel,
    )

    semantic = initial.get("semantic", [])
    recent = initial.get("recent", [])
    graph = initial.get("graph", [])
    tiers = initial.get("tiers", {})
    heartbeat = initial.get("heartbeat", {})
    semantic_cache_hit = bool(initial.get("semantic_cache_hit", False))
    source_errors = dict(initial.get("errors", {}))
    timed_out_sources = list(initial.get("timed_out_sources", []))
    skipped_sources = list(initial.get("skipped_sources", []))

    deep = _maybe_run_deep_investigation(
        query=query,
        semantic=semantic,
        recent=recent,
        graph=graph,
        tiers=tiers,
        heartbeat=heartbeat,
        sem_limit=sem_limit,
        rec_limit=rec_limit,
        hours=hours,
        min_score=min_score,
        filter_heartbeats=filter_heartbeats,
        tier_filter=tier_filter,
        base_deadline_sec=deadline_sec,
        max_parallel=max_parallel,
        include_external_sources=True,
    )
    semantic = deep.get("semantic", semantic)
    recent = deep.get("recent", recent)
    graph = deep.get("graph", graph)
    tiers = deep.get("tiers", tiers)
    heartbeat = deep.get("heartbeat", heartbeat)
    investigation_pass = deep.get("investigation_pass", {})

    deep_sources = investigation_pass.get("deep_sources", {}) if isinstance(investigation_pass, dict) else {}
    for item in (deep_sources.get("timed_out_sources", []) if isinstance(deep_sources, dict) else []):
        timed_out_sources.append(f"deep:{item}")
    for item in (deep_sources.get("skipped_sources", []) if isinstance(deep_sources, dict) else []):
        skipped_sources.append(f"deep:{item}")
    if isinstance(deep_sources, dict):
        for k, v in (deep_sources.get("errors", {}) or {}).items():
            source_errors[f"deep:{k}"] = v

    synthesis_text = ""
    if synthesize and (time.time() - start) < deadline_sec:
        try:
            synthesis_text = _layer_synthesis(query, semantic, recent, graph, tiers)
        except Exception as e:
            source_errors["synthesis"] = str(e)

    # ---- construir secciones --------------------------------------------
    immediate_lines = [f"Consulta actual: {query}"]
    system_lines = _heartbeat_to_lines(heartbeat)

    recent_lines = []
    for r in recent:
        if "_error" in r:
            continue
        who = "Alberto" if r.get("speaker") == "user" else r.get("speaker", "?")
        recent_lines.append(f"[{r.get('datetime','')}] <{who}> {r.get('message','')[:160]}")

    semantic_valid = [r for r in semantic if "_error" not in r]
    uncertainty_lines = _semantic_uncertainty_lines(semantic_valid, investigation_pass)
    memory_lines = []
    if semantic_valid or uncertainty_lines:
        memory_lines.append(_research_policy_line(investigation_pass))
        if investigation_pass.get("triggered"):
            final_meta = investigation_pass.get("final_confidence", {})
            still_uncertain = bool(final_meta.get("needs_confirmation"))
            memory_lines.append(
                "[Investigacion profunda] "
                + ("persiste incertidumbre; requiere confirmar" if still_uncertain else "resolvio la incertidumbre")
            )
            selected_external = _humanize_sources(
                (investigation_pass.get("source_plan", {}) or {}).get("external", [])
                if isinstance(investigation_pass.get("source_plan"), dict) else []
            )
            if selected_external:
                memory_lines.append(f"[Investigacion profunda] Fuentes externas sugeridas: {selected_external}")
        memory_lines.extend(uncertainty_lines)
    for r in semantic_valid:
        score_pct = int(_semantic_rank_value(r) * 100)
        sim_pct = int(float(r.get("similarity", 0.0) or 0.0) * 100)
        memory_lines.append(f"[score={score_pct}% | sim={sim_pct}%] {r.get('message','')[:200]}")

    graph_lines = []
    for rel in graph:
        if "_error" in rel:
            continue
        if "rel" in rel:
            graph_lines.append(
                f"{rel.get('from','?')} --{rel.get('rel','?')}--> {rel.get('to','?')}"
            )
        elif "node" in rel:
            graph_lines.append(f"[nodo] {rel.get('node','?')}")

    tier_lines = []
    for tier_name, items in (tiers or {}).items():
        for item in (items if isinstance(items, list) else [])[:3]:
            if isinstance(item, dict):
                content = item.get("content", item.get("text", ""))
            else:
                content = str(item)
            if content:
                tier_lines.append(f"[{tier_name}] {content[:180]}")

    synthesis_lines = [synthesis_text[:500]] if synthesis_text else []

    section_payload = {
        "immediate": immediate_lines,
        "system": system_lines,
        "recent": recent_lines,
        "memory": memory_lines,
        "graph": graph_lines,
        "tiers": tier_lines,
        "synthesis": synthesis_lines,
    }

    alloc = profile["alloc"]
    section_meta = {}
    selected = {}
    total_tokens = 0

    for section_name in ("immediate", "system", "recent", "memory", "graph", "tiers", "synthesis"):
        lines = section_payload.get(section_name, [])
        ratio = float(alloc.get(section_name, 0.0))
        budget = max(16, int(token_budget * ratio))
        always_keep = section_name == "immediate"
        kept, used, dropped = _apply_budget(lines, budget, always_keep=always_keep)
        selected[section_name] = kept
        section_meta[section_name] = {
            "budget_tokens": budget,
            "used_tokens": used,
            "kept_lines": len(kept),
            "dropped_lines": dropped,
            "hard_pruned": 0,
        }
        total_tokens += used

    # pruning duro (de menor prioridad a mayor prioridad)
    hard_prune_order = ["tiers", "graph", "synthesis", "recent", "memory", "system"]
    while total_tokens > token_budget:
        removed_any = False
        for section_name in hard_prune_order:
            if not selected.get(section_name):
                continue
            removed = selected[section_name].pop()
            t = _estimate_tokens(removed) + 1
            total_tokens = max(0, total_tokens - t)
            section_meta[section_name]["hard_pruned"] += 1
            removed_any = True
            if total_tokens <= token_budget:
                break
        if not removed_any:
            break

    headings = {
        "immediate": "── CONSULTA ACTUAL ──",
        "system": "── ESTADO DEL SISTEMA ──",
        "recent": "── CONTEXTO RECIENTE ──",
        "memory": "── MEMORIA RELEVANTE ──",
        "graph": "── RELACIONES (GRAFO) ──",
        "tiers": "── MEMORIA PERMANENTE ──",
        "synthesis": "── SINTESIS COGNITIVA ──",
    }

    out_lines = []
    for section_name in ("immediate", "system", "recent", "memory", "graph", "tiers", "synthesis"):
        lines = selected.get(section_name, [])
        if not lines:
            continue
        out_lines.append(headings[section_name])
        out_lines.extend(lines)
        out_lines.append("")

    if out_lines and out_lines[-1] == "":
        out_lines.pop()

    formatted_context = ""
    if out_lines:
        formatted_context = "<industrial-memory>\n" + "\n".join(out_lines) + "\n</industrial-memory>"

    semantic_count = len([r for r in semantic if isinstance(r, dict) and "_error" not in r])
    recent_count = len([r for r in recent if isinstance(r, dict) and "_error" not in r])
    graph_count = len([r for r in graph if isinstance(r, dict) and "_error" not in r])

    return {
        "query": query,
        "mode": profile_name,
        "semantic": semantic,
        "recent": recent,
        "graph": graph,
        "tiers": tiers,
        "synthesis": synthesis_text,
        "heartbeat": heartbeat,
        "investigation_pass": investigation_pass,
        "formatted_context": formatted_context,
        "semantic_count": semantic_count,
        "recent_count": recent_count,
        "graph_count": graph_count,
        "semantic_confidence": _semantic_confidence_meta(semantic),
        "context_packet": {
            "token_budget": token_budget,
            "token_estimate": total_tokens,
            "deadline_sec": deadline_sec,
            "agent_id": agent_id,
            "channel": channel,
            "semantic_mode": semantic_mode,
            "semantic_cache_hit": semantic_cache_hit,
            "sections": section_meta,
            "timed_out_sources": timed_out_sources,
            "skipped_sources": skipped_sources,
            "errors": source_errors,
            "elapsed_ms": int((time.time() - start) * 1000),
            "investigation_pass": investigation_pass,
        },
    }


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
