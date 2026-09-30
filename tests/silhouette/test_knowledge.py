"""Real SQLite conflict and evidence lifecycle tests."""

import pytest

from silhouette.storage.knowledge import KnowledgeStore


def test_claim_temporal_conflicts_and_lineage(tmp_path):
    store = KnowledgeStore(tmp_path / "knowledge.db")
    original = store.propose_claim("Alberto", "lives_in", "Lima", evidence=["ep1"],
                                   valid_from=0, valid_to=10)
    store.approve_claim(original)
    later = store.propose_claim("Alberto", "lives_in", "Bogotá", evidence=["ep2"],
                                valid_from=11)
    assert store.claim(later)["status"] == "PROPOSED"
    store.approve_claim(later)
    conflict = store.propose_claim("Alberto", "lives_in", "Quito", evidence=["ep3"],
                                   valid_from=12)
    assert store.claim(conflict)["status"] == "CONFLICTED"
    with pytest.raises(ValueError):
        store.approve_claim(conflict)
    assert store.retract_evidence("ep2") == 1
    assert store.claim(later)["status"] == "SUPERSEDED"
    store.close()


def test_procedures_never_auto_approve_and_revoke_on_loss(tmp_path):
    store = KnowledgeStore(tmp_path / "knowledge.db")
    with pytest.raises(ValueError):
        store.propose_procedure("ready", ["run"], "done", evidence=[])
    procedure_id = store.propose_procedure("ready", ["run"], "done", evidence=["ep1"])
    assert store._conn.execute("SELECT status FROM procedures WHERE id=?", (procedure_id,)).fetchone()[0] == "PROPOSED"
    assert store.retract_evidence("ep1") == 1
    assert store._conn.execute("SELECT status FROM procedures WHERE id=?", (procedure_id,)).fetchone()[0] == "REVOKED"
    store.close()


def test_forget_invalidates_claim_evidence(memory):
    record = memory.remember("Alberto lives in Lima")
    claim_id = memory.knowledge.propose_claim("Alberto", "lives_in", "Lima", evidence=[record.id])
    memory.knowledge.approve_claim(claim_id)
    assert memory.forget(record.id)
    assert memory.knowledge.claim(claim_id)["status"] == "SUPERSEDED"
