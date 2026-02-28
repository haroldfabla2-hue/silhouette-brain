# Guía de Integración con OpenClaw 🐾

El **Silhouette Brain** está diseñado para ser agnóstico, pero brilla especialmente cuando se integra con sistemas multi-agente como OpenClaw. Para que tus agentes realmente "cobren vida" y parezca que tienen una memoria humana continua, debes ajustar ligeramente su configuración y levantar los procesos de sincronización.

Aquí te explicamos cómo lograr la simbiosis perfecta:

## 1. Mantener Personalidades + Inyectar Memoria

El error más común al integrar una memoria externa es sobrescribir la personalidad del agente. **No lo hagas.** Los agentes deben seguir siendo ellos mismos (ej. sarcásticos, formales, analíticos), pero con una regla estricta sobre sus acciones.

**Cómo editar el `system_prompt` de tus agentes:**
Añade este bloque al *final* de las instrucciones base de tus agentes en OpenClaw, sin borrar su personalidad original:

```markdown
# 🧠 REGLA COGNITIVA ESTRICTA (Silhouette Brain)
Tú estás conectado a un "Cerebro" (Brain API) que almacena el contexto global de todo el ecosistema. 
- **ANTES de iniciar CUALQUIER tarea o responder**, debes usar tus herramientas (como `curl` o tus scripts) para consultar el Brain API en `http://localhost:9876/api/memory/semantic?query=tema_de_la_charla`.
- Lee el contexto histórico devuelto. Si descubres que otro agente ya hizo algo, o que el usuario ya dio una instrucción previa, adapta tu respuesta a esa realidad.
- Si no sabes quién es una persona o qué es un proyecto, consulta `http://localhost:9876/api/memory/entities`.
- **Mantén tu personalidad intacta**, pero usa estos recuerdos como si fueran tuyos.
```

## 2. Herramientas Necesarias (Tools)
Para que los agentes de OpenClaw puedan consultar la API, asegúrate de que tengan habilitada la herramienta `exec` (para poder ejecutar llamadas a red) o proporciónales una "Skill" que contenga un script en Python (como el provisto en `src/core/agent_memory_client.py`).

## 3. APIs Extras Requeridas
Para que el cerebro funcione en su totalidad, necesitarás definir en tu archivo `.env`:
- **OpenAI API Key (`OPENAI_API_KEY`):** Estrictamente necesaria para generar los *Embeddings Vectoriales* (convertir el texto en matemáticas para que la IA pueda buscar por significado y no solo por coincidencia de palabras).
- **Notion / Trello (Opcional):** Si deseas usar los scripts de integración (`trello_monitor.py` o `larry_notion_check.py`), necesitarás las credenciales correspondientes. Si no los usas, puedes ignorar o desactivar esos cron jobs.

## 4. El Latido del Corazón: Sincronización Global Ininterrumpida
El cerebro no funciona si no se alimenta. Para que el sistema esté "vivo", se utiliza un **Daemon de Sincronización Global** que captura en tiempo real (cada 2 minutos) lo que los agentes de OpenClaw están haciendo en todos sus canales (Discord, Terminal, Web, etc) y lo inyecta en el Cerebro.

A diferencia del pasado donde se dependía de tareas `cron`, ahora se usa un proceso gestionado por `pm2` que funciona de forma 100% desacoplada:

1. **Autodescubrimiento:** Escanea dinámicamente `/root/.openclaw/workspace/` y `/root/.openclaw/agents/` buscando cualquier carpeta de canales o sesiones. Si el día de mañana agregas Slack o Telegram, el cerebro los leerá automáticamente sin tocar código.
2. **Eficiencia:** Guarda un estado interno para recordar qué mensajes ya leyó, evitando consumo excesivo de disco y CPU.

**Cómo verificar que el Daemon está corriendo:**
```bash
pm2 status | grep silhouette-global-sync
```

**Si necesitas reiniciarlo o ver sus logs:**
```bash
pm2 restart silhouette-global-sync
pm2 logs silhouette-global-sync
```

## 5. Arquitectura Desacoplada y Segura (Por qué no se romperá)
El mayor miedo al integrar sistemas complejos es romper lo que ya funciona. Silhouette Brain soluciona esto usando una **Arquitectura Desacoplada**.

En lugar de instalar el cerebro *dentro* de la carpeta de OpenClaw (lo que causaría que una actualización de OpenClaw borre tu memoria), el cerebro corre en su propio "universo" aislado mediante Docker:

1. **Aislamiento Docker:** Al usar `docker-compose up`, Neo4j, Redis y la Brain API se levantan en contenedores sellados. No tocan ni modifican las dependencias de Node.js o el código fuente de OpenClaw.
2. **Comunicación por Red (HTTP):** OpenClaw y Silhouette Brain **solo hablan a través de red** (`http://localhost:9876`). Si OpenClaw se actualiza, la red sigue existiendo. Si Silhouette Brain se actualiza, la API sigue respondiendo igual.
3. **Resiliencia:** Si la Brain API se cae temporalmente, tus agentes de OpenClaw seguirán funcionando (solo perderán el acceso al contexto histórico hasta que el cerebro vuelva a encenderse). ¡Nada explotará!

## Resumen de la Simbiosis
1. Los **Procesos Sync** "escuchan" todo lo que OpenClaw hace y lo envían a la API.
2. Los **Motores Cognitivos** (Dreamer, Janitor) organizan esa basura durante la noche y la convierten en recuerdos estructurados en Neo4j.
3. El **Agente** recibe un nuevo mensaje, consulta la API antes de hablar, y responde como si tuviera una memoria perfecta a largo plazo.