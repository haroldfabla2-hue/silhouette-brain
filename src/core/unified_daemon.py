#!/usr/bin/env python3
"""
Silhouette Unified Daemon v1.0
================================
Un solo proceso PM2 que orquesta TODAS las tareas periódicas del Brain:

  Tarea                Intervalo   Descripción
  ──────────────────── ──────────  ─────────────────────────────────────
  session_sync         120 s       Sync JSONL → DB (ex global_memory_daemon)
  embedding_sync        300 s       Genera embeddings fastembed para msgs nuevos
  api_health           180 s       Vigila y reinicia la Brain API si cae
  curiosity              1 h       Detecta gaps + DESPACHA investigaciones
  dreamer                6 h       Consolida memoria (asociaciones hebbianas)
  janitor               12 h       Resuelve contradicciones en entidades
  evolution              6 h       Ciclo de auto-mejora del sistema

Ventajas sobre múltiples crons:
  - Un solo restart = todo vuelve en orden
  - Estado compartido (qué se ejecutó y cuándo)
  - Aislamiento de errores por tarea (una tarea rota no mata el daemon)
  - Curiosidad activa: los gaps generan tareas que los agentes ven en auto-recall
"""

import json
import os
import sys
import time
import signal
import logging
import traceback
import fcntl
import hashlib
import re
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass
from typing import Callable, List, Optional

# ── Paths ──────────────────────────────────────────────────────────────────
BRAIN_ROOT     = Path(os.getenv("BRAIN_ROOT", "/root/silhouette-brain"))
BRAIN_SRC_CORE = BRAIN_ROOT / "src" / "core"
BRAIN_SRC_COG  = BRAIN_ROOT / "src" / "cognitive_engines"
BRAIN_DATA     = Path(os.getenv("BRAIN_DATA_DIR", str(BRAIN_ROOT / "data")))
STATE_FILE     = BRAIN_DATA / "unified_daemon_state.json"
SESSION_OFFSETS_FILE = BRAIN_DATA / "session_offsets.json"
CURIOSITY_DISPATCH_FILE = BRAIN_DATA / "curiosity_dispatched_gaps.json"
LOCK_FILE      = BRAIN_DATA / "unified_daemon.lock"
LOG_FILE       = BRAIN_ROOT / "logs" / "silhouette_unified_daemon.log"
# Asegurar que el directorio de logs existe
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

# Asegurar paths disponibles
for p in [str(BRAIN_SRC_CORE), str(BRAIN_SRC_COG), str(BRAIN_ROOT / "src")]:
    if p not in sys.path:
        sys.path.insert(0, p)

from dotenv import load_dotenv
load_dotenv(str(BRAIN_ROOT / ".env"))

# ── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(str(LOG_FILE), encoding="utf-8"),
    ],
)
log = logging.getLogger("unified")


_proactive_runtime = None


def _get_proactive_runtime():
    """Lazy-load proactive runtime to keep startup resilient."""
    global _proactive_runtime
    if _proactive_runtime is not None:
        return _proactive_runtime
    try:
        from proactive_runtime import ProactiveRuntime

        _proactive_runtime = ProactiveRuntime(BRAIN_DATA, logger=log)
    except Exception as e:
        log.warning(f"[proactive] runtime no disponible: {e}")
        _proactive_runtime = False
    return _proactive_runtime


# ============================================================================
# Task dataclass
# ============================================================================

@dataclass
class Task:
    name:          str
    interval:      int          # segundos entre ejecuciones
    fn:            Callable
    enabled:       bool  = True
    last_run:      float = 0.0  # epoch timestamp
    run_count:     int   = 0
    err_count:     int   = 0
    in_subprocess: bool  = False   # aislar en proceso hijo para liberar RAM al terminar
    timeout:       int   = 7200    # segundos máximos para subprocess (2h por defecto)

    def due(self, now: float) -> bool:
        return self.enabled and (now - self.last_run) >= self.interval

    def run(self):
        import multiprocessing
        t0 = time.time()
        modo = " [subprocess]" if self.in_subprocess else ""
        log.info(f"[{self.name}] ▶ inicio{modo}")
        try:
            if self.in_subprocess:
                p = multiprocessing.Process(target=self.fn, name=f"sil-{self.name}", daemon=True)
                p.start()
                p.join(self.timeout)
                if p.is_alive():
                    log.warning(f"[{self.name}] Timeout ({self.timeout}s) — terminando proceso...")
                    p.terminate()
                    p.join(10)
                    if p.is_alive():
                        p.kill()
                    raise TimeoutError(f"Timeout tras {self.timeout}s")
                if p.exitcode not in (0, None):
                    raise RuntimeError(f"Subprocess terminó con código {p.exitcode}")
            else:
                self.fn()

            self.last_run  = time.time()
            self.run_count += 1
            log.info(f"[{self.name}] ✓ completado en {time.time()-t0:.1f}s")
        except Exception as e:
            self.err_count += 1
            log.error(f"[{self.name}] ✗ ERROR (intento #{self.err_count}): {e}")
            log.debug(traceback.format_exc())
            # Marcar last_run para no reintentar inmediatamente
            self.last_run = time.time()


# ============================================================================
# TAREA 0 — Heartbeat (estado del sistema, para auto-recall del agente)
# ============================================================================

# Referencia global al daemon para que task_heartbeat acceda a métricas de tareas
_daemon_ref = None

