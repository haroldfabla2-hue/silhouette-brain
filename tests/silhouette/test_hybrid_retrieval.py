"""Real SQLite / FTS5 integration tests; no fake search backend."""

from silhouette.models import MemoryRecord
from silhouette.storage.semantic import SemanticStore


def test_lexical_finds_late_record_and_filters_before_limit(memory):
    for i in range(520):
        memory.remember(f"ordinary note {i}", tags=["other"])
    target = memory.remember("rarewordxyz exact designation", tags=["wanted"])
    assert memory.semantic.lexical_search("rarewordxyz", limit=1, tags=["wanted"])[0].record.id == target.id
    assert not memory.semantic.lexical_search("rarewordxyz", tags=["other"])
    assert memory.semantic.hybrid_search("rarewordxyz", limit=1, tags=["wanted"])[0].record.id == target.id


def test_lexical_rebuild_from_legacy_and_forget(tmp_path, memory):
    record = memory.remember("café hypergraphical project", tags=["demo"])
    path = memory.settings.db_path("semantic.db")
    memory.semantic.close()
    reopened = SemanticStore(path, memory.embedder)
    memory.semantic = reopened
    assert reopened.lexical_search("hypergraphical", tags=["demo"])[0].record.id == record.id
    assert reopened.delete(record.id)
    assert not reopened.lexical_search("hypergraphical")


def test_legacy_vector_backfill_and_hostile_query(tmp_path, memory):
    record = MemoryRecord(content="oddball technical phrase", tags=["legacy"])
    memory.semantic.add(record)
    memory.semantic._conn.execute("DELETE FROM vectors_fts WHERE id=?", (record.id,))
    memory.semantic._conn.commit()
    memory.semantic.close()
    reopened = SemanticStore(memory.settings.db_path("semantic.db"), memory.embedder)
    memory.semantic = reopened
    assert reopened.lexical_search('"oddball" OR *', tags=["legacy"])[0].record.id == record.id
    assert not reopened.lexical_search("!#$%", tags=["legacy"])
