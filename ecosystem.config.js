// PM2 ecosystem config for Silhouette Brain v3.
// Secrets via environment — never hardcode here.
const path = require("path");

const BRAIN_ROOT = process.env.BRAIN_ROOT || __dirname;
const DATA_DIR = process.env.SILHOUETTE_DATA_DIR || process.env.BRAIN_DATA_DIR || path.join(BRAIN_ROOT, "data");
const LOGS_DIR = path.join(BRAIN_ROOT, "logs");

const commonEnv = {
  BRAIN_ROOT,
  SILHOUETTE_DATA_DIR: DATA_DIR,
  SILHOUETTE_NEO4J_URI:        process.env.SILHOUETTE_NEO4J_URI || process.env.NEO4J_URI || "bolt://localhost:17687",
  SILHOUETTE_NEO4J_USER:        process.env.SILHOUETTE_NEO4J_USER || process.env.NEO4J_USER || "neo4j",
  SILHOUETTE_NEO4J_PASSWORD:   process.env.SILHOUETTE_NEO4J_PASSWORD || process.env.NEO4J_PASSWORD,
  SILHOUETTE_REDIS_URL:        process.env.SILHOUETTE_REDIS_URL || process.env.REDIS_URL || "redis://localhost:6379",
  SILHOUETTE_REASONING_PROVIDER: process.env.SILHOUETTE_REASONING_PROVIDER || process.env.REASONING_PROVIDER || "none",
  SILHOUETTE_REASONING_API_KEY:  process.env.SILHOUETTE_REASONING_API_KEY || process.env.REASONING_API_KEY,
  PYTHONUNBUFFERED: "1",
};

module.exports = {
  apps: [
    {
      name: "silhouette-daemon",
      script: path.join(BRAIN_ROOT, "src", "silhouette", "daemon", "runner.py"),
      interpreter: "python3",
      cwd: BRAIN_ROOT,
      env: commonEnv,
      max_memory_restart: "3G",
      restart_delay: 10000,
      out_file: path.join(LOGS_DIR, "daemon.log"),
      err_file: path.join(LOGS_DIR, "daemon.err"),
    },
    {
      name: "silhouette-api",
      script: "silhouette",
      args: "serve",
      interpreter: "python3",
      cwd: BRAIN_ROOT,
      env: {
        ...commonEnv,
        SILHOUETTE_API_HOST: process.env.SILHOUETTE_API_HOST || "127.0.0.1",
        SILHOUETTE_API_PORT: process.env.SILHOUETTE_API_PORT || "9876",
      },
      max_memory_restart: "2G",
      restart_delay: 5000,
      out_file: path.join(LOGS_DIR, "api.log"),
      err_file: path.join(LOGS_DIR, "api.err"),
    },
  ],
};
