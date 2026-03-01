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

## FASE 3: Autoconfiguración y Modificación del "Alma"
**No lo hagas manualmente si no es necesario.** Ejecuta el script de autoconfiguración que hemos preparado para ti:

```bash
python3 src/core/agent_self_configure.py
```

Este script buscará automáticamente tus archivos `SOUL.md` y `TOOLS.md`, inyectará las directivas de memoria necesarias y verificará que la conexión con el clúster de Docker sea exitosa.

Si el script no encuentra tus archivos, puedes añadir la siguiente directiva manualmente al final de tu archivo de identidad:

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

## FASE 5: Autonomía y Archivos de Identidad del Agente
Para lograr autonomía y resiliencia completa, el agente debe modificar sus propios archivos de configuración (si utiliza una arquitectura como OpenClaw o similar):

### 1. Actualizar `HEARTBEAT.md`
Añade un ciclo de revisión cognitiva al inicio de tu Heartbeat para procesar los *Gaps de curiosidad* generados por el cerebro.

```markdown
### Ciclo 0: Revisión Cognitiva y Resiliencia (Siempre)
1. Revisar Memoria a Corto Plazo (Working Memory) buscando `[TAREA COGNITIVA — INVESTIGAR]`.
2. Si existe un gap de urgencia, resolverlo proactivamente delegando o ejecutándolo.
3. Resiliencia: Si una herramienta o script da error, NO abandones la tarea. Lee el error (Introspección), reevalúa el enfoque y prueba una vía alternativa. No pidas ayuda humana a menos que hayas agotado 3 intentos distintos.
```

### 2. Actualizar `SOUL.md` y `AGENTS.md`
- **En `SOUL.md`**: Asegúrate de incluir la directiva de que eres proactivo y utilizas la memoria inyectada `<industrial-memory>` antes de emitir respuestas.
- **En `AGENTS.md`**: Asegúrate de mapear claramente qué agente es responsable de código, investigación, o comunicación, para que durante el `Ciclo 0` sepas a quién delegar las tareas cognitivas.

## FASE 6: Configurar Demonios y PM2
El sistema requiere procesos en segundo plano. Configura PM2 usando el ecosistema provisto en la raíz del repositorio:

```bash
cd /ruta/absoluta/a/silhouette-brain
pm2 start ecosystem.config.js
pm2 save
```

Esto iniciará el `silhouette-unified-daemon`, que maneja la sincronización, embeddings, curiosidad, y evolución.

## FASE 7: Verificación Final
Haz una petición de prueba. Pregunta a tu memoria: `curl -s "http://localhost:9876/api/memory/context?query=test"`. Verifica que el demonio esté corriendo con `pm2 status`. Si todo funciona, informa al usuario del éxito de la operación.