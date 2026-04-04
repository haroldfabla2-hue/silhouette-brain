# Silhouette Brain 🧠

> Advanced 4-Tier Cognitive Memory System for AI Agents

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Last Commit](https://img.shields.io/github/last-commit/haroldfabla2-hue/silhouette-brain)](https://github.com/haroldfabla2-hue/silhouette-brain)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](https://www.docker.com/)

**Silhouette Brain** is an advanced cognitive memory system designed for AI agents. It processes, cleans, and evolves information from its environment using AI, graph structures (Neo4j), and vector databases.

Originally built for OpenClaw agents, now decoupled to be **framework-agnostic** via HTTP API.

---

## 🎯 What is this?

Silhouette Brain implements a **4-Tier Memory Architecture** that mirrors human cognition:

```
┌─────────────────────────────────────────────────────────────┐
│                    SILHOUETTE BRAIN                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────┐     ┌─────────────┐                       │
│  │  WORKING    │────▶│   MEDIUM    │────▶┌─────────────┐   │
│  │  (Redis)    │     │   (SQLite)  │     │    DEEP     │   │
│  │  Instant    │     │  Recent     │     │   (Neo4j)   │   │
│  └─────────────┘     └─────────────┘     │  Graph Rags  │   │
│         ▲                ▲               └─────────────┘   │
│         │                │                     ▲           │
│         └────────────────┴─────────────────┘           │
│                    COGNITIVE ENGINES                    │
│         Curiosity │ Janitor │ Dreamer │ Evolution        │
└─────────────────────────────────────────────────────────────┘
```

| Tier | Storage | Purpose | Speed |
|------|---------|---------|-------|
| **Working** | Redis / RAM | Ultra-fast ephemeral cache | ⚡⚡⚡ |
| **Medium** | SQLite | Recent episodes & context | ⚡⚡ |
| **Long-Term** | SQLite + Vectors | Persistent knowledge with embeddings | ⚡ |
| **Deep** | Neo4j Graph | Complex semantic relationships | Slow |

---

## 🧠 Cognitive Engines

| Engine | Function |
|--------|----------|
| **Curiosity** | Proactively explores the database for information "gaps" and formulates questions to fill voids |
| **Janitor** | Cleans recent memories, resolves contradictions (e.g., "I like coffee" vs "I hate coffee" → detects & reconciles) |
| **Dreamer** | Runs during low-activity periods, consolidates Medium → Deep memory into solid Neo4j graph connections |
| **Evolution** | Evaluates system performance metrics (truth verification rate) and proposes self-improvements |

---

## 🚀 Quick Start

### Prerequisites
- Python 3.10+
- Docker & Docker Compose

### One-Command Install

```bash
git clone https://github.com/haroldfabla2-hue/silhouette-brain.git && cd silhouette-brain && ./install.sh
```

### Manual Setup

```bash
# 1. Clone the repo
git clone https://github.com/haroldfabla2-hue/silhouette-brain.git
cd silhouette-brain

# 2. Copy environment file
cp .env.example .env

# 3. Edit .env with your API keys
#    - Embeddings: 100% Local (using fastembed) - NO API key needed!
#    - Reasoning (Optional): Configure your preferred model in REASONING_PROVIDER

# 4. Start the ecosystem
docker-compose up -d

# Brain API available at: http://localhost:9876
```

---

## 📡 API Usage

The API runs at `http://localhost:9876`.

### Query the Memory

```bash
curl "http://localhost:9876/api/reasoning/context?query=your_question"
```

### Response Structure

```json
{
  "query": "your_question",
  "synthesis": "AI-generated answer based on memory",
  "sources": [
    {"type": "graph", "data": "...", "confidence": 0.95},
    {"type": "vector", "data": "...", "confidence": 0.87}
  ],
  "reasoning_chain": ["step1", "step2", "step3"]
}
```

---

## 🏗️ Architecture

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Client     │────▶│  Brain API  │────▶│  Memory API  │
│   (Agent)    │◀────│  (FastAPI)  │◀────│  (Layered)  │
└──────────────┘     └──────────────┘     └──────────────┘
                                                 │
                    ┌───────────────────────────┼───────────────────────────┐
                    ▼                           ▼                           ▼
             ┌─────────────┐           ┌─────────────┐           ┌─────────────┐
             │    Redis    │           │   SQLite    │           │    Neo4j    │
             │   (Working) │           │   (Medium)  │           │    (Deep)   │
             └─────────────┘           └─────────────┘           └─────────────┘
```

---

## 💡 Use Cases

- **AI Agents** — Give your AI agents persistent, evolving memory
- **Chatbots** — Build context-aware conversational AI with long-term memory
- **Research Assistants** — AI that remembers and connects knowledge across sessions
- **Autonomous Systems** — Self-improving AI with cognitive cycles
- **Knowledge Graphs** — Structured memory with semantic relationships

---

## 🤝 Contributing

Contributions are welcome! Please read our guidelines and submit PRs.

```bash
# Run tests
pytest tests/

# Run linting
flake8 src/
```

---

## 📄 License

MIT License - See [LICENSE](LICENSE) for details.

---

## 🌟 Stars & Support

If Silhouette Brain helps your AI agents, please star the repo and share it with the community.

Built with ❤️ for the AI developer community.

---

## 🏗️ System Architecture

```mermaid
graph TB
    subgraph External["External Layer"]
        Agent[AI Agent]
        API[Brain API]
    end
    
    subgraph Cognitive["Cognitive Engines"]
        Curiosity[Curiosity Engine]
        Janitor[Janitor Engine]
        Dreamer[Dreamer Engine]
        Evolution[Evolution Engine]
    end
    
    subgraph Memory["Memory Tiers"]
        Working[(Redis<br/>Working Memory)]
        Medium[(SQLite<br/>Medium Memory)]
        LongTerm[(Vectors<br/>Long-Term Memory)]
        Deep[(Neo4j<br/>Deep Memory)]
    end
    
    Agent --> API
    API --> Working
    Working --> Medium
    Medium --> LongTerm
    Medium --> Deep
    Curiosity -.->|explores gaps| Memory
    Janitor -.->|cleans| Medium
    Dreamer -.->|consolidates| Deep
    Evolution -.->|optimizes| Memory
```

### Data Flow

```
┌─────────────┐
│   AGENT     │ ←─── Reasoning + Synthesis
└──────┬──────┘
       │
       ▼
┌─────────────────────────────────────────┐
│            BRAIN API (FastAPI)           │
│  ┌─────────────────────────────────┐  │
│  │   Memory Integration Layer        │  │
│  │  ┌───────┐ ┌───────┐ ┌─────┐  │  │
│  │  │Redis  │ │SQLite │ │Neo4j│  │  │
│  │  │ Cache │ │Medium │ │Graph │  │  │
│  │  └───────┘ └───────┘ └──┬──┘  │  │
│  └─────────────────────────┼───────┘  │
└────────────────────────────┼────────────┘
                           │
                           ▼
              ┌──────────────────────┐
              │  Cognitive Engines   │
              │ Curiosity │ Janitor  │
              │ Dreamer  │ Evolution │
              └──────────────────────┘
```

### Cognitive Engine Cycle

```
┌─────────────────────────────────────────────────────────────┐
│                    AGENT SESSION                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   ┌─────────┐    Store    ┌─────────┐   Consolidate   ┌─────────┐
│   │ Working │────────────▶│ Medium  │───────────────▶│   Deep  │
│   │ (Redis) │   session   │ (SQLite)│   nightly     │ (Neo4j) │
│   └─────────┘    data      └─────────┘                └─────────┘
│        ▲              ▲                                   │
│        │              │                                   │
│   ┌────┴──────────────┴────┐                    ┌────┴────┐
│   │   Curiosity Engine     │                    │ Dreamer │
│   │  Finds knowledge gaps  │                    │ Engine  │
│   └───────────────────────┘                    └─────────┘
│        ▲              │                              │
│        │              │                              │
│   ┌────┴──────────────┴────┐               ┌────┴────────┐
│   │   Janitor Engine       │               │ Evolution  │
│   │ Resolves conflicts    │               │  Engine   │
│   └───────────────────────┘               └───────────┘
└─────────────────────────────────────────────────────────────┘
```

---

## 📊 Performance Metrics

The system tracks:

| Metric | Description | Target |
|--------|-------------|--------|
| Truth Rate | Ratio of verified truths to total facts | >95% |
| Memory Efficiency | Relevant context retrieval rate | >90% |
| Cognitive Cycles | Auto-evolution runs per day | 4-6 |
| Gap Coverage | Knowledge gaps filled over time | 80% |

---

## 🛠️ Tech Stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| **API** | FastAPI | HTTP endpoints |
| **Working Memory** | Redis | Session cache |
| **Medium Memory** | SQLite | Episode storage |
| **Long-Term Memory** | FastEmbed | Vector embeddings |
| **Deep Memory** | Neo4j | Knowledge graphs |
| **Orchestration** | Python asyncio | Concurrent engines |
| **Container** | Docker Compose | Full stack deploy |

---

## 📚 Further Reading

- [API Documentation](https://github.com/haroldfabla2-hue/silhouette-brain#api-usage)
- [Cognitive Engines Deep Dive](docs/cognitive_engines.md)
- [Architecture Decisions](docs/adr.md)
- [OpenClaw Integration](docs/openclaw.md)
