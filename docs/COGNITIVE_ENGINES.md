# Motores Cognitivos (Cognitive Engines)

El Silhouette Brain no es solo una base de datos estática; es un sistema "vivo" gracias a sus motores cognitivos. Estos son scripts de Python ubicados en `src/cognitive_engines/` que deben ejecutarse periódicamente mediante tareas Cron o schedulers.

Simulan el ciclo biológico del cerebro humano:

## 🌙 1. Dreamer (`run_dreamer.py`)
- **Frecuencia recomendada:** Madrugada (1 vez al día).
- **Función:** Simula la fase de sueño REM. Toma todo lo guardado durante el día en la Memoria Reciente y lo mueve a la Deep Memory (Neo4j). Crea nuevas asociaciones entre conceptos, y realiza una "Poda Sináptica" (Synaptic Pruning) eliminando conexiones o datos débiles que ya no son relevantes.

## 🧹 2. Janitor (`run_janitor.py`)
- **Frecuencia recomendada:** Medio día.
- **Función:** El conserje lógico. Analiza las entidades de la base de datos buscando "Contradicciones". Si el Agente A dijo que un proyecto fue un éxito, pero el Agente B dijo que fue un fracaso, el Janitor lee el contexto, evalúa las pruebas y define una "Verdad" (Truth) oficial, actualizando la propiedad de la entidad.

## 🔍 3. Curiosity (`run_curiosity.py`)
- **Frecuencia recomendada:** Cada 2-4 horas.
- **Función:** El motor explorador. Lee la red de grafos en Neo4j buscando "huecos" (ej. "Sabemos que Alberto trabaja en Brandistry, pero no sabemos qué tecnología usan allí"). El motor genera estas preguntas y las inserta en la Memoria de Trabajo (Working Memory) para que, cuando un agente despierte, intente investigar y llenar ese vacío.

## 🧬 4. Auto-Evolución (`evolution_cycle.py`)
- **Frecuencia recomendada:** Cada 6 horas.
- **Función:** Es un proceso meta-cognitivo. Evalúa el rendimiento de los otros motores (ej. ¿Qué porcentaje de las entidades tienen verdades verificadas por el Janitor? ¿Se han guardado suficientes mensajes hoy?). Si el rendimiento baja, sugiere y registra mejoras. 

*(Nota: En modo seguro, este motor solo audita y propone. Para que haga cambios directos en el código fuente de los agentes, se requiere habilitar los permisos en el script)*.