"""WebAuthn owner assertions over real FastAPI + SQLite.

The authenticator here is SOFTWARE: real P-256 keys and ECDSA in the exact WebAuthn byte
formats. It validates server logic only; no hardware key or browser ceremony is exercised.
"""
import hashlib
import json
import os
import secrets
import struct

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from silhouette.api import create_app
from silhouette.storage.owner_identity import IdentityConfig, b64u

RP, ORIGIN = 'review.example.test', 'https://review.example.test'


def head(major, n):
    if n < 24:
        return bytes([(major << 5) | n])
    return bytes([(major << 5) | 24, n]) if n < 256 else bytes([(major << 5) | 25]) + struct.pack('>H', n)


def c_int(n):
    return head(0, n) if n >= 0 else head(1, -1 - n)


def c_bytes(b):
    return head(2, len(b)) + b


def c_text(t):
    return head(3, len(t.encode())) + t.encode()


def c_map(pairs):
    return head(5, len(pairs)) + b''.join(k + v for k, v in pairs)


class Authenticator:
    def __init__(self):
        self.key = ec.generate_private_key(ec.SECP256R1())
        nums = self.key.public_key().public_numbers()
        self.x, self.y = nums.x.to_bytes(32, 'big'), nums.y.to_bytes(32, 'big')
        self.cred = secrets.token_bytes(32)
        self.counter = 0

    def _ad(self, flags, with_key):
        base = hashlib.sha256(RP.encode()).digest() + bytes([flags]) + struct.pack('>I', self.counter)
        if not with_key:
            return base
        cose = c_map([(c_int(1), c_int(2)), (c_int(3), c_int(-7)), (c_int(-1), c_int(1)),
                      (c_int(-2), c_bytes(self.x)), (c_int(-3), c_bytes(self.y))])
        return base + bytes(16) + struct.pack('>H', len(self.cred)) + self.cred + cose

    def register(self, challenge, origin=ORIGIN, flags=0x45):
        client = json.dumps({'type': 'webauthn.create', 'challenge': challenge, 'origin': origin}).encode()
        att = c_map([(c_text('fmt'), c_text('none')), (c_text('attStmt'), c_map([])),
                     (c_text('authData'), c_bytes(self._ad(flags, True)))])
        return {'challenge': challenge, 'client_data_json': b64u(client), 'attestation_object': b64u(att)}

    def assertion(self, challenge, origin=ORIGIN, flags=0x05, bump=True, kind='webauthn.get', cred=None):
        if bump:
            self.counter += 1
        client = json.dumps({'type': kind, 'challenge': challenge, 'origin': origin}).encode()
        ad = self._ad(flags, False)
        sig = self.key.sign(ad + hashlib.sha256(client).digest(), ec.ECDSA(hashes.SHA256()))
        return {'challenge': challenge, 'credential_id': b64u(cred or self.cred),
                'client_data_json': b64u(client), 'authenticator_data': b64u(ad), 'signature': b64u(sig)}


@pytest.fixture
def env(memory):
    token = secrets.token_hex(32)
    app = create_app(memory, owner_review_token=token, owner_reviewer='owner-test',
                     owner_identity=IdentityConfig(RP, (ORIGIN,), challenge_ttl_s=60))
    with TestClient(app) as client:
        yield client, {'Authorization': f'Bearer {token}'}, memory


def proposal(memory, value='Lima'):
    evidence = memory.remember(f'Test resident lives in {value}', apply_noise_filter=False)
    return memory.knowledge.propose_claim('resident', 'city', value, evidence=[evidence.id])


def enroll(client, headers, auth):
    ch = client.post('/api/owner-review/identity/enroll/begin', headers=headers, json={}).json()['challenge']
    r = client.post('/api/owner-review/identity/enroll/finish', headers=headers, json=auth.register(ch))
    assert r.status_code == 200, r.text
    return r.json()['credential_id']


def start(client, headers, target, reason='reviewed exact evidence', decision='approve'):
    route = f'/api/owner-review/claim/{target}'
    snap = client.get(route, headers=headers).json()['snapshot_sha256']
    body = {'snapshot_sha256': snap, 'decision': decision, 'reason': reason}
    ch = client.post(route + '/challenge', headers=headers, json=body).json()['challenge']
    return route, body, ch


def test_token_alone_can_read_but_not_decide_and_second_enrollment_refused(env):
    client, headers, memory = env
    target = proposal(memory)
    auth = Authenticator()
    enroll(client, headers, auth)
    route = f'/api/owner-review/claim/{target}'
    snap = client.get(route, headers=headers).json()['snapshot_sha256']
    assert client.post(route, headers=headers, json={'snapshot_sha256': snap, 'decision': 'approve', 'reason': 'x'}).status_code == 403
    assert client.post('/api/owner-review/identity/enroll/begin', headers=headers, json={}).status_code == 409
    assert memory.knowledge.claim(target)['status'] == 'PROPOSED'


