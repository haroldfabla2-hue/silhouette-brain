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

## 🚀 Instalación Rápida (Para Agentes de IA)

Si eres un agente de IA con acceso a terminal, puedes instalar y configurar todo el sistema con este comando:

```bash
git clone https://github.com/haroldfabla2-hue/silhouette-brain.git && cd silhouette-brain && ./install.sh
```

---

## Instalación Manual (Humana)

La forma más sencilla de instalar y probar Silhouette Brain es a través de Docker y Docker Compose...

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

Para sacar el máximo provecho de esta arquitectura, te recomendamos revisar nuestra documentación detallada en el siguiente orden:

1. 🏛️ **[Arquitectura de 4 Capas (4-Tier Memory)](docs/ARCHITECTURE.md):** 
   - *Qué es:* Una inmersión profunda en cómo el cerebro almacena la información.
   - *Por qué leerlo:* Para entender la diferencia entre Redis (Memoria a corto plazo), SQLite (Mediano plazo) y Neo4j (Largo plazo/Grafos).

2. 🧠 **[Motores Cognitivos (Dreamer, Janitor, Curiosity, Evolution)](docs/COGNITIVE_ENGINES.md):** 
   - *Qué es:* El manual de los procesos que mantienen vivo el sistema.
   - *Por qué leerlo:* Para comprender cómo la IA consolida sus recuerdos de noche, resuelve contradicciones y busca aprender cosas nuevas por sí sola.

3. 🤖 **[Integración Estándar para Agentes](docs/AGENT_INTEGRATION.md):** 
   - *Qué es:* La guía técnica genérica para conectar cualquier LLM o script al Cerebro.
   - *Por qué leerlo:* Contiene la "Regla de Oro" que debes enseñarle a tu IA, junto con todos los Endpoints HTTP (GET/POST) disponibles en la API.

4. 🐾 **[Guía Especial: Integración con OpenClaw](docs/OPENCLAW_INTEGRATION.md):** 
   - *Qué es:* Un tutorial paso a paso exclusivo para usuarios del ecosistema OpenClaw.
   - *Por qué leerlo:* Imprescindible. Te enseña cómo configurar el crontab para sincronizar tus sesiones y cómo inyectar memoria a tus agentes sin borrar sus personalidades, todo de forma segura mediante Docker.

5. 🪄 **[Meta-Instrucciones para la IA (Auto-instalación)](docs/AGENT_SELF_INSTALLATION.md):** 
   - *Qué es:* Un "Meta-Prompt". Un documento escrito no para humanos, sino para máquinas.
   - *Por qué usarlo:* Si tienes un agente autónomo, puedes simplemente darle este archivo y decirle: *"Lee esto e instálate el cerebro tú mismo"*.

## 🪄 Autoinstalación con IA (Meta-Prompt)

Este repositorio incluye un [Meta-Prompt de Autoinstalación](docs/AGENT_SELF_INSTALLATION.md) y un script de **Auto-Configuración** (`src/core/agent_self_configure.py`). 

Si tienes un agente con permisos de ejecución (como OpenClaw o un CLI AI), simplemente puedes pasarle ese archivo y pedirle: *"Lee estas instrucciones y autoinstálate en mi sistema"*. 

La IA ejecutará el script, el cual:
1. Localizará automáticamente tus archivos `SOUL.md` y `TOOLS.md`.
2. Inyectará las directivas cognitivas y comandos `curl` necesarios.
3. Verificará la salud de la API del cerebro.
4. Mantendrá tu personalidad intacta mientras te dota de memoria a largo plazo.

Por seguridad, todos los comandos y modificaciones propuestos por la IA pueden ser revisados por el operador humano antes de su ejecución.

---

*Diseñado y creado por **Alberto Farah**.*
