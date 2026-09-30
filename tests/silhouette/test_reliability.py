"""Crash/replay and lineage regression tests for the canonical episodic store."""

import pytest

from silhouette.storage import MemorySystem


def test_projection_failure_keeps_source_and_replays(settings, monkeypatch):
    mem = MemorySystem(settings)
    original = mem.semantic.add
    def fail(_record):
        raise OSError("disk unavailable")
    monkeypatch.setattr(mem.semantic, "add", fail)
    with pytest.raises(OSError):
        mem.remember("Ada and Lin build Atlas")
    assert mem.episodic.count() == 1
    assert len(mem.episodic.pending()) == 1
    monkeypatch.setattr(mem.semantic, "add", original)
    mem.close()
    mem = MemorySystem(settings)
    assert mem.episodic.count() == mem.semantic.count() == 1
    assert mem.graph.relationship_count() == 3
    assert mem.episodic.pending() == []
    mem.close()


def test_graph_replay_is_idempotent_and_forget_retains_shared_support(memory):
    a = memory.remember("Ada and Lin build Atlas")
    b = memory.remember("Ada and Lin build Atlas")
    assert memory.graph.relationships()[0].weight == 2.0
    memory.episodic.queue(a)
    memory.reconcile()
    assert memory.graph.relationships()[0].weight == 2.0
    assert memory.forget(a.id)
    assert memory.graph.relationships()[0].weight == 1.0
    assert memory.forget(b.id)
    assert memory.graph.relationship_count() == 0
    assert memory.graph.entity_count() == 0


def test_delete_failure_is_not_reported_as_success(settings, monkeypatch):
    mem = MemorySystem(settings)
    record = mem.remember("Ada and Lin build Atlas")
    original = mem.graph.retract_episode
    def fail(_id):
        raise OSError("graph unavailable")
    monkeypatch.setattr(mem.graph, "retract_episode", fail)
    with pytest.raises(OSError):
        mem.forget(record.id)
    assert mem.episodic.get(record.id) is None
    assert len(mem.episodic.pending()) == 1
    monkeypatch.setattr(mem.graph, "retract_episode", original)
    mem.close()
    mem = MemorySystem(settings)
    assert not mem.semantic.has_embedding(record.id)
    assert mem.graph.entity_count() == 0
    assert mem.episodic.pending() == []
    mem.close()


def test_janitor_retracts_duplicate_graph_support(memory):
    from silhouette.engines.janitor import JanitorEngine
    memory.remember("Ada and Lin build Atlas", importance=0.9)
    memory.remember("Ada and Lin build Atlas", importance=0.3)
    result = JanitorEngine(dup_threshold=0.95).run(memory)
    assert result.ok
    assert memory.graph.relationships()[0].weight == 1.0


def test_upgrade_preserves_unattributed_legacy_graph(settings):
    from silhouette.models import Entity, Relationship
    from silhouette.storage.graph import SqliteGraphStore
    path = settings.db_path("graph.db")
    graph = SqliteGraphStore(path)
    graph.upsert_entity(Entity(name="Ada"))
    graph.upsert_entity(Entity(name="Lin"))
    graph.add_relationship(Relationship(source="Ada", target="Lin", type="CO_MENTION"))
    graph.close()
    import sqlite3
    with sqlite3.connect(path) as conn:
        conn.execute("DROP TABLE entity_support")
        conn.execute("DROP TABLE edge_support")
    mem = MemorySystem(settings)
    new = mem.remember("Ada and Lin build Atlas")
    assert mem.forget(new.id)
    assert {entity.name for entity in mem.entities()} == {"Ada", "Lin"}
    assert len(mem.graph.relationships()) == 1
    mem.close()
