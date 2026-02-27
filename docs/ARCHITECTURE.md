# Arquitectura de 4 Capas (4-Tier Memory System)

El **Silhouette Brain** está construido bajo un modelo de arquitectura cognitiva profunda (Deep Cognitive Architecture). En lugar de usar una simple base de datos o depender solo del contexto del modelo (context window), divide la memoria en 4 capas de persistencia y velocidad distintas, imitando el cerebro humano.

## 1. Working Memory (Memoria de Trabajo)
- **Tecnología:** Redis (Caché en Memoria RAM).
- **Velocidad:** Ultra-rápida (ms).
- **Propósito:** Almacena el contexto actual de la conversación, IDs de sesión temporales y entidades que se están discutiendo en los últimos 5-10 minutos. 
- **Limpieza:** Los datos aquí expiran (TTL).

## 2. Medium-Term Memory (Memoria Reciente)
- **Tecnología:** SQLite (`memory_core.db`).
- **Velocidad:** Rápida.
- **Propósito:** Almacena todos los mensajes recientes (hasta un par de días), reportes diarios de los agentes y "memorias episódicas".
- **Limpieza:** Se depura periódicamente moviendo las piezas valiosas a las capas inferiores y borrando la basura ("noise cleanup").

## 3. Long-Term Memory (Conocimiento Semántico)
- **Tecnología:** SQLite + OpenAI Vector Embeddings (text-embedding-3-small) / LanceDB.
- **Velocidad:** Media.
- **Propósito:** Búsqueda semántica (Búsqueda por significado, no solo por palabras clave). Guarda conceptos clave, instrucciones de proyectos, y datos técnicos estáticos.

## 4. Deep Memory (Red Semántica / Grafos)
- **Tecnología:** Neo4j (Graph Database).
- **Velocidad:** Compleja (Consultas Cypher).
- **Propósito:** Relaciona entidades entre sí. Si un agente habla sobre "Alberto", Neo4j sabe que Alberto "es_dueño_de" -> "Brandistry" y "trabaja_con" -> "React". Esto le da al sistema "sentido común" y la capacidad de entender el mundo.

## El Puente: Brain API
Ningún agente interactúa directamente con las bases de datos. Todos deben pasar por `enhanced_memory_api.py`, un servidor Flask ligero expuesto típicamente en el puerto `9876`. Esto asegura que:
1. No haya corrupción de datos por concurrencia.
2. OpenClaw (o cualquier otro sistema multi-agente) pueda actualizarse sin romper la memoria.