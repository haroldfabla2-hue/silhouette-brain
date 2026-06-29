# Deprecated — use `silhouette` (v3) instead

The modules in this directory are **legacy code** from pre-v3 deployments
(OpenClaw-oriented, copy-paste evolution). They are **not maintained** and may
contain broken imports or duplicate functionality.

## Supported replacement (v3)

| Legacy | v3 replacement |
|--------|----------------|
| `src/api/enhanced_memory_api.py` | `silhouette serve` |
| `src/core/unified_daemon.py` | `silhouette daemon` |
| `src/core/memory_*.py` (many) | `silhouette.storage.MemorySystem` |
| `src/cognitive_engines/*.py` | `silhouette.engines.*` |
| `src/core/conversation_injection_guard.py` | `silhouette.security.injection` |
| `src/core/memory_noise_filter.py` | `silhouette.security.noise` |
| `src/core/hooks_system.py` | `silhouette.hooks` |
| `src/core/session_sync.py` | `silhouette.integrations.openclaw` |

See [LEGACY.md](../../LEGACY.md) at the repository root for the full migration
guide.

**Do not add new features here.** Open PRs against `src/silhouette/` only.
