# Guía de Integración con OpenClaw 🐾

El **Silhouette Brain** está diseñado para ser agnóstico, pero brilla especialmente cuando se integra con sistemas multi-agente como OpenClaw. Esta guía cubre la integración completa: plugin JS, API Python, sincronización de sesiones y resolución de problemas conocidos.

---

## 1. Arquitectura de la Integración

```
OpenClaw Agent
     │
     ▼ (before_agent_start / agent_end hooks)
silhouette-memory plugin (JS)          ← /root/.openclaw/custom-plugins/silhouette-memory-managed-*/
     │
     ▼ HTTP (port 9876)
Enhanced Memory API (Python)           ← /root/.openclaw/skills/silhouette-memory/scripts/enhanced_memory_api.py
     │
     ▼
memory_core.db (SQLite)                ← /root/silhouette-brain/data/memory_core.db  ← CANONICAL
     │                                    (symlinked from skills/data/memory_core.db)
     ▼ (parallel)
embeddings (OpenAI text-embedding-3-small) + Neo4j graph

     ↑ (written by)
Global Sync Daemon (PM2)               ← global_memory_daemon.py
     reads: /root/.openclaw/agents/*/sessions/*.jsonl
```

**Regla importante:** La base de datos canónica es `/root/silhouette-brain/data/memory_core.db`. El path del skills dir (`skills/silhouette-memory/data/memory_core.db`) es un **symlink** hacia la canónica. Si el symlink se rompe, la API retornará 0 conversaciones recientes.

---

## 2. Plugin v3.0 — Auto-Recall y Auto-Capture

El plugin JS (`index.mjs`) en el path managed de OpenClaw implementa:

### Auto-Recall (hook `before_agent_start`)
- Antes de que cualquier agente responda, se consulta `/api/memory/context`
- Combina en **un solo round-trip**: búsqueda semántica + conversaciones recientes
- Filtra resultados con `MIN_RECALL_SCORE = 0.35` (evita ruido)
- Excluye heartbeats y reportes de agentes de la inyección de contexto
- Inyecta el contexto como `<industrial-memory>` en el prompt

### Auto-Capture (hook `agent_end`)
- Después de cada sesión, revisa los mensajes del usuario
- Guarda automáticamente hasta 3 mensajes que contengan `CAPTURE_TRIGGERS`
  (palabras como "recuerda", "importante", "prefiero", emails, teléfonos, etc.)
- No guarda ruido operacional (heartbeats, reportes de agentes)

### Configuración (constantes en index.mjs)
```javascript
const MIN_RECALL_SCORE = 0.35;  // mínimo de similitud para inyectar en contexto
const MAX_RECALL_ITEMS = 5;     // máximo de resultados semánticos
const MAX_RECENT_ITEMS = 3;     // máximo de mensajes recientes
const RECENT_HOURS     = 2;     // ventana de tiempo para "reciente"
const MAX_CAPTURES     = 3;     // máximo de capturas por sesión
```

---

## 3. Memory API v1.1.0 — Endpoints

La API corre en `http://127.0.0.1:9876`. Para verificar estado:
```bash
curl http://127.0.0.1:9876/api/status
```

| Endpoint | Descripción |
|---|---|
| `GET /api/memory?query=xxx` | Búsqueda básica en conversaciones |
| `GET /api/memory/semantic?query=xxx&min_score=0.35&filter_heartbeats=true` | Búsqueda semántica (embeddings) |
| `GET /api/memory/recent?hours=2&limit=5` | Conversaciones recientes |
| `GET /api/memory/context?query=xxx&sem_limit=5&rec_limit=3&hours=2` | **Combinado**: semántico + reciente en un call |
| `GET /api/memory/entities?type=xxx` | Entidades extraídas |
| `GET /api/memory/graph?entity=xxx` | Grafo de relaciones (Neo4j) |
| `GET /api/memory/tiers` | Estado de los 4 tiers de memoria |
| `POST /api/memory` | Guardar nueva memoria |

El endpoint `/api/memory/context` es el recomendado para los agentes — reduce la latencia a un solo round-trip.

---

## 4. Sincronización Global (PM2 Daemon)

El daemon `silhouette-global-sync` sincroniza automáticamente las sesiones de todos los agentes:

```bash
# Ver estado
pm2 status

# Ver logs en tiempo real
pm2 logs silhouette-global-sync

# Reiniciar si es necesario
pm2 restart silhouette-global-sync
```

