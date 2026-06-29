# Silhouette Brain — production image for the v3 'silhouette' package.
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    SILHOUETTE_DATA_DIR=/data \
    SILHOUETTE_API_HOST=0.0.0.0 \
    SILHOUETTE_API_PORT=9876

WORKDIR /app

# Install dependencies first for better layer caching.
COPY pyproject.toml README.md ./
COPY src ./src
# Install with all production backends (embeddings, graph, cache, api, llm).
RUN pip install ".[all]"

# Persistent data (SQLite tiers, heartbeat, evolution state) lives here.
RUN mkdir -p /data
VOLUME ["/data"]

EXPOSE 9876

# Default: serve the HTTP API. Override the command with `silhouette daemon`
# to run the cognitive engines (see docker-compose.yml).
CMD ["silhouette", "serve"]
