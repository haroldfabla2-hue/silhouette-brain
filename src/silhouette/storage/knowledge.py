"""Evidence-linked proposals, never executable instructions or assumed facts."""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path

from silhouette.storage.sqlite import connect, writing


class KnowledgeStore:
    """Store reviewed claims and procedures separately from episodic evidence.

    Extraction is deliberately out of scope: callers propose structured data,
    and review is required before any claim is shown as accepted. Procedures
    are never automatically executed by this registry.
    """

    def __init__(self, path: str | Path) -> None:
        self._conn = connect(path)
        with writing(self._conn):
            self._conn.execute("""CREATE TABLE IF NOT EXISTS claims (
                id TEXT PRIMARY KEY, subject TEXT NOT NULL, predicate TEXT NOT NULL,
                object TEXT NOT NULL, polarity INTEGER NOT NULL,
                valid_from REAL, valid_to REAL, observed_at REAL NOT NULL,
                evidence TEXT NOT NULL, confidence REAL NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('PROPOSED','ACCEPTED','CONFLICTED','SUPERSEDED'))
                )""")
            self._conn.execute("""CREATE TABLE IF NOT EXISTS procedures (
                id TEXT PRIMARY KEY, version INTEGER NOT NULL,
                precondition TEXT NOT NULL, steps TEXT NOT NULL,
                postcondition TEXT NOT NULL, evidence TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('PROPOSED','APPROVED','REVOKED')),
                UNIQUE (id, version))""")

    def propose_claim(self, subject: str, predicate: str, object_: str, *,
                      evidence: list[str], confidence: float = 0.5,
                      polarity: bool = True, valid_from: float | None = None,
                      valid_to: float | None = None) -> str:
        if not evidence or any(not item for item in evidence):
            raise ValueError("Claim requires episode evidence IDs")
        if not 0 <= confidence <= 1 or (valid_from is not None and valid_to is not None
                                        and valid_to < valid_from):
            raise ValueError("Invalid confidence or valid interval")
        claim_id = uuid.uuid4().hex
        with writing(self._conn):
            conflicts = self._conn.execute("""SELECT * FROM claims WHERE subject=?
                AND predicate=? AND status='ACCEPTED' AND (object != ? OR polarity != ?)""",
                (subject, predicate, object_, int(polarity))).fetchall()
            overlapping = any((valid_to is None or row["valid_from"] is None
                               or valid_to >= row["valid_from"])
                              and (row["valid_to"] is None or valid_from is None
                                   or row["valid_to"] >= valid_from) for row in conflicts)
            status = "CONFLICTED" if overlapping else "PROPOSED"
            self._conn.execute("""INSERT INTO claims VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                               (claim_id, subject, predicate, object_, int(polarity),
                                valid_from, valid_to, time.time(), json.dumps(evidence),
                                confidence, status))
        return claim_id

    def claim(self, claim_id: str) -> sqlite3.Row | None:
        return self._conn.execute("SELECT * FROM claims WHERE id=?", (claim_id,)).fetchone()

    def approve_claim(self, claim_id: str) -> None:
        with writing(self._conn):
            row = self.claim(claim_id)
            if row is None or row["status"] != "PROPOSED":
                raise ValueError("Only non-conflicted proposals can be reviewed as facts")
            self._conn.execute("UPDATE claims SET status='ACCEPTED' WHERE id=?", (claim_id,))

    def retract_evidence(self, episode_id: str) -> int:
        """Invalidate derivations when their source is forgotten."""
        changed = 0
        with writing(self._conn):
            for row in self._conn.execute("SELECT id, evidence FROM claims").fetchall():
                if episode_id in json.loads(row["evidence"]):
                    self._conn.execute("UPDATE claims SET status='SUPERSEDED' WHERE id=?", (row["id"],))
                    changed += 1
            for row in self._conn.execute("SELECT id, evidence FROM procedures WHERE status!='REVOKED'").fetchall():
                if episode_id in json.loads(row["evidence"]):
                    self._conn.execute("UPDATE procedures SET status='REVOKED' WHERE id=?", (row["id"],))
                    changed += 1
        return changed

    def propose_procedure(self, precondition: str, steps: list[str],
                          postcondition: str, *, evidence: list[str]) -> str:
        if not evidence or not steps or not all(evidence) or not all(steps):
            raise ValueError("A procedure needs observed evidence and steps")
        procedure_id = uuid.uuid4().hex
        with writing(self._conn):
            self._conn.execute("INSERT INTO procedures VALUES (?, 1, ?, ?, ?, ?, 'PROPOSED')",
                               (procedure_id, precondition, json.dumps(steps),
                                postcondition, json.dumps(evidence)))
        return procedure_id

    def close(self) -> None:
        self._conn.close()
