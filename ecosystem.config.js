module.exports = {
  apps: [
    {
      name: "silhouette-unified-daemon",
      script: "/root/silhouette-brain/src/core/unified_daemon.py",
      interpreter: "python3",
      cwd: "/root/silhouette-brain",
      env: {
        BRAIN_ROOT:          "/root/silhouette-brain",
        BRAIN_SRC_DIR:       "/root/silhouette-brain/src/core",
        BRAIN_DATA_DIR:      "/root/silhouette-brain/data",
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
        PYTHONUNBUFFERED:    "1",
        PYTHONPATH:          "/root/silhouette-brain/src/core:/root/silhouette-brain/src/api",
      },
      // Reiniciar solo si supera 500MB (no por crashes normales de tareas)
      max_memory_restart: "500M",
      restart_delay:       5000,    // 5s antes de reiniciar
      max_restarts:        10,      // máximo 10 reinicios consecutivos
      min_uptime:          "30s",   // debe vivir 30s para resetear contador
      // Logs
      out_file:  "/root/silhouette-brain/logs/unified_daemon.log",
      err_file:  "/root/silhouette-brain/logs/unified_daemon.err",
      log_date_format: "YYYY-MM-DD HH:mm:ss",
      merge_logs: false,
    }
  ]
};
