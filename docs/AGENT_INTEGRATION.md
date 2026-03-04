# Integración con Agentes (Agent Integration)

Silhouette Brain está diseñado para que los agentes operen con memoria real, investigación verificable y criterio de incertidumbre.

## Regla Operativa
**"No respondas por intuición si puedes verificar."**

Antes de responder, el agente debe consultar memoria/contexto. Si la certeza es baja, debe investigar más. Solo pregunta al usuario al final, cuando todavía hay duda después de investigar.

## Flujo Recomendado (v2)
1. **Estado del sistema**
   - `GET /api/heartbeat`
   - Si `brain_api` o `neo4j` están `DOWN`, priorizar diagnóstico.
2. **Recuperación contextual**
   - Preferido: `GET /api/context/assemble?query=...&mode=reply_fast`
   - Alternativa: `GET /api/reasoning/context?query=...`
3. **Evaluación de certeza**
   - Leer `semantic_confidence` e `investigation_pass`.
   - Si `needs_confirmation=true` o `still_uncertain=true`, no cerrar respuesta.
4. **Investigación profunda multinivel**
   - Usar primero capas internas: `semantic`, `recent`, `graph`, `tiers`, `heartbeat`.
   - Luego usar fuentes externas recomendadas en `investigation_pass.source_plan.external`.
   - El motor detecta capacidades disponibles y genera `source_plan.ranked_external`.
5. **Resolución**
   - Si la evidencia converge: responder con la conclusión.
   - Si no converge tras investigación profunda: preguntar al usuario de forma puntual.
6. **Aprendizaje de ranking**
   - Registrar outcome para mejorar el ranking de fuentes:
   - `POST /api/reasoning/feedback` con `sources`, `outcome`, `reason`, `actor`.

## Endpoints Clave

| Endpoint | Método | Uso |
|---|---|---|
| `/api/status` | GET | Estado y features activas |
| `/api/heartbeat` | GET | Estado operativo + investigaciones pendientes |
| `/api/context/assemble` | GET | Context packet optimizado por presupuesto/tokens |
| `/api/reasoning/context` | GET | Contexto cognitivo unificado |
| `/api/reasoning/feedback` | GET/POST | Snapshot y escritura de feedback de fuentes |
| `/api/memory/semantic` | GET | Búsqueda semántica |
| `/api/memory/recent` | GET | Contexto reciente |
| `/api/memory/graph` | GET | Relaciones en Neo4j |
| `/api/memory/tiers` | GET | 4 capas de memoria |
| `/api/memory` | POST | Ingesta de memoria |

## Gaps de Curiosidad: Qué son y para qué sirven
- El motor Curiosity detecta vacíos de información y despacha tareas de investigación.
- Esas tareas aparecen en `heartbeat_state` (`investigaciones` y `pendientes`).
- Su objetivo es aumentar cobertura de conocimiento y prevenir respuestas superficiales.
- El agente debe procesar esas tareas en heartbeats y registrar hallazgos en memoria.

## Política de Fuentes (evitar alucinaciones)
1. Priorizar evidencia interna con mayor score.
2. Si hay conflicto o score competitivo, ampliar investigación.
3. Incluir `heartbeat` como fuente interna crítica de autonomía.
4. Escalar a fuentes externas solo cuando la señal interna no alcance.
5. Preguntar al usuario únicamente cuando persista incertidumbre real.

## Ejemplo: Registro de feedback de fuentes
```bash
curl -s -X POST "http://127.0.0.1:9876/api/reasoning/feedback" \
  -H "Content-Type: application/json" \
  -d '{
    "sources": ["workspace_digital","google_workspace","web_search"],
    "outcome": "success",
    "reason": "evidencia_consistente",
    "actor": "silhouette"
  }'
```

## Nota de implementación
- El ranking aprendido se persiste en `data/source_feedback.json`.
- Este archivo ajusta multiplicadores por fuente y mejora la selección futura.
