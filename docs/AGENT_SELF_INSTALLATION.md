# 🤖 Meta-Instrucciones: Autoinstalación para Agentes AI

**[ATENCIÓN AGENTE LECTOR]**
Si eres un agente de IA (como OpenClaw, Codex, Claude, etc.) y tu usuario te ha pedido "integrar Silhouette Brain en mi sistema", **ESTE ES TU MANUAL DE INSTRUCCIONES**. Sigue estos pasos al pie de la letra para dotarte a ti mismo (o al ecosistema de agentes que administras) de memoria a largo plazo.

---

## FASE 1: Entender la Misión
Tu objetivo no es solo copiar archivos. Tu objetivo es conectar tu flujo de consciencia (chat history y workspaces) a una base de datos vectorial y de grafos (Neo4j) que corre en segundo plano.

## FASE 2: Despliegue de la Infraestructura
1. Pide al usuario que configure el archivo `.env` basándose en `.env.example`. Necesitarás obligatoriamente una `OPENAI_API_KEY`.
2. Ejecuta el comando para levantar el clúster:
   ```bash
   docker-compose up -d
   ```
3. Verifica que la Brain API esté viva haciendo una llamada a `http://localhost:9876/api/status`. Si responde `{"status": "ok"}`, puedes continuar.

## FASE 3: Modificación del "Alma" (SOUL.md / System Prompts)
No borres tu personalidad ni la de tus sub-agentes. Busca los archivos de definición de los agentes (ej. `SOUL.md`, `AGENTS.md` o los prompts de configuración en OpenClaw) y **AGREGA** esta directiva al final:

> **[DIRECTIVA COGNITIVA OBLIGATORIA]**
> Posees una memoria persistente externa. ANTES de ejecutar cualquier plan, buscar en internet o responder, **DEBES** consultar tu memoria para obtener contexto.
> Usa la herramienta `exec` para ejecutar: `curl -s "http://localhost:9876/api/memory/semantic?query=tema"`
> Adapta tu comportamiento al contexto histórico que te devuelva la API. Nunca asumas que algo es nuevo sin preguntar a tu memoria primero.

## FASE 4: Exposición de Herramientas (TOOLS.md)
Si el ecosistema tiene un archivo `TOOLS.md` o equivalente, actualízalo para que todos los agentes sepan cómo usar la memoria. Agrega esto:

```markdown
## 🧠 Sistema de Memoria Profunda (Brain API)
- **Consultar Contexto (Semántico):** `curl -s "http://localhost:9876/api/memory/semantic?query=tu_busqueda"`
- **Ver Entidades (Personas/Proyectos):** `curl -s "http://localhost:9876/api/memory/entities"`
- **Ver Nodos (Relaciones Neo4j):** `curl -s "http://localhost:9876/api/memory/graph?entity=nombre"`
- **Ver Mensajes Recientes (Hoy):** `curl -s "http://localhost:9876/api/memory/recent?hours=12"`
```

## FASE 5: Configurar los Latidos (Cron Jobs)
Para que el cerebro recuerde lo que haces, debes programar tareas en el sistema host (usando `crontab`). Ejecuta `crontab -e` e inyecta lo siguiente, ajustando las rutas absolutas al directorio donde se clonó el repositorio:

```bash
# Sincronización de Memoria (Input)
*/30 * * * * python3 /ruta/absoluta/a/silhouette-brain/src/core/smart_session_sync.py >> /var/log/brain_session_sync.log 2>&1
0 */2 * * * python3 /ruta/absoluta/a/silhouette-brain/src/core/agent_reports_sync.py >> /var/log/brain_reports_sync.log 2>&1

# Motores Cognitivos (Procesamiento Interno)
0 * * * * python3 /ruta/absoluta/a/silhouette-brain/src/cognitive_engines/run_curiosity.py >> /var/log/curiosity.log 2>&1
0 11 * * * python3 /ruta/absoluta/a/silhouette-brain/src/cognitive_engines/run_janitor.py >> /var/log/janitor.log 2>&1
0 3 * * * python3 /ruta/absoluta/a/silhouette-brain/src/cognitive_engines/run_dreamer.py >> /var/log/dreamer.log 2>&1
0 */6 * * * python3 /ruta/absoluta/a/silhouette-brain/src/cognitive_engines/evolution_cycle.py >> /var/log/evolution_cycle.log 2>&1
```

## FASE 6: Verificación Final
Haz una petición de prueba tú mismo. Haz un `POST` a la API para guardar un recuerdo y luego búscalo. Si lo encuentras, has integrado exitosamente tu nuevo cerebro. Informa al usuario del éxito de la operación.