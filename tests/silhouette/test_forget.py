"""Deleting memories across tiers."""


def test_forget_removes_from_every_tier(memory):
    record = memory.remember("un recuerdo cualquiera", tags=["prueba"])
    assert memory.recall("recuerdo cualquiera", limit=5, min_score=0.0)

    assert memory.forget(record.id) is True

    semantic = memory.recall("recuerdo cualquiera", limit=5, min_score=0.0)
    assert all(hit.record.id != record.id for hit in semantic)
    assert all(r.id != record.id for r in memory.recent(hours=99, limit=50))
    assert memory.working.get(record.id) is None


def test_forget_returns_false_when_absent(memory):
    assert memory.forget("no-existe") is False


def test_forget_tagged_only_removes_the_asked_tag(memory):
    memory.remember("cosa de carla", tags=["rep:carla"])
    memory.remember("cosa de diego", tags=["rep:diego"])

    assert memory.forget_tagged(["rep:carla"]) == 1

    quedan = [r.content for r in memory.recent(hours=99, limit=50)]
    assert any("diego" in c for c in quedan)
    assert not any("carla" in c for c in quedan)


def test_forget_tagged_without_tags_deletes_nothing(memory):
    memory.remember("algo", tags=["x"])
    assert memory.forget_tagged([]) == 0
    assert len(memory.recent(hours=99, limit=50)) == 1