def task_heartbeat():
    """
    Escribe heartbeat_state.json con el estado real del sistema.
    Los agentes lo leen en auto-recall para saber qué está pasando, qué investigar,
    y qué tareas cognitivas están pendientes.
    """
    import sqlite3
    import pytz
    
    peru_tz = pytz.timezone("America/Lima")
    now_peru = datetime.now(peru_tz)
    
    state = {
        "timestamp":    datetime.now().isoformat(),
        "timestamp_peru": now_peru.isoformat(),
        "latido":       "ALIVE",
        "servicios":    {},
        "memoria":      {},
        "cognitivo":    {},
        "pendientes":   [],
        "proactive_signal": False,
        "proactive_reason": None,
        "energia":      1.0,
    }

    # ── Estado de servicios ────────────────────────────────────────────────
    try:
        import urllib.request
        urllib.request.urlopen("http://127.0.0.1:9876/api/status", timeout=4)
        state["servicios"]["brain_api"] = "OK"
    except Exception:
        state["servicios"]["brain_api"] = "DOWN"
        state["proactive_signal"] = True
        state["proactive_reason"] = "CRÍTICO: Brain API no responde"

    try:
        from neo4j import GraphDatabase
        drv = GraphDatabase.driver(
            os.getenv("NEO4J_URI", "bolt://localhost:17687"),
            auth=("neo4j", os.getenv("NEO4J_PASSWORD", "silhouette2035"))
        )
        drv.verify_connectivity()
        drv.close()
        state["servicios"]["neo4j"] = "OK"
    except Exception:
        state["servicios"]["neo4j"] = "DOWN"
        state["proactive_signal"] = True
        state["proactive_reason"] = "CRÍTICO: Neo4j (Long Memory) caído"

    # ── Ventanas de Standup (Proactividad Temporal) ────────────────────────
    # Standup Morning: 09:00 - 09:30 Perú
    # Standup Evening: 17:00 - 17:30 Perú
    current_time = now_peru.strftime("%H:%M")
    if "09:00" <= current_time <= "09:30":
        state["proactive_signal"] = True
        state["proactive_reason"] = "STANDUP: Morning Standup (9am Perú)"
    elif "17:00" <= current_time <= "17:30":
        state["proactive_signal"] = True
        state["proactive_reason"] = "STANDUP: Evening Standup (5pm Perú)"

    try:
        import redis as _redis
        r = _redis.Redis(host="localhost", port=6379)
        r.ping()
        state["servicios"]["redis"] = "OK"
    except Exception:
        state["servicios"]["redis"] = "DOWN"

    # ── Métricas de memoria ────────────────────────────────────────────────
    db = BRAIN_DATA / "memory_core.db"
    memory_db = BRAIN_DATA / "memory.db"
    if db.exists():
        try:
            conn = sqlite3.connect(str(db))
            total   = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
            con_emb = conn.execute("SELECT COUNT(*) FROM conversations WHERE embedding IS NOT NULL").fetchone()[0]
            recents = conn.execute(
                "SELECT speaker, message FROM conversations ORDER BY id DESC LIMIT 5"
            ).fetchall()
            conn.close()
            state["memoria"]["conversaciones"]  = total
            state["memoria"]["con_embedding"]   = con_emb
            state["memoria"]["cobertura_emb"]   = f"{con_emb/max(total,1)*100:.0f}%"
            state["memoria"]["recientes"]       = [
                {"quien": r[0], "texto": r[1][:100]} for r in recents
            ]
        except Exception as e:
            state["memoria"]["error"] = str(e)

    # ── Estado cognitivo (tareas del daemon) ───────────────────────────────
    if _daemon_ref is not None:
        tareas = {}
        pendientes = []
        for t in _daemon_ref.tasks:
            next_in = max(0, t.interval - (time.time() - t.last_run))
            tareas[t.name] = {
                "runs":    t.run_count,
                "errores": t.err_count,
                "next_in": f"{next_in/60:.0f}min",
            }
            if t.err_count > 0:
                pendientes.append(f"⚠ Tarea '{t.name}' tiene {t.err_count} errores — revisar logs")
        state["cognitivo"]["tareas"] = tareas
        state["pendientes"] = pendientes

    # ── Tareas cognitivas activas (investigaciones despachadas) ───────────
    cognitive_items = []
    try:
        working_file = BRAIN_DATA / "working.json"
        if working_file.exists():
            working = json.loads(working_file.read_text())
            cognitive = [
                item for item in (working if isinstance(working, list) else [])
                if isinstance(item, dict) and "cognitive_task" in str(item.get("tags", []))
            ]
            if cognitive:
                cognitive_items.extend(cognitive[:10])
    except Exception:
        pass

    # Fallback real: las tareas de curiosity viven en memory.db (SQLite).
    if not cognitive_items and memory_db.exists():
        try:
            conn = sqlite3.connect(str(memory_db))
            rows = conn.execute(
                """
                SELECT content, timestamp
                FROM memory_nodes
                WHERE tags LIKE '%cognitive_task%'
                  AND tags LIKE '%investigation%'
                ORDER BY timestamp DESC LIMIT 10
                """
            ).fetchall()
            conn.close()
            cognitive_items = [{"content": r[0], "timestamp": r[1]} for r in rows]
        except Exception:
            pass

    if cognitive_items:
        state["pendientes"] += [
            f"🔍 Investigar: {item.get('content','')[:80]}"
            for item in cognitive_items[:3]
        ]

    # ── Introspección cognitiva ────────────────────────────────────────────
    try:
        from introspection_engine import get_introspection_engine
        engine = get_introspection_engine()
        cycle  = engine.run_cycle()
        state["introspection"] = {
            "ciclo":       cycle["cycle"],
            "sugerencias": cycle["planning"].get("suggestions", [])[:3],
            "fase":        cycle["introspection"].get("phase"),
            "preguntas":   cycle["introspection"].get("questions", [])[:3],
        }
    except Exception:
        pass

    # ── Investigaciones cognitivas despachadas (DB) ────────────────────────
    state["investigaciones"] = []
    if db.exists():
        try:
            conn = sqlite3.connect(str(db))
            rows = conn.execute(
                """
                SELECT speaker, message, timestamp
                FROM conversations
                WHERE tags LIKE '%cognitive_task%'
                  AND tags LIKE '%investigation%'
                ORDER BY id DESC LIMIT 10
                """
            ).fetchall()
            conn.close()
            state["investigaciones"] = [
                {"quien": r[0], "tarea": r[1][:200], "ts": r[2]}
                for r in rows
            ]
        except Exception:
            state["investigaciones"] = []

    # Fallback: si memory_core no tiene registros etiquetados, usar memory.db.
    if not state["investigaciones"] and memory_db.exists():
        try:
            conn = sqlite3.connect(str(memory_db))
            rows = conn.execute(
                """
                SELECT content, timestamp
                FROM memory_nodes
                WHERE tags LIKE '%cognitive_task%'
                  AND tags LIKE '%investigation%'
                ORDER BY timestamp DESC LIMIT 10
                """
            ).fetchall()
            conn.close()
            state["investigaciones"] = [
                {
                    "quien": "curiosity",
                    "tarea": str(r[0])[:200],
                    "ts": datetime.utcfromtimestamp(float(r[1])).isoformat() + "Z",
                }
                for r in rows
            ]
        except Exception:
            pass

    # ── Energía del sistema (0.0-1.0) ─────────────────────────────────────
    api_ok   = state["servicios"].get("brain_api") == "OK"
    neo4j_ok = state["servicios"].get("neo4j")     == "OK"
    total_errs = sum(
        t.err_count for t in (_daemon_ref.tasks if _daemon_ref else [])
    )
    state["energia"] = round(
        (1.0 if api_ok else 0.5)
        * (1.0 if neo4j_ok else 0.8)
        * max(0.3, 1.0 - total_errs * 0.03),
        2
    )

    # ── Escribir archivos ──────────────────────────────────────────────────
    BRAIN_DATA.mkdir(parents=True, exist_ok=True)
    # 1. Brain data dir (para la API)
    with open(BRAIN_DATA / "heartbeat_state.json", "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    # 2. OpenClaw workspace (para que los agentes lo lean directamente)
    ws = Path("/root/.openclaw/workspace")
    if ws.exists():
        with open(ws / "heartbeat-state.json", "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)

    svcs = ", ".join(f"{k}={v}" for k, v in state["servicios"].items())
    log.info(
        f"[heartbeat] energia={state['energia']} | {svcs} | "
        f"mem={state['memoria'].get('conversaciones','?')} convs | "
        f"pendientes={len(state['pendientes'])}"
    )

    # Proactividad robusta: alertas útiles con límites y anti-injection.
    try:
        proactive = _get_proactive_runtime()
        if proactive:
            from proactive_runtime import ProactiveEvent

            critical_down = [
                svc for svc in ("brain_api", "neo4j")
                if state["servicios"].get(svc) != "OK"
            ]
            if critical_down:
                reason = ", ".join(critical_down)
                proactive.notify(
                    event=ProactiveEvent(
                        kind="service_alert",
                        title="Servicios críticos degradados",
                        body=f"Detecté caída en: {reason}. Energía del sistema: {state['energia']}.",
                        severity="critical",
                        dedupe_key=f"service:{reason}",
                        requester_id="system-daemon",
                        action_prompt=(
                            "Diagnostica servicio degradado del brain (api/neo4j), "
                            "resume impacto y pasos de recuperación en memoria."
                        ),
                    )
                )
            elif state.get("proactive_signal") and state.get("proactive_reason"):
                proactive.notify(
                    event=ProactiveEvent(
                        kind="heartbeat_signal",
                        title="Señal proactiva del heartbeat",
                        body=(
                            f"{state.get('proactive_reason')}. "
                            f"Energía={state['energia']}, pendientes={len(state['pendientes'])}."
                        ),
                        severity="medium",
                        dedupe_key=f"heartbeat:{state.get('proactive_reason')}",
                        requester_id="system-daemon",
                    )
                )

            # Reintentar acciones pendientes si el gateway estuvo inestable.
            replay = proactive.replay_pending_actions(max_items=3, max_age_hours=48)
            if replay.get("ok") and replay.get("processed", 0):
                log.info(
                    "[proactive] replay pendientes: "
                    f"processed={replay.get('processed')} sent={replay.get('sent')} "
                    f"remaining={replay.get('remaining')}"
                )
            elif not replay.get("ok"):
                log.debug(f"[proactive] replay error: {replay.get('error')}")
    except Exception as e:
        log.debug(f"[proactive] heartbeat notify error: {e}")


# ============================================================================
# TAREA 1 — Session Sync (de global_memory_daemon)
# ============================================================================

# Estado de la sesión (persistido en STATE_FILE["session_offsets"])
_SESSION_OFFSETS: dict = {}

# Session sync controls (robusto en producción, sin saturar servidor).
SESSION_SYNC_TIME_BUDGET_SEC = max(
    10.0, float(os.getenv("SESSION_SYNC_TIME_BUDGET_SEC", "45"))
)
SESSION_SYNC_MAX_NEW_LINES = max(
    200, int(os.getenv("SESSION_SYNC_MAX_NEW_LINES", "2500"))
)
SESSION_SYNC_FLUSH_EVERY = max(
    50, int(os.getenv("SESSION_SYNC_FLUSH_EVERY", "250"))
)
SESSION_SYNC_BACKEND = os.getenv(
    "SESSION_SYNC_BACKEND", "sqlite"
).strip().lower()
if SESSION_SYNC_BACKEND not in {"sqlite", "auto_memory"}:
    SESSION_SYNC_BACKEND = "sqlite"
SESSION_SYNC_BOOTSTRAP_MODE = os.getenv(
    "SESSION_SYNC_BOOTSTRAP_MODE", "tail"
).strip().lower()
if SESSION_SYNC_BOOTSTRAP_MODE not in {"tail", "backfill"}:
    SESSION_SYNC_BOOTSTRAP_MODE = "tail"


def _load_session_offsets_file() -> dict:
    if not SESSION_OFFSETS_FILE.exists():
        return {}
    try:
        raw = json.loads(SESSION_OFFSETS_FILE.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def _save_session_offsets_file(offsets: dict):
    try:
        BRAIN_DATA.mkdir(parents=True, exist_ok=True)
        tmp = SESSION_OFFSETS_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(offsets, indent=2), encoding="utf-8")
        tmp.replace(SESSION_OFFSETS_FILE)
    except Exception as e:
        log.debug(f"[session_sync] no se pudo guardar offsets: {e}")

OPENCLAW_WORKSPACE = Path("/root/.openclaw/workspace")
OPENCLAW_AGENTS    = Path("/root/.openclaw/agents")

def _get_all_jsonl_files():
    files = []
    if OPENCLAW_WORKSPACE.exists():
        for d in OPENCLAW_WORKSPACE.glob("memory_*"):
            if d.is_dir():
                for f in d.glob("*.jsonl"):
                    files.append((f, f"channel_{d.name.replace('memory_', '')}"))
    if OPENCLAW_AGENTS.exists():
        for agent_dir in OPENCLAW_AGENTS.iterdir():
            sd = agent_dir / "sessions"
            if sd.is_dir():
                for f in sd.glob("*.jsonl"):
                    if not f.name.endswith(".lock"):
                        files.append((f, f"agent_{agent_dir.name}"))
    multi = OPENCLAW_WORKSPACE / "multi-agent"
    if multi.exists():
        for f in multi.glob("*.jsonl"):
            files.append((f, "multi_agent"))
    return files

def _parse_jsonl_line(line: str) -> Optional[dict]:
    try:
        data = json.loads(line)
        if data.get("type") in ("session", "model_change", "tool_call", "tool_result"):
            return None
        msg = data.get("message", data)
        role = msg.get("role", "unknown")
        content = msg.get("content", [])
        if isinstance(content, list):
            text = " ".join(p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text")
        else:
            text = str(content)
        if role and text.strip():
            return {
                "role": role,
                "content": text[:1000],
                "source": data.get("channel", "openclaw"),
                "timestamp": (
                    data.get("timestamp")
                    or msg.get("timestamp")
                    or data.get("createdAt")
                    or data.get("time")
                ),
            }
    except Exception:
        pass
    return None


def _ensure_memory_core_conversations_schema(conn):
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            timestamp REAL NOT NULL,
            speaker TEXT NOT NULL,
            message TEXT NOT NULL,
            context TEXT,
            embedding BLOB,
            tags TEXT,
            dreamed INTEGER DEFAULT 0
        )
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_conv_time
        ON conversations(timestamp)
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_conv_speaker
        ON conversations(speaker)
        """
    )
    conn.commit()


def _open_session_sync_sqlite():
    import sqlite3

    db = BRAIN_DATA / "memory_core.db"
    conn = sqlite3.connect(str(db), timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    _ensure_memory_core_conversations_schema(conn)
    return conn


def _to_epoch_seconds(ts_value) -> float:
    if ts_value is None:
        return time.time()
    if isinstance(ts_value, (int, float)):
        return float(ts_value)
    if isinstance(ts_value, str):
        value = ts_value.strip()
        if not value:
            return time.time()
        try:
            return float(value)
        except Exception:
            pass
        try:
            iso = value.replace("Z", "+00:00")
            return datetime.fromisoformat(iso).timestamp()
        except Exception:
            return time.time()
    return time.time()


def _store_message_sqlite(conn, *, message_id: str, timestamp: float, speaker: str, message: str, context: str, tags: list) -> bool:
    try:
        conn.execute(
            """
            INSERT OR IGNORE INTO conversations
            (id, timestamp, speaker, message, context, embedding, tags)
            VALUES (?, ?, ?, ?, ?, NULL, ?)
            """,
            (
                message_id,
                timestamp,
                speaker or "unknown",
                message,
                context,
                json.dumps(tags or [], ensure_ascii=False),
            ),
        )
        return True
    except Exception:
        return False


def task_session_sync():
    """Sync JSONL de OpenClaw → memory_core.db (reemplaza global_memory_daemon)."""
    global _SESSION_OFFSETS
    start_ts = time.time()
    time_budget = SESSION_SYNC_TIME_BUDGET_SEC
    max_new_lines = SESSION_SYNC_MAX_NEW_LINES
    max_lines_per_file = max(200, max_new_lines // 2)
    bootstrap_mode = SESSION_SYNC_BOOTSTRAP_MODE
    backend = SESSION_SYNC_BACKEND
    mem = None
    sqlite_conn = None
    sqlite_pending = 0

    if backend == "auto_memory":
        try:
            from auto_memory import SilhouetteAutoMemory

            mem = SilhouetteAutoMemory()
        except Exception as e:
            log.warning(
                f"[session_sync] auto_memory no disponible: {e} — fallback SQLite"
            )
            backend = "sqlite"

    if backend == "sqlite":
        try:
            sqlite_conn = _open_session_sync_sqlite()
        except Exception as e:
            log.warning(f"[session_sync] SQLite no disponible: {e}")
            if mem is None:
                # Último intento para no perder integración de memoria.
                try:
                    from auto_memory import SilhouetteAutoMemory

                    mem = SilhouetteAutoMemory()
                    backend = "auto_memory"
                except Exception as e2:
                    log.warning(
                        f"[session_sync] sin backend de almacenamiento ({e2})"
                    )
                    return

    total_new_lines = 0
    total_ingested = 0
    parse_skipped = 0
    store_errors = 0
    files_touched = 0
    bootstrapped = 0

    def _time_exceeded() -> bool:
        return (time.time() - start_ts) >= time_budget

    files = []
    for file_path, source_tag in _get_all_jsonl_files():
        try:
            stat = file_path.stat()
            files.append((file_path, source_tag, stat.st_mtime, stat.st_size, stat.st_ino))
        except Exception:
            continue
    files.sort(key=lambda item: item[2])  # más antiguos primero

    for file_path, source_tag, _mtime, file_size, inode in files:
        if _time_exceeded() or total_new_lines >= max_new_lines:
            break

        key    = str(file_path)

        record = _SESSION_OFFSETS.get(key)
        if isinstance(record, dict):
            offset = int(record.get("pos", 0) or 0)
            prev_inode = int(record.get("inode", 0) or 0)
            if prev_inode and prev_inode != inode:
                # Rotación/reemplazo de archivo.
                offset = 0
        elif isinstance(record, (int, float)):
            # Compatibilidad con estado legado.
            offset = int(record)
        else:
            offset = 0

        if offset < 0:
            offset = 0
        if offset > file_size:
            offset = 0

        if not file_path.exists():
            continue

        if record is None and bootstrap_mode == "tail":
            # Raíz del cuello de botella detectado: replay completo tras restart.
            # En producción, cuando no hay offset previo, iniciamos al final.
            _SESSION_OFFSETS[key] = {"pos": file_size, "inode": inode}
            bootstrapped += 1
            continue

        if offset >= file_size:
            continue

        files_touched += 1
        lines_in_file = 0
        try:
            with open(file_path, "rb") as fh:
                fh.seek(offset)
                while True:
                    if _time_exceeded() or total_new_lines >= max_new_lines:
                        break
                    if lines_in_file >= max_lines_per_file:
                        break

                    raw = fh.readline()
                    if not raw:
                        break

                    offset = fh.tell()
                    _SESSION_OFFSETS[key] = {"pos": offset, "inode": inode}
                    total_new_lines += 1
                    lines_in_file += 1

                    line = raw.decode("utf-8", errors="replace").strip()
                    if not line:
                        continue

                    msg = _parse_jsonl_line(line)
                    if not msg:
                        parse_skipped += 1
                        continue

                    if backend == "auto_memory" and mem:
                        try:
                            mem.process_message(
                                speaker=msg["role"],
                                message=msg["content"],
                                tags=["unified-daemon", source_tag],
                            )
                            total_ingested += 1
                        except Exception as e:
                            store_errors += 1
                            if store_errors <= 3:
                                log.debug(f"[session_sync] store error ({file_path.name}): {e}")
                    elif sqlite_conn is not None:
                        msg_id = hashlib.sha1(
                            f"{key}:{inode}:{offset}".encode("utf-8")
                        ).hexdigest()[:16]
                        tags = ["unified-daemon", source_tag]
                        source_hint = str(msg.get("source", "")).strip()
                        if source_hint:
                            tags.append(f"source:{source_hint[:64]}")
                        ok = _store_message_sqlite(
                            sqlite_conn,
                            message_id=msg_id,
                            timestamp=_to_epoch_seconds(msg.get("timestamp")),
                            speaker=msg["role"],
                            message=msg["content"],
                            context=f"{source_tag}:{file_path.name}",
                            tags=tags,
                        )
                        if ok:
                            total_ingested += 1
                            sqlite_pending += 1
                        else:
                            store_errors += 1
                            if store_errors <= 3:
                                log.debug(
                                    f"[session_sync] sqlite store error ({file_path.name})"
                                )
                    else:
                        store_errors += 1

                    if total_new_lines % SESSION_SYNC_FLUSH_EVERY == 0:
                        if sqlite_conn is not None and sqlite_pending > 0:
                            sqlite_conn.commit()
                            sqlite_pending = 0
                        _save_session_offsets_file(_SESSION_OFFSETS)
        except Exception as e:
            log.warning(f"[session_sync] Error en {file_path.name}: {e}")

    if sqlite_conn is not None and sqlite_pending > 0:
        sqlite_conn.commit()

    _save_session_offsets_file(_SESSION_OFFSETS)

    elapsed = time.time() - start_ts
    if sqlite_conn is not None:
        try:
            sqlite_conn.close()
        except Exception:
            pass
    if total_new_lines or bootstrapped:
        log.info(
            f"[session_sync] líneas={total_new_lines}, integrados={total_ingested}, "
            f"parse_skip={parse_skipped}, store_err={store_errors}, "
            f"files={files_touched}/{len(files)}, bootstrapped={bootstrapped}, "
            f"elapsed={elapsed:.1f}s, mode={bootstrap_mode}, backend={backend}"
        )


# ============================================================================
# TAREA 2 — Embedding Sync (embeddings para msgs sin embedding)
# ============================================================================

EMBEDDING_SYNC_BATCH_LIMIT = max(
    20, int(os.getenv("EMBEDDING_SYNC_BATCH_LIMIT", "120"))
)
EMBEDDING_SYNC_TIME_BUDGET_SEC = max(
    30.0, float(os.getenv("EMBEDDING_SYNC_TIME_BUDGET_SEC", "150"))
)


def task_embedding_sync():
    """Genera embeddings fastembed para mensajes nuevos sin embedding."""
    started = time.time()
    deadline = started + EMBEDDING_SYNC_TIME_BUDGET_SEC
    # 1. Procesar memory_core.db (conversations)
    _sync_db_embeddings(
        BRAIN_DATA / "memory_core.db",
        "conversations",
        "message",
        "embedding",
        limit=EMBEDDING_SYNC_BATCH_LIMIT,
        deadline=deadline,
    )
    
    # 2. Procesar memory.db (memory_nodes) - Para items guardados vía API/Tiers
    _sync_db_embeddings(
        BRAIN_DATA / "memory.db",
        "memory_nodes",
        "content",
        "embedding",
        limit=EMBEDDING_SYNC_BATCH_LIMIT,
        deadline=deadline,
    )


def _sync_db_embeddings(db_path, table, text_col, emb_col, limit: int = 120, deadline: Optional[float] = None):
    """Helper para sincronizar embeddings en una tabla específica."""
    import sqlite3
    import numpy as np
    import time

    if deadline is not None and time.time() >= deadline:
        return

    if not db_path.exists():
        return

    try:
        from local_embeddings import get_embedding_batch
    except ImportError:
        return

    conn = sqlite3.connect(str(db_path))
    expected_bytes = 384 * 4
    # Mensajes sin embedding o con dimensión incorrecta (stale)
    rows = conn.execute(
        f"SELECT id, {text_col} FROM {table} "
        f"WHERE {emb_col} IS NULL OR length({emb_col}) != ? LIMIT ?",
        (expected_bytes, int(max(1, limit))),
    ).fetchall()

    if not rows:
        conn.close()
        return

    ids   = [r[0] for r in rows]
    texts = [r[1][:512] for r in rows]

    try:
        vecs = get_embedding_batch(texts)
        updates = [
            (np.array(v, dtype=np.float32).tobytes(), id_)
            for v, id_ in zip(vecs, ids)
            if v and len(v) == 384
        ]
        if updates:
            conn.executemany(f"UPDATE {table} SET {emb_col}=? WHERE id=?", updates)
            conn.commit()
            log.info(
                f"[embedding_sync] {len(updates)} embeddings generados/normalizados en {db_path.name}:{table}"
            )
    except Exception as e:
        log.warning(f"[embedding_sync] Error en {db_path.name}: {e}")
    finally:
        conn.close()


# ============================================================================
# TAREA 3 — API Health Check
# ============================================================================

def task_api_health():
    """Vigila la Brain API. La reinicia si no responde Y el puerto está libre.

    Verificar el puerto antes de spawn evita lanzar procesos duplicados cuando
    la API está arrancando lentamente o cuando PM2 ya la está reiniciando.
    """
    import subprocess
    import socket
    import requests as req

    try:
        r = req.get("http://127.0.0.1:9876/api/status", timeout=5)
        if r.status_code == 200:
            return  # Todo bien
    except Exception:
        pass

    # Verificar si el puerto ya está ocupado (API iniciando o proceso duplicado)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        port_in_use = s.connect_ex(('127.0.0.1', 9876)) == 0

    if port_in_use:
        log.info("[api_health] Puerto 9876 ocupado — API probablemente iniciando, sin acción")
        return

    log.warning("[api_health] Brain API no responde y puerto libre — reiniciando...")
    api_script = BRAIN_ROOT / "src" / "api" / "enhanced_memory_api.py"
    if api_script.exists():
        subprocess.Popen(
            [sys.executable, str(api_script)],
            env={**os.environ, "BRAIN_SRC_DIR": str(BRAIN_ROOT / "src" / "core")},
            stdout=open(BRAIN_ROOT / "logs" / "memory_api.log", "a"),
            stderr=subprocess.STDOUT,
        )
        time.sleep(3)
        log.info("[api_health] Brain API reiniciada")


# ============================================================================
# TAREA 4 — Curiosity (detección + DESPACHO activo de investigaciones)
# ============================================================================

# Control de gaps ya despachados (para no repetir en la misma sesión)
_dispatched_gaps: dict = {}   # entity → epoch timestamp del último despacho
GAP_RENOTIFY_HOURS = 24       # No re-despachar el mismo gap en 24h
GAP_URGENCY_THRESHOLD = 0.5   # discovery_potential mínimo para despachar
GAP_NOTIFY_THRESHOLD = 0.75   # mínimo para notificación proactiva al humano


def _normalize_gap_key(entity: str) -> str:
    raw = str(entity or "").strip().lower()
    if not raw:
        return ""
    # Canonicalizar para dedupe estable: "N8N ", "n8n.", "n8n-" -> "n8n"
    raw = re.sub(r"[^a-z0-9]+", " ", raw)
    raw = re.sub(r"\s+", " ", raw).strip()
    return raw


def _entity_tag_slug(entity: str) -> str:
    key = _normalize_gap_key(entity)
    return key.replace(" ", "_") if key else ""


def _merge_dispatched_gaps(dst: dict, src: dict) -> dict:
    out = dict(dst or {})
    for raw_key, raw_ts in (src or {}).items():
        key = _normalize_gap_key(raw_key)
        if not key:
            continue
        try:
            ts = float(raw_ts)
        except Exception:
            continue
        if ts > float(out.get(key, 0) or 0):
            out[key] = ts
    return out


def _prune_dispatched_gaps(gaps: dict, now_ts: float = None) -> dict:
    now_ts = float(now_ts or time.time())
    # Mantener historial acotado: 14 días de TTL técnico para evitar crecimiento infinito.
    keep_after = now_ts - (14 * 86400)
    out = {}
    for raw_key, raw_ts in (gaps or {}).items():
        key = _normalize_gap_key(raw_key)
        if not key:
            continue
        try:
            ts = float(raw_ts)
        except Exception:
            continue
        if ts >= keep_after:
            out[key] = ts
    return out


def _load_dispatched_gaps_file() -> dict:
    if not CURIOSITY_DISPATCH_FILE.exists():
        return {}
    try:
        raw = json.loads(CURIOSITY_DISPATCH_FILE.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return {}
        return _prune_dispatched_gaps(raw)
    except Exception:
        return {}


def _save_dispatched_gaps_file(gaps: dict):
    try:
        BRAIN_DATA.mkdir(parents=True, exist_ok=True)
        payload = _prune_dispatched_gaps(gaps)
        tmp = CURIOSITY_DISPATCH_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(CURIOSITY_DISPATCH_FILE)
    except Exception as e:
        log.debug(f"[curiosity] no se pudo guardar dedupe de gaps: {e}")


def task_curiosity():
    """
    Ciclo de curiosidad activo:
    1. Detecta gaps de información en la DB de entidades
    2. Encuentra conexiones novedosas entre entidades
    3. DESPACHA tareas de investigación en memoria (los agentes las ven en auto-recall)
    4. Registra el hallazgo en memoria para análisis posterior
    """
    now = time.time()

    # Importar módulos cognitivos
    try:
        from advanced_discovery import CuriosityDiscovery, MemoryAssociation
        from silhouette_memory import SilhouetteMemory
    except ImportError as e:
        log.warning(f"[curiosity] Módulos no disponibles: {e}")
        return

    # Assembler opcional para decisiones más informadas
    context_assembler = None
    try:
        from reasoning_engine import assemble_context_packet as _assemble_context_packet
        context_assembler = _assemble_context_packet
    except Exception:
        context_assembler = None

    global _dispatched_gaps
    _dispatched_gaps = _merge_dispatched_gaps(
        _dispatched_gaps,
        _load_dispatched_gaps_file(),
    )
    _dispatched_gaps = _prune_dispatched_gaps(_dispatched_gaps, now)

    memory = SilhouetteMemory()
    curiosity = CuriosityDiscovery(memory)

    # ── Detectar gaps ──────────────────────────────────────────────────────
    try:
        gaps = curiosity.find_information_gaps()
    except Exception as e:
        log.warning(f"[curiosity] find_information_gaps error: {e}")
        gaps = []

    # Priorizar pocos gaps de alto valor para no saturar recursos
    ranked_gaps = sorted(
        [g for g in gaps if isinstance(g, dict)],
        key=lambda g: float(g.get("discovery_potential", 0.0)),
        reverse=True,
    )[:8]
    dispatched_gaps = []

    dispatched = 0
    for gap in ranked_gaps:
        entity   = gap.get("entity", "")
        potential = gap.get("discovery_potential", 0.0)

        if not entity or potential < GAP_URGENCY_THRESHOLD:
            continue

        # ¿Ya despachado recientemente?
        entity_key = _normalize_gap_key(entity)
        last_dispatch = float(_dispatched_gaps.get(entity_key, 0) or 0)
        if now - last_dispatch < GAP_RENOTIFY_HOURS * 3600:
            continue

        # ── Validación contextual opcional (motor de contexto) ─────────────
        context_confidence = 0.0
        if context_assembler is not None:
            try:
                pkt = context_assembler(
                    query=entity,
                    mode="discovery",
                    token_budget=900,
                    sem_limit=4,
                    rec_limit=2,
                    hours=48,
                    min_score=0.10,
                    include_graph=True,
                    include_tiers=True,
                    synthesize=False,
                    filter_heartbeats=True,
                    include_heartbeat=True,
                    agent_id="daemon-curiosity",
                    channel="internal",
                )
                sem_count = int(pkt.get("semantic_count", 0))
                rec_count = int(pkt.get("recent_count", 0))
                graph_count = int(pkt.get("graph_count", 0))
                context_confidence = min(
                    1.0,
                    sem_count * 0.15 + rec_count * 0.07 + graph_count * 0.08,
                )
            except Exception as e:
                log.debug(f"[curiosity] context assembler error para '{entity}': {e}")

        # Si hay muy poco contexto y el potencial no es extremo, difiere despacho
        gap["_context_confidence"] = context_confidence
        if context_confidence < 0.12 and potential < 0.80:
            continue

        # ── DESPACHAR como tarea cognitiva en memoria ──────────────────────
        urgency_label = "ALTA" if potential >= 0.8 else "MEDIA"
        task_text = (
            f"[TAREA COGNITIVA — INVESTIGAR]\n"
            f"Entidad: {entity}\n"
            f"Urgencia: {urgency_label} ({potential:.0%} potencial de descubrimiento)\n"
            f"Confianza contextual: {context_confidence:.0%}\n"
            f"Acción: Busca información actualizada sobre '{entity}', "
            f"reporta el estado actual y guarda los hallazgos en memoria."
        )
        try:
            entity_tag = _entity_tag_slug(entity)
            tags = ["cognitive_task", "investigation", "curiosity"]
            if entity_tag:
                tags.append(entity_tag)
            memory.add(
                task_text,
                importance=min(0.7 + potential * 0.3, 0.98),
                tags=tags,
                tier="WORKING",
            )
            _dispatched_gaps[entity_key] = now
            dispatched += 1
            dispatched_gaps.append(
                {
                    "entity": entity,
                    "entity_key": entity_key,
                    "potential": float(potential),
                    "context_confidence": float(context_confidence),
                    "urgency": urgency_label,
                }
            )
            log.info(f"[curiosity] Gap despachado: '{entity}' (urgencia {urgency_label})")
        except Exception as e:
            log.warning(f"[curiosity] Error despachando gap '{entity}': {e}")

    _dispatched_gaps = _prune_dispatched_gaps(_dispatched_gaps, now)
    _save_dispatched_gaps_file(_dispatched_gaps)

    # ── Conexiones novedosas ───────────────────────────────────────────────
    novel_connections = []
    try:
        from memory_core_embeddings import get_memory_core
        core     = get_memory_core()
        entities = core.get_entities()
        ma       = MemoryAssociation()
        entity_names = [e["name"] for e in entities[:20]]
        novel_connections = ma.find_novel_connections(entity_names)
    except Exception as e:
        log.debug(f"[curiosity] novel_connections error: {e}")

    # ── Guardar resumen del ciclo ──────────────────────────────────────────
    summary = {
        "type": "curiosity_cycle",
        "timestamp": datetime.now().isoformat(),
        "gaps_found": len(gaps),
        "gaps_ranked": len(ranked_gaps),
        "gaps_dispatched": dispatched,
        "novel_connections": len(novel_connections),
    }
    try:
        memory.add(
            json.dumps(summary),
            tags=["curiosity", "cycle_log"],
            importance=0.3,
        )
    except Exception:
        pass

    memory.close()
    log.info(
        f"[curiosity] {len(gaps)} gaps ({len(ranked_gaps)} priorizados), "
        f"{dispatched} despachados, {len(novel_connections)} conexiones novedosas"
    )

    # Señales proactivas controladas (sin spam, con dedupe/rate-limit).
    try:
        proactive = _get_proactive_runtime()
        if proactive:
            from proactive_runtime import ProactiveEvent

            # Notificar solo gaps realmente despachados y de relevancia alta.
            top_dispatched = dispatched_gaps[0] if dispatched_gaps else None
            if top_dispatched and float(top_dispatched.get("potential", 0.0)) >= GAP_NOTIFY_THRESHOLD:
                entity = str(top_dispatched.get("entity", "")).strip()
                potential = float(top_dispatched.get("potential", 0.0))
                context_conf = float(top_dispatched.get("context_confidence", 0.0))
                entity_key = str(top_dispatched.get("entity_key", "")).strip() or _normalize_gap_key(entity)
                if entity:
                    severity = "high" if potential >= 0.85 else "medium"
                    proactive.notify(
                        event=ProactiveEvent(
                            kind="curiosity_gap",
                            title=f"Curiosity abrió investigación sobre '{entity}'",
                            body=(
                                f"Ya quedó en la cola cognitiva de Silhouette "
                                f"(potencial {potential:.0%}, contexto {context_conf:.0%})."
                            ),
                            severity=severity,
                            dedupe_key=f"gap:{entity_key}",
                            requester_id="system-daemon",
                            action_prompt=(
                                f"Prioriza una investigación acotada de '{entity}' y guarda "
                                "hallazgos accionables en memoria de trabajo."
                                if potential >= 0.88
                                else None
                            ),
                        )
                    )
            elif novel_connections:
                first = novel_connections[0]
                left = str(first.get("from", "")).strip()
                right = str(first.get("to", "")).strip()
                if left and right:
                    proactive.notify(
                        event=ProactiveEvent(
                            kind="curiosity_novel",
                            title="Curiosity encontró conexión novedosa",
                            body=f"Conexión sugerida: {left} ↔ {right}.",
                            severity="medium",
                            dedupe_key=f"novel:{left.lower()}:{right.lower()}",
                            requester_id="system-daemon",
                        )
                    )
    except Exception as e:
        log.debug(f"[proactive] curiosity notify error: {e}")


# ============================================================================
# TAREA 5 — Dreamer (consolidación de memoria)
# ============================================================================

def task_dreamer():
    """Consolidación cognitiva: asociaciones hebbianas, poda sináptica, atajos."""
    result = None
    try:
        from cognitive_engines.run_dreamer import run_dream_cycle
        result = run_dream_cycle()
    except ImportError:
        # Intentar import alternativo
        try:
            spec_path = BRAIN_SRC_COG / "run_dreamer.py"
            import importlib.util
            spec = importlib.util.spec_from_file_location("run_dreamer", spec_path)
            mod  = importlib.util.load_from_spec(spec)
            spec.loader.exec_module(mod)
            result = mod.run_dream_cycle()
        except Exception as e:
            log.warning(f"[dreamer] No disponible: {e}")

    if isinstance(result, dict):
        try:
            proactive = _get_proactive_runtime()
            if proactive:
                from proactive_runtime import ProactiveEvent

                consolidated = int(result.get("consolidated", 0))
                shortcuts = int(result.get("shortcuts", 0))
                associations = int(result.get("associations", 0))
                if consolidated >= 5 or shortcuts >= 8:
                    proactive.notify(
                        event=ProactiveEvent(
                            kind="dreamer_cycle",
                            title="Dreamer consolidó memoria",
                            body=(
                                f"Consolidado={consolidated}, shortcuts={shortcuts}, "
                                f"asociaciones={associations}."
                            ),
                            severity="medium",
                            dedupe_key=f"dreamer:{datetime.utcnow().date().isoformat()}",
                            requester_id="system-daemon",
                        )
                    )
        except Exception as e:
            log.debug(f"[proactive] dreamer notify error: {e}")


# ============================================================================
# TAREA 6 — Janitor (resolución de contradicciones)
# ============================================================================

def task_janitor():
    """Limpia contradicciones en entidades por voto mayoritario."""
    try:
        from cognitive_engines.run_janitor import run_janitor
        run_janitor()
    except ImportError:
        try:
            spec_path = BRAIN_SRC_COG / "run_janitor.py"
            import importlib.util
            spec = importlib.util.spec_from_file_location("run_janitor", spec_path)
            mod  = importlib.util.load_from_spec(spec)
            spec.loader.exec_module(mod)
            mod.run_janitor()
        except Exception as e:
            log.warning(f"[janitor] No disponible: {e}")


# ============================================================================
# TAREA 7 — Evolution Cycle (auto-mejora)
# ============================================================================

def task_evolution():
    """Ciclo de auto-mejora: analiza métricas, detecta issues, propone mejoras."""
    try:
        from cognitive_engines.evolution_cycle import run_evolution_cycle
        run_evolution_cycle()
    except ImportError:
        try:
            spec_path = BRAIN_SRC_COG / "evolution_cycle.py"
            import importlib.util
            spec = importlib.util.spec_from_file_location("evolution_cycle", spec_path)
            mod  = importlib.util.load_from_spec(spec)
            spec.loader.exec_module(mod)
            mod.run_evolution_cycle()
        except Exception as e:
            log.warning(f"[evolution] No disponible: {e}")


# ============================================================================
# DAEMON PRINCIPAL
# ============================================================================

class UnifiedDaemon:
    """Orquestador de tareas periódicas de Silhouette Brain."""

    TICK_INTERVAL = 10   # segundos entre checks del scheduler

    def __init__(self):
        global _daemon_ref
        self.running = True
        self._lock_handle = None
        self.tasks: List[Task] = [
            # Tareas ligeras — in-process, estado compartido
            Task("heartbeat",      interval=600,   fn=task_heartbeat),   # 10min
            Task("api_health",     interval=180,   fn=task_api_health),
            # Tareas que cargan modelos o procesan mucha data — subprocess para liberar RAM
            Task("session_sync",   interval=120,   fn=task_session_sync,   in_subprocess=True, timeout=180),
            Task("embedding_sync", interval=300,   fn=task_embedding_sync, in_subprocess=True, timeout=900),
            Task("curiosity",      interval=3600,  fn=task_curiosity,      in_subprocess=True),
            # Tareas pesadas — subprocess: RAM liberada automáticamente al terminar
            Task("dreamer",   interval=21600, fn=task_dreamer,   in_subprocess=True, timeout=7200),
            Task("janitor",   interval=43200, fn=task_janitor,   in_subprocess=True, timeout=3600),
            Task("evolution", interval=21600, fn=task_evolution, in_subprocess=True, timeout=7200),
        ]
        _daemon_ref = self  # Heartbeat puede acceder a métricas de tareas
        self._acquire_single_instance_lock()
        self._load_state()
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT,  self._handle_signal)

    # ── State persistence ──────────────────────────────────────────────────

    def _load_state(self):
        global _SESSION_OFFSETS, _dispatched_gaps
        if STATE_FILE.exists():
            try:
                with open(STATE_FILE) as f:
                    state = json.load(f)
                _SESSION_OFFSETS = state.get("session_offsets", {})
                _dispatched_gaps  = state.get("dispatched_gaps", {})
                last_runs = state.get("task_last_run", {})
                for task in self.tasks:
                    if task.name in last_runs:
                        task.last_run = last_runs[task.name]
                disk_offsets = _load_session_offsets_file()
                if disk_offsets:
                    if not isinstance(_SESSION_OFFSETS, dict):
                        _SESSION_OFFSETS = {}
                    _SESSION_OFFSETS.update(disk_offsets)
                disk_dispatched = _load_dispatched_gaps_file()
                if disk_dispatched:
                    _dispatched_gaps = _merge_dispatched_gaps(_dispatched_gaps, disk_dispatched)
                _dispatched_gaps = _prune_dispatched_gaps(_dispatched_gaps)
                log.info(f"Estado cargado ({len(_SESSION_OFFSETS)} archivos tracked)")
            except Exception as e:
                log.warning(f"Error cargando estado: {e}")
        else:
            # Fallback para reinicios donde solo existe offsets sidecar.
            disk_offsets = _load_session_offsets_file()
            if disk_offsets:
                _SESSION_OFFSETS = disk_offsets
                log.info(f"Offsets cargados desde sidecar ({len(_SESSION_OFFSETS)} archivos)")

    def _save_state(self):
        global _SESSION_OFFSETS, _dispatched_gaps
        try:
            BRAIN_DATA.mkdir(parents=True, exist_ok=True)
            # session_sync corre en subprocess; sus offsets viven en sidecar.
            # Antes de persistir estado del daemon, fusionamos sidecar -> memoria
            # para evitar sobrescribir progreso con dict vacío del proceso padre.
            disk_offsets = _load_session_offsets_file()
            if disk_offsets:
                if not isinstance(_SESSION_OFFSETS, dict):
                    _SESSION_OFFSETS = {}
                _SESSION_OFFSETS.update(disk_offsets)
            disk_dispatched = _load_dispatched_gaps_file()
            if disk_dispatched:
                _dispatched_gaps = _merge_dispatched_gaps(_dispatched_gaps, disk_dispatched)
            _dispatched_gaps = _prune_dispatched_gaps(_dispatched_gaps)
            state = {
                "session_offsets": _SESSION_OFFSETS,
                "dispatched_gaps":  _dispatched_gaps,
                "task_last_run":   {t.name: t.last_run for t in self.tasks},
                "task_run_count":  {t.name: t.run_count for t in self.tasks},
                "task_err_count":  {t.name: t.err_count for t in self.tasks},
                "updated_at":      datetime.now().isoformat(),
            }
            with open(STATE_FILE, "w") as f:
                json.dump(state, f, indent=2)
            _save_session_offsets_file(_SESSION_OFFSETS)
            _save_dispatched_gaps_file(_dispatched_gaps)
        except Exception as e:
            log.warning(f"Error guardando estado: {e}")

    # ── Signal handling ────────────────────────────────────────────────────

    def _handle_signal(self, signum, frame):
        log.info(f"Señal {signum} recibida — cerrando ordenadamente...")
        self.running = False

    def _acquire_single_instance_lock(self):
        """
        Prevent concurrent master daemons.
        Child subprocesses use fork and share this lock descriptor, so they do
        not create lock contention.
        """
        BRAIN_DATA.mkdir(parents=True, exist_ok=True)
        self._lock_handle = open(LOCK_FILE, "a+", encoding="utf-8")
        try:
            fcntl.flock(self._lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("Ya existe una instancia activa de unified_daemon")
        self._lock_handle.write(f"{os.getpid()}\n")
        self._lock_handle.flush()

    # ── Main loop ──────────────────────────────────────────────────────────

    def run(self):
        log.info("=" * 60)
        log.info("  Silhouette Unified Daemon v1.0")
        log.info(f"  Tareas: {', '.join(t.name for t in self.tasks)}")
        log.info("=" * 60)

        # Forzar heartbeat, session_sync y api_health en el primer tick
        now = time.time()
        for task in self.tasks:
            if task.name in ("heartbeat", "session_sync", "api_health"):
                task.last_run = 0  # Correr inmediatamente

        while self.running:
            now = time.time()
            for task in self.tasks:
                if task.due(now):
                    task.run()
                    self._save_state()

            # Status periódico cada 5 minutos
            if int(now) % 300 < self.TICK_INTERVAL:
                self._log_status()

            time.sleep(self.TICK_INTERVAL)

        log.info("Daemon detenido.")

    def _log_status(self):
        lines = ["[status]"]
        now   = time.time()
        for t in self.tasks:
            next_in = max(0, t.interval - (now - t.last_run))
            lines.append(
                f"  {t.name:<18} runs={t.run_count:3d}  errs={t.err_count}  "
                f"next_in={next_in/60:.0f}min"
            )
        log.info("\n".join(lines))


# ============================================================================
# ENTRYPOINT
# ============================================================================

if __name__ == "__main__":
    daemon = UnifiedDaemon()
    daemon.run()
