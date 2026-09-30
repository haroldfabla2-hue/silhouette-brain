"""Opt-in owner review endpoints. A deployment-owned token binds one reviewer.

Not multi-tenant authentication. Run behind TLS on a private interface. Existing
legacy API routes are unaffected and are not secured by this module.
"""
from __future__ import annotations

import hmac
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from silhouette.storage.review import ReviewService


class ReviewDecision(BaseModel):
    model_config = ConfigDict(extra='forbid')
    snapshot_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    decision: str = Field(pattern=r'^(approve|revoke)$')
    reason: str = Field(min_length=1, max_length=2000)


def review_router(service: ReviewService, token: str) -> APIRouter:
    if len(token.encode()) < 32:
        raise ValueError('Review token must be a deployment-generated secret of at least 32 bytes')
    token_bytes = token.encode()

    def authenticate(authorization: str | None = Header(default=None)) -> None:
        supplied = authorization or ''
        if not supplied.startswith('Bearer ') or not hmac.compare_digest(
                supplied[7:].encode(), token_bytes):
            raise HTTPException(401, 'Owner review authentication required')

    router = APIRouter(prefix='/api/owner-review', dependencies=[Depends(authenticate)])

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
    def decide(kind: str, target_id: str, request: ReviewDecision) -> dict[str, Any]:
        try:
            return service.decide(kind, target_id, expected_snapshot=request.snapshot_sha256,
                                  decision=request.decision, reason=request.reason)
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    return router
