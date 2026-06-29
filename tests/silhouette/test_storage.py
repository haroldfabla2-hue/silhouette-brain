import time

from silhouette.config import Settings
from silhouette.models import MemoryRecord
from silhouette.storage import EpisodicStore, SqliteGraphStore, WorkingMemory
from silhouette.storage.entities import extract_entities


def test_remember_populates_all_tiers(memory):
    rec = memory.remember("Alberto is building the Silhouette Brain project", importance=0.8)
    assert rec.id
    stats = memory.stats()
    assert stats["episodic"] == 1
    assert stats["semantic"] == 1
    assert stats["working"] == 1
    assert stats["entities"] >= 1


def test_semantic_recall_ranks_relevant_first(memory):
    memory.remember("The dreamer engine consolidates medium memory into the graph")
    memory.remember("I had a sandwich for lunch today")
    results = memory.recall("memory consolidation engine", limit=2)
    assert results
    assert "dreamer" in results[0].record.content.lower()
    assert results[0].score >= results[-1].score


def test_recent_returns_recent_only(memory):
    memory.remember("recent event")
    recent = memory.recent(hours=1, limit=10)
    assert len(recent) == 1
    assert recent[0].content == "recent event"


def test_recent_excludes_old(settings):
    from silhouette.storage import MemorySystem

    mem = MemorySystem(settings)
    try:
        rec = mem.remember("old event")
        # Backdate the episode by writing an old timestamp directly.
        old = MemoryRecord(content="ancient", created_at=time.time() - 10 * 3600)
        mem.episodic.add(old)
        recent = mem.recent(hours=1, limit=10)
        contents = {r.content for r in recent}
        assert "old event" in contents
        assert "ancient" not in contents
        assert rec.id
    finally:
        mem.close()


def test_graph_co_mentions_create_relationships(memory):
    memory.remember("Alberto met Silhouette in Madrid")
    rels = memory.graph.relationships(limit=20)
    assert any(r.type == "CO_MENTION" for r in rels)


def test_working_memory_lru_eviction():
    settings = Settings(use_fastembed=False, working_capacity=3, working_ttl_seconds=0)
    wm = WorkingMemory(settings)
    ids = []
    for i in range(5):
        rec = MemoryRecord(content=f"item {i}")
        wm.put(rec)
        ids.append(rec.id)
    assert len(wm) == 3
    # Oldest two evicted.
    assert wm.get(ids[0]) is None
    assert wm.get(ids[-1]) is not None


def test_episodic_delete(tmp_path):
    store = EpisodicStore(tmp_path / "ep.db")
    rec = MemoryRecord(content="to delete")
    store.add(rec)
    assert store.count() == 1
    assert store.delete(rec.id) is True
    assert store.count() == 0
    assert store.delete("nope") is False
    store.close()


def test_graph_neighbors(tmp_path):
    g = SqliteGraphStore(tmp_path / "g.db")
    from silhouette.models import Entity, Relationship

    g.upsert_entity(Entity(name="A"))
    g.upsert_entity(Entity(name="B"))
    g.add_relationship(Relationship(source="A", target="B", type="CO_MENTION"))
    g.add_relationship(Relationship(source="A", target="B", type="CO_MENTION"))
    neighbors = g.neighbors("A")
    assert len(neighbors) == 1
    assert neighbors[0].weight == 2.0  # weight accumulated
    g.close()


def test_entity_extraction():
    pairs = dict(extract_entities("Alberto loves #python and pinged @silhouette"))
    assert pairs.get("python") == "topic"
    assert pairs.get("silhouette") == "person"
    assert "Alberto" in pairs
