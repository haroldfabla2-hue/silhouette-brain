"""Offline NLI evaluation metrics, never acceptance or truth confidence."""
import math

LABELS = ['entailment', 'neutral', 'contradiction']


def rescale(scores, temperature):
    logits = [math.log(max(scores[label], 1e-15)) / temperature for label in LABELS]
    raw = [math.exp(x - max(logits)) for x in logits]
    return [x / sum(raw) for x in raw]


def metrics(rows, temperature=1):
    matrix = [[0] * 3 for _ in LABELS]
    bins = [[] for _ in range(10)]
    loss, brier, correct = 0.0, 0.0, 0
    for row in rows:
        probs = rescale(row['scores'], temperature)
        label = row['label']
        predicted = max(range(3), key=lambda i: probs[i])
        hit = predicted == label
        correct += hit
        matrix[label][predicted] += 1
        loss -= math.log(max(probs[label], 1e-15))
        brier += sum((p - (i == label)) ** 2 for i, p in enumerate(probs))
        confidence = max(probs)
        bins[min(9, int(confidence * 10))].append((confidence, hit))
    count = len(rows)
    if not count:
        raise ValueError('No scored examples')
    return {'scored': count, 'correct': correct, 'accuracy': correct / count,
            'nll': loss / count, 'brier': brier / count,
            'ece_10_bins': sum(abs(sum(c - h for c, h in bucket)) for bucket in bins) / count,
            'confusion_labels': LABELS, 'confusion_matrix': matrix}
