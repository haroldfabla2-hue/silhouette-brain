from silhouette.engines import (
    CuriosityEngine,
    DreamerEngine,
    EvolutionEngine,
    JanitorEngine,
)
from silhouette.engines.base import CognitiveEngine
from silhouette.models import EngineResult, MemoryRecord


def test_base_isolates_errors(memory):
    class Boom(CognitiveEngine):
        name = "boom"

        def _execute(self, memory):
            raise RuntimeError("kaboom")

    result = Boom().run(memory)
    assert isinstance(result, EngineResult)
    assert result.ok is False
    assert "kaboom" in (result.error or "")
    assert result.duration_ms >= 0


def test_curiosity_generates_questions(memory):
    memory.remember("Madrid is a city")  # single-mention entity → a gap
    result = CuriosityEngine(max_questions=3, min_mentions=5).run(memory)
    assert result.ok
    assert result.stats["questions_generated"] >= 1
    # Questions land in working memory tagged 'curiosity'.
    qs = [r for r in memory.working.recent(50) if "curiosity" in r.tags]
    assert qs


def test_janitor_removes_duplicates(memory):
    memory.remember("The dreamer consolidates memory into the graph", importance=0.9)
    memory.remember("The dreamer consolidates memory into the graph", importance=0.3)
    before = memory.episodic.count()
    result = JanitorEngine(dup_threshold=0.95).run(memory)
    assert result.ok
    assert result.stats["duplicates_removed"] == 1
    assert memory.episodic.count() == before - 1
    # The higher-importance copy survives.
    survivors = memory.episodic.all()
    assert survivors[0].importance == 0.9


def test_janitor_flags_contradiction(memory):
    memory.remember("I really like coffee in the morning")
    memory.remember("I really do not like coffee in the morning")
    result = JanitorEngine().run(memory)
    assert result.stats["contradictions_found"] >= 1


def test_dreamer_consolidates_and_backfills(memory):
    # Add an episode that exists in episodic but not semantic.
    rec = MemoryRecord(content="Alberto and Silhouette ship the Brain", importance=0.7)
    memory.episodic.add(rec)
    assert not memory.semantic.has_embedding(rec.id)
    result = DreamerEngine().run(memory)
    assert result.ok
    assert result.stats["embeddings_added"] >= 1
    assert memory.semantic.has_embedding(rec.id)


def test_evolution_reports_metrics_and_proposals(memory):
    memory.remember("Alberto builds Silhouette with Curiosity and Dreamer engines")
    result = EvolutionEngine().run(memory)
    assert result.ok
    metrics = result.stats["metrics"]
    assert "embedding_coverage" in metrics
    assert "graph_density" in metrics
    import os

    assert os.path.exists(result.stats["report_path"])
