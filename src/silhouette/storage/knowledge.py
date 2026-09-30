"""Evidence-linked proposals, never executable instructions or assumed facts."""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from collections.abc import Callable
from pathlib import Path

from silhouette.models import MemoryRecord
from silhouette.storage.critic import EvidenceSpan, SummaryStatement, verify_summary
from silhouette.storage.sqlite import connect, writing


class KnowledgeStore:
    """Store reviewed claims and procedures separately from episodic evidence.

    Extraction is deliberately out of scope: callers propose structured data,
    and review is required before any claim is shown as accepted. Procedures
    are never automatically executed by this registry.
    """

    def __init__(self, path: str | Path, *, resolve_evidence: Callable[[str], MemoryRecord | None] | None = None) -> None:
        self._conn = connect(path)
        self._resolve_evidence = resolve_evidence
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

            self._conn.execute("""CREATE TABLE IF NOT EXISTS reviews (
                id TEXT PRIMARY KEY, kind TEXT NOT NULL, target_id TEXT NOT NULL,
                reviewer TEXT NOT NULL, decision TEXT NOT NULL, reason TEXT NOT NULL,
                reviewed_at REAL NOT NULL)""")
            self._conn.execute("""CREATE TABLE IF NOT EXISTS summaries (
                id TEXT PRIMARY KEY, statements TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('PROPOSED','VERIFIED_EXTRACT','REJECTED','REVOKED')),
                errors TEXT NOT NULL)""")

    def _evidence_live(self, evidence: list[str]) -> bool:
        # Standalone stores retain compatibility; verified workflows require a resolver.
        return bool(evidence) and (self._resolve_evidence is None or
                                  all(self._resolve_evidence(item) is not None for item in evidence))

    def _review(self, kind: str, target_id: str, reviewer: str,
                decision: str, reason: str) -> None:
        self._conn.execute("INSERT INTO reviews VALUES (?, ?, ?, ?, ?, ?, ?)",
                           (uuid.uuid4().hex, kind, target_id, reviewer,
                            decision, reason, time.time()))

    def _conflicts(self, row: sqlite3.Row) -> list[str]:
        candidates = self._conn.execute("""SELECT * FROM claims WHERE subject=?
            AND predicate=? AND status='ACCEPTED' AND id!=?
            AND (object!=? OR polarity!=?)""",
            (row['subject'], row['predicate'], row['id'], row['object'], row['polarity'])).fetchall()
        return [other['id'] for other in candidates
                if (row['valid_to'] is None or other['valid_from'] is None
                    or row['valid_to'] >= other['valid_from'])
                and (other['valid_to'] is None or row['valid_from'] is None
                     or other['valid_to'] >= row['valid_from'])]

    def conflicts(self, claim_id: str) -> list[str]:
        row = self.claim(claim_id)
        return self._conflicts(row) if row is not None else []

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

    def approve_claim(self, claim_id: str, *, reviewer: str = 'manual', reason: str = 'reviewed') -> None:
        if not reviewer.strip() or not reason.strip():
            raise ValueError("Review identity and reason required")
        conflict = False
        with writing(self._conn):
            # Acquire the SQLite writer lock before the check, including across processes.
            self._conn.execute("UPDATE claims SET status=status WHERE id=?", (claim_id,))
            row = self.claim(claim_id)
            if row is None or row['status'] != 'PROPOSED':
                raise ValueError("Only non-conflicted proposals can be reviewed as facts")
            if not self._evidence_live(json.loads(row['evidence'])):
                raise ValueError("Missing or retracted evidence")
            if self._conflicts(row):
                self._conn.execute("UPDATE claims SET status='CONFLICTED' WHERE id=?", (claim_id,))
                self._review('claim', claim_id, reviewer, 'CONFLICTED', reason)
                conflict = True
            else:
                self._conn.execute("UPDATE claims SET status='ACCEPTED' WHERE id=?", (claim_id,))
                self._review('claim', claim_id, reviewer, 'ACCEPTED', reason)
        if conflict:
            raise ValueError("Overlapping accepted claim requires conflict review")

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
            for row in self._conn.execute("SELECT id, statements FROM summaries WHERE status!='REVOKED'").fetchall():
                if any(item['citation']['episode_id'] == episode_id
                       for item in json.loads(row['statements'])):
                    self._conn.execute("UPDATE summaries SET status='REVOKED' WHERE id=?", (row['id'],))
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

    def propose_summary(self, statements: list[SummaryStatement]) -> str:
        from dataclasses import asdict

        summary_id = uuid.uuid4().hex
        with writing(self._conn):
            self._conn.execute("INSERT INTO summaries VALUES (?, ?, 'PROPOSED', '[]')",
                               (summary_id, json.dumps([asdict(item) for item in statements])))
        return summary_id

    def summary(self, summary_id: str) -> sqlite3.Row | None:
        return self._conn.execute("SELECT * FROM summaries WHERE id=?", (summary_id,)).fetchone()

    def verify_summary(self, summary_id: str) -> list[str]:
        if self._resolve_evidence is None:
            raise ValueError("Summary critic requires a live episode resolver")
        with writing(self._conn):
            self._conn.execute("UPDATE summaries SET status=status WHERE id=?", (summary_id,))
            row = self.summary(summary_id)
            if row is None or row['status'] == 'REVOKED':
                raise ValueError("Unknown or revoked summary")
            statements = [SummaryStatement(item['text'], EvidenceSpan(**item['citation']))
                          for item in json.loads(row['statements'])]
            errors = verify_summary(statements, self._resolve_evidence)
            self._conn.execute("UPDATE summaries SET status=?, errors=? WHERE id=?",
                               ('REJECTED' if errors else 'VERIFIED_EXTRACT', json.dumps(errors), summary_id))
            self._review('summary', summary_id, 'extractive-critic',
                         'REJECTED' if errors else 'VERIFIED_EXTRACT',
                         'Current episode hashes and exact spans checked')
        return errors

    def procedure(self, procedure_id: str) -> sqlite3.Row | None:
        return self._conn.execute("SELECT * FROM procedures WHERE id=?", (procedure_id,)).fetchone()

    def approve_procedure(self, procedure_id: str, *, reviewer: str, reason: str,
                          expected_steps: list[str], expected_precondition: str,
                          expected_postcondition: str) -> None:
        """Record an exact reviewed proposal, not permission to run anything."""
        if self._resolve_evidence is None or not reviewer.strip() or not reason.strip():
            raise ValueError("Explicit reviewer, reason and live evidence resolver required")
        with writing(self._conn):
            self._conn.execute("UPDATE procedures SET status=status WHERE id=?", (procedure_id,))
            row = self.procedure(procedure_id)
            if row is None or row['status'] != 'PROPOSED':
                raise ValueError("Only a proposed procedure can be approved")
            if (json.loads(row['steps']) != expected_steps
                    or row['precondition'] != expected_precondition
                    or row['postcondition'] != expected_postcondition):
                raise ValueError("Proposal differs from reviewed steps and conditions")
            if not self._evidence_live(json.loads(row['evidence'])):
                raise ValueError("Missing or retracted evidence")
            self._conn.execute("UPDATE procedures SET status='APPROVED' WHERE id=?", (procedure_id,))
            self._review('procedure', procedure_id, reviewer, 'APPROVED', reason)

    def revoke_procedure(self, procedure_id: str, *, reviewer: str, reason: str) -> None:
        if not reviewer.strip() or not reason.strip():
            raise ValueError("Reviewer and reason required")
        with writing(self._conn):
            if self.procedure(procedure_id) is None:
                raise ValueError("Unknown procedure")
            self._conn.execute("UPDATE procedures SET status='REVOKED' WHERE id=?", (procedure_id,))
            self._review('procedure', procedure_id, reviewer, 'REVOKED', reason)

    def close(self) -> None:
        self._conn.close()
