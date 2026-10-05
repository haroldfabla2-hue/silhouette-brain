# Owner review screen: explicit token, exact evidence, two-step decision

Adds `/api/owner-review-ui` only when the existing deployment owner-review token
and server-bound reviewer are explicitly configured. Default stays disabled.
UI shell contains no owner data or token. Every data read/write still uses the
existing authenticated review routes and exact snapshot digest. Approval never
executes a procedure. Existing legacy API routes remain unchanged and unprotected
by this owner-review token; do not expose the whole service publicly.

Single-owner deployment token authentication, not proof a human was present,
not multi-tenant session/SSO/passkey identity. User enters the deployment secret
on HTTPS or loopback only, then the password field is immediately cleared. Token
is retained only in tab memory, not local/session storage, cookies, URLs or HTML.
Disconnect/pagehide clears it. No analytics/CDN/external resources. Untrusted
proposal/evidence uses textContent only; instructions and markup remain data.
Shell has no-store, no-referrer, nosniff, frame-ancestors none and a hash-pinned
script CSP. Same-origin fetch denies redirects and omits cookies. Rate limiting,
TLS provisioning, credential rotation and global service auth remain deployment
responsibilities, not claimed complete here.

Screen displays structured exact proposal, live cited text/hash and snapshot.
Reason and reviewed checkbox required. A separate final-decision screen shows
item, snapshot, action and reason before explicit confirmation. Edits invalidate
staged decisions. Duplicate submits disabled; server rejects stale snapshot.
Unknown/missing/changed evidence cannot become accepted through the UI. Existing
claim conflict checks/audit and procedure revoke behavior retained. Queue bounded
20 pending proposals; inspect by exact ID also supports approved procedure revoke.

October 1 local published-slice validation: 147 full tests, lint/mypy pass; two
new real HTTP shell/auth/security tests. Real Chromium against local FastAPI +
SQLite also verified token login, malicious evidence markup rendered as text,
no browser storage, approval not fired at staging, explicit approve/revoke with
stored state checks, disconnect and no JS errors. Pixels inspected at desktop
1280x1000 and mobile390x844; mobile overflow fixed and re-tested. No simulated
backend/model or production approvals. No dependency added to production;
Playwright used only for the actual local inspection, not required by core CI.

Still not a complete human-authentication product: bearer possession binds one
configured reviewer, it does not prove a physical human. No claim of authenticated
biometric user presence, tenant isolation or hostile-code execution. Those require
separate reviewed deployment architecture rather than claiming a UI solves them.

## Owner identity: WebAuthn (opt-in, extra `review-auth`)

`create_app(memory, owner_review_token=..., owner_reviewer=..., owner_identity=IdentityConfig(rp_id, origins))`
(or `IdentityConfig.from_env()`: `SILHOUETTE_REVIEW_RP_ID`, `SILHOUETTE_REVIEW_ORIGINS`
comma separated; there are no defaults). Local use: rp_id `localhost`, origin
`http://localhost:<port>`. For a server later, set the HTTPS host and origin; nothing else changes.
Install: `pip install -e ".[api,review-auth]"` (adds `cryptography`).

With identity configured the bearer token can read but cannot approve or revoke (403).
Flow: `POST /api/owner-review/{kind}/{id}/challenge` returns a single-use challenge bound to
kind, id, exact snapshot hash, decision and reason; the UI shows that exact data, the
authenticator signs, and `POST /api/owner-review/{kind}/{id}` carries the assertion.
Checks: ceremony type, challenge, allowed origin, rpIdHash, user presence AND verification,
ES256 signature, strictly increasing counter. The challenge is consumed atomically before
verification, so a failed try burns it. The first credential is enrolled with
`identity/enroll/begin|finish` (needs the token); once one exists, further enrollment is refused.

Limits: tests use a SOFTWARE authenticator (real P-256/ECDSA, exact WebAuthn byte formats);
no hardware key or real browser ceremony has been exercised. Attestation "none": proves a key
and user verification, not the device model. No credential removal or recovery, one reviewer,
no quorum. Browsers require HTTPS or localhost for WebAuthn.
