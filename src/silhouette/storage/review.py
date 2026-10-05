"""Exact-snapshot review service, independent of HTTP and model inference."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from silhouette.storage.critic import content_hash
from silhouette.storage.knowledge import KnowledgeStore
from silhouette.storage.sqlite import writing


class ReviewService:
    def __init__(self, store: KnowledgeStore, reviewer: str) -> None:
        if not reviewer.strip() or store._resolve_evidence is None:
            raise ValueError('Server reviewer identity and live evidence resolver required')
        self.store, self.reviewer = store, reviewer

    def snapshot(self, kind: str, target_id: str) -> dict[str, Any]:
        if kind not in ('claim', 'procedure'):
            raise ValueError('Unknown review kind')
        row = self.store.claim(target_id) if kind == 'claim' else self.store.procedure(target_id)
        if row is None:
            raise LookupError('Unknown proposal')
        proposal = dict(row)
        proposal['evidence'] = json.loads(row['evidence'])
        if kind == 'procedure':
            proposal['steps'] = json.loads(row['steps'])
        resolve = self.store._resolve_evidence
        assert resolve is not None
        evidence = []
        for episode_id in proposal['evidence']:
            record = resolve(episode_id)
            evidence.append({'id': episode_id, 'content': record.content if record else None,
                             'sha256': content_hash(record.content) if record else None})
        result = {'kind': kind, 'proposal': proposal, 'evidence': evidence}
        digest = hashlib.sha256(json.dumps(result, sort_keys=True, separators=(',', ':'),
                                          allow_nan=False).encode()).hexdigest()
        return {**result, 'snapshot_sha256': digest}

    def decide(self, kind: str, target_id: str, *, expected_snapshot: str,
               decision: str, reason: str) -> dict[str, Any]:
        if decision not in ('approve', 'revoke') or not reason.strip():
            raise ValueError('Explicit decision and reason required')
        if kind == 'claim' and decision == 'revoke':
            raise ValueError('Claim revocation is not supported by this slice')
        table = {'claim': 'claims', 'procedure': 'procedures'}.get(kind)
        if table is None:
            raise ValueError('Unknown review kind')
        conflict = False
        store = self.store
        with writing(store._conn):
            # Reserve SQLite writer before snapshot/conflict checks across processes.
            store._conn.execute(f'UPDATE {table} SET status=status WHERE id=?', (target_id,))
            current = self.snapshot(kind, target_id)
            if current['snapshot_sha256'] != expected_snapshot:
                raise ValueError('Stale reviewed snapshot; read the proposal again')
            row = current['proposal']
            if decision == 'revoke':
                store._conn.execute("UPDATE procedures SET status='REVOKED' WHERE id=?", (target_id,))
                store._review(kind, target_id, self.reviewer, 'REVOKED', reason)
            else:
                if row['status'] != 'PROPOSED':
                    raise ValueError('Only non-conflicted proposals can be approved')
                if not current['evidence'] or any(e['sha256'] is None for e in current['evidence']):
                    raise ValueError('Missing or retracted evidence')
                if kind == 'claim':
                    raw = store.claim(target_id)
                    assert raw is not None
                    conflict = bool(store._conflicts(raw))
                    status = 'CONFLICTED' if conflict else 'ACCEPTED'
                else:
                    status = 'APPROVED'
                store._conn.execute(f'UPDATE {table} SET status=? WHERE id=?', (status, target_id))
                store._review(kind, target_id, self.reviewer, status, reason)
        if conflict:
            raise ValueError('Overlapping accepted claim requires conflict review')
        return self.snapshot(kind, target_id)
