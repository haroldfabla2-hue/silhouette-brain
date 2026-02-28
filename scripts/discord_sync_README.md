# Discord Session Sync

Sincroniza conversaciones de Discord desde OpenClaw a memoria.

## Uso

```bash
python3 scripts/discord_sync.py
```

## Configuración

El script lee sesiones de TODOS los agentes en `/root/.openclaw/agents/`:
- main, silhouette, rick, roger, cami, jack, rose, larry, flocky

Guarda en: `/root/.openclaw/workspace/memory_discord/discord_messages.jsonl`

## Cron (cada 15 min)

```bash
*/15 * * * * cd /root/silhouette-brain && python3 scripts/discord_sync.py
```

## Requisitos

- Python 3.8+
- Acceso a `/root/.openclaw/agents/`
