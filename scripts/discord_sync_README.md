# Discord Session Sync - Producción

Sincroniza conversaciones de Discord desde OpenClaw a memoria.

## Características

- ✅ Lee sesiones de TODOS los agentes
- ✅ Backup automático a JSONL
- ✅ Integración con Brain API (cuando esté disponible)
- ✅ Modo fallback (sin Brain API = solo JSONL)
- ✅ Logging detallado
- ✅ Manejo de errores robusto

## Uso

```bash
python3 scripts/discord_sync.py
```

## Configuración (variables de entorno)

| Variable | Default | Descripción |
|----------|---------|-------------|
| OPENCLAW_AGENTS_DIR | /root/.openclaw/agents | Directorio de agentes |
| MEMORY_OUTPUT_DIR | /root/.openclaw/workspace/memory_discord | Output JSONL |
| BRAIN_API_URL | http://localhost:9876 | URL del Brain API |

## Cron (cada 15 min)

```bash
*/15 * * * * cd /root/silhouette-brain && python3 scripts/discord_sync.py >> /var/log/discord_sync.log 2>&1
```

## Requisitos

- Python 3.8+
- requests (para Brain API)
