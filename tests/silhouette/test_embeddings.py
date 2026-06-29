from silhouette.embeddings import HashingEmbedder, cosine_similarity, get_embedder
from silhouette.embeddings.base import l2_normalize


def test_hashing_embedder_dims_and_determinism():
    emb = HashingEmbedder(dims=128)
    assert emb.dims == 128
    v1 = emb.embed("the quick brown fox")
    v2 = emb.embed("the quick brown fox")
    assert len(v1) == 128
    assert v1 == v2  # deterministic


def test_hashing_embedder_is_normalized():
    emb = HashingEmbedder(dims=64)
    v = emb.embed("hello world memory system")
    norm = sum(x * x for x in v) ** 0.5
    assert abs(norm - 1.0) < 1e-6


def test_similar_text_scores_higher_than_unrelated():
    emb = HashingEmbedder(dims=512)
    base = emb.embed("the cognitive memory engine consolidates knowledge")
    similar = emb.embed("the memory engine consolidates cognitive knowledge")
    unrelated = emb.embed("bananas are a yellow tropical fruit")
    assert cosine_similarity(base, similar) > cosine_similarity(base, unrelated)


def test_empty_text_returns_zero_vector():
    emb = HashingEmbedder(dims=32)
    v = emb.embed("")
    assert v == [0.0] * 32


def test_cosine_edge_cases():
    assert cosine_similarity([], []) == 0.0
    assert cosine_similarity([1.0], [1.0, 2.0]) == 0.0
    assert cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0
    assert abs(cosine_similarity([1.0, 0.0], [1.0, 0.0]) - 1.0) < 1e-9


def test_l2_normalize_zero_vector():
    assert l2_normalize([0.0, 0.0]) == [0.0, 0.0]


def test_batch_matches_single():
    emb = HashingEmbedder(dims=64)
    texts = ["alpha beta", "gamma delta"]
    batch = emb.embed_batch(texts)
    assert batch == [emb.embed(texts[0]), emb.embed(texts[1])]


def test_factory_falls_back_without_fastembed(monkeypatch):
    from silhouette.config import Settings

    settings = Settings(use_fastembed=False, embedding_dims=77)
    emb = get_embedder(settings)
    assert isinstance(emb, HashingEmbedder)
    assert emb.dims == 77
