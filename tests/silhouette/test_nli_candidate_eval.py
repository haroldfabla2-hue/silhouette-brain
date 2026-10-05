"""Math and gating tests only. They do not run any model or claim any accuracy."""
import pytest

from silhouette.storage.nli_candidate_eval import (
    paired,
    percentile,
    sha256_file,
    verify_artifact,
    wilson_interval,
)


def row(index, label, e, n, c):
    return {'index': index, 'label': label, 'scores': {'entailment': e, 'neutral': n, 'contradiction': c}}


def test_wilson_known_values_and_bounds():
    low, high = wilson_interval(50, 100)
    assert low == pytest.approx(0.4038, abs=1e-3) and high == pytest.approx(0.5962, abs=1e-3)
    low, high = wilson_interval(0, 10)
    assert low == pytest.approx(0, abs=1e-12) and 0 < high < 0.4
    with pytest.raises(ValueError):
        wilson_interval(11, 10)


def test_paired_counts_agreement_and_diff():
    ref = [row(0, 0, .8, .1, .1), row(1, 1, .1, .8, .1), row(2, 2, .1, .1, .8), row(3, 0, .1, .8, .1)]
    oth = [row(0, 0, .7, .2, .1), row(1, 1, .8, .1, .1), row(2, 2, .1, .1, .8), row(3, 0, .1, .8, .1)]
    result = paired(ref, oth)
    assert result['prediction_agreement'] == 0.75
    assert (result['both_correct'], result['only_reference_correct'],
            result['only_other_correct'], result['neither_correct']) == (2, 1, 0, 1)
    assert result['max_abs_probability_diff'] == pytest.approx(0.7)


def test_paired_rejects_different_rows_or_labels():
    a, b = [row(0, 0, .8, .1, .1)], [row(1, 0, .8, .1, .1)]
    with pytest.raises(ValueError, match='identical rows'):
        paired(a, b)
    with pytest.raises(ValueError, match='Label mismatch'):
        paired([row(0, 0, .8, .1, .1)], [row(0, 1, .8, .1, .1)])


def test_checksum_gate(tmp_path):
    path = tmp_path / 'a.bin'
    path.write_bytes(b'abc')
    verify_artifact(path, sha256_file(path))
    with pytest.raises(ValueError, match='Checksum mismatch'):
        verify_artifact(path, '0' * 64)


def test_percentile_nearest_rank():
    assert percentile([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], .95) == 10
    assert percentile([5.0], .5) == 5.0
