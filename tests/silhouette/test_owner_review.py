"""Real FastAPI + SQLite integration, no mocked authentication or stores."""
import secrets

import pytest
from fastapi.testclient import TestClient

from silhouette.api import create_app
from silhouette.storage.review import ReviewService


@pytest.fixture
def owner(memory):
    token = secrets.token_hex(32)
    with TestClient(create_app(memory, owner_review_token=token, owner_reviewer='owner-test')) as client:
        yield client, {'Authorization': f'Bearer {token}'}


def claim(memory, object_='Lima'):
    evidence = memory.remember(f'Test resident lives in {object_}', apply_noise_filter=False)
    return memory.knowledge.propose_claim('resident', 'city', object_, evidence=[evidence.id]), evidence


def test_default_disabled_and_explicit_identity(memory):
    with TestClient(create_app(memory)) as client:
        assert client.get('/api/owner-review/claim').status_code == 404
    with pytest.raises(ValueError, match='identity'):
        create_app(memory, owner_review_token=secrets.token_hex(32))
    with pytest.raises(ValueError, match='32 bytes'):
        create_app(memory, owner_review_token='short', owner_reviewer='owner')


def test_auth_covers_reads_writes_and_forged_reviewer(owner, memory):
    client, headers = owner
    target, _ = claim(memory)
    route = f'/api/owner-review/claim/{target}'
    assert client.get(route).status_code == 401
    assert client.get(route, headers={'Authorization': 'Bearer wrong'}).status_code == 401
    assert client.get('/api/owner-review/claim').status_code == 401
    assert client.post(route, json={}).status_code == 401
    data = client.get(route, headers=headers).json()
    body = {'snapshot_sha256': data['snapshot_sha256'], 'decision': 'approve', 'reason': 'reviewed'}
    assert client.post(route, headers=headers, json={**body, 'reviewer': 'forged'}).status_code == 422
    assert client.post(route, headers=headers, json=body).status_code == 200
    row = memory.knowledge._conn.execute('SELECT reviewer FROM reviews WHERE target_id=?', (target,)).fetchone()
    assert row[0] == 'owner-test'
    assert client.post(route, headers=headers, json=body).status_code == 409


def test_exact_claim_and_evidence_snapshot(owner, memory):
    client, headers = owner
    target, evidence = claim(memory)
    route = f'/api/owner-review/claim/{target}'
    data = client.get(route, headers=headers).json()
    assert data['evidence'][0]['content'] == evidence.content
    assert data['proposal']['object'] == 'Lima'
    body = {'snapshot_sha256': data['snapshot_sha256'], 'decision': 'approve', 'reason': 'checked'}
    # Direct SQL changes are detected, not silently approved.
    memory.knowledge._conn.execute("UPDATE claims SET object='Cusco' WHERE id=?", (target,))
    memory.knowledge._conn.commit()
    assert client.post(route, headers=headers, json=body).status_code == 409
    body['snapshot_sha256'] = client.get(route, headers=headers).json()['snapshot_sha256']
    memory.forget(evidence.id)
    assert client.post(route, headers=headers, json=body).status_code == 409
    assert memory.knowledge.claim(target)['status'] == 'SUPERSEDED'


def test_retracted_unknown_evidence_cannot_approve(owner, memory):
    client, headers = owner
    target = memory.knowledge.propose_claim('x', 'y', 'z', evidence=['missing'])
    route = f'/api/owner-review/claim/{target}'
    data = client.get(route, headers=headers).json()
    assert data['evidence'][0]['sha256'] is None
    r = client.post(route, headers=headers, json={'snapshot_sha256': data['snapshot_sha256'],
                                                'decision': 'approve', 'reason': 'checked'})
    assert r.status_code == 409
    assert memory.knowledge.claim(target)['status'] == 'PROPOSED'


def test_conflict_rechecked_inside_review(owner, memory):
    client, headers = owner
    one, _ = claim(memory, 'Lima')
    two, _ = claim(memory, 'Cusco')
    route = f'/api/owner-review/claim/{two}'
    before = client.get(route, headers=headers).json()
    memory.knowledge.approve_claim(one)
    r = client.post(route, headers=headers, json={'snapshot_sha256': before['snapshot_sha256'],
                                                'decision': 'approve', 'reason': 'checked'})
    assert r.status_code == 409
    assert memory.knowledge.claim(two)['status'] == 'CONFLICTED'


def test_procedure_approve_and_revoke_no_execution(owner, memory):
    client, headers = owner
    evidence = memory.remember('Observed: check inventory manually', apply_noise_filter=False)
    target = memory.knowledge.propose_procedure('owner present', ['check inventory'], 'count recorded',
                                               evidence=[evidence.id])
    route = f'/api/owner-review/procedure/{target}'
    for decision, status in (('approve', 'APPROVED'), ('revoke', 'REVOKED')):
        before = client.get(route, headers=headers).json()
        r = client.post(route, headers=headers, json={'snapshot_sha256': before['snapshot_sha256'],
                                                     'decision': decision, 'reason': 'owner decision'})
        assert r.status_code == 200
        assert r.json()['proposal']['status'] == status
    assert client.post('/api/procedures/execute', headers=headers, json={}).status_code == 404
    reviews = memory.knowledge._conn.execute('SELECT decision FROM reviews WHERE target_id=?', (target,)).fetchall()
    assert [row[0] for row in reviews] == ['APPROVED', 'REVOKED']


def test_queue_limits_unknown_kind_and_reason(owner, memory):
    client, headers = owner
    for i in range(3):
        claim(memory, f'city{i}')
    response = client.get('/api/owner-review/claim?limit=2', headers=headers)
    assert len(response.json()['proposals']) == 2
    assert client.get('/api/owner-review/claim?limit=1000', headers=headers).status_code == 422
    assert client.get('/api/owner-review/unknown', headers=headers).status_code == 400
    assert client.get('/api/owner-review/claim/unknown', headers=headers).status_code == 404
    service = ReviewService(memory.knowledge, 'owner-test')
    target, _ = claim(memory, 'Piura')
    with pytest.raises(ValueError, match='reason'):
        service.decide('claim', target, expected_snapshot=service.snapshot('claim', target)['snapshot_sha256'],
                       decision='approve', reason=' ')
