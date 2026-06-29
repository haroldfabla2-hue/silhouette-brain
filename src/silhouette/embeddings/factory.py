"""Select the best available embedder given the settings."""

from __future__ import annotations

import logging

from silhouette.config import Settings, get_settings
from silhouette.embeddings.base import Embedder
from silhouette.embeddings.hashing import HashingEmbedder

logger = logging.getLogger("silhouette.embeddings")


def get_embedder(settings: Settings | None = None) -> Embedder:
    """Return a fastembed embedder when possible, else the hashing fallback."""
    settings = settings or get_settings()
    if settings.use_fastembed:
        try:
            from silhouette.embeddings.fastembed_embedder import FastEmbedEmbedder

            embedder = FastEmbedEmbedder(settings.embedding_model, settings.embedding_dims)
            logger.info("Using %s", embedder.name)
            return embedder
        except Exception as exc:  # pragma: no cover - depends on optional dep
            logger.warning(
                "fastembed unavailable (%s); falling back to dependency-free embedder",
                exc,
            )
    return HashingEmbedder(settings.embedding_dims)
