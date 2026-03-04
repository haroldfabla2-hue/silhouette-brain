# Heartbeat y Notificaciones

Este documento define el comportamiento oficial de autonomía y mensajería del sistema.

## Principio operativo

- Los **gaps de Curiosity** son internos del sistema.
- El humano **no** debe recibir gaps crudos por Telegram/Discord.
- El humano recibe luego **conclusiones** o **reportes accionables** del agente.

## Flujo correcto

1. Curiosity detecta un gap.
2. El daemon despacha la tarea a memoria con tags `cognitive_task` + `investigation`.
3. `task_heartbeat` publica esas tareas en `heartbeat_state.json` (`investigaciones` y `pendientes`).
4. El agente, durante heartbeat, toma una investigación, la ejecuta y guarda hallazgos.
5. El agente reporta al humano solo resultado útil, no la alarma cruda.

## Dónde se guarda cada cosa

- Dedupe de gaps despachados: `data/curiosity_dispatched_gaps.json`
- Estado heartbeat: `data/heartbeat_state.json`
- Fallback de lectura para workspace: `/root/.openclaw/workspace/heartbeat-state.json`

## Endpoints relevantes

- `GET /api/heartbeat`
- `GET /api/context/assemble`
- `GET /api/reasoning/context`
- `POST /api/reasoning/feedback`

## Política de notificaciones

- `service_alert` y alertas críticas de infraestructura pueden notificar al humano.
- `curiosity_gap` y `curiosity_novel` quedan internos por diseño.
- Si se necesita cambiar política, hacerlo explícitamente en `data/proactive_policy.json`.

## Criterio de calidad

- Menos ruido de sistema al humano.
- Más autonomía real del agente.
- Reportes finales con evidencia, no pings técnicos.
