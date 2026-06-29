# Legacy code migration guide

Silhouette Brain **v3** (`src/silhouette/`) is the supported, tested, typed core.
The old tree (`src/core/`, `src/cognitive_engines/`, legacy API) remains in the
repository for reference but is **deprecated**.

## Quick migration

```bash
# Old
python src/api/enhanced_memory_api.py
python src/core/unified_daemon.py

# New (supported)
pip install -e ".[all]"
silhouette serve
silhouette daemon
```

## Environment variables

| Legacy | v3 (`SILHOUETTE_` prefix) |
|--------|---------------------------|
| `BRAIN_DATA_DIR` | `SILHOUETTE_DATA_DIR` |
| `NEO4J_URI` | `SILHOUETTE_NEO4J_URI` |
| `NEO4J_PASSWORD` | `SILHOUETTE_NEO4J_PASSWORD` |
| `REDIS_URL` | `SILHOUETTE_REDIS_URL` |
| `REASONING_PROVIDER` | `SILHOUETTE_REASONING_PROVIDER` |
| `REASONING_API_KEY` | `SILHOUETTE_REASONING_API_KEY` |
| OpenClaw agents dir (hardcoded) | `SILHOUETTE_OPENCLAW_AGENTS_DIR` |

## HTTP API compatibility

The v3 FastAPI app exposes the same primary routes as the legacy server, plus
legacy aliases:

- `GET /api/reasoning/context` → same as `GET /api/context`
- `GET /api/semantic` → same as `GET /api/memory/semantic`
- `GET /api/heartbeat` → reads `heartbeat_state.json` from the daemon

OpenAPI documentation is available at `/docs` when running `silhouette serve`.

## What was ported from legacy

These valuable legacy features now live in v3:

- **Injection guard** → `silhouette.security.injection`
- **Runtime noise / heartbeat filtering** → `silhouette.security.noise`
- **Hooks system** → `silhouette.hooks`
- **OpenClaw session sync** → `silhouette.integrations.openclaw` (opt-in via env)

## What was intentionally not ported

- **Scraper noise injection** (`api_scraper_detection`) — silently corrupts
  responses; removed in v3.
- **anti_distillation / undercover_filter** — adversarial complexity with unclear
  value; not ported.
- **63 duplicate memory modules** — replaced by a single `MemorySystem`.

## Removing legacy code

A future major release may delete `src/core/` entirely. If you depend on a legacy
module, open an issue describing the use case so it can be added properly to v3
before removal.
