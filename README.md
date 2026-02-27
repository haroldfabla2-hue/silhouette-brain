# Silhouette Brain 🧠

Silhouette Brain es un sistema cognitivo de memoria avanzado, diseñado originalmente para interactuar con agentes de OpenClaw, pero desacoplado para ser agnóstico y funcionar vía API HTTP.

Integra múltiples motores cognitivos que se ejecutan en segundo plano (simulando el ciclo de un cerebro real) para procesar, limpiar y evolucionar la información de su entorno utilizando inteligencia artificial, grafos (Neo4j) y bases de datos vectoriales.

## Arquitectura de Memoria 4-Tier
1. **Working Memory:** Capa ultra rápida y efímera (Redis/Memoria RAM).
2. **Medium Memory:** Capa de episodios recientes (SQLite).
3. **Long-Term Memory:** Capa de conocimiento vectorial persistente (SQLite + OpenAI Embeddings).
4. **Deep Memory:** Capa de relaciones semánticas complejas (Grafos en Neo4j).

## Motores Cognitivos
- **Curiosity (`run_curiosity.py`):** Explora proactivamente la base de datos en busca de "huecos" de información y formula preguntas para llenar vacíos.
- **Janitor (`run_janitor.py`):** Motor de limpieza. Lee las memorias recientes buscando contradicciones (Ej: Si un agente dijo "Me gusta el café" y otro día "Odio el café", el Janitor evalúa la verdad mayoritaria).
- **Dreamer (`run_dreamer.py`):** Se ejecuta en la noche/periodos de baja actividad. Asienta las memorias de la capa *Medium* hacia *Deep* creando nodos y conexiones sólidas en Neo4j.
- **Evolution (`evolution_cycle.py`):** Evalúa el rendimiento métrico del sistema (tasa de verificación de verdades) y propone auto-mejoras.

## Instalación Fácil (Docker)

La forma más sencilla de instalar y probar Silhouette Brain es a través de Docker y Docker Compose, que levantarán automáticamente las bases de datos y la API.

1. Clona este repositorio.
2. Copia el archivo de entorno:
   ```bash
   cp .env.example .env
   ```
3. Edita `.env` con tu clave de OpenAI (requerido para los embeddings).
4. Levanta el ecosistema:
   ```bash
   docker-compose up -d
   ```

El servidor "Brain API" estará disponible en: `http://localhost:9876`

## Uso de la API (Brain API)

Puedes consultar la memoria a través de solicitudes HTTP simples:

- **Estado del sistema:** `GET /api/status`
- **Búsqueda semántica:** `GET /api/memory/semantic?query=tu_texto`
- **Consulta de entidades (Janitor):** `GET /api/entities`
- **Consulta del grafo:** `GET /api/graph?entity=nombre`
- **Ingesta de memoria:** `POST /api/memory`
  ```json
  {
    "text": "Hoy aprendí a configurar Neo4j",
    "importance": 0.8,
    "tags": ["tech", "database"],
    "tier": "WORKING"
  }
  ```
## 📚 Documentación Completa

Para sacar el máximo provecho de esta arquitectura, revisa nuestra documentación detallada:
- [Arquitectura de 4 Capas (4-Tier Memory)](docs/ARCHITECTURE.md)
- [Motores Cognitivos (Dreamer, Janitor, Curiosity)](docs/COGNITIVE_ENGINES.md)
- [Integración Estándar para Agentes](docs/AGENT_INTEGRATION.md)
- **[Guía Especial: Integración con OpenClaw](docs/OPENCLAW_INTEGRATION.md)** - *¡Imprescindible si usas el ecosistema OpenClaw!*
- **[Meta-Instrucciones para la IA (Auto-instalación)](docs/AGENT_SELF_INSTALLATION.md)** - *¡Dale este archivo a tu IA para que se integre sola!*

## 🪄 Autoinstalación con IA (Meta-Prompt)

Este repositorio incluye un [Meta-Prompt de Autoinstalación](docs/AGENT_SELF_INSTALLATION.md). Si tienes un agente con permisos de ejecución (como OpenClaw o un CLI AI), simplemente puedes pasarle ese archivo y pedirle: *"Lee estas instrucciones y autoinstálate en mi sistema"*. 

La IA leerá el documento, entenderá cómo conectarse a la API, inyectará las reglas cognitivas en sus propios prompts base (sin borrar su personalidad) y configurará los procesos en segundo plano. Por seguridad, todos los comandos y modificaciones propuestos por la IA pueden ser revisados por el operador humano antes de su ejecución, dependiendo del nivel de autonomía que le hayas otorgado a tu agente.

---

*Diseñado y creado por **Alberto Farah**.*
