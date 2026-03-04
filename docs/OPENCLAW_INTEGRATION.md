# Guía de Integración con OpenClaw

Esta guía documenta la integración actual entre OpenClaw y Silhouette Brain (API v2.0.0 + daemon unificado).

## 1. Arquitectura operativa

```
OpenClaw Agent
   │
   ├─ plugin/hooks de memoria
   ▼
Enhanced Memory API (127.0.0.1:9876)
   │
   ├─ reasoning/context
   ├─ context/assemble
   ├─ memory/* (semantic, recent, graph, tiers)
   └─ reasoning/feedback
   ▼
SQLite + embeddings + Neo4j + heartbeat_state
   ▲
   └─ silhouette-unified-daemon (sync + motores cognitivos + heartbeat)
```

DB canónica:
- `/root/silhouette-brain/data/memory_core.db`

Estado heartbeat:
- `/root/silhouette-brain/data/heartbeat_state.json`
- fallback lectura: `/root/.openclaw/workspace/heartbeat-state.json`

## 2. Endpoints recomendados para OpenClaw

| Endpoint | Método | Uso |
|---|---|---|
| `/api/status` | GET | Ver estado/feature flags |
| `/api/heartbeat` | GET | Salud servicios y cola cognitiva |
| `/api/context/assemble` | GET | Contexto listo para inyección `<industrial-memory>` |
| `/api/reasoning/context` | GET | Contexto cognitivo detallado |
| `/api/reasoning/feedback` | GET/POST | Ranking aprendido de fuentes |
| `/api/memory` | POST | Ingesta explícita |

Ejemplo de recall recomendado:
```bash
curl -s "http://127.0.0.1:9876/api/context/assemble?query=tema&mode=reply_fast&token_budget=2800&semantic=full"
```

## 3. Daemon unificado y autonomía

Servicio principal:
- `src/core/unified_daemon.py`

Responsabilidades:
- sincronización de sesiones OpenClaw
- heartbeat operativo
- ejecución de motores cognitivos (curiosity, janitor, dreamer, evolution)
- despacho de tareas cognitivas de investigación

Comandos útiles:
```bash
systemctl status silhouette-memory-api.service
pm2 status
pm2 logs silhouette-unified-daemon --lines 100
```

## 4. Heartbeat y gaps de Curiosity

`heartbeat_state` incluye señales para autonomía:
- `servicios` (brain_api, neo4j, redis)
- `pendientes`
- `investigaciones` (gaps despachados)
- `introspection`
- `energia`

Qué debe hacer el agente:
1. Si hay servicios críticos `DOWN`, diagnosticar primero.
2. Si hay `investigaciones`, procesar al menos una por heartbeat.
3. Guardar hallazgo en memoria.
4. Reportar si aún hay incertidumbre real.

Política de mensajería:
- Los gaps de Curiosity (`curiosity_gap`, `curiosity_novel`) se tratan como internos.
- El humano no recibe el ping técnico del gap; recibe la conclusión del agente tras investigar.

## 5. Política anti-alucinación (OpenClaw)

El agente no debe responder por primer match. Flujo obligatorio:
1. Consultar memoria/contexto.
2. Revisar `semantic_confidence` e `investigation_pass`.
3. Si hay conflicto o baja señal, investigar profundo.
4. Usar `source_plan` para elegir fuentes.
5. Preguntar al usuario solo al final si persiste duda.

## 6. Aprendizaje de ranking por feedback

Después de una investigación/respuesta, registrar outcome:

```bash
curl -s -X POST "http://127.0.0.1:9876/api/reasoning/feedback" \
  -H "Content-Type: application/json" \
  -d '{
    "sources": ["workspace_digital", "google_workspace", "web_search"],
    "outcome": "success",
    "reason": "evidencia_coincidente",
    "actor": "openclaw-agent"
  }'
```

Esto actualiza el ranking persistido en:
- `data/source_feedback.json`

## 7. Diagnóstico rápido

Problema: no aparecen investigaciones en heartbeat
1. Confirmar daemon activo.
2. Revisar logs del daemon.
3. Validar que `memory.db`/`memory_core.db` existan y sean accesibles.

Problema: respuestas ambiguas o contradictorias
1. Consultar `investigation_pass` en `/api/reasoning/context`.
2. Verificar si `still_uncertain=true`.
3. Ejecutar investigación adicional y registrar feedback.

Problema: endpoint nuevo no disponible
1. `curl /api/status`
2. Revisar `features.context_assembler` y `features.source_feedback`.
