// PM2 ecosystem config.
// Paths are derived from this file's location (__dirname) so the project can
// live anywhere. Secrets (API keys, DB passwords) are NEVER hardcoded here —
// they are read from the parent process environment (e.g. exported in your
// shell or loaded from a .env via `pm2 start ecosystem.config.js`).
const path = require("path");

const BRAIN_ROOT = process.env.BRAIN_ROOT || __dirname;
const SRC_CORE = path.join(BRAIN_ROOT, "src", "core");
const SRC_API = path.join(BRAIN_ROOT, "src", "api");
const DATA_DIR = process.env.BRAIN_DATA_DIR || path.join(BRAIN_ROOT, "data");
const LOGS_DIR = path.join(BRAIN_ROOT, "logs");

const commonEnv = {
  BRAIN_ROOT:       BRAIN_ROOT,
  BRAIN_SRC_DIR:    SRC_CORE,
  BRAIN_DATA_DIR:   DATA_DIR,
  NEO4J_URI:        process.env.NEO4J_URI || "bolt://localhost:17687",
  NEO4J_USER:       process.env.NEO4J_USER || "neo4j",
  NEO4J_PASSWORD:   process.env.NEO4J_PASSWORD,
  REDIS_URL:        process.env.REDIS_URL || "redis://localhost:6379",
  PYTHONPATH:       `${SRC_CORE}:${SRC_API}`,
  PYTHONUNBUFFERED: "1",
};

module.exports = {
  apps: [
    {
      name: "silhouette-unified-daemon",
      script: path.join(SRC_CORE, "unified_daemon.py"),
      interpreter: "python3",
      cwd: BRAIN_ROOT,
      env: {
        ...commonEnv,
        // Multi-provider settings for reasoning (minimax, openai, anthropic, zhipu)
        REASONING_PROVIDER:  process.env.REASONING_PROVIDER || "minimax",
        REASONING_API_KEY:   process.env.REASONING_API_KEY,
        REASONING_MODEL:     process.env.REASONING_MODEL || "MiniMax-M2.5",
        FASTEMBED_MODEL:     process.env.FASTEMBED_MODEL || "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
      },
      // Aumentar a 3GB para evitar reinicios por fastembed
      max_memory_restart: "3G",
      restart_delay:       10000,   // 10s antes de reiniciar
      max_restarts:        10,
      min_uptime:          "60s",
      out_file:  path.join(LOGS_DIR, "unified_daemon.log"),
      err_file:  path.join(LOGS_DIR, "unified_daemon.err"),
      log_date_format: "YYYY-MM-DD HH:mm:ss",
      merge_logs: false,
    },
    {
      name: "silhouette-memory-api",
      script: path.join(SRC_API, "enhanced_memory_api.py"),
      interpreter: "python3",
      cwd: BRAIN_ROOT,
      env: {
        ...commonEnv,
      },
      max_memory_restart: "2G",
      restart_delay:       5000,
      out_file:  path.join(LOGS_DIR, "memory_api.log"),
      err_file:  path.join(LOGS_DIR, "memory_api.err"),
      log_date_format: "YYYY-MM-DD HH:mm:ss",
    }
  ]
};
