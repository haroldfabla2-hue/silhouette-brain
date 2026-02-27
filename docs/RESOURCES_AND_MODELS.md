# Gestión de Recursos y Modelos AI ⚙️

El **Silhouette Brain** es un sistema potente, pero su ejecución implica el consumo de recursos computacionales y créditos de APIs externas. Esta guía te ayudará a configurar el sistema según tus necesidades y presupuesto.

## 🔋 Consumo de Recursos (Hardware)

A diferencia de un simple script, Silhouette Brain levanta una infraestructura completa:

1.  **Neo4j (Grafos):** Consume una cantidad considerable de RAM (mínimo recomendado: 1GB libre para el contenedor). Si notas lentitud en tu servidor, puedes limitar su uso en el `docker-compose.yml`.
2.  **Redis (Cache):** Muy ligero en CPU, pero consume RAM según el volumen de mensajes recientes.
3.  **Procesos de Fondo (Engines):** Los scripts como `Dreamer` o `Janitor` realizan cálculos intensivos de red y lógica cuando se ejecutan. Recomendamos programarlos en horarios de baja actividad.

## 💸 Consumo de API (Costos)

El sistema utiliza **OpenAI** para generar "Embeddings" (vectores matemáticos de significado). 

- **Costo por Mensaje:** Cada vez que un agente guarda una memoria o busca contexto, se realiza una llamada a la API de OpenAI.
- **Optimización:** Hemos implementado un sistema de **Caché de Embeddings** en SQLite. Si una frase ya fue procesada, el cerebro no volverá a gastar dinero en ella; simplemente recuperará el vector matemático de la base de datos local.

## 🧠 Selección de Modelos (Libertad de Elección)

Por defecto, el sistema utiliza `text-embedding-3-small` de OpenAI por su excelente relación calidad-precio. Sin embargo, tienes total libertad para cambiarlo.

### Cómo cambiar el modelo de Embeddings
Edita tu archivo `.env` y añade la variable:
```env
EMBEDDING_MODEL=text-embedding-3-large
```
*Nota: Si cambias el modelo después de haber guardado memorias, el sistema detectará la discrepancia y podría generar errores de dimensión en Neo4j. Se recomienda empezar con un modelo fijo o limpiar la base de datos al cambiar.*

### Opciones Disponibles
Puedes configurar cualquier modelo compatible con la API de OpenAI que soporte embeddings:
- `text-embedding-3-small` (Económico y rápido - Predeterminado)
- `text-embedding-3-large` (Máxima precisión)
- `text-embedding-ada-002` (Legacy)

## 🛠️ Consejos de Optimización
- **Ajusta los Cron Jobs:** No sincronices cada minuto si no es necesario. Cada 30-60 minutos es ideal para la mayoría de los usuarios.
- **Filtra el Ruido:** Enseña a tus agentes a no guardar "basura" (ej. "Hola", "Ok", "Gracias"). Solo deben inyectar información con `importance > 0.5`.
