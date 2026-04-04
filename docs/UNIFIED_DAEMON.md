# Unified Daemon — silhouette-unified-daemon

The **Unified Daemon** (`src/core/unified_daemon.py`) is the central orchestrator of Silhouette Brain. It runs as a long-lived Python process managed by PM2, scheduling and executing all cognitive tasks.

## 🎛️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                  UNIFIED DAEMON (PID)                       │
│                    PM2: silhouette-unified-daemon           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   Scheduler (ticks every 10s)                               │
│   ├── heartbeat (10min)     → Lightweight in-process       │
│   ├── api_health (3min)    → Lightweight in-process       │
│   ├── session_sync (2min)  → Subprocess                    │
│   ├── embedding_sync (5min)→ Subprocess                    │
│   ├── curiosity (1h)       → Subprocess                    │
│   ├── dreamer (6h)         → Subprocess                    │
│   ├── janitor (12h)        → Subprocess                    │
│   └── evolution (6h)      → Subprocess                    │
│                                                             │
│   State: Redis pub/sub, SQLite persistence                 │
└─────────────────────────────────────────────────────────────┘
```

## ⚙️ Services

| Service | Interval | Type | Timeout | Function |
|---------|----------|------|---------|----------|
| **heartbeat** | 600s | in-process | — | Monitor all system services (brain_api, neo4j, redis), detect down services, publish alerts |
| **api_health** | 180s | in-process | — | HTTP health check against Brain API, track latency, log failures |
| **session_sync** | 120s | subprocess | 180s | Sync agent sessions to Medium memory (SQLite), clean old sessions |
| **embedding_sync** | 300s | subprocess | 900s | Generate embeddings for new messages, store in vector DB |
| **curiosity** | 3600s | subprocess | — | Explore Neo4j graph for knowledge gaps, generate investigation tasks |
| **dreamer** | 21600s | subprocess | 7200s | Consolidate Medium → Deep memory, create graph relations, synaptic pruning |
| **janitor** | 43200s | subprocess | 3600s | Detect and resolve entity contradictions, verify truths |
| **evolution** | 21600s | subprocess | 7200s | Evaluate system metrics, propose/apply self-improvements |

## 🔄 Task Lifecycle

```
Tick (10s) → Check intervals → Run due tasks → Log results → Persist state
```

### In-Process Tasks
Run directly in the daemon's memory space. Fast, shared state.

### Subprocess Tasks
Spawn a child process. Daemon's RAM is freed when the subprocess completes. Prevents memory leaks from long-running heavy tasks (embedding models, graph operations).

## 📊 State Management

- **PID Lock**: Single-instance enforcement via `fcntl.flock()` — prevents duplicate daemons
- **State File**: `data/daemon_state.json` — persists last_run timestamps for all tasks
- **Redis**: Pub/sub for real-time alerts (`service_alert` events)
- **SQLite**: Medium memory storage, investigation queue

## 🚦 Service Dependencies

```
brain_api → neo4j → redis → FastEmbed
                    ↓
            unified_daemon ← PM2
                    ↓
            (all 8 cognitive tasks)
```

## 🛠️ Management Commands

```bash
# Check status
pm2 status silhouette-unified-daemon

# View logs
pm2 logs silhouette-unified-daemon --lines 50

# Restart
pm2 restart silhouette-unified-daemon

# Stop
pm2 stop silhouette-unified-daemon

# Monit (real-time dashboard)
pm2 monit
```

## 🔍 Health Monitoring

The daemon monitors:
- `brain_api`: `GET /api/health` → should return 200
- `neo4j`: bolt connection on port 17687
- `redis`: TCP connection on port 6379

When a service fails 3 consecutive checks → publishes `service_alert` to Redis → AlertCron detects and notifies Alberto.

## 📁 Key Files

| File | Purpose |
|------|---------|
| `src/core/unified_daemon.py` | Main daemon (1662 lines) |
| `ecosystem.config.js` | PM2 configuration |
| `data/daemon_state.json` | Task scheduling state |
| `src/core/unified_daemon.py:1493` | `UnifiedDaemon` class — the main scheduler |

## 🔧 Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `BRAIN_ROOT` | `/root/silhouette-brain` | Root path |
| `BRAIN_SRC_DIR` | `/root/silhouette-brain/src/core` | Source directory |
| `BRAIN_DATA_DIR` | `/root/silhouette-brain/data` | Data directory |
| `NEO4J_URI` | `bolt://localhost:17687` | Neo4j connection |
| `REDIS_URL` | `redis://localhost:6379` | Redis connection |
| `REASONING_PROVIDER` | `minimax` | LLM provider for cognitive tasks |

