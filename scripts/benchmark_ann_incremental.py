"""Reproducible synthetic/hash incremental shadow measurement, not semantic quality."""
import argparse
import json
import statistics
import tempfile
from pathlib import Path

from silhouette.embeddings.hashing import HashingEmbedder
from silhouette.models import MemoryRecord
from silhouette.storage.semantic import SemanticStore

parser = argparse.ArgumentParser()
parser.add_argument('--size', type=int, default=5000)
parser.add_argument('--ef', type=int, default=500)
args = parser.parse_args()
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    embedder = HashingEmbedder()
    store = SemanticStore(root / 'vectors.db', embedder, ann_shadow=True,
                          ann_cache_path=root / 'ann.db', ann_ef=args.ef)
    for i in range(args.size):
        store.add(MemoryRecord(id=f'{i:06}', content=f'memory {i} Lima stock item {i * 17}'))
    cold = store.ann_shadow_compare('memory 20 Lima stock item 340')
    reports = []
    for i in range(20):
        store.add(MemoryRecord(id=f'new{i}', content=f'unique quetzal Bogota number {i}'))
        reports.append(store.ann_shadow_compare(f'unique quetzal Bogota number {i}'))
    store.close()
    store = SemanticStore(root / 'vectors.db', embedder, ann_shadow=True,
                          ann_cache_path=root / 'ann.db', ann_ef=args.ef)
    restart = store.ann_shadow_compare('unique quetzal Bogota number 19')
    def p95(field):
        return sorted(float(r[field]) for r in reports)[18]
    print(json.dumps({
        'corpus_initial': args.size, 'incremental_updates': 20, 'ef': args.ef,
        'embedder': embedder.name, 'python': __import__('sys').version,
        'cold_sync_ms': cold['sync_ms'], 'cold': cold['incremental'],
        'update_sync_p95_ms': p95('sync_ms'), 'exact_p95_ms': p95('exact_ms'),
        'ann_p95_ms': p95('ann_ms'),
        'exact_overlap_recall10_mean': statistics.mean(r['recall_at_k'] for r in reports),
        'exact_overlap_recall10_min': min(r['recall_at_k'] for r in reports),
        'restart_sync_ms': restart['sync_ms'], 'restart': restart['incremental'],
        'limitations': 'Generated hash vectors, source-sentence queries; not labeled semantic relevance. Full checkpoint serialization still O(N).',
        'updates': reports}, indent=2))
    store.close()