def test_valid_assertion_approves_and_challenge_is_single_use(env):
    client, headers, memory = env
    target, auth = proposal(memory), Authenticator()
    enroll(client, headers, auth)
    route, body, ch = start(client, headers, target)
    assert client.post(route, headers=headers, json={**body, **auth.assertion(ch)}).status_code == 200
    assert memory.knowledge.claim(target)['status'] == 'ACCEPTED'
    assert client.post(route, headers=headers, json={**body, **auth.assertion(ch)}).status_code == 403


def test_binding_to_exact_decision_reason_and_target(env):
    client, headers, memory = env
    target, other, auth = proposal(memory), proposal(memory, 'Cusco'), Authenticator()
    enroll(client, headers, auth)
    route, body, ch = start(client, headers, target)
    assert client.post(route, headers=headers, json={**body, 'reason': 'different', **auth.assertion(ch)}).status_code == 403
    route2, body2, ch2 = start(client, headers, target)
    other_route = f'/api/owner-review/claim/{other}'
    other_snap = client.get(other_route, headers=headers).json()['snapshot_sha256']
    forged = {**body2, 'snapshot_sha256': other_snap, **auth.assertion(ch2)}
    assert client.post(other_route, headers=headers, json=forged).status_code == 403
    assert memory.knowledge.claim(target)['status'] == 'PROPOSED' and memory.knowledge.claim(other)['status'] == 'PROPOSED'


@pytest.mark.parametrize('kwargs,why', [
    ({'origin': 'https://evil.example.test'}, 'Origin'),
    ({'flags': 0x01}, 'verification'),
    ({'kind': 'webauthn.create'}, 'ceremony'),
    ({'cred': b'x' * 32}, 'enrolled'),
])
def test_refuses_bad_assertions(env, kwargs, why):
    client, headers, memory = env
    target, auth = proposal(memory), Authenticator()
    enroll(client, headers, auth)
    route, body, ch = start(client, headers, target)
    r = client.post(route, headers=headers, json={**body, **auth.assertion(ch, **kwargs)})
    assert r.status_code == 403 and why in r.json()['detail']
    assert memory.knowledge.claim(target)['status'] == 'PROPOSED'


def test_forged_signature_and_cloned_counter(env):
    client, headers, memory = env
    target, auth = proposal(memory), Authenticator()
    enroll(client, headers, auth)
    attacker = Authenticator()
    route, body, ch = start(client, headers, target)
    forged = attacker.assertion(ch, cred=auth.cred)
    assert 'signature' in client.post(route, headers=headers, json={**body, **forged}).json()['detail']
    route, body, ch = start(client, headers, target)
    assert client.post(route, headers=headers, json={**body, **auth.assertion(ch)}).status_code == 200
    target2 = proposal(memory, 'Piura')
    route, body, ch = start(client, headers, target2)
    r = client.post(route, headers=headers, json={**body, **auth.assertion(ch, bump=False)})
    assert 'counter' in r.json()['detail']


def test_enrollment_rejects_bad_flags_and_origin(env):
    client, headers, _ = env
    auth = Authenticator()
    for kwargs, why in (({'flags': 0x41}, 'verification'), ({'origin': 'https://evil.example.test'}, 'Origin')):
        ch = client.post('/api/owner-review/identity/enroll/begin', headers=headers, json={}).json()['challenge']
        r = client.post('/api/owner-review/identity/enroll/finish', headers=headers, json=auth.register(ch, **kwargs))
        assert r.status_code == 400 and why in r.json()['detail']


def test_config_from_env_has_no_defaults_and_legacy_path_unchanged(memory):
    with pytest.raises(ValueError):
        IdentityConfig.from_env({})
    cfg = IdentityConfig.from_env({'SILHOUETTE_REVIEW_RP_ID': 'localhost', 'SILHOUETTE_REVIEW_ORIGINS': 'http://localhost:8000, http://127.0.0.1:8000'})
    assert cfg.origins == ('http://localhost:8000', 'http://127.0.0.1:8000')
    token = secrets.token_hex(32)
    with TestClient(create_app(memory, owner_review_token=token, owner_reviewer='o')) as client:
        h = {'Authorization': f'Bearer {token}'}
        t = proposal(memory)
        snap = client.get(f'/api/owner-review/claim/{t}', headers=h).json()['snapshot_sha256']
        assert client.post(f'/api/owner-review/claim/{t}', headers=h, json={'snapshot_sha256': snap, 'decision': 'approve', 'reason': 'ok'}).status_code == 200
        assert client.post(f'/api/owner-review/claim/{t}/challenge', headers=h, json={}).status_code in (404, 405)
