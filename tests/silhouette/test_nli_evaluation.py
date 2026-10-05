"""Math tests, not fabricated model inference or accuracy."""
import math

import pytest

from silhouette.storage.nli_evaluation import metrics, rescale


def test_temperature_preserves_class_and_normalization():
    scores = {'entailment': 0.8, 'neutral': 0.15, 'contradiction': 0.05}
    for temperature in [0.5, 1, 2, 4]:
        probs = rescale(scores, temperature)
        assert sum(probs) == pytest.approx(1)
        assert max(range(3), key=lambda i: probs[i]) == 0
    assert rescale(scores, 2)[0] < scores['entailment']


def test_perfect_and_wrong_metrics_confusion_order():
    rows = [{'label': 0, 'scores': {'entailment': 0.8, 'neutral': 0.1, 'contradiction': 0.1}},
            {'label': 2, 'scores': {'entailment': 0.1, 'neutral': 0.8, 'contradiction': 0.1}}]
    result = metrics(rows)
    assert result['accuracy'] == 0.5
    assert result['confusion_matrix'] == [[1, 0, 0], [0, 0, 0], [0, 1, 0]]
    assert result['nll'] == pytest.approx((-math.log(0.8) - math.log(0.1)) / 2)
    assert result['brier'] == pytest.approx((0.06 + 1.46) / 2)
    assert result['ece_10_bins'] == pytest.approx(0.3)


def test_empty_evaluation_rejected():
    with pytest.raises(ValueError, match='No scored'):
        metrics([])
