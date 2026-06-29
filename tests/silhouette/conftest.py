import pytest

from silhouette.config import Settings
from silhouette.storage import MemorySystem


@pytest.fixture
def settings(tmp_path):
    return Settings(
        data_dir=tmp_path / "data",
        use_fastembed=False,
        embedding_dims=256,
        working_capacity=50,
    )


@pytest.fixture
def memory(settings):
    mem = MemorySystem(settings)
    yield mem
    mem.close()
