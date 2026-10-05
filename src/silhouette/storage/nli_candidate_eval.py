"""Pure helpers for the offline NLI candidate comparison. No models, network or approval."""
from __future__ import annotations

import hashlib
import math
from pathlib import Path

from silhouette.storage.nli_evaluation import LABELS


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def verify_artifact(path: str | Path, expected: str) -> None:
    """Fail loudly on a byte mismatch: a wrong file must never produce a number."""
    actual = sha256_file(path)
    if actual != expected:
        raise ValueError(f'Checksum mismatch for {Path(path).name}: expected {expected}, got {actual}')


def wilson_interval(correct: int, total: int, z: float = 1.959964) -> tuple[float, float]:
    if total <= 0 or not 0 <= correct <= total:
        raise ValueError('Invalid counts')
    p = correct / total
    denominator = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return centre - half, centre + half


def predicted(scores: dict[str, float]) -> int:
    probs = [scores[label] for label in LABELS]
    return max(range(3), key=lambda i: probs[i])


def paired(reference: list[dict], other: list[dict]) -> dict:
    """Compare two variants on the SAME rows (matched by index). Mismatched row sets are an error."""
    if [r['index'] for r in reference] != [r['index'] for r in other]:
        raise ValueError('Variants were not scored on identical rows')
    if not reference:
        raise ValueError('No rows')
    agree = both = only_ref = only_other = neither = 0
    worst = total = 0.0
    for a, b in zip(reference, other, strict=True):
        if a['label'] != b['label']:
            raise ValueError('Label mismatch between variants')
        pa, pb = predicted(a['scores']), predicted(b['scores'])
        agree += pa == pb
        ra, rb = pa == a['label'], pb == b['label']
        both += ra and rb
        only_ref += ra and not rb
        only_other += rb and not ra
        neither += not ra and not rb
        diff = max(abs(a['scores'][k] - b['scores'][k]) for k in LABELS)
        worst = max(worst, diff)
        total += diff
    n = len(reference)
    return {'rows': n, 'prediction_agreement': agree / n, 'both_correct': both,
            'only_reference_correct': only_ref, 'only_other_correct': only_other,
            'neither_correct': neither, 'max_abs_probability_diff': worst,
            'mean_abs_probability_diff': total / n}


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError('No values')
    return ordered[max(0, math.ceil(len(ordered) * fraction) - 1)]
