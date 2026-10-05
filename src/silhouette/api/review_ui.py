"""No-data UI shell, installed only when owner review is explicitly enabled."""
import base64
import hashlib
import re

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from silhouette.api.review_ui_page import PAGE


def owner_review_ui_router() -> APIRouter:
    router = APIRouter()
    scripts = re.findall(r'<script>(.*?)</script>', PAGE, re.S)

    def hashes(parts: list[str]) -> str:
        return ' '.join("'sha256-" + base64.b64encode(hashlib.sha256(
            part.encode()).digest()).decode() + "'" for part in parts)

    @router.get('/api/owner-review-ui', response_class=HTMLResponse)
    def screen() -> HTMLResponse:
        return HTMLResponse(PAGE, headers={
            'Content-Security-Policy': "default-src 'none'; script-src " + hashes(scripts)
                + "; style-src 'unsafe-inline'; connect-src 'self'; "
                + "img-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
            'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer',
            'X-Content-Type-Options': 'nosniff', 'Permissions-Policy': 'camera=(), microphone=()',
        })

    return router
