# ANN shadow and reviewed derivations

This branch stacks on P1/P2 PR #5. Nothing is merged and exact cosine remains
unchanged as the default. Install `.[ann]` and set `SILHOUETTE_ANN_SHADOW=true`
only to call `semantic.ann_shadow_compare(query, limit=10)` explicitly.
Missing HNSW dependencies and invalid vectors fail that diagnostic, not normal
retrieval. The in-process HNSW projection backfills from SQLite, rebuilds after
local/external commits, and checks freshness after each comparison. It is not
persisted as a second source of truth. Rebuilds are expensive and this first
implementation is a diagnostic, not an incremental production rollout.

## Actual local measurements

Python 3.10.12, Linux x86_64, HNSW cosine M16, ef100, ef_construction200,
single thread, 384-dimensional real feature-hash text embeddings. Synthetic
English event sentences, six cities/seven topics, seed 17. Queries are sampled
corpus sentences, not held-out human-labeled questions. Recall here means top-10
ID overlap with exact cosine, not semantic relevance or model accuracy.

| Rows | Queries | Mean/min recall@10 | Exact p95 ms | ANN p95 ms | Backfill ms |
| --- | --- | --- | --- | --- | --- |
| 5,000 | 12 | 1.0 / 1.0 | 883.21 | 5.82 | 1,500.42 |
| 20,000 | 20 | 0.995 / 0.9 | 2,782.72 | 4.97 | 6,227.13 |

p95 is nearest-rank measured wall time, including query embedding, SQLite fetch,
and scoring/rerank, excluding backfill. Twenty queries are still a small sample for a stable
p95 estimate. Raw per-query results are committed in `docs/benchmarks/`.
50,000-row attempts exceeded the local command time window and produced no
completed measurement; no numbers are claimed for them.
Reproduce with `python scripts/benchmark_ann.py --size 20000 --queries 20
--output result.json`. CI runs actual HNSW tests using the optional extra.

## Critic and review

Summary statements cite episode ID, SHA256 and character span. The critic checks
current non-tombstoned source and exact span equality, storing VERIFIED_EXTRACT
or REJECTED with error reasons. Forgetting source evidence revokes summaries.
VERIFIED_EXTRACT means faithfully copied source text, not a proven world fact.
Paraphrases are deliberately rejected; NLI/live-model evaluation is still pending.
No automatic summary generation/promotion or dream-to-fact path was added.

Claim approval now takes the SQLite writer lock then rechecks accepted temporal
conflicts. Two earlier nonconflicting proposals cannot both silently become
accepted contradictory facts. Conflict IDs and review audit history are retained.
Standalone legacy KnowledgeStore callers keep ID-only evidence behavior; the
MemorySystem supplies its actual live episode resolver. This registry does not
prove external owner identity or NLP extraction accuracy.

Procedures require explicit reviewer/reason and an exact reviewed snapshot of
steps/pre/postconditions plus live evidence. Approval/revocation is audited.
There is deliberately no execution API: approved does not mean permission to
run code. Authenticated owner review UI and a real isolation sandbox remain
pending, as do revision migration and richer temporal multi-valued predicates.

## Validation and honest limits

120 tests passed locally; one existing notification-hook integration test skips
because no OpenClaw gateway is configured. No new tests mock or skip behavior.
Lint/typecheck pass. An existing API test used a semantic paraphrase with a
feature-hash embedder; its query now shares real lexical tokens with its source,
without changing production retrieval or claiming transformer semantics.
Production corpora, multilingual relevance labels, model/provider identity
migration, incremental persistent ANN, cutover/rollback and live NLI benchmarks
are not completed here. Do not turn the synthetic overlap numbers into a
production claim or enable approximate retrieval by default.
