"""Opt-in local ONNX NLI advice. No downloads, remote code or automatic approval."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from silhouette.storage.entailment import EntailmentScores


class LocalOnnxNLI:
    """Explicit trusted-local artifacts, pinned hashes and declared class mapping.

    Model probabilities are not calibrated confidence or proof. Oversize pairs
    fail rather than silently discarding cited evidence. Use offline evaluation
    for the deployment's languages before enabling this adapter.
    """

    def __init__(self, directory: str, *, model_file: str, model_sha256: str,
                 tokenizer_sha256: str, config_sha256: str, name: str,
                 revision: str, max_tokens: int = 512, threads: int = 1):
        if not name.strip() or not revision.strip():
            raise ValueError('Versioned provider identity required')
        if not 8 <= max_tokens <= 512 or not 1 <= threads <= 8:
            raise ValueError('Invalid inference budget')
        root = Path(directory).resolve(strict=True)
        artifacts = {}
        for filename, expected in [(model_file, model_sha256),
                                   ('tokenizer.json', tokenizer_sha256),
                                   ('config.json', config_sha256)]:
            path = (root / filename).resolve(strict=True)
            if not path.is_relative_to(root) or len(expected) != 64:
                raise ValueError('Artifact outside trusted directory or invalid hash')
            digest = hashlib.sha256()
            with path.open('rb') as source:
                for block in iter(lambda: source.read(1024 * 1024), b''):
                    digest.update(block)
            if digest.hexdigest() != expected:
                raise ValueError('Artifact checksum mismatch')
            artifacts[filename] = path
        config = json.loads(artifacts['config.json'].read_text())
        mapping = config.get('id2label', {})
        labels = [str(mapping.get(str(i), '')).lower() for i in range(3)]
        if set(labels) != {'entailment', 'contradiction', 'neutral'}:
            raise ValueError('Explicit three-class NLI label mapping required')
        import onnxruntime as ort
        from tokenizers import Tokenizer
        self._tokenizer = Tokenizer.from_file(str(artifacts['tokenizer.json']))
        self._tokenizer.no_truncation()
        self._tokenizer.no_padding()
        options = ort.SessionOptions()
        options.intra_op_num_threads = threads
        options.inter_op_num_threads = 1
        self._session = ort.InferenceSession(str(artifacts[model_file]), options,
                                            providers=['CPUExecutionProvider'])
        self._inputs = {item.name for item in self._session.get_inputs()}
        if not {'input_ids', 'attention_mask'} <= self._inputs or not self._inputs <= {
                'input_ids', 'attention_mask', 'token_type_ids'}:
            raise ValueError('Unsupported model inputs')
        self.name, self.revision = name, revision
        self._labels, self._max_tokens = labels, max_tokens

    def score(self, premise: str, hypothesis: str) -> EntailmentScores:
        if not premise.strip() or not hypothesis.strip():
            raise ValueError('Nonempty evidence and statement required')
        if len(premise.encode()) + len(hypothesis.encode()) > 65536:
            raise ValueError('Text byte budget exceeded')
        import numpy as np
        encoded = self._tokenizer.encode(premise, hypothesis)
        if len(encoded.ids) > self._max_tokens:
            raise ValueError('Pair exceeds token budget; evidence is never truncated')
        data = {'input_ids': encoded.ids, 'attention_mask': encoded.attention_mask,
                'token_type_ids': encoded.type_ids}
        logits = self._session.run(None, {
            key: np.asarray([data[key]], dtype=np.int64) for key in self._inputs})[0]
        if logits.shape != (1, 3) or not np.isfinite(logits).all():
            raise ValueError('Invalid NLI output')
        values = [math.exp(float(x) - float(logits.max())) for x in logits[0]]
        probabilities = dict(zip(self._labels, [x / sum(values) for x in values], strict=True))
        return EntailmentScores(**probabilities)
