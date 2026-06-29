"""Turn retrieved memories into a short synthesized answer.

The default :class:`ExtractiveSynthesizer` needs no network or API key: it
stitches together the most relevant snippets. When a reasoning provider is
configured, :class:`LLMSynthesizer` produces a fluent answer via an
OpenAI-compatible chat endpoint.
"""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

from silhouette.config import Settings, get_settings
from silhouette.models import MemoryRecord, ScoredRecord

logger = logging.getLogger("silhouette.reasoning")


@runtime_checkable
class Synthesizer(Protocol):
    @property
    def name(self) -> str: ...

    def synthesize(
        self, query: str, semantic: list[ScoredRecord], recent: list[MemoryRecord]
    ) -> str: ...


class ExtractiveSynthesizer:
    """Dependency-free synthesis: concise, sourced extract of top snippets."""

    name = "extractive"

    def synthesize(
        self, query: str, semantic: list[ScoredRecord], recent: list[MemoryRecord]
    ) -> str:
        snippets: list[str] = []
        for s in semantic[:3]:
            snippets.append(f"- ({s.score:.2f}) {s.record.content.strip()}")
        for r in recent[:2]:
            text = r.content.strip()
            if all(text not in line for line in snippets):
                snippets.append(f"- (recent) {text}")
        if not snippets:
            return f"No relevant memory found for: {query}"
        header = f"Relevant memory for '{query}':"
        return header + "\n" + "\n".join(snippets)


class LLMSynthesizer:  # pragma: no cover - requires network/provider
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @property
    def name(self) -> str:
        return f"{self._settings.reasoning_provider}:{self._settings.reasoning_model}"

    def _base_url(self) -> str:
        if self._settings.reasoning_base_url:
            return self._settings.reasoning_base_url.rstrip("/")
        return {
            "openai": "https://api.openai.com/v1",
            "minimax": "https://api.minimax.chat/v1",
        }.get(self._settings.reasoning_provider, "https://api.openai.com/v1")

    def synthesize(
        self, query: str, semantic: list[ScoredRecord], recent: list[MemoryRecord]
    ) -> str:
        import httpx

        context = "\n".join(
            [f"- {s.record.content}" for s in semantic[:5]]
            + [f"- {r.content}" for r in recent[:3]]
        )
        messages = [
            {
                "role": "system",
                "content": "You answer using ONLY the provided memory context. "
                "Be concise and cite nothing you cannot see.",
            },
            {"role": "user", "content": f"Memory:\n{context}\n\nQuestion: {query}"},
        ]
        resp = httpx.post(
            f"{self._base_url()}/chat/completions",
            headers={"Authorization": f"Bearer {self._settings.reasoning_api_key}"},
            json={"model": self._settings.reasoning_model, "messages": messages},
            timeout=30.0,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()


def get_synthesizer(settings: Settings | None = None) -> Synthesizer:
    settings = settings or get_settings()
    if settings.reasoning_provider != "none" and settings.reasoning_api_key:
        try:
            return LLMSynthesizer(settings)
        except Exception as exc:  # pragma: no cover
            logger.warning("LLM synthesizer unavailable (%s); using extractive", exc)
    return ExtractiveSynthesizer()
