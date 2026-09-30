"""Real HNSW persistence and transactional SQLite replay, no test doubles."""
import json
import sqlite3

import pytest

from silhouette.embeddings.hashing import HashingEmbedder
from silhouette.models import MemoryRecord
from silhouette.storage.ann_persistent import PersistentShadowIndex
from silhouette.storage.semantic import SemanticStore


def open_store(tmp_path):
    return SemanticStore(tmp_path / 'vectors.db', HashingEmbedder(), ann_shadow=True,
                         ann_cache_path=tmp_path / 'ann.db')


def test_incremental_add_update_delete_readd_restart(tmp_path):
    store = open_store(tmp_path)
    for i in range(80):
        store.add(MemoryRecord(id=str(i), content=f'Lima warehouse memory {i} item {i * 17}'))
    first = store.ann_shadow_compare('Lima warehouse memory 20 item 340')
    assert first['incremental']['rebuild']
    index = store._ann._index
    for i in range(6):
        store.add(MemoryRecord(id=f'new{i}', content=f'unique quetzal Bogota number {i}'))
    report = store.ann_shadow_compare('unique quetzal Bogota number 4')
    assert report['incremental']['changed_ids'] == 6
    assert report['incremental']['rebuild'] is False
    assert store._ann._index is index
    assert report['rebuild_ms'] == 0
    assert report['ann_ids'][0] == 'new4'
    store.add(MemoryRecord(id='new4', content='singular Kyoto crane'))
    assert store.ann_shadow_compare('singular Kyoto crane')['ann_ids'][0] == 'new4'
    store.delete('new4')
    assert 'new4' not in store.ann_shadow_compare('singular Kyoto crane')['ann_ids']
    store.add(MemoryRecord(id='new4', content='restored Kyoto crane'))
    assert store.ann_shadow_compare('restored Kyoto crane')['ann_ids'][0] == 'new4'
    store.close()
    restarted = open_store(tmp_path)
    report = restarted.ann_shadow_compare('restored Kyoto crane')
    assert report['incremental']['restored']
    assert report['incremental']['changed_ids'] == 0
    assert report['incremental']['rebuild'] is False
    assert report['ann_ids'][0] == 'new4'
    restarted.close()


def test_external_write_rollback_and_direct_sql_rename(tmp_path):
    store = open_store(tmp_path)
    store.add(MemoryRecord(id='a', content='Lima cafe'))
    store.ann_shadow_compare('Lima')
    other = SemanticStore(tmp_path / 'vectors.db', HashingEmbedder())
    other.add(MemoryRecord(id='b', content='rare alpaca Cusco'))
    report = store.ann_shadow_compare('rare alpaca Cusco')
    assert report['incremental']['changed_ids'] == 1
    assert report['ann_ids'][0] == 'b'
    seq = report['incremental']['checkpoint']
    with sqlite3.connect(tmp_path / 'vectors.db') as db:
        db.execute('DELETE FROM vectors WHERE id=?', ('b',))
        db.rollback()
    report = store.ann_shadow_compare('rare alpaca Cusco')
    assert report['incremental']['checkpoint'] == seq
    assert report['incremental']['changed_ids'] == 0
    with sqlite3.connect(tmp_path / 'vectors.db') as db:
        db.execute('UPDATE vectors SET id=? WHERE id=?', ('renamed', 'b'))
    report = store.ann_shadow_compare('rare alpaca Cusco')
    assert report['ann_ids'][0] == 'renamed'
    assert 'b' not in report['ann_ids']
    assert report['incremental']['changed_ids'] == 2
    other.close()
    store.close()


def test_delete_all_then_readd_and_empty_restart(tmp_path):
    store = open_store(tmp_path)
    assert store.ann_shadow_compare('Lima')['ann_ids'] == []
    store.add(MemoryRecord(id='a', content='Lima'))
    store.ann_shadow_compare('Lima')
    store.delete('a')
    assert store.ann_shadow_compare('Lima')['ann_ids'] == []
    store.close()
    store = open_store(tmp_path)
    assert store.ann_shadow_compare('Lima')['incremental']['restored']
    store.add(MemoryRecord(id='a', content='Lima'))
    assert store.ann_shadow_compare('Lima')['ann_ids'] == ['a']
    store.close()


def test_invalid_delta_does_not_advance_checkpoint(tmp_path):
    store = open_store(tmp_path)
    store.add(MemoryRecord(id='a', content='Lima'))
    store.ann_shadow_compare('Lima')
    with sqlite3.connect(tmp_path / 'ann.db') as cache:
        before = cache.execute('SELECT meta FROM checkpoint').fetchone()[0]
    store.add(MemoryRecord(id='bad', content='bad', embedding=[1.0]))
    with pytest.raises(ValueError, match='dimension'):
        store.ann_shadow_compare('Lima')
    with sqlite3.connect(tmp_path / 'ann.db') as cache:
        assert cache.execute('SELECT meta FROM checkpoint').fetchone()[0] == before
    store.delete('bad')
    assert store.ann_shadow_compare('Lima')['ann_ids'] == ['a']
    store.close()


def test_corrupt_payload_recovers_without_deleting_source(tmp_path):
    store = open_store(tmp_path)
    store.add(MemoryRecord(id='a', content='Lima'))
    store.ann_shadow_compare('Lima')
    store.close()
    with sqlite3.connect(tmp_path / 'ann.db') as cache:
        cache.execute("UPDATE checkpoint SET payload=x'000102'")
    store = open_store(tmp_path)
    report = store.ann_shadow_compare('Lima')
    assert report['incremental']['rebuild']
    assert report['ann_ids'] == ['a']
    assert store.count() == 1
    store.close()


def test_provider_change_rebuilds_and_cache_cannot_alias_source(tmp_path):
    store = open_store(tmp_path)
    store.add(MemoryRecord(id='a', content='Lima'))
    store.ann_shadow_compare('Lima')
    embedder = HashingEmbedder()
    index = PersistentShadowIndex(tmp_path / 'vectors.db', tmp_path / 'ann.db',
                                  embedder.dims, 'different-provider')
    assert index.sync()['rebuild']
    assert index.candidates(embedder.embed('Lima'), 10) == ['a']
    with pytest.raises(ValueError, match='canonical'):
        PersistentShadowIndex(tmp_path / 'vectors.db', tmp_path / 'vectors.db',
                              embedder.dims, embedder.name)
    store.close()


def test_schema_migration_and_cache_identity(tmp_path):
    path = tmp_path / 'vectors.db'
    with sqlite3.connect(path) as db:
        db.execute('''CREATE TABLE vectors (id TEXT PRIMARY KEY, content TEXT NOT NULL,
            tags TEXT NOT NULL, source TEXT NOT NULL, importance REAL NOT NULL,
            created_at REAL NOT NULL, embedding TEXT NOT NULL)''')
        db.execute('INSERT INTO vectors VALUES (?, ?, ?, ?, ?, ?, ?)',
                   ('legacy', 'Lima', '[]', '', 0.5, 0.0,
                    json.dumps(HashingEmbedder().embed('Lima'))))
    store = open_store(tmp_path)
    assert store.ann_shadow_compare('Lima')['ann_ids'] == ['legacy']
    store.close()
    # Reusing the cache for a different corpus must not leak old ids.
    new = SemanticStore(tmp_path / 'other.db', HashingEmbedder(), ann_shadow=True,
                        ann_cache_path=tmp_path / 'ann.db')
    new.add(MemoryRecord(id='other', content='Cusco'))
    report = new.ann_shadow_compare('Cusco')
    assert report['incremental']['rebuild']
    assert report['ann_ids'] == ['other']
    new.close()
