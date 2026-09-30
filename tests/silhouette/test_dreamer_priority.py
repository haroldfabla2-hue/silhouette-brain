from silhouette.engines.dreamer import DreamerEngine


def test_budgeted_replay_no_fabricated_claims(memory):
    low = memory.remember("Alberto visits Madrid", importance=0.1)
    high = memory.remember("Silhouette builds Brain", importance=0.9)
    memory.semantic.delete(low.id)
    memory.semantic.delete(high.id)
    result = DreamerEngine(budget=1).run(memory)
    assert result.ok
    assert result.stats["consolidated"] == 1
    assert memory.semantic.has_embedding(high.id)
    assert not memory.semantic.has_embedding(low.id)
    assert memory.knowledge._conn.execute("SELECT count(*) FROM claims").fetchone()[0] == 0
    second = DreamerEngine(budget=1).run(memory)
    assert second.ok
    assert memory.graph.relationship_count() >= 0
