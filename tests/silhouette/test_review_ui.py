"""Real HTTP shell/security and SQLite review tests, no mocked identity."""
import secrets

from fastapi.testclient import TestClient

from silhouette.api import create_app


def test_ui_disabled_without_explicit_owner_setup(memory):
    with TestClient(create_app(memory)) as client:
        assert client.get('/api/owner-review-ui').status_code == 404


def test_shell_has_no_token_or_evidence_and_security_headers(memory):
    token = secrets.token_hex(32)
    evidence = memory.remember('Private evidence not in public shell', apply_noise_filter=False)
    memory.knowledge.propose_claim('test', 'field', 'value', evidence=[evidence.id])
    with TestClient(create_app(memory, owner_review_token=token, owner_reviewer='test-owner')) as client:
        response = client.get('/api/owner-review-ui')
        assert response.status_code == 200
        assert token not in response.text and evidence.content not in response.text
        assert response.headers['cache-control'] == 'no-store'
        assert "frame-ancestors 'none'" in response.headers['content-security-policy']
        assert 'sha256-' in response.headers['content-security-policy']
        assert 'localStorage' not in response.text and 'sessionStorage' not in response.text
        assert 'innerHTML' not in response.text
        assert client.get('/api/owner-review/claim').status_code == 401
