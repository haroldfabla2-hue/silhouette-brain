"""Pluggable text embedders with a dependency-free default."""

from silhouette.embeddings.base import Embedder, cosine_similarity
from silhouette.embeddings.factory import get_embedder
from silhouette.embeddings.hashing import HashingEmbedder

__all__ = ["Embedder", "HashingEmbedder", "cosine_similarity", "get_embedder"]
