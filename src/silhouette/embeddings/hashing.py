"""A deterministic, dependency-free embedder.

This is the default so the whole system works with zero ML dependencies. It
uses the feature-hashing trick over word unigrams + bigrams with signed buckets
and L2 normalization. It is not as semantically rich as a transformer model,
but it is fast, stable, multilingual-agnostic, and good enough for tests and
small/offline deployments. Swap in :class:`FastEmbedEmbedder` for production.
"""

from __future__ import annotations

import hashlib
import re
from itertools import pairwise

from silhouette.embeddings.base import l2_normalize

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def _tokens(text: str) -> list[str]:
    words = _TOKEN_RE.findall(text.lower())
    grams = list(words)
    grams += [f"{a}_{b}" for a, b in pairwise(words)]
    return grams


def _bucket(token: str, dims: int) -> tuple[int, float]:
    digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
    idx = int.from_bytes(digest[:4], "little") % dims
    sign = 1.0 if (digest[4] & 1) == 0 else -1.0
    return idx, sign


class HashingEmbedder:
    def __init__(self, dims: int = 384) -> None:
        if dims <= 0:
            raise ValueError("dims must be positive")
        self._dims = dims

    @property
    def dims(self) -> int:
        return self._dims

    @property
    def name(self) -> str:
        return f"hashing-{self._dims}"

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self._dims
        for token in _tokens(text or ""):
            idx, sign = _bucket(token, self._dims)
            vec[idx] += sign
        return l2_normalize(vec)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]
