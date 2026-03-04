# HEARTBEAT — Protocolo de Silhouette

Cada heartbeat es un ciclo de trabajo, no un ping vacío.

## PASO 1: Estado vital

Lee `heartbeat_state.json` (workspace o `/api/heartbeat`) y extrae:
- `energia`
- `servicios` (`brain_api`, `neo4j`, `redis`)
- `pendientes`
- `investigaciones`
- `introspection.sugerencias`

Si `brain_api` o `neo4j` están `DOWN`, eso es prioridad 1.

## PASO 2: Procesar gaps de Curiosity

Si hay `investigaciones`:
1. Toma una tarea relevante.
2. Consulta:
   - `GET /api/reasoning/context?query=<tema>`
   - o `GET /api/context/assemble?query=<tema>&mode=discovery`
3. Revisa `semantic_confidence` e `investigation_pass`.
4. Si hay duda, sigue `source_plan` y profundiza en múltiples fuentes (internas y externas disponibles).
5. Solo si persiste la incertidumbre tras investigar, formula una pregunta puntual al usuario.
6. Guarda el hallazgo en memoria con tags de investigación.

## PASO 3: Registrar feedback de fuentes

Después de cerrar una investigación:
- si resolviste bien, reporta `outcome=success`
- si no resolviste o la fuente fue mala, `outcome=failure`

Ejemplo:
```bash
curl -s -X POST "http://127.0.0.1:9876/api/reasoning/feedback" \
  -H "Content-Type: application/json" \
  -d '{"sources":["workspace_digital","web_search"],"outcome":"success","reason":"evidencia_convergente","actor":"silhouette"}'
```

## PASO 4: Proactividad operativa

Si no hay gaps urgentes:
- Revisa proyectos críticos con poca actividad.
- Verifica errores repetidos del daemon.
- Si aparece señal de standup/proactividad, genera actualización breve y accionable.

## PASO 5: Cierre del heartbeat

Responde `HEARTBEAT_OK` solo cuando:
- no hay servicios críticos sin atender
- no ignoraste investigaciones urgentes
- no quedan fallos recurrentes sin reportar

Formato sugerido:
```
HEARTBEAT_OK | energia=0.8 | servicios_criticos=OK | investigaciones_pendientes=0
```
