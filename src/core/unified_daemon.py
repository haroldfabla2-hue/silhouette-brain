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
BRAIN_ROOT     = Path(os.getenv("BRAIN_ROOT", "/root/silhouette-brain"))
BRAIN_SRC_CORE = BRAIN_ROOT / "src" / "core"
BRAIN_SRC_COG  = BRAIN_ROOT / "src" / "cognitive_engines"
BRAIN_DATA     = Path(os.getenv("BRAIN_DATA_DIR", str(BRAIN_ROOT / "data")))
STATE_FILE     = BRAIN_DATA / "unified_daemon_state.json"
LOG_FILE       = Path("/var/log/silhouette_unified_daemon.log")

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
    name:      str
    interval:  int          # segundos entre ejecuciones
    fn:        Callable
    enabled:   bool = True
    last_run:  float = 0.0  # epoch timestamp
    run_count: int   = 0
    err_count: int   = 0

    def due(self, now: float) -> bool:
        return self.enabled and (now - self.last_run) >= self.interval

    def run(self):
        t0 = time.time()
        log.info(f"[{self.name}] ▶ inicio")
        try:
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
# TAREA 1 — Session Sync (de global_memory_daemon)
# ============================================================================

# Estado de la sesión (persistido en STATE_FILE["session_offsets"])
_SESSION_OFFSETS: dict = {}

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

    db_path = BRAIN_DATA / "memory_core.db"
    if not db_path.exists():
        return

    try:
        from zhipu_embeddings import get_embedding_batch
    except ImportError:
        return  # fastembed no instalado

    conn = sqlite3.connect(str(db_path))
    # Solo mensajes recientes sin embedding (últimas 6h)
    cutoff = int(time.time()) - 21600
    rows = conn.execute(
        "SELECT id, message FROM conversations WHERE embedding IS NULL AND timestamp > ? LIMIT 200",
        (cutoff,)
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
            conn.executemany("UPDATE conversations SET embedding=? WHERE id=?", updates)
            conn.commit()
            log.info(f"[embedding_sync] {len(updates)} embeddings generados")
    except Exception as e:
        log.warning(f"[embedding_sync] Error: {e}")
    finally:
        conn.close()


# ============================================================================
# TAREA 3 — API Health Check
# ============================================================================

def task_api_health():
    """Vigila la Brain API. La reinicia si no responde."""
    import subprocess
    import requests as req

    try:
        r = req.get("http://127.0.0.1:9876/api/status", timeout=5)
        if r.status_code == 200:
            return  # Todo bien
    except Exception:
        pass

    log.warning("[api_health] Brain API no responde — reiniciando...")
    scripts_dst = Path("/root/.openclaw/skills/silhouette-memory/scripts")
    api_script  = scripts_dst / "enhanced_memory_api.py"
    if api_script.exists():
        subprocess.Popen(
            [sys.executable, str(api_script)],
            env={**os.environ, "BRAIN_SRC_DIR": str(scripts_dst)},
            stdout=open("/var/log/memory_api.log", "a"),
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
        self.running = True
        self.tasks: List[Task] = [
            Task("session_sync",    interval=120,   fn=task_session_sync),
            Task("embedding_sync",  interval=300,   fn=task_embedding_sync),
            Task("api_health",      interval=180,   fn=task_api_health),
            Task("curiosity",       interval=3600,  fn=task_curiosity),
            Task("dreamer",         interval=21600, fn=task_dreamer),    # 6h
            Task("janitor",         interval=43200, fn=task_janitor),    # 12h
            Task("evolution",       interval=21600, fn=task_evolution),  # 6h
        ]
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

        # Forzar session_sync y api_health en el primer tick
        now = time.time()
        for task in self.tasks:
            if task.name in ("session_sync", "api_health"):
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
