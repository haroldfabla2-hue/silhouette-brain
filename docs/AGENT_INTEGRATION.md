# Integración con Agentes (Agent Integration)

El objetivo principal de Silhouette Brain es servir como el centro cognitivo para ecosistemas multi-agentes (como **OpenClaw**). Para que el sistema funcione, los agentes deben estar instruidos para consumir esta memoria.

## La Regla de Oro
**"NUNCA hagas una tarea ni respondas sin consultar la memoria primero."**

Esta regla debe estar inyectada en el prompt del sistema (System Prompt) o en el archivo de reglas (`TOOLS.md` / `AGENTS_MEMORY_INTEGRATION.md`) de tu orquestador de agentes.

## Scripts Clave para Agentes
En `src/core/agent_memory_client.py` encontrarás un wrapper en Python optimizado para agentes. Tiene un sistema de caché de 5 minutos integrado para que, si un agente hace un loop o se equivoca llamando 100 veces a la API, no sature la base de datos ni los tokens de OpenAI.

### Flujo Ideal de un Agente:
1. **Inicio de Tarea:** El agente recibe una solicitud (ej. "Revisa el código de la landing page").
2. **Context Retrieval:** El agente ejecuta internamente un comando shell o un script Python:
   ```bash
   curl -s "http://localhost:9876/api/memory/semantic?query=landing+page+codigo&limit=3"
   ```
3. **Análisis:** El agente lee la respuesta de la API y descubre que "Rick modificó la landing ayer para arreglar un botón".
4. **Ejecución:** El agente realiza su tarea basándose en ese contexto histórico.
5. **Ingesta:** (Opcional pero recomendado) Al terminar, el agente registra un pequeño reporte o resumen que los scripts de sincronización (Sync) subirán de vuelta al Brain.

## Endpoints Disponibles
El Brain expone los siguientes endpoints HTTP (REST):

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/api/status` | GET | Estado de salud de todas las bases (Redis, SQLite, Neo4j) |
| `/api/memory?query=x` | GET | Búsqueda básica por texto exacto (rápida) |
| `/api/memory/semantic?query=x` | GET | Búsqueda con Inteligencia Artificial (Embeddings) |
| `/api/memory/entities` | GET | Lista de conceptos/personas clave conocidas por el sistema |
| `/api/memory/graph?entity=x`| GET | Devuelve el grafo de conexiones de una entidad en Neo4j |
| `/api/memory/recent?hours=x`| GET | Devuelve los últimos mensajes y contexto del día |
| `/api/memory` | POST | Permite inyectar una nueva memoria con su nivel de prioridad |