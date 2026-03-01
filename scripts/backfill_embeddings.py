#!/usr/bin/env python3
"""
Embedding Backfill Script
==========================
Genera embeddings locales (fastembed ONNX) para todas las conversaciones.
Reemplaza embeddings incompatibles de OpenAI (1536-dim) con vectores HF (384-dim).

Modos:
  --mode=missing   Solo mensajes SIN embedding (26K aprox)  [default]
  --mode=all       Todos los mensajes, incluyendo re-embeddings de OpenAI (115K)
  --mode=stale     Solo mensajes con embedding de dimensión incorrecta (89K OpenAI)

Características:
  - fastembed local (ONNX, sin API, sin rate limits, ~500 msgs/seg)
  - Batching para máxima eficiencia
  - Checkpoint: guarda progreso cada X batches → reanudable con Ctrl+C
  - Filtro de ruido: salta heartbeats y mensajes operacionales

Uso:
  python3 backfill_embeddings.py               # solo missing (~26K)
  python3 backfill_embeddings.py --mode=all    # todo (~115K)
  python3 backfill_embeddings.py --mode=stale  # solo OpenAI incompatibles (~89K)
"""
import os
import sys
import json
import time
import sqlite3
import argparse
import numpy as np
from datetime import datetime

# ── Paths ──────────────────────────────────────────────────────────────────
_DIR        = os.path.dirname(os.path.abspath(__file__))
_ROOT       = os.path.dirname(_DIR)
BRAIN_DATA  = os.getenv("BRAIN_DATA_DIR", os.path.join(_ROOT, "data"))
DB_PATH     = os.path.join(BRAIN_DATA, "memory_core.db")
CHECKPOINT  = os.path.join(BRAIN_DATA, "backfill_checkpoint.json")

# ── Embedding model (fastembed local ONNX) ────────────────────────────────
FASTEMBED_MODEL = os.getenv(
    "FASTEMBED_MODEL",
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)
TARGET_DIMS    = 384   # dims del modelo
EXPECTED_BYTES = TARGET_DIMS * 4  # float32 → 4 bytes por dimensión

_embed_model = None

def _get_model():
    global _embed_model
    if _embed_model is None:
        print("Cargando modelo fastembed (primera vez, ~25MB descarga)...")
        from fastembed import TextEmbedding
        _embed_model = TextEmbedding(FASTEMBED_MODEL)
        print("Modelo listo.\n")
    return _embed_model

# ── Noise filter (inline, sin importar módulo) ─────────────────────────────
import re
_NOISE = [
    re.compile(r'\bHEARTBEAT_OK\b', re.I),
    re.compile(r'Scout\s+completado\s*[-–]\s*Ciclo\s+\d+', re.I),
    re.compile(r'\[AGENT:[A-Z]+\].*Ciclo\s+\d+', re.I),
    re.compile(r'exec host\s*=\s*sandbox', re.I),
    re.compile(r'sandbox runtime\s+(?:is\s+)?unavailable', re.I),
    re.compile(r'KEEPALIVE', re.I),
    re.compile(r'"status":\s*"failed_manual_attention"'),
    re.compile(r'<industrial-memory>'),
    re.compile(r'^\s*\{.*"timestamp_utc"'),
    re.compile(r'\|\s*(?:Oportunidades|High Priority)\s*\|.*\|'),
]

def is_noise(text: str) -> bool:
    if not text or len(text.strip()) < 10:
        return True
    for p in _NOISE:
        if p.search(text):
            return True
    return False


# ── fastembed local batch ─────────────────────────────────────────────────

def embed_batch(texts: list) -> list | None:
    """
    Genera embeddings locales con fastembed ONNX.
    Sin API, sin rate limits, ~500 mensajes/segundo.
    """
    try:
        model  = _get_model()
        vecs   = list(model.embed(texts))
        return [v.tolist() for v in vecs]
    except Exception as e:
        print(f"\n  [ERROR embed_batch] {e}", flush=True)
        return None


