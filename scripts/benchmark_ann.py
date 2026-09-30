"""Reproducible generated-text benchmark; NOT labeled production recall.

Measures HNSW overlap with exact cosine on the actual SQLite path, including
query embedding, candidate fetch and rerank. Backfill is excluded from p95 and
reported separately. No mocks, model APIs, random vectors or invented timings.
"""
from __future__ import annotations

import argparse
import json
import math
import platform
import random
import statistics
import tempfile
import time
from pathlib import Path

from silhouette.embeddings.hashing import HashingEmbedder
from silhouette.models import MemoryRecord
from silhouette.storage.semantic import SemanticStore

parser = argparse.ArgumentParser()
parser.add_argument('--size', type=int, default=20000)
parser.add_argument('--queries', type=int, default=20)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
rng = random.Random(17)
cities = ['Lima', 'Bogota', 'Quito', 'Arequipa', 'Cusco', 'Madrid']
topics = ['inventory', 'supplier', 'memory', 'backup', 'coffee', 'shipment', 'calendar']
texts = [f'Event {i}: {rng.choice(topics)} in {rng.choice(cities)} '
         f'order {rng.randrange(1000000)} quantity {rng.randrange(1000)} '
         f'owner reviewed reference {rng.randrange(1000000)}' for i in range(args.size)]
with tempfile.TemporaryDirectory() as directory:
    store = SemanticStore(Path(directory) / 'semantic.db', HashingEmbedder(), ann_shadow=True)
    started = time.perf_counter()
    for i, text in enumerate(texts):
        store.add(MemoryRecord(id=f'{i:08}', content=text))
    ingestion_s = time.perf_counter() - started
    warmup = store.ann_shadow_compare(texts[0])
    reports = [store.ann_shadow_compare(texts[i])
               for i in rng.sample(range(args.size), args.queries)]
    def p95(key):
        times = sorted(float(row[key]) for row in reports)
        return times[math.ceil(len(times) * .95) - 1]
    output = {'corpus_size': args.size, 'queries': args.queries, 'seed': 17,
              'corpus': 'generated English event text, six cities, seven topics',
              'queries_kind': 'held corpus sentences, not representative paraphrases',
              'embedder': 'hashing-384', 'index': 'hnswlib 0.8, cosine M16 ef100 ef_construction200, single thread',
              'reference': 'SQLite exact cosine, not human relevance labels',
              'recall_at_10_mean': statistics.mean(float(row['recall_at_k']) for row in reports),
              'recall_at_10_min': min(float(row['recall_at_k']) for row in reports),
              'exact_p95_ms': p95('exact_ms'), 'ann_p95_ms': p95('ann_ms'),
              'backfill_ms': warmup['rebuild_ms'], 'ingestion_s': ingestion_s,
              'platform': platform.platform(), 'python': platform.python_version(),
              'runs': reports}
    args.output.write_text(json.dumps(output, indent=2) + '\n')
    print(json.dumps({k: v for k, v in output.items() if k != 'runs'}, indent=2))
    store.close()
