"""Local artifact gates; actual inference is exercised by the offline evaluation script."""
import hashlib
import json

import pytest

from silhouette.storage.local_nli import LocalOnnxNLI


def artifacts(path, labels=None):
    (path / 'model.onnx').write_bytes(b'not an executable model')
    (path / 'tokenizer.json').write_text('{}')
    (path / 'config.json').write_text(json.dumps({'id2label': labels or {}}))
    return {'model_file': 'model.onnx', 'name': 'test-artifact', 'revision': 'test-revision',
                'model_sha256': hashlib.sha256((path / 'model.onnx').read_bytes()).hexdigest(),
                'tokenizer_sha256': hashlib.sha256((path / 'tokenizer.json').read_bytes()).hexdigest(),
                'config_sha256': hashlib.sha256((path / 'config.json').read_bytes()).hexdigest()}


def test_checksum_before_loading(tmp_path):
    config = artifacts(tmp_path)
    config['model_sha256'] = '0' * 64
    with pytest.raises(ValueError, match='checksum'):
        LocalOnnxNLI(str(tmp_path), **config)


def test_unmapped_labels_before_loading(tmp_path):
    with pytest.raises(ValueError, match='label'):
        LocalOnnxNLI(str(tmp_path), **artifacts(tmp_path))


def test_outside_directory_before_loading(tmp_path):
    config = artifacts(tmp_path)
    (tmp_path / 'linked').symlink_to('/etc/passwd')
    config['model_file'] = 'linked'
    with pytest.raises(ValueError, match='outside'):
        LocalOnnxNLI(str(tmp_path), **config)


@pytest.mark.parametrize('kwargs', [{'max_tokens': 513}, {'threads': 0}, {'revision': ''}])
def test_invalid_budgets_and_identity(tmp_path, kwargs):
    config = {**artifacts(tmp_path), **kwargs}
    with pytest.raises(ValueError):
        LocalOnnxNLI(str(tmp_path), **config)
