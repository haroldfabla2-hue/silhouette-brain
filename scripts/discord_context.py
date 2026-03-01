#!/usr/bin/env python3
"""
Discord Context Client v2.0
============================
Cliente del Reasoning Engine para el bot de Discord (y cualquier canal externo).

Uso:
    from discord_context import DiscordContextClient

    client = DiscordContextClient()
    context_block = client.get_context_block(user_message)
    # → string <industrial-memory>...</industrial-memory> listo para prepender

    # O con síntesis completa:
    full = client.get_full_reasoning(user_message)
    print(full["synthesis"])
"""
import os
import json
import requests

BRAIN_API_URL  = os.getenv("BRAIN_API_URL", "http://localhost:9876")
REQUEST_TIMEOUT = 10  # segundos


class DiscordContextClient:
    """
    Cliente del motor de razonamiento de Silhouette Brain para canales externos.
    Llama automáticamente al Reasoning Engine antes de generar respuestas.
    """

    def __init__(self, api_url: str = BRAIN_API_URL):
        self.api_url = api_url.rstrip("/")
        self._reasoning_available: bool | None = None

    # -------------------------------------------------------------------------
    # Probe: detectar si el Reasoning Engine está disponible
    # -------------------------------------------------------------------------

    def _check_reasoning(self) -> bool:
        if self._reasoning_available is not None:
            return self._reasoning_available
        try:
            r = requests.get(
                f"{self.api_url}/api/status",
                timeout=5,
            )
            if r.status_code == 200:
                self._reasoning_available = r.json().get("features", {}).get("reasoning", False)
            else:
                self._reasoning_available = False
        except Exception:
            self._reasoning_available = False
        return self._reasoning_available

    # -------------------------------------------------------------------------
    # MÉTODO PRINCIPAL: contexto formateado listo para inyectar en el bot
    # -------------------------------------------------------------------------

    def get_context_block(
        self,
        message: str,
        *,
        sem_limit: int   = 5,
        rec_limit: int   = 3,
        hours:     int   = 2,
        min_score: float = 0.3,
        include_graph: bool = True,
    ) -> str:
        """
        Devuelve un bloque <industrial-memory>...</industrial-memory> listo para
        prepender al system prompt del bot de Discord.

        Args:
            message: El mensaje que acaba de enviar el usuario.

        Returns:
            String con el bloque de contexto, o "" si no hay contexto relevante.
        """
        if not message or not message.strip():
            return ""

        if self._check_reasoning():
            return self._get_via_reasoning(message, sem_limit, rec_limit, hours, min_score, include_graph, synthesize=False)
        else:
            return self._get_via_legacy(message, sem_limit, rec_limit, hours, min_score)

    def get_full_reasoning(
        self,
        message: str,
        *,
        sem_limit: int   = 8,
        rec_limit: int   = 4,
        hours:     int   = 4,
        min_score: float = 0.2,
    ) -> dict:
        """
        Contexto completo CON síntesis GLM-4.7-flash.
        Útil cuando el bot necesita razonamiento profundo (comandos /think, etc.).

        Returns:
            dict con: synthesis, formatted_context, semantic[], recent[], graph[]
        """
        try:
            r = requests.get(
                f"{self.api_url}/api/reasoning/context",
                params={
                    "query":             message[:512],
                    "sem_limit":         sem_limit,
                    "rec_limit":         rec_limit,
                    "hours":             hours,
                    "min_score":         min_score,
                    "graph":             "true",
                    "tiers":             "true",
                    "synthesize":        "true",
                    "filter_heartbeats": "true",
                },
                timeout=REQUEST_TIMEOUT,
            )
            if r.status_code == 200:
                return r.json()
        except Exception as e:
            print(f"[DiscordContext] get_full_reasoning error: {e}")

        return {"synthesis": "", "formatted_context": "", "semantic": [], "recent": [], "graph": []}

    # -------------------------------------------------------------------------
    # Guardar mensaje de Discord en memoria
    # -------------------------------------------------------------------------

    def save_message(
        self,
        content:      str,
        channel:      str,
        speaker:      str  = "user",
        importance:   float = 0.7,
    ) -> bool:
        """
        Guarda un mensaje del canal de Discord en Silhouette Brain.
        Llama esto para INCOMING (mensaje del usuario) y OUTGOING (respuesta del bot).
        """
        if not content or not content.strip():
            return False

        payload = {
            "text":       content[:500],
            "importance": importance,
            "tier":       "MEDIUM",
            "category":   "discord",
            "metadata": {
                "channel": channel,
                "speaker": speaker,
            },
        }
        try:
            r = requests.post(
                f"{self.api_url}/api/memory",
                json=payload,
                timeout=REQUEST_TIMEOUT,
            )
            return r.status_code in (200, 201)
        except Exception as e:
            print(f"[DiscordContext] save_message error: {e}")
            return False

    # -------------------------------------------------------------------------
    # Internals
    # -------------------------------------------------------------------------

    def _get_via_reasoning(
        self, message, sem_limit, rec_limit, hours, min_score, include_graph, synthesize
    ) -> str:
        try:
            r = requests.get(
                f"{self.api_url}/api/reasoning/context",
                params={
                    "query":             message[:512],
                    "sem_limit":         sem_limit,
                    "rec_limit":         rec_limit,
                    "hours":             hours,
                    "min_score":         min_score,
                    "graph":             "true" if include_graph else "false",
                    "tiers":             "false",
                    "synthesize":        "true" if synthesize else "false",
                    "filter_heartbeats": "true",
                },
                timeout=REQUEST_TIMEOUT,
            )
            if r.status_code == 200:
                data = r.json()
                return data.get("formatted_context", "")
        except Exception as e:
            print(f"[DiscordContext] reasoning error: {e}")
        return ""

    def _get_via_legacy(self, message, sem_limit, rec_limit, hours, min_score) -> str:
        """Fallback al endpoint /api/memory/context (v1)."""
        try:
            r = requests.get(
                f"{self.api_url}/api/memory/context",
                params={
                    "query":             message[:512],
                    "sem_limit":         sem_limit,
                    "rec_limit":         rec_limit,
                    "hours":             hours,
                    "min_score":         min_score,
                    "filter_heartbeats": "true",
                },
                timeout=REQUEST_TIMEOUT,
            )
            if r.status_code != 200:
                return ""
            data     = r.json()
            semantic = data.get("semantic", [])
            recent   = data.get("recent",   [])
            if not semantic and not recent:
                return ""

            lines = []
            if recent:
                lines.append("── CONTEXTO RECIENTE ──")
                for c in recent[:rec_limit]:
                    who = "Alberto" if c.get("speaker") == "user" else c.get("speaker", "?")
                    lines.append(f"[{c.get('datetime','')}] <{who}> {c.get('message','')[:150]}")
            if semantic:
                if lines: lines.append("")
                lines.append("── MEMORIA RELEVANTE ──")
                for s in semantic[:sem_limit]:
                    pct = int(float(s.get("similarity", 0)) * 100)
                    lines.append(f"[{pct}%] {s.get('message','')[:180]}")

            return "<industrial-memory>\n" + "\n".join(lines) + "\n</industrial-memory>"
        except Exception as e:
            print(f"[DiscordContext] legacy error: {e}")
            return ""


