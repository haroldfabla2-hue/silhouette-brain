from silhouette.storage.activation import activation_score


def test_meaningful_access_bounded_and_reversible(memory):
    rec = memory.remember("A confirmed preference", tags=["confirmed_preference"])
    old = rec.created_at + 86400 * 40
    before = memory.explain_activation(rec.id, now=old)
    assert before["protected"]
    assert memory.episodic.record_meaningful_access(rec.id, at=old - 86400)
    assert memory.episodic.record_meaningful_access(rec.id, at=old - 86400 + 15)
    after = memory.explain_activation(rec.id, now=old)
    assert after["access_days"] == 1
    assert after["score"] > before["score"]
    assert memory.episodic.get(rec.id) is not None
    memory.episodic.reset_access_history(rec.id)
    assert memory.explain_activation(rec.id, now=old) == before
    assert memory.forget(rec.id)
    assert memory.explain_activation(rec.id, now=old) is None
    assert not memory.episodic.access_history(rec.id)


def test_time_travel_and_frequency_cap():
    created = 1_700_000_000.0
    now = created + 86400 * 20
    sparse = activation_score(created, [], now=now)
    repeated = activation_score(created, [now - 600] * 100, now=now)
    assert repeated["access_days"] == 1
    assert repeated["score"] > sparse["score"]
    assert activation_score(created, [], now=created)["score"] > sparse["score"]
