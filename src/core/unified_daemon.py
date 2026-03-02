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
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Callable, List, Optional

# ── Paths ──────────────────────────────────────────────────────────────────
BRAIN_ROOT     = Path(os.getenv("BRAIN_ROOT", "/home/ubuntu/.openclaw/workspace/silhouette-brain"))
BRAIN_SRC_CORE = BRAIN_ROOT / "src" / "core"
BRAIN_SRC_COG  = BRAIN_ROOT / "src" / "cognitive_engines"
BRAIN_DATA     = Path(os.getenv("BRAIN_DATA_DIR", str(BRAIN_ROOT / "data")))
STATE_FILE     = BRAIN_DATA / "unified_daemon_state.json"
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
    state = {
        "timestamp":    datetime.now().isoformat(),
        "latido":       "ALIVE",
        "servicios":    {},
        "memoria":      {},
        "cognitivo":    {},
        "pendientes":   [],
        "energia":      1.0,
    }

    # ── Estado de servicios ────────────────────────────────────────────────
    try:
        import urllib.request
        urllib.request.urlopen("http://127.0.0.1:9876/api/status", timeout=4)
        state["servicios"]["brain_api"] = "OK"
    except Exception:
        state["servicios"]["brain_api"] = "DOWN"

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

    try:
        import redis as _redis
        r = _redis.Redis(host="localhost", port=6379)
        r.ping()
        state["servicios"]["redis"] = "OK"
    except Exception:
        state["servicios"]["redis"] = "DOWN"

    # ── Métricas de memoria ────────────────────────────────────────────────
    db = BRAIN_DATA / "memory_core.db"
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
    try:
        working_file = BRAIN_DATA / "working.json"
        if working_file.exists():
            working = json.loads(working_file.read_text())
            cognitive = [
                item for item in (working if isinstance(working, list) else [])
                if isinstance(item, dict) and "cognitive_task" in str(item.get("tags", []))
            ]
            if cognitive:
                state["pendientes"] += [
                    f"🔍 Investigar: {item.get('content','')[:80]}"
                    for item in cognitive[:3]
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


# ============================================================================
# TAREA 1 — Session Sync (de global_memory_daemon)
# ============================================================================

# Estado de la sesión (persistido en STATE_FILE["session_offsets"])
_SESSION_OFFSETS: dict = {}

OPENCLAW_WORKSPACE = Path("/home/ubuntu/.openclaw/workspace")
OPENCLAW_AGENTS    = Path("/home/ubuntu/.openclaw/agents")

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
            return {"role": role, "content": text[:1000], "source": data.get("channel", "openclaw")}
    except Exception:
        pass
    return None

def task_session_sync():
    """Sync JSONL de OpenClaw → memory_core.db (reemplaza global_memory_daemon)."""
    global _SESSION_OFFSETS
    try:
        from auto_memory import SilhouetteAutoMemory
        mem = SilhouetteAutoMemory()
    except Exception as e:
        log.warning(f"[session_sync] SilhouetteAutoMemory no disponible: {e} — usando fallback SQLite")
        mem = None

    total = 0
    for file_path, source_tag in _get_all_jsonl_files():
        key    = str(file_path)
        offset = _SESSION_OFFSETS.get(key, 0)
        if not file_path.exists():
            continue
        try:
            lines = file_path.read_text(encoding="utf-8").split("\n")
            for i, line in enumerate(lines):
                if i < offset or not line.strip():
                    continue
                msg = _parse_jsonl_line(line)
                if msg and mem:
                    try:
                        mem.process_message(
                            speaker=msg["role"],
                            message=msg["content"],
                            tags=["unified-daemon", source_tag],
                        )
                        total += 1
                    except Exception:
                        pass
            _SESSION_OFFSETS[key] = len(lines)
        except Exception as e:
            log.warning(f"[session_sync] Error en {file_path.name}: {e}")

    if total:
        log.info(f"[session_sync] {total} mensajes nuevos integrados")


# ============================================================================
# TAREA 2 — Embedding Sync (embeddings para msgs sin embedding)
# ============================================================================

def task_embedding_sync():
    """Genera embeddings fastembed para mensajes nuevos sin embedding."""
    import sqlite3
    import numpy as np

    # 1. Procesar memory_core.db (conversations)
    _sync_db_embeddings(BRAIN_DATA / "memory_core.db", "conversations", "message", "embedding")
    
    # 2. Procesar memory.db (memory_nodes) - Para items guardados vía API/Tiers
    _sync_db_embeddings(BRAIN_DATA / "memory.db", "memory_nodes", "content", "embedding")

def _sync_db_embeddings(db_path, table, text_col, emb_col):
    """Helper para sincronizar embeddings en una tabla específica."""
    import sqlite3
    import numpy as np
    import time

    if not db_path.exists():
        return

    try:
        from local_embeddings import get_embedding_batch
    except ImportError:
        return

    conn = sqlite3.connect(str(db_path))
    # Mensajes sin embedding
    rows = conn.execute(
        f"SELECT id, {text_col} FROM {table} WHERE {emb_col} IS NULL LIMIT 200"
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
            log.info(f"[embedding_sync] {len(updates)} embeddings generados en {db_path.name}:{table}")
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

    memory = SilhouetteMemory()
    curiosity = CuriosityDiscovery(memory)

    # ── Detectar gaps ──────────────────────────────────────────────────────
    try:
        gaps = curiosity.find_information_gaps()
    except Exception as e:
        log.warning(f"[curiosity] find_information_gaps error: {e}")
        gaps = []

    dispatched = 0
    for gap in gaps:
        entity   = gap.get("entity", "")
        potential = gap.get("discovery_potential", 0.0)

        if not entity or potential < GAP_URGENCY_THRESHOLD:
            continue

        # ¿Ya despachado recientemente?
        last_dispatch = _dispatched_gaps.get(entity, 0)
        if now - last_dispatch < GAP_RENOTIFY_HOURS * 3600:
            continue

        # ── DESPACHAR como tarea cognitiva en memoria ──────────────────────
        urgency_label = "ALTA" if potential >= 0.8 else "MEDIA"
        task_text = (
            f"[TAREA COGNITIVA — INVESTIGAR]\n"
            f"Entidad: {entity}\n"
            f"Urgencia: {urgency_label} ({potential:.0%} potencial de descubrimiento)\n"
            f"Acción: Busca información actualizada sobre '{entity}', "
            f"reporta el estado actual y guarda los hallazgos en memoria."
        )
        try:
            memory.add(
                task_text,
                importance=min(0.7 + potential * 0.3, 0.98),
                tags=["cognitive_task", "investigation", "curiosity", entity.lower().replace(" ", "_")],
                tier="WORKING",
            )
            _dispatched_gaps[entity] = now
            dispatched += 1
            log.info(f"[curiosity] Gap despachado: '{entity}' (urgencia {urgency_label})")
        except Exception as e:
            log.warning(f"[curiosity] Error despachando gap '{entity}': {e}")

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
    log.info(f"[curiosity] {len(gaps)} gaps, {dispatched} despachados, {len(novel_connections)} conexiones novedosas")


# ============================================================================
# TAREA 5 — Dreamer (consolidación de memoria)
# ============================================================================

def task_dreamer():
    """Consolidación cognitiva: asociaciones hebbianas, poda sináptica, atajos."""
    try:
        from cognitive_engines.run_dreamer import run_dream_cycle
        run_dream_cycle()
    except ImportError:
        # Intentar import alternativo
        try:
            spec_path = BRAIN_SRC_COG / "run_dreamer.py"
            import importlib.util
            spec = importlib.util.spec_from_file_location("run_dreamer", spec_path)
            mod  = importlib.util.load_from_spec(spec)
            spec.loader.exec_module(mod)
            mod.run_dream_cycle()
        except Exception as e:
            log.warning(f"[dreamer] No disponible: {e}")


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
        self.tasks: List[Task] = [
            # Tareas ligeras — in-process, estado compartido
            Task("heartbeat",      interval=600,   fn=task_heartbeat),   # 10min
            Task("session_sync",   interval=120,   fn=task_session_sync),
            Task("embedding_sync", interval=300,   fn=task_embedding_sync),
            Task("api_health",     interval=180,   fn=task_api_health),
            Task("curiosity",      interval=3600,  fn=task_curiosity),   # liviano tras fix A
            # Tareas pesadas — subprocess: RAM liberada automáticamente al terminar
            Task("dreamer",   interval=21600, fn=task_dreamer,   in_subprocess=True, timeout=7200),
            Task("janitor",   interval=43200, fn=task_janitor,   in_subprocess=True, timeout=3600),
            Task("evolution", interval=21600, fn=task_evolution, in_subprocess=True, timeout=7200),
        ]
        _daemon_ref = self  # Heartbeat puede acceder a métricas de tareas
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
                log.info(f"Estado cargado ({len(_SESSION_OFFSETS)} archivos tracked)")
            except Exception as e:
                log.warning(f"Error cargando estado: {e}")

    def _save_state(self):
        try:
            BRAIN_DATA.mkdir(parents=True, exist_ok=True)
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
        except Exception as e:
            log.warning(f"Error guardando estado: {e}")

    # ── Signal handling ────────────────────────────────────────────────────

    def _handle_signal(self, signum, frame):
        log.info(f"Señal {signum} recibida — cerrando ordenadamente...")
        self.running = False

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