# -------------------------------------------------------------------------
# Funciones de compatibilidad con el bot existente
# -------------------------------------------------------------------------

_default_client = DiscordContextClient()


def get_context_for_iris():
    """Compatibilidad con uso anterior — busca contexto sobre Iris."""
    return _default_client.get_context_block("Iris protocolo check-in")


def search_context(query: str) -> str:
    """Compatibilidad: devuelve bloque de contexto para un query."""
    return _default_client.get_context_block(query)


def get_discord_context(message: str, channel: str = "") -> str:
    """
    Helper principal para el bot de Discord.

    Uso en el bot:
        context = get_discord_context(user_message, channel_id)
        system_prompt = context + "\\n\\n" + base_system_prompt
    """
    return _default_client.get_context_block(message)


def save_discord_message(content: str, channel: str, message_type: str, metadata: dict = None) -> bool:
    """Compatibilidad con discord_memory_manager.save_discord_message."""
    speaker = "user" if message_type == "incoming" else "bot"
    return _default_client.save_message(content, channel, speaker=speaker)


# -------------------------------------------------------------------------
# Test
# -------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    client = DiscordContextClient()

    print("=== Discord Context Client v2.0 ===\n")
    print(f"Reasoning Engine disponible: {client._check_reasoning()}\n")

    print("--- Test: get_context_block ---")
    block = client.get_context_block("¿Cuáles son los proyectos de Alberto en Brandistry?")
    print(block or "[Sin contexto recuperado]")

    print("\n--- Test: get_full_reasoning ---")
    full = client.get_full_reasoning("¿Qué sabe Silhouette sobre automatización?")
    print(f"Síntesis: {full.get('synthesis', '[vacía]')}")
    print(f"Semánticos: {len(full.get('semantic', []))}")
    print(f"Recientes:  {len(full.get('recent', []))}")
    print(f"Grafo:      {len(full.get('graph', []))}")
