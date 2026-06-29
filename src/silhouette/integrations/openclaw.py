"""Sync OpenClaw agent session JSONL files into the memory system.

When ``SILHOUETTE_OPENCLAW_AGENTS_DIR`` points at an OpenClaw agents tree
(``.../agents/<name>/sessions/*.jsonl``), this module tails those files and
ingests new user/assistant messages via :meth:`MemorySystem.remember`.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from silhouette.config import Settings, get_settings
from silhouette.security.noise import should_skip_ingestion
from silhouette.storage.memory import MemorySystem

logger = logging.getLogger("silhouette.integrations.openclaw")


def _extract_text(line: str) -> str | None:
    try:
        data = json.loads(line)
        if data.get("type") in ("session", "model_change"):
            return None
        msg = data.get("message", {})
        content = msg.get("content", [])
        if isinstance(content, list):
            parts = [
                block.get("text", "")
                for block in content
                if isinstance(block, dict) and block.get("text")
            ]
            return " ".join(parts) if parts else None
        return content if isinstance(content, str) else None
    except (json.JSONDecodeError, AttributeError):
        return None


@dataclass
class OpenClawSessionSync:
    agents_dir: Path
    state_path: Path
    _offsets: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._load_state()

    def _load_state(self) -> None:
        if self.state_path.exists():
            try:
                data = json.loads(self.state_path.read_text(encoding="utf-8"))
                self._offsets = dict(data.get("offsets", {}))
            except json.JSONDecodeError:
                self._offsets = {}

    def _save_state(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(
            json.dumps({"offsets": self._offsets}, indent=2),
            encoding="utf-8",
        )

    def _session_files(self) -> list[tuple[Path, str]]:
        if not self.agents_dir.is_dir():
            return []
        out: list[tuple[Path, str]] = []
        for agent_dir in self.agents_dir.iterdir():
            sessions = agent_dir / "sessions"
            if not sessions.is_dir():
                continue
            for path in sessions.glob("*.jsonl"):
                if path.name.endswith(".lock"):
                    continue
                out.append((path, agent_dir.name))
        return out

    def sync(self, memory: MemorySystem) -> dict[str, object]:
        ingested = 0
        skipped = 0
        files_seen = 0

        for path, agent in self._session_files():
            files_seen += 1
            key = f"{agent}:{path.name}"
            size = path.stat().st_size
            offset = self._offsets.get(key, 0)
            if size <= offset:
                continue

            with path.open(encoding="utf-8") as fh:
                fh.seek(offset)
                for line in fh:
                    text = _extract_text(line)
                    if not text or len(text.strip()) < 8:
                        continue
                    if should_skip_ingestion(text):
                        skipped += 1
                        continue
                    memory.remember(
                        text,
                        importance=0.4,
                        tags=["openclaw", f"agent:{agent}"],
                        source=f"openclaw:{agent}",
                    )
                    ingested += 1
            self._offsets[key] = size

        self._save_state()
        summary = f"synced {ingested} messages from {files_seen} session files ({skipped} skipped as noise)"
        logger.info(summary)
        return {
            "files_seen": files_seen,
            "ingested": ingested,
            "skipped_noise": skipped,
            "summary": summary,
        }


def sync_openclaw_sessions(
    memory: MemorySystem | None = None,
    settings: Settings | None = None,
) -> dict[str, object]:
    settings = settings or get_settings()
    memory = memory or MemorySystem(settings)
    if not settings.openclaw_agents_dir:
        return {"skipped": True, "reason": "SILHOUETTE_OPENCLAW_AGENTS_DIR not set"}
    syncer = OpenClawSessionSync(
        agents_dir=settings.openclaw_agents_dir,
        state_path=settings.db_path("openclaw_sync_state.json"),
    )
    return syncer.sync(memory)
