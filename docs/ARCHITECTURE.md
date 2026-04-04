# Silhouette Brain — 4-Tier Memory Architecture

Silhouette Brain implements a **Deep Cognitive Architecture** that mimics the human brain's memory system. Rather than relying on a model's context window, it divides memory into 4 layers of persistence and speed.

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                           AGENTS (OpenClaw, etc.)                    │
└─────────────────────────────────┬────────────────────────────────────┘
                                  │ HTTP / API
                                  ▼
┌──────────────────────────────────────────────────────────────────────┐
│                        BRAIN API (:9876)                            │
│                  enhanced_memory_api.py (FastAPI)                   │
│                  Reasoning + Memory Integration Layer                │
└─────────────────────────────────┬────────────────────────────────────┘
                                  │
        ┌─────────────────────────┼─────────────────────────┐
        ▼                         ▼                         ▼
┌───────────────┐       ┌───────────────────┐       ┌─────────────┐
│    WORKING    │       │      MEDIUM        │       │    DEEP     │
│    (Redis)    │       │     (SQLite)       │       │   (Neo4j)   │
│   RAM Cache   │       │  Recent Episodes   │       │ Graph DB    │
│   Instant     │       │    Fast query      │       │ Relations   │
└───────────────┘       └───────────────────┘       └─────────────┘
        │                         │                         │
        └─────────────────────────┼─────────────────────────┘
                                  │
                    ┌─────────────┴─────────────┐
                    │   COGNITIVE ENGINES       │
                    │  Curiosity │ Janitor     │
                    │  Dreamer   │ Evolution   │
                    └──────────────────────────┘
                                  │
                    ┌─────────────┴─────────────┐
                    │     UNIFIED DAEMON         │
                    │  (PM2 managed process)     │
                    │  8 scheduled tasks         │
                    └────────────────────────────┘
```

## The 4 Memory Tiers

### Tier 1: Working Memory — Redis (RAM Cache)
- **Purpose:** Active conversation context, session IDs, entities discussed in last 5-10 minutes
- **Speed:** ⚡⚡⚡ Ultra-fast (ms)
- **Persistence:** Ephemeral (TTL-based expiry)
- **Use case:** Real-time context, temporary state

### Tier 2: Medium Memory — SQLite
- **Purpose:** Recent messages (up to a few days), agent daily reports, episodic memories
- **Speed:** ⚡⚡ Fast
- **Persistence:** Days to weeks
- **Use case:** Session history, recent context

### Tier 3: Long-Term Memory — SQLite + Vectors
- **Purpose:** Semantic search (meaning-based, not keyword-based), key concepts, project instructions
- **Speed:** ⚡ Medium
- **Persistence:** Months
- **Use case:** Knowledge retrieval, concept lookups

### Tier 4: Deep Memory — Neo4j (Graph Database)
- **Purpose:** Entity relationships, semantic network (Alberto "owns" Brandistry, "works_with" React)
- **Speed:** Slow (Cypher queries)
- **Persistence:** Long-term
- **Use case:** Common sense reasoning, relationship understanding

## Brain API — The Only Door

No agent touches the databases directly. All access goes through `enhanced_memory_api.py` (FastAPI on port 9876). This ensures:
1. No data corruption from concurrent writes
2. Framework-agnostic design (OpenClaw, CrewAI, LangGraph, etc.)
3. Consistent reasoning and memory patterns

## Cognitive Engines

Four Python engines run as scheduled tasks inside the Unified Daemon:

| Engine | Schedule | Function |
|--------|----------|----------|
| **Curiosity** | Every 1h | Finds knowledge gaps in the graph, generates investigation tasks |
| **Janitor** | Every 12h | Detects contradictions (Agent A said X, Agent B said not-X), resolves and verifies truths |
| **Dreamer** | Every 6h | Consolidates Medium → Deep memory, creates graph relations, synaptic pruning |
| **Evolution** | Every 6h | Evaluates system metrics, proposes/applies self-improvements |

## System Dependencies

```
Redis (6379) ←→ Brain API ←→ Neo4j (17687)
                   ↑
           Unified Daemon (PM2)
              ├── session_sync (2min)
              ├── embedding_sync (5min)
              ├── curiosity (1h)
              ├── dreamer (6h)
              ├── janitor (12h)
              └── evolution (6h)
```

## Key Files

| File | Description |
|------|-------------|
| `src/core/enhanced_memory_api.py` | FastAPI server — main HTTP interface |
| `src/core/unified_daemon.py` | PM2-managed scheduler — runs all 8 tasks |
| `src/core/unified_memory.py` | Core memory operations class |
| `src/cognitive_engines/` | Curiosity, Janitor, Dreamer, Evolution engines |
| `data/memory_core.db` | SQLite medium-term storage |
| `data/vector_store/` | FastEmbed vector storage |
