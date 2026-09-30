"""Explicit, reversible retrieval priority. Scores never delete source episodes."""

from __future__ import annotations

import math
import time
from collections.abc import Sequence


def activation_score(created_at: float, accesses: Sequence[float], *,
                     now: float | None = None, importance: float = 0.5,
                     protected: bool = False) -> dict[str, float | bool]:
    """A bounded ACT-R-inspired score with independently visible components.

    Caller records *meaningful* accesses explicitly; automatic searches must
    not reinforce memories merely because they were returned in a result.
    """
    clock = time.time() if now is None else now
    age_days = max(0.0, (clock - created_at) / 86400)
    unique_days = sorted({int(max(created_at, stamp) / 86400) for stamp in accesses
                          if created_at <= stamp <= clock})[-30:]
    # Cap one reinforcement per day, so repeated refreshes cannot dominate.
    strength = (age_days + 1) ** -0.5
    strength += sum(((clock / 86400 - day) + 1) ** -0.5 for day in unique_days)
    base = math.log(strength)
    salience = max(0.0, min(1.0, importance))
    recency = 0.25 / (age_days + 1)
    return {"score": base + salience + recency,
            "base": base, "salience": salience, "recency": recency,
            "protected": protected, "access_days": float(len(unique_days))}
