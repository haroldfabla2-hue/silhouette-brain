"""Real evidence lineage and transactional review regression tests."""
import pytest

from silhouette.storage.critic import EvidenceSpan, SummaryStatement, content_hash
from silhouette.storage.knowledge import KnowledgeStore


def test_approval_rechecks_two_pending_proposals(tmp_path):
    path = tmp_path / 'claims.db'
    first = KnowledgeStore(path)
    second = KnowledgeStore(path)
    a = first.propose_claim('Alberto', 'lives_in', 'Lima', evidence=['ep1'])
    b = second.propose_claim('Alberto', 'lives_in', 'Quito', evidence=['ep2'])
    first.approve_claim(a, reviewer='owner', reason='source reviewed')
    with pytest.raises(ValueError, match='Overlapping'):
        second.approve_claim(b)
    assert second.claim(b)['status'] == 'CONFLICTED'
    assert second.conflicts(b) == [a]
    assert first.claim(a)['status'] == 'ACCEPTED'
    assert first._conn.execute('SELECT count(*) FROM reviews').fetchone()[0] == 2
    first.close()
    second.close()


def test_summary_exact_spans_reject_changed_and_hallucinated(memory):
    episode = memory.remember('Alberto lives in Lima. He likes coffee.')
    citation = EvidenceSpan(episode.id, 0, 21, content_hash(episode.content))
    good = memory.knowledge.propose_summary([SummaryStatement('Alberto lives in Lima', citation)])
    assert memory.knowledge.verify_summary(good) == []
    assert memory.knowledge.summary(good)['status'] == 'VERIFIED_EXTRACT'
    bad = memory.knowledge.propose_summary([SummaryStatement('Alberto lives in Quito', citation)])
    assert memory.knowledge.verify_summary(bad)
    assert memory.knowledge.summary(bad)['status'] == 'REJECTED'
    changed = memory.knowledge.propose_summary([SummaryStatement('Alberto lives in Lima',
        EvidenceSpan(episode.id, 0, 21, 'stale-hash'))])
    assert 'source changed' in memory.knowledge.verify_summary(changed)[0]
    memory.forget(episode.id)
    assert memory.knowledge.summary(good)['status'] == 'REVOKED'
    with pytest.raises(ValueError, match='revoked'):
        memory.knowledge.verify_summary(good)


def test_procedure_explicit_review_snapshot_revoke_and_missing_evidence(memory):
    episode = memory.remember('Owner reviewed backups before running local tests')
    procedure = memory.knowledge.propose_procedure('backup ready', ['run local tests'],
                                                  'tests pass', evidence=[episode.id])
    with pytest.raises(ValueError, match='differs'):
        memory.knowledge.approve_procedure(procedure, reviewer='owner', reason='reviewed',
            expected_steps=['delete data'], expected_precondition='backup ready',
            expected_postcondition='tests pass')
    assert memory.knowledge.procedure(procedure)['status'] == 'PROPOSED'
    memory.knowledge.approve_procedure(procedure, reviewer='owner', reason='reviewed',
        expected_steps=['run local tests'], expected_precondition='backup ready',
        expected_postcondition='tests pass')
    assert memory.knowledge.procedure(procedure)['status'] == 'APPROVED'
    memory.knowledge.revoke_procedure(procedure, reviewer='owner', reason='cancelled')
    assert memory.knowledge.procedure(procedure)['status'] == 'REVOKED'
    missing = memory.knowledge.propose_claim('a', 'b', 'c', evidence=['unknown'])
    with pytest.raises(ValueError, match='Missing'):
        memory.knowledge.approve_claim(missing)
