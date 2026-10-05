# Owner review, entailment advice and procedure preview

This slice adds foundations, not a production authentication system, neural
validation result, or arbitrary-code sandbox. All paths are off by default.

## Review API

A deployment can explicitly pass a generated secret (at least 32 bytes) and
server-bound reviewer identity to `create_app`:

```python
app = create_app(memory, owner_review_token=secret_from_environment,
                 owner_reviewer='configured-owner-identity')
```

Token must come from secure deployment configuration. Do not place it in source,
URLs or examples, and do not expose this service without TLS and a private
interface. Token possession authenticates that configured reviewer. It does not
prove a human personally clicked, nor supply multi-user identities. No endpoint
can set the reviewer from the request body.

Bearer authentication covers every `/api/owner-review` read and write:

- GET `/{claim|procedure}?limit=20`: bounded proposal queue.
- GET `/{claim|procedure}/{id}`: structured proposal, current source text/hash,
  deterministic snapshot digest.
- POST same item route: `snapshot_sha256`, `decision`, `reason` only. Decisions
  are claim approve or procedure approve/revoke. Extra fields are rejected.

Approval binds the exact proposal and currently resolved evidence. Proposal or
source changes require a fresh review. A SQLite writer reservation protects the
knowledge snapshot/conflict decision across processes. Reviews are audited;
claim conflict is rechecked inside the write transaction. Approval of procedures
changes registry state only, never executes steps. No bulk approval, extraction,
conflict resolution or owner UI is provided.

Legacy memory and engine routes are unchanged and NOT protected by this token.
Production needs service-wide auth, TLS, credential rotation, principal/session
lifecycle, rate limiting and a real owner UI. Evidence and knowledge use separate
SQLite databases: there is no distributed transaction joining them. Concurrent
source deletion after checking is still possible. Existing forget invalidates
derivations, but strict cross-store atomic review/retrieval remains future work.

## NLI/paraphrase-aware groundwork

`review_statement` checks live citation id/hash/span. Exact statements return
VERIFIED_EXTRACT, not proof of world truth. Paraphrases without an evaluated
provider return NEEDS_OWNER_REVIEW. The versioned provider interface receives
only cited premise + hypothesis, validates probability shape, fails closed on
inference errors, rechecks evidence afterward and always returns advice requiring
owner review. Model scores never auto-accept claims or alter knowledge state.

No model/adapter is installed or evaluated. Tests use actual stored evidence and
the no-provider path, not fake inference or fabricated accuracy. Provider
execution branches still need integration tests with a real adapter plus a
labeled multilingual corpus, contradiction/paraphrase thresholds and adversarial
failure evaluation before use.

## Safest procedure slice

`procedure_preview.preview` is a tiny declarative in-memory evaluator. It accepts
only JSON scalar literals and selection of previous results, at most 32
operations / 16 KiB, bound to an exact supplied plan digest. Unsupported fields,
filesystem/network/shell operations, imports, dynamic code and unknown operations
are rejected. Strings remain data, even when they contain command text.

This is PREVIEW_ONLY, not execution authority, not an OS security boundary and
not a natural-language-to-code compiler. No API execution route is installed.
Registry approval is never interpreted as permission to execute. Future execution
requires exact action-level approval, isolation outside the service (separate
unprivileged worker/container), no ambient credentials, default-deny network and
filesystem, resource/time quotas, revocation recheck, and auditable outputs. A
Python subprocess alone is not a safe hostile-code sandbox. No arbitrary-code
first slice is attempted here.