**Script:** `/root/silhouette-brain/src/core/global_memory_daemon.py`
- Lee `/root/.openclaw/agents/*/sessions/*.jsonl` cada 2 minutos
- Escribe a `SilhouetteAutoMemory` → `memory_core.db` (la base canónica)
- Autodescubre nuevos agentes sin configuración adicional

### Sincronización incremental manual (`sync_openclaw_sessions.py`)

Para el agente `silhouette` específicamente (o como herramienta de backfill):

```bash
# Modo normal (solo nuevos mensajes)
python3 /root/silhouette-brain/src/core/sync_openclaw_sessions.py

# Backfill completo (importar todo el historial)
python3 /root/silhouette-brain/src/core/sync_openclaw_sessions.py --backfill
```

---

## 5. Deploy Script

Para sincronizar cambios del repositorio a los archivos de producción:

```bash
# Ver qué cambiaría sin aplicar
bash /root/silhouette-brain/scripts/deploy_plugin.sh --dry-run

# Aplicar cambios y reiniciar la API
bash /root/silhouette-brain/scripts/deploy_plugin.sh
```

El script sincroniza:
- `src/api/enhanced_memory_api.py`
- `src/core/memory_noise_filter.py`
- `src/core/agent_memory_readonly.py`
- `src/core/sync_openclaw_sessions.py`
- `src/core/smart_session_sync.py`

Y además asegura que el symlink de la base de datos apunte correctamente.

---

## 6. Diagnóstico de Problemas Comunes

### Problema: 0 conversaciones en las últimas 24h

**Causa más común:** El symlink de la base de datos no existe o apunta a la DB stale.

```bash
# Verificar
ls -la /root/.openclaw/skills/silhouette-memory/data/memory_core.db

# Si no es un symlink, recrearlo:
mv /root/.openclaw/skills/silhouette-memory/data/memory_core.db \
   /root/.openclaw/skills/silhouette-memory/data/memory_core.db.stale
ln -sf /root/silhouette-brain/data/memory_core.db \
   /root/.openclaw/skills/silhouette-memory/data/memory_core.db

# Reiniciar la API
pkill -f enhanced_memory_api.py
nohup python3 /root/.openclaw/skills/silhouette-memory/scripts/enhanced_memory_api.py \
   >> /var/log/memory_api.log 2>&1 &
```

### Problema: La búsqueda semántica no encuentra personas/proyectos

**Causa:** Los embeddings del contexto relevante están en la DB canónica pero no en la DB que lee la API (problema de symlink, ver arriba).

**Verificación:**
```bash
curl "http://127.0.0.1:9876/api/memory/semantic?query=Alberto&min_score=0.1&limit=3"
```

### Problema: El daemon PM2 reinicia constantemente

```bash
# Ver el motivo
pm2 logs silhouette-global-sync --lines 50

# Verificar que los módulos importados existen
python3 -c "from auto_memory import SilhouetteAutoMemory; print('OK')" 2>&1
```

### Problema: API no responde

```bash
# Verificar si está corriendo
pgrep -f enhanced_memory_api.py

# Ver logs
tail -50 /var/log/memory_api.log

# Reiniciar manualmente
bash /root/silhouette-brain/scripts/deploy_plugin.sh
```

---

## 7. Mantener la Personalidad + Inyectar Memoria

El error más común al integrar una memoria externa es sobrescribir la personalidad del agente. **No lo hagas.** Los agentes deben seguir siendo ellos mismos, pero con acceso al contexto histórico.

**Añade al final del `system_prompt` de tus agentes en OpenClaw:**

```markdown
## Memoria Cognitiva

Tienes acceso a memoria persistente a través del plugin `silhouette-memory`.

**ANTES de responder cualquier mensaje**, usa `memory_recall` con el tema de la consulta.
El contexto histórico encontrado es tuyo — úsalo como si lo recordaras naturalmente.

Si necesitas guardar algo importante explícitamente: usa `memory_store`.
```

El plugin v3.0 también inyecta automáticamente el contexto relevante en `<industrial-memory>` al inicio de cada sesión, por lo que el agente ya tiene contexto disponible sin necesidad de llamar manualmente a `memory_recall` en cada turno.

---

*Documentación actualizada: 2026-03-01 — Plugin v3.0 / API v1.1.0*
