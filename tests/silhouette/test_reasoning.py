from silhouette.reasoning import (
    ContextAssembler,
    ExtractiveSynthesizer,
    estimate_tokens,
    get_synthesizer,
)


def test_estimate_tokens():
    assert estimate_tokens("") == 0
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("a" * 400) == 100


def _seed(memory):
    memory.remember("The Dreamer engine consolidates episodic memory into the deep graph")
    memory.remember("The Janitor engine resolves contradictions between memories")
    memory.remember("I ate pasta for dinner")


def test_assemble_basic(memory):
    _seed(memory)
    asm = ContextAssembler(memory, ExtractiveSynthesizer())
    packet = asm.assemble("memory consolidation engine", sem_limit=3, min_score=0.0)
    assert packet.query
    assert packet.semantic
    assert "semantic" in packet.sources_used
    assert packet.token_estimate > 0
    assert packet.latency_ms >= 0


def test_assemble_with_synthesis(memory):
    _seed(memory)
    asm = ContextAssembler(memory, ExtractiveSynthesizer())
    packet = asm.assemble("dreamer", sem_limit=3, min_score=0.0, synthesize=True)
    assert packet.synthesis is not None
    assert any(s.startswith("synthesis:") for s in packet.sources_used)


def test_token_budget_prunes(memory):
    for i in range(10):
        memory.remember("consolidation engine memory graph " * 5 + f" variant {i}")
    asm = ContextAssembler(memory)
    full = asm.assemble("consolidation engine", sem_limit=10, min_score=0.0)
    tight = asm.assemble(
        "consolidation engine", sem_limit=10, min_score=0.0, token_budget=20
    )
    assert tight.token_estimate <= full.token_estimate
    assert tight.token_estimate <= 20 + 30  # within one item of the budget


def test_assemble_with_graph(memory):
    memory.remember("Alberto works with Silhouette on the Brain")
    asm = ContextAssembler(memory)
    packet = asm.assemble("Alberto", include_graph=True, min_score=0.0)
    assert isinstance(packet.graph, list)


def test_get_synthesizer_defaults_to_extractive(settings):
    syn = get_synthesizer(settings)
    assert isinstance(syn, ExtractiveSynthesizer)


def test_assemble_dedupes_semantic_and_recent(memory):
    memory.remember("Unique fact about the Quasar engine design")
    asm = ContextAssembler(memory)
    packet = asm.assemble("Quasar engine", sem_limit=5, rec_limit=5, min_score=0.0)
    ids = [s.record.id for s in packet.semantic] + [r.id for r in packet.recent]
    assert len(ids) == len(set(ids))


def test_entities_are_query_relevant(memory):
    memory.remember("Alberto works with Silhouette on the Brain")
    asm = ContextAssembler(memory)
    unrelated = asm.assemble("pasta dinner tonight", min_score=0.0)
    assert unrelated.entities == []
    related = asm.assemble("Alberto", min_score=0.0)
    assert any(e.name == "Alberto" for e in related.entities)


def test_entity_matching_uses_word_boundaries(memory):
    memory.remember("Ai is a short project codename")
    asm = ContextAssembler(memory)
    packet = asm.assemble("what was said in the meeting", min_score=0.0)
    assert packet.entities == []


def test_graph_skips_arbitrary_fallback(memory):
    memory.remember("Alberto works with Silhouette on the Brain")
    asm = ContextAssembler(memory)
    packet = asm.assemble("zzz lowercase query", include_graph=True, min_score=0.0)
    assert packet.graph == []
    related = asm.assemble("Alberto", include_graph=True, min_score=0.0)
    assert len(related.graph) > 0


def test_token_budget_covers_entities_and_graph(memory):
    for name in ["Alpha", "Beta", "Gamma", "Delta", "Epsilon"]:
        memory.remember(f"{name} is part of the Constellation project")
    asm = ContextAssembler(memory)
    packet = asm.assemble(
        "Alpha Beta Gamma Delta Epsilon",
        min_score=0.0,
        token_budget=8,
        budget_split=(0.0, 0.0, 1.0),
    )
    # Only the entities+graph share (8 tokens) is available: bounded.
    assert packet.semantic == []
    assert packet.recent == []
    assert packet.token_estimate <= 8
    assert len(packet.entities) < 5


def test_budget_split_is_validated(memory):
    asm = ContextAssembler(memory)
    try:
        asm.assemble("x", token_budget=10, budget_split=(0.0, 0.0, 0.0))
    except ValueError:
        return
    raise AssertionError("expected ValueError for zero budget_split")
