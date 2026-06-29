import json

import pytest

from silhouette.cli import main


@pytest.fixture(autouse=True)
def _isolate_data(monkeypatch, tmp_path):
    # Force the CLI's MemorySystem() to use a temp data dir + the fallback embedder.
    monkeypatch.setenv("SILHOUETTE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("SILHOUETTE_USE_FASTEMBED", "false")
    monkeypatch.setenv("SILHOUETTE_EMBEDDING_DIMS", "128")
    import silhouette.config as cfg

    cfg.get_settings.cache_clear()
    yield
    cfg.get_settings.cache_clear()


def test_remember_query_stats_roundtrip(capsys):
    assert main(["remember", "The dreamer consolidates memory", "--importance", "0.9"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "ok"

    assert main(["query", "memory consolidation", "--min-score", "0.0"]) == 0
    results = json.loads(capsys.readouterr().out)
    assert any("dreamer" in r["content"].lower() for r in results)

    assert main(["stats"]) == 0
    stats = json.loads(capsys.readouterr().out)
    assert stats["episodic"] == 1


def test_engine_command(capsys):
    main(["remember", "Madrid and Barcelona"])
    capsys.readouterr()
    assert main(["engine", "evolution"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["engine"] == "evolution"


def test_engine_unknown_returns_error():
    assert main(["engine", "does-not-exist"]) == 2


def test_context_command(capsys):
    main(["remember", "Alberto builds Silhouette"])
    capsys.readouterr()
    assert main(["context", "Silhouette", "--synthesize"]) == 0
    packet = json.loads(capsys.readouterr().out)
    assert packet["query"] == "Silhouette"
