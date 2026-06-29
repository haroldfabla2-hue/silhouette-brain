"""Optional fastembed-backed embedder (ONNX, multilingual, no API key).

Imported lazily by the factory so that ``fastembed`` is only required when it
is actually requested and installed.
"""

from __future__ import annotations

from silhouette.embeddings.base import l2_normalize


class FastEmbedEmbedder:
    def __init__(self, model_name: str, dims: int) -> None:
        from fastembed import TextEmbedding

        self._model_name = model_name
        self._dims = dims
        self._model = TextEmbedding(model_name)

    @property
    def dims(self) -> int:
        return self._dims

    @property
    def name(self) -> str:
        return f"fastembed:{self._model_name}"

    def embed(self, text: str) -> list[float]:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        vectors = list(self._model.embed([t or "" for t in texts]))
        return [l2_normalize([float(x) for x in v]) for v in vectors]
