"""Opt-in owner review endpoints. A deployment-owned token binds one reviewer.

Not multi-tenant authentication. Run behind TLS on a private interface. Existing
legacy API routes are unaffected and are not secured by this module.
"""
from __future__ import annotations

import hmac
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from silhouette.storage.owner_identity import IdentityError, OwnerIdentity
from silhouette.storage.review import ReviewService


class ReviewDecision(BaseModel):
    model_config = ConfigDict(extra='forbid')
    snapshot_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    decision: str = Field(pattern=r'^(approve|revoke)$')
    reason: str = Field(min_length=1, max_length=2000)


class DecisionChallengeRequest(ReviewDecision):
    pass


class SignedDecision(ReviewDecision):
    challenge: str = Field(min_length=20, max_length=200)
    credential_id: str = Field(min_length=10, max_length=2000)
    client_data_json: str = Field(min_length=10, max_length=8000)
    authenticator_data: str = Field(min_length=10, max_length=4000)
    signature: str = Field(min_length=10, max_length=4000)


class EnrollFinish(BaseModel):
    model_config = ConfigDict(extra='forbid')
    challenge: str = Field(min_length=20, max_length=200)
    client_data_json: str = Field(min_length=10, max_length=8000)
    attestation_object: str = Field(min_length=10, max_length=20000)


def review_router(service: ReviewService, token: str, identity: OwnerIdentity | None = None) -> APIRouter:
    if len(token.encode()) < 32:
        raise ValueError('Review token must be a deployment-generated secret of at least 32 bytes')
    token_bytes = token.encode()

    def authenticate(authorization: str | None = Header(default=None)) -> None:
        supplied = authorization or ''
        if not supplied.startswith('Bearer ') or not hmac.compare_digest(
                supplied[7:].encode(), token_bytes):
            raise HTTPException(401, 'Owner review authentication required')

    router = APIRouter(prefix='/api/owner-review', dependencies=[Depends(authenticate)])

    def binding(kind: str, target_id: str, body: ReviewDecision) -> dict[str, str]:
        return {'kind': kind, 'id': target_id, 'snapshot': body.snapshot_sha256,
                'decision': body.decision, 'reason': body.reason}

    if identity is not None:
        # Registered before the generic routes so these literal paths win.
        @router.post('/identity/enroll/begin')
        def enroll_begin() -> dict[str, Any]:
            # First credential: the deployment token holder bootstraps trust. Later ones are refused
            # here, so a leaked token alone cannot add a second authenticator.
            if identity.has_credentials():
                raise HTTPException(409, 'A credential is already enrolled')
            return {'challenge': identity.begin_enrollment(), 'rp_id': identity.cfg.rp_id}

        @router.post('/identity/enroll/finish')
        def enroll_finish(body: EnrollFinish) -> dict[str, Any]:
            try:
                return {'credential_id': identity.finish_enrollment(
                    body.challenge, body.client_data_json, body.attestation_object)}
            except IdentityError as exc:
                raise HTTPException(400, str(exc)) from exc

        @router.post('/{kind}/{target_id}/challenge')
        def decision_challenge(kind: str, target_id: str, body: DecisionChallengeRequest) -> dict[str, Any]:
            try:
                current = service.snapshot(kind, target_id)
            except LookupError as exc:
                raise HTTPException(404, str(exc)) from exc
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
            if current['snapshot_sha256'] != body.snapshot_sha256:
                raise HTTPException(409, 'Stale reviewed snapshot; read the proposal again')
            return {'challenge': identity.begin_decision(binding(kind, target_id, body)),
                    'rp_id': identity.cfg.rp_id, 'credential_required': identity.has_credentials()}

    @router.get('/{kind}/{target_id}')
    def snapshot(kind: str, target_id: str) -> dict[str, Any]:
        try:
            return service.snapshot(kind, target_id)
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @router.get('/{kind}')
    def queue(kind: str, limit: int = Query(20, ge=1, le=100)) -> dict[str, Any]:
        table = {'claim': 'claims', 'procedure': 'procedures'}.get(kind)
        if table is None:
            raise HTTPException(400, 'Unknown review kind')
        ids = service.store._conn.execute(
            f"SELECT id FROM {table} WHERE status IN ('PROPOSED','CONFLICTED') ORDER BY id LIMIT ?",
            (limit,)).fetchall()
        return {'proposals': [service.snapshot(kind, row['id']) for row in ids]}

    @router.post('/{kind}/{target_id}')
    def decide(kind: str, target_id: str, request: ReviewDecision | SignedDecision) -> dict[str, Any]:
        if identity is not None:
            # The bearer token alone can read but can no longer decide.
            if not isinstance(request, SignedDecision):
                raise HTTPException(403, 'Owner assertion required')
            try:
                identity.verify_decision(request.challenge, binding(kind, target_id, request),
                                         request.credential_id, request.client_data_json,
                                         request.authenticator_data, request.signature)
            except IdentityError as exc:
                raise HTTPException(403, str(exc)) from exc
        try:
            return service.decide(kind, target_id, expected_snapshot=request.snapshot_sha256,
                                  decision=request.decision, reason=request.reason)
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    return router
