module.exports = {
  apps: [
    {
      name: "silhouette-unified-daemon",
      script: "/home/ubuntu/.openclaw/workspace/silhouette-brain/src/core/unified_daemon.py",
      interpreter: "python3",
      cwd: "/home/ubuntu/.openclaw/workspace/silhouette-brain",
      env: {
        BRAIN_ROOT:          "/home/ubuntu/.openclaw/workspace/silhouette-brain",
        BRAIN_SRC_DIR:       "/home/ubuntu/.openclaw/workspace/silhouette-brain/src/core",
        BRAIN_DATA_DIR:      "/home/ubuntu/.openclaw/workspace/silhouette-brain/data",
        // Multi-provider settings for reasoning (minimax, openai, anthropic, zhipu)
        REASONING_PROVIDER:  "minimax",
        REASONING_API_KEY:   "sk-cp-xncSehim5dGFqvsdPbo5IyTKNwNewWRCrf53Fd2uOPk0CKlBpa-20kvtX8yFB-P1tJlfrkuraIOFyMXw5iPhY6CPKU1kZQvmNG7SWLYHlYMFnXxNYs2-gPI",
        REASONING_MODEL:     "MiniMax-M2.5",
        // Neo4j Settings
        NEO4J_URI:           "bolt://localhost:17687",
        NEO4J_USER:          "neo4j",
        NEO4J_PASSWORD:      "silhouette2035",
        // Local Embeddings
        FASTEMBED_MODEL:     "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        // Database Connections (Docker)
        NEO4J_URI:           "bolt://localhost:7687",
        NEO4J_USER:          "neo4j",
        NEO4J_PASSWORD:      "openclaw123",
        REDIS_URL:           "redis://localhost:6379",
        PYTHONUNBUFFERED:    "1",
        PYTHONPATH:          "/home/ubuntu/.openclaw/workspace/silhouette-brain/src/core:/home/ubuntu/.openclaw/workspace/silhouette-brain/src/api",
      },
      // Reiniciar solo si supera 500MB (no por crashes normales de tareas)
      max_memory_restart: "500M",
      restart_delay:       5000,    // 5s antes de reiniciar
      max_restarts:        10,      // máximo 10 reinicios consecutivos
      min_uptime:          "30s",   // debe vivir 30s para resetear contador
      // Logs
      out_file:  "/home/ubuntu/.openclaw/workspace/silhouette-brain/logs/unified_daemon.log",
      err_file:  "/home/ubuntu/.openclaw/workspace/silhouette-brain/logs/unified_daemon.err",
      log_date_format: "YYYY-MM-DD HH:mm:ss",
      merge_logs: false,
    },
    {
      name: "silhouette-memory-api",
      script: "/home/ubuntu/.openclaw/workspace/silhouette-brain/src/api/enhanced_memory_api.py",
      interpreter: "python3",
      cwd: "/home/ubuntu/.openclaw/workspace/silhouette-brain",
      env: {
        BRAIN_ROOT:          "/home/ubuntu/.openclaw/workspace/silhouette-brain",
        BRAIN_SRC_DIR:       "/home/ubuntu/.openclaw/workspace/silhouette-brain/src/core",
        BRAIN_DATA_DIR:      "/home/ubuntu/.openclaw/workspace/silhouette-brain/data",
        NEO4J_URI:           "bolt://localhost:7687",
        NEO4J_USER:          "neo4j",
        NEO4J_PASSWORD:      "openclaw123",
        REDIS_URL:           "redis://localhost:6379",
        PYTHONPATH:          "/home/ubuntu/.openclaw/workspace/silhouette-brain/src/core:/home/ubuntu/.openclaw/workspace/silhouette-brain/src/api",
        PYTHONUNBUFFERED:    "1"
      },
      max_memory_restart: "300M",
      restart_delay:       2000,
      out_file:  "/home/ubuntu/.openclaw/workspace/silhouette-brain/logs/memory_api.log",
      err_file:  "/home/ubuntu/.openclaw/workspace/silhouette-brain/logs/memory_api.err",
      log_date_format: "YYYY-MM-DD HH:mm:ss",
    }
  ]
};
