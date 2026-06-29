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
