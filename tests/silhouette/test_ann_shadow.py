"""Actual HNSW/SQLite tests, no stub index or simulated timing."""
import pytest

from silhouette.embeddings.hashing import HashingEmbedder
from silhouette.models import MemoryRecord
from silhouette.storage.semantic import SemanticStore


def test_default_disabled_and_exact_unchanged(tmp_path):
    store = SemanticStore(tmp_path / 'vectors.db', HashingEmbedder())
    store.add(MemoryRecord(id='a', content='Alberto in Lima'))
    assert store.search('Alberto')[0].record.id == 'a'
    with pytest.raises(RuntimeError, match='explicitly'):
        store.ann_shadow_compare('Alberto')
    store.close()


def test_backfill_mutation_restart_and_external_commit(tmp_path):
    path = tmp_path / 'vectors.db'
    embedder = HashingEmbedder()
    legacy = SemanticStore(path, embedder)
    for index in range(120):
        legacy.add(MemoryRecord(id=f'{index:04}', content=f'memory {index} Lima item {index * 17}'))
    legacy.close()
    store = SemanticStore(path, embedder, ann_shadow=True)
    report = store.ann_shadow_compare('memory 55 Lima item 935')
    assert report['recall_at_k'] >= 0.8
    exact_before = [h.record.id for h in store.search('memory 55 Lima item 935', limit=10)]
    assert exact_before == report['exact_ids']
    assert report['rebuild_ms'] > 0
    assert store.ann_shadow_compare('memory 55 Lima item 935')['rebuild_ms'] == 0
    store.delete('0055')
    assert '0055' not in store.ann_shadow_compare('memory 55 Lima item 935')['ann_ids']
    other = SemanticStore(path, embedder)
    other.add(MemoryRecord(id='new', content='unique quetzal Bogota'))
    assert store.ann_shadow_compare('unique quetzal Bogota')['ann_ids'][0] == 'new'
    other.close()
    store.close()
    reopened = SemanticStore(path, embedder, ann_shadow=True)
    assert reopened.ann_shadow_compare('unique quetzal Bogota')['ann_ids'][0] == 'new'
    reopened.close()


def test_zero_and_wrong_dimension_fail_closed(tmp_path):
    store = SemanticStore(tmp_path / 'vectors.db', HashingEmbedder(), ann_shadow=True)
    assert store.ann_shadow_compare('abc')['ann_ids'] == []
    store.add(MemoryRecord(id='bad', content='bad', embedding=[1.0]))
    with pytest.raises(ValueError, match='dimension'):
        store.ann_shadow_compare('abc')
    assert store.count() == 1
    store.delete('bad')
    store.add(MemoryRecord(id='zero', content=''))
    with pytest.raises(ValueError, match='nonzero'):
        store.ann_shadow_compare('abc')
    store.close()
