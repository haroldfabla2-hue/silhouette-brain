"""Lightweight, dependency-free entity extraction.

This is deliberately simple and explainable (no heavy NLP): it surfaces
hashtags, @mentions, and multi-word Capitalized spans, which is enough to build
a useful relationship graph. It can be swapped for an NER model later without
touching the rest of the system.
"""

from __future__ import annotations

import re

_HASHTAG = re.compile(r"#(\w{2,})")
_MENTION = re.compile(r"@(\w{2,})")
# Sequences of Capitalized words (incl. accented chars), length >= 1.
_PROPER = re.compile(r"\b([A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ]+)*)\b")

_STOPWORDS = {
    "El", "La", "Los", "Las", "Un", "Una", "Y", "O", "De", "En", "The", "A",
    "An", "And", "Or", "If", "It", "I", "We", "You",
}


def extract_entities(text: str) -> list[tuple[str, str]]:
    """Return a de-duplicated list of ``(name, type)`` pairs.

    Types: ``topic`` (hashtag), ``person`` (mention), ``concept`` (proper noun).
    """
    found: dict[str, str] = {}

    for tag in _HASHTAG.findall(text or ""):
        found.setdefault(tag.lower(), "topic")
    for mention in _MENTION.findall(text or ""):
        found.setdefault(mention.lower(), "person")
    for span in _PROPER.findall(text or ""):
        span = span.strip()
        if span in _STOPWORDS or len(span) < 3:
            continue
        found.setdefault(span, "concept")

    return list(found.items())
