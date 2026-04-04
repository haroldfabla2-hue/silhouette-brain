# Brain API Reference

Base URL: `http://localhost:9876`

## Endpoints

### Memory — Context

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/memory/context?query=<text>` | Combined semantic + recent in one call |
| GET | `/api/memory` | Full 4-tier memory dump |
| GET | `/api/entities` | List all entities |
| GET | `/api/recent` | Recent messages (medium memory) |
| GET | `/api/semantic?query=<text>` | Semantic search (vector similarity) |

### Memory — Graph (Neo4j)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/graph` | Full knowledge graph |
| GET | `/api/tiers` | Tier file status |

### Reasoning

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/reasoning/context?query=<text>` | Deep reasoning with context synthesis |
| POST | `/api/reasoning/feedback` | Record feedback for truth verification |
| POST | `/api/reasoning/source-feedback` | Record source attribution feedback |

### Assembler

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/context/assemble?query=<text>&depth=<level>` | Full context packet (semantic + graph + recent) |

### Health

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/api/health` | Extended health with all services |

## Query Parameters

| Parameter | Applies to | Description |
|-----------|------------|-------------|
| `query` | context, semantic, reasoning | Search text |
| `depth` | assemble | low / medium / high |
| `limit` | entities, recent | Max results (default 10) |

## Example Responses

### `/api/memory/context?query=Alberto`

```json
{
  "query": "Alberto",
  "semantic_results": [...],
  "recent_context": [...],
  "graph_connections": [...],
  "response": "..."
}
```

### `/api/reasoning/context?query=Brandistry`

```json
{
  "query": "Brandistry",
  "reasoning": "...",
  "context_used": {...},
  "confidence": 0.87,
  "sources": [...]
}
```
