# Discord Memory Integration

Scripts para integrar Discord con silhouette-brain.

## Scripts

### 1. discord_memory_manager.py
Guarda mensajes en la Brain API.

```python
from discord_memory_manager import save_discord_message

# Guardar mensaje saliente
save_discord_message("Hola!", "123456789", "outgoing")

# Guardar mensaje entrante
save_discord_message("Hola!", "123456789", "incoming")
```

### 2. discord_context.py
Consulta contexto durante conversaciones.

```python
from discord_context import search_context, get_context_for_iris

# Buscar contexto específico
results = search_context("Iris check-in")

# Obtener contexto de Iris
context = get_context_for_iris()
```

### 3. memory_consult.py
Consulta general en la memoria.

```bash
python3 memory_consult.py "protocolo iris"
```

## Uso

1. Asegurar que Brain API esté corriendo en puerto 9876
2. Los scripts se conectan automáticamente
