"""Tag matching shared by the memory stores."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

__all__ = ["normalize_tags", "matches_tags"]


def normalize_tags(tags: Iterable[str] | None) -> tuple[str, ...]:
    """Trim, drop empties and de-duplicate while preserving order."""
    if not tags:
        return ()
    seen: dict[str, None] = {}
    for tag in tags:
        cleaned = str(tag).strip()
        if cleaned:
            seen.setdefault(cleaned, None)
    return tuple(seen)


def matches_tags(record_tags: Sequence[str], wanted: Sequence[str]) -> bool:
    """Return True when the record carries at least one wanted tag.

    An empty ``wanted`` means "no filtering", so every record matches and the
    previous behaviour is preserved.

    The ANY semantics are deliberate. Callers compose their own policy by
    asking for the set of tags they are entitled to see -- for instance one
    subject plus a shared tag -- and never receive a record from outside that
    set. Keeping the rule this simple leaves the policy where it belongs, in
    the caller, and keeps this store generic.
    """
    if not wanted:
        return True
    return any(tag in wanted for tag in record_tags)