def vec_to_bytes(vec: list[float]) -> bytes:
    return np.array(vec, dtype=np.float32).tobytes()

def bytes_to_dims(b: bytes) -> int:
    return len(b) // 4  # float32 = 4 bytes


# ── Checkpoint ─────────────────────────────────────────────────────────────

def load_checkpoint() -> set:
    if os.path.exists(CHECKPOINT):
        try:
            with open(CHECKPOINT) as f:
                data = json.load(f)
            return set(data.get("done_ids", []))
        except Exception:
            pass
    return set()

def save_checkpoint(done_ids: set, total_done: int, total_skipped: int):
    with open(CHECKPOINT, "w") as f:
        json.dump({
            "done_ids":     list(done_ids),
            "total_done":   total_done,
            "total_skipped": total_skipped,
            "updated_at":   datetime.now().isoformat(),
        }, f)


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Backfill embeddings HuggingFace")
    parser.add_argument("--mode",  default="missing", choices=["missing", "stale", "all"],
                        help="missing=sin embedding | stale=dims incorrectas | all=todos")
    parser.add_argument("--batch", type=int, default=64,
                        help="Textos por batch fastembed (default: 64)")
    parser.add_argument("--delay", type=float, default=0.0,
                        help="Segundos entre batches (default: 0 — fastembed es local)")
    parser.add_argument("--limit", type=int, default=0,
                        help="Procesar solo N mensajes (0=todos)")
    parser.add_argument("--reset", action="store_true",
                        help="Ignorar checkpoint previo")
    args = parser.parse_args()

    if not os.path.exists(DB_PATH):
        print(f"ERROR: DB no encontrada en {DB_PATH}")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"  Silhouette Brain — Embedding Backfill")
    print(f"  Modo:    {args.mode}")
    print(f"  Batch:   {args.batch} textos/request")
    print(f"  Engine:  fastembed local ONNX (sin API, sin rate limits)")
    print(f"  DB:      {DB_PATH}")
    print(f"{'='*60}\n")

    # ── Conectar DB ────────────────────────────────────────────────────────
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # ── Seleccionar filas a procesar ───────────────────────────────────────
    if args.mode == "missing":
        query = """
            SELECT id, message FROM conversations
            WHERE embedding IS NULL
            ORDER BY timestamp DESC
        """
        print("Modo: solo mensajes SIN embedding")

    elif args.mode == "stale":
        # Embeddings con dimensión ≠ TARGET_DIMS (ej. OpenAI 1536-dim = 6144 bytes)
        query = """
            SELECT id, message FROM conversations
            WHERE embedding IS NOT NULL
              AND length(embedding) != ?
            ORDER BY timestamp DESC
        """
        print(f"Modo: mensajes con embedding de dimensión incorrecta (≠ {TARGET_DIMS} dims)")

    else:  # all
        query = """
            SELECT id, message FROM conversations
            ORDER BY timestamp DESC
        """
        print("Modo: TODOS los mensajes (missing + stale)")

    if args.mode == "stale":
        rows = conn.execute(query, (EXPECTED_BYTES,)).fetchall()
    else:
        rows = conn.execute(query).fetchall()

    if args.limit > 0:
        rows = rows[:args.limit]

    total_rows = len(rows)
    print(f"Mensajes a procesar: {total_rows:,}\n")

    if total_rows == 0:
        print("Nada que procesar. ¡Todo actualizado!")
        conn.close()
        return

    # ── Cargar checkpoint ──────────────────────────────────────────────────
    done_ids  = set() if args.reset else load_checkpoint()
    if done_ids:
        print(f"Checkpoint cargado: {len(done_ids):,} IDs ya procesados\n")

    # ── Filtrar filas ya procesadas y ruido ────────────────────────────────
    pending = [
        r for r in rows
        if r["id"] not in done_ids and not is_noise(r["message"] or "")
    ]
    skipped_noise = total_rows - len(pending) - len(done_ids & {r["id"] for r in rows})

    print(f"Pendientes:     {len(pending):,}")
    print(f"Ya procesados:  {len(done_ids):,}")
    print(f"Filtrado ruido: {skipped_noise:,}")

    if not pending:
        print("\n✅ Nada pendiente.")
        conn.close()
        return

    # ── Estimar tiempo ─────────────────────────────────────────────────────
    n_batches    = (len(pending) + args.batch - 1) // args.batch
    est_minutes  = n_batches * args.delay / 60
    print(f"\nBatches estimados: {n_batches:,}")
    print(f"Tiempo estimado:   ~{est_minutes:.0f} min")
    print(f"\nIniciando... (Ctrl+C para pausar y guardar checkpoint)\n")
    time.sleep(2)

    # ── Procesar ───────────────────────────────────────────────────────────
    done_this_run  = 0
    errors         = 0
    batch_num      = 0
    start_time     = time.time()

    try:
        for i in range(0, len(pending), args.batch):
            batch     = pending[i : i + args.batch]
            batch_num += 1
            texts     = [r["message"][:512] for r in batch]

            embeddings = embed_batch(texts)

            if embeddings is None or len(embeddings) != len(batch):
                errors += len(batch)
                for row in batch:
                    done_ids.add(row["id"])
            else:
                # Guardar embeddings en DB
                updates = [
                    (vec_to_bytes(emb), row["id"])
                    for emb, row in zip(embeddings, batch)
                    if emb and len(emb) == TARGET_DIMS
                ]
                if updates:
                    conn.executemany(
                        "UPDATE conversations SET embedding = ? WHERE id = ?",
                        updates,
                    )
                    conn.commit()

                for row in batch:
                    done_ids.add(row["id"])
                done_this_run += len(updates)

            # ── Progreso ───────────────────────────────────────────────────
            total_done  = len(done_ids)
            pct         = total_done / total_rows * 100 if total_rows else 100
            elapsed     = time.time() - start_time
            rate        = done_this_run / elapsed if elapsed > 0 else 0
            eta_s       = (len(pending) - i - len(batch)) / (rate * args.batch) if rate > 0 else 0
            eta_min     = eta_s / 60

            print(
                f"\r  [{batch_num:4d}/{n_batches}]  {pct:5.1f}%  "
                f"Procesados: {done_this_run:,}  Errores: {errors}  "
                f"ETA: {eta_min:.0f}min",
                end="", flush=True,
            )

            # ── Checkpoint cada 50 batches ─────────────────────────────────
            if batch_num % 50 == 0:
                save_checkpoint(done_ids, done_this_run, skipped_noise)

            # ── Rate limiting ──────────────────────────────────────────────
            time.sleep(args.delay)

    except KeyboardInterrupt:
        print(f"\n\n⏸  Interrumpido por usuario. Guardando checkpoint...")

    finally:
        save_checkpoint(done_ids, done_this_run, skipped_noise)
        conn.close()

    # ── Resumen ────────────────────────────────────────────────────────────
    elapsed = time.time() - start_time
    print(f"\n\n{'='*60}")
    print(f"  RESUMEN BACKFILL")
    print(f"  Embeddings generados: {done_this_run:,}")
    print(f"  Errores:              {errors:,}")
    print(f"  Tiempo total:         {elapsed/60:.1f} min")
    print(f"  Velocidad:            {done_this_run/(elapsed/60):.0f} msgs/min")
    print(f"{'='*60}\n")

    if errors > 0:
        print(f"⚠️  {errors} mensajes fallaron. Puedes re-ejecutar para reintentar.")
    else:
        print("✅ Backfill completado sin errores.")

    # Limpiar checkpoint si todo OK
    if errors == 0 and os.path.exists(CHECKPOINT):
        os.remove(CHECKPOINT)
        print("   Checkpoint eliminado (ya no necesario).")


if __name__ == "__main__":
    main()
