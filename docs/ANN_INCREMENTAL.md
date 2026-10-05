# Persistent incremental ANN shadow

Exact search remains canonical and default. Enable only for local diagnostics:

```python
store = SemanticStore('vectors.db', embedder, ann_shadow=True,
                      ann_cache_path='private-cache.db', ann_ef=500)
report = store.ann_shadow_compare('query')
```

SQLite triggers journal committed vector inserts, updates, deletes and id renames,
including writers outside this process. The first sync backfills; subsequent syncs
read changed ids and update the existing HNSW graph. A private cache SQLite file
stores index bytes, label mapping, corpus identity, provider name, dimensions and
journal checkpoint in one transaction. Restart restores it and replays later
changes. Invalid vectors fail closed before advancing a checkpoint. Checksum or
provider/corpus mismatches rebuild from the canonical vectors, without deleting
source data. Mutation during comparison rejects the measurement.

Cache paths must be private trusted local files. Do not load user-uploaded or
untrusted HNSW binaries. Cache write failure blocks diagnostics, not exact search.
A physically corrupt/unwritable cache SQLite file can require the operator to
choose a new cache path; no automatic deletion is attempted.

## Actual measurements

Run `python scripts/benchmark_ann_incremental.py --size 5000 --ef 500`.
Raw JSON for ef=100 and ef=500 is committed under docs/benchmarks.
Generated 5,000 hash-vector records, 20 single-record incremental updates and
source-sentence queries, Python 3.12.14, real hnswlib 0.8.0:

| Metric | ef=100 | ef=500 |
|---|---:|---:|
| Initial backfill + checkpoint ms | 2003.89 | 2310.46 |
| Incremental sync p95 ms | 49.42 | 43.16 |
| Exact p95 ms | 373.84 | 346.68 |
| ANN candidates + exact rerank p95 ms | 5.09 | 5.71 |
| Exact-overlap recall@10 mean | .410 | .955 |
| Exact-overlap recall@10 minimum | .000 | .500 |
| Restart restore ms, no rebuild | 26.23 | 26.17 |

This exposed low recall for distribution-shifted incremental queries at ef=100.
ef=500 improves this corpus but does not pass a production relevance gate.
Several exact scores tie in this generated/hash corpus; overlap is sensitive to
which tied ids HNSW returns. Neither report establishes multilingual semantic
relevance, live neural/NLI model quality, nor production performance. Times are
single-machine measurements, not guarantees. No production cutover.

## Deliberate limits

- Graph updates are incremental; each checkpoint still serializes the full graph,
  an O(N) disk cost. No claim of fully O(delta) persistence.
- Journal and deleted labels grow; compaction must be an explicit future migration.
- Provider identity uses name + dimensions. Operators must use versioned provider
  names and canonical re-embedding for a model change; this does not re-embed.
- Concurrent processes may overwrite checkpoints with older consistent snapshots;
  replay catches up on restart. No cross-process graph sharing or checkpoint lock.
- Persistent mode needs an on-disk canonical database, not `:memory:`.
- No owner authentication UI, NLI reviewer or procedure execution in this slice.
