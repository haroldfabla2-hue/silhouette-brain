# Meta-Instrucciones: Autoinstalación para Agentes AI

Si eres un agente (OpenClaw, Codex, Claude Code, etc.) y te pidieron integrar Silhouette Brain, este es tu procedimiento operativo.

## Fase 1: Levantar infraestructura
1. Configura `.env` desde `.env.example`.
2. Inicia stack:
   ```bash
   docker-compose up -d
   ```
3. Verifica API:
   ```bash
   curl -s http://127.0.0.1:9876/api/status
   ```
4. Verifica heartbeat:
   ```bash
   curl -s http://127.0.0.1:9876/api/heartbeat
   ```

## Fase 2: Autoconfiguración del agente
Ejecuta:
```bash
python3 src/core/agent_self_configure.py
```

El script inyecta reglas en `SOUL.md`/`TOOLS.md` sin romper personalidad base.

## Fase 3: Regla cognitiva obligatoria (debe quedar escrita)
Inyecta esta política en identidad/sistema del agente:

1. Antes de responder, consultar `context/assemble` o `reasoning/context`.
2. Si la certeza es baja, investigar profundo en múltiples capas/fuentes.
3. Detectar y usar fuentes disponibles inteligentemente.
4. Preguntar al usuario solo si persiste incertidumbre después de investigar interno + externo.
5. Registrar feedback de fuentes para aprendizaje de ranking.

## Fase 4: Detección inteligente de fuentes
El motor detecta capacidades en runtime y arma `source_plan`:
- Internas: `semantic`, `recent`, `graph`, `tiers`, `heartbeat`.
- Externas (si disponibles): `workspace_digital`, `google_workspace`, `notebook_intel`, `web_search`, `gmail_monitor`.

Tu comportamiento debe respetar ese plan; no usar siempre la misma fuente por defecto.

## Fase 5: Integración en HEARTBEAT.md
Asegura que el heartbeat:
1. Lea `heartbeat_state.json`.
2. Procese `investigaciones` despachadas por Curiosity.
3. Investigue, documente hallazgo y guarde memoria.
4. Envíe feedback de fuentes usadas.
5. Responda `HEARTBEAT_OK` solo si no quedan pendientes críticas.
6. No envíe gaps crudos al humano; reporta solo conclusiones verificadas.

## Fase 6: Integración en TOOLS.md
Agrega comandos base para todos los agentes:

```markdown
## Silhouette Brain API
- Estado: `curl -s "http://127.0.0.1:9876/api/status"`
- Heartbeat: `curl -s "http://127.0.0.1:9876/api/heartbeat"`
- Context Assembler: `curl -s "http://127.0.0.1:9876/api/context/assemble?query=<tema>&mode=reply_fast"`
- Reasoning Context: `curl -s "http://127.0.0.1:9876/api/reasoning/context?query=<tema>"`
- Feedback fuentes (POST): `curl -s -X POST "http://127.0.0.1:9876/api/reasoning/feedback" -H "Content-Type: application/json" -d '{"sources":["workspace_digital"],"outcome":"success","reason":"util","actor":"agent"}'`
```

## Fase 7: Persistencia para agentes nuevos (templates)
Mantén plantillas actualizadas en `agent-templates/`:
- `AGENTS.md`
- `SOUL.md`
- `HEARTBEAT.md`
- `TOOLS.md`

Y usa el hook `bootstrap-extra-files` en OpenClaw para que agentes nuevos nazcan con estas reglas.

## Fase 8: Verificación final
1. Consulta de prueba:
   ```bash
   curl -s "http://127.0.0.1:9876/api/context/assemble?query=test&mode=reply_fast"
   ```
2. Verifica que incluya `investigation_pass` y `sources_policy`.
3. Registra feedback de prueba y confirma snapshot:
   ```bash
   curl -s "http://127.0.0.1:9876/api/reasoning/feedback?limit=5"
   ```

Operación correcta = agente con memoria, investigación multinivel y aprendizaje de fuentes activo.
