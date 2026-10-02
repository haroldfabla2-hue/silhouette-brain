"""WebAuthn owner assertions for review decisions (opt-in, needs the `review-auth` extra).

Verifies real WebAuthn byte formats server-side. Attestation "none" and ES256 only.
It proves possession of an enrolled key plus user verification, bound to one exact
decision. It does not prove the authenticator make/model.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import sqlite3
import struct
import time
from dataclasses import dataclass
from typing import Any

UP, UV, AT = 0x01, 0x04, 0x40


class IdentityError(ValueError):
    """Raised for any refused ceremony. Message is safe to show the owner."""


def b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode()


def unb64u(text: str) -> bytes:
    try:
        return base64.urlsafe_b64decode(text + '=' * (-len(text) % 4))
    except Exception as exc:
        raise IdentityError('Malformed base64url') from exc


def _cbor(buf: bytes, at: int = 0, depth: int = 0) -> tuple[Any, int]:
    """Minimal CBOR reader for WebAuthn attestation objects and COSE keys."""
    if depth > 8 or at >= len(buf):
        raise IdentityError('Bad CBOR')
    head = buf[at]
    major, info, pos = head >> 5, head & 31, at + 1
    if info < 24:
        n = info
    elif info == 24:
        n, pos = buf[pos], pos + 1
    elif info == 25:
        n, pos = struct.unpack_from('>H', buf, pos)[0], pos + 2
    elif info == 26:
        n, pos = struct.unpack_from('>I', buf, pos)[0], pos + 4
    else:
        raise IdentityError('Unsupported CBOR length')
    if major == 0:
        return n, pos
    if major == 1:
        return -1 - n, pos
    if major in (2, 3):
        if pos + n > len(buf):
            raise IdentityError('Bad CBOR')
        raw = bytes(buf[pos:pos + n])
        return (raw if major == 2 else raw.decode('utf-8')), pos + n
    if major == 4:
        out = []
        for _ in range(n):
            value, pos = _cbor(buf, pos, depth + 1)
            out.append(value)
        return out, pos
    if major == 5:
        mapping = {}
        for _ in range(n):
            key, pos = _cbor(buf, pos, depth + 1)
            mapping[key], pos = _cbor(buf, pos, depth + 1)
        return mapping, pos
    raise IdentityError('Unsupported CBOR')


@dataclass(frozen=True)
class IdentityConfig:
    rp_id: str
    origins: tuple[str, ...]
    challenge_ttl_s: int = 120

    def __post_init__(self) -> None:
        if not self.rp_id or not self.origins:
            raise ValueError('rp_id and at least one origin required')

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> IdentityConfig:
        """SILHOUETTE_REVIEW_RP_ID and SILHOUETTE_REVIEW_ORIGINS (comma separated). No defaults on purpose."""
        import os
        source = os.environ if env is None else env
        rp_id = source.get('SILHOUETTE_REVIEW_RP_ID', '').strip()
        origins = tuple(o.strip() for o in source.get('SILHOUETTE_REVIEW_ORIGINS', '').split(',') if o.strip())
        if not rp_id or not origins:
            raise ValueError('Set SILHOUETTE_REVIEW_RP_ID and SILHOUETTE_REVIEW_ORIGINS')
        return cls(rp_id, origins)


def _check_client(client_json: str, kind: str, challenge: str, cfg: IdentityConfig) -> None:
    try:
        client = json.loads(unb64u(client_json))
    except (ValueError, UnicodeDecodeError) as exc:
        raise IdentityError('Bad clientDataJSON') from exc
    if client.get('type') != kind:
        raise IdentityError('Wrong ceremony type')
    if not hmac.compare_digest(str(client.get('challenge')).encode(), challenge.encode()):
        raise IdentityError('Challenge mismatch')
    if client.get('origin') not in cfg.origins:
        raise IdentityError('Origin not allowed')
    if client.get('crossOrigin') is True:
        raise IdentityError('Cross-origin ceremony refused')


def _auth_data(ad: bytes, cfg: IdentityConfig) -> tuple[int, int, bytes]:
    if len(ad) < 37:
        raise IdentityError('Short authenticator data')
    if not hmac.compare_digest(ad[:32], hashlib.sha256(cfg.rp_id.encode()).digest()):
        raise IdentityError('rpId mismatch')
    return ad[32], struct.unpack('>I', ad[33:37])[0], ad[37:]


def _public_key(x: bytes, y: bytes) -> Any:
    # Imported lazily so the base install and the legacy review path never need `cryptography`.
    from cryptography.hazmat.primitives.asymmetric import ec
    try:
        return ec.EllipticCurvePublicNumbers(int.from_bytes(x, 'big'), int.from_bytes(y, 'big'),
                                             ec.SECP256R1()).public_key()
    except ValueError as exc:
        raise IdentityError('Bad public key') from exc


def verify_registration(client_json: str, attestation: str, challenge: str,
                        cfg: IdentityConfig) -> tuple[str, bytes, bytes, int]:
    """Return (credential_id, x, y, sign_count) for an attestation-"none" registration."""
    _check_client(client_json, 'webauthn.create', challenge, cfg)
    obj, _ = _cbor(unb64u(attestation))
    if not isinstance(obj, dict) or obj.get('fmt') != 'none' or not isinstance(obj.get('authData'), bytes):
        raise IdentityError('Only attestation "none" is supported')
    flags, count, rest = _auth_data(obj['authData'], cfg)
    if not (flags & UP and flags & UV and flags & AT):
        raise IdentityError('User presence, verification and attested data required')
    if len(rest) < 18:
        raise IdentityError('Short attested data')
    id_len = struct.unpack('>H', rest[16:18])[0]
    if id_len < 16 or id_len > 1023 or len(rest) < 18 + id_len:
        raise IdentityError('Bad credential id')
    key, _ = _cbor(rest, 18 + id_len)
    if not isinstance(key, dict) or key.get(1) != 2 or key.get(3) != -7 or key.get(-1) != 1:
        raise IdentityError('Only ES256 (P-256) credentials are supported')
    x, y = key.get(-2), key.get(-3)
    if not isinstance(x, bytes) or not isinstance(y, bytes) or len(x) != 32 or len(y) != 32:
        raise IdentityError('Bad public key')
    _public_key(x, y)
    return b64u(rest[18:18 + id_len]), x, y, count


class OwnerIdentity:
    """Credentials, single-use challenges and assertion checks on the review database."""

    def __init__(self, conn: sqlite3.Connection, config: IdentityConfig) -> None:
        self.conn, self.cfg = conn, config
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS owner_credentials (
                credential_id TEXT PRIMARY KEY, x BLOB NOT NULL, y BLOB NOT NULL,
                sign_count INTEGER NOT NULL, created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS owner_challenges (
                challenge TEXT PRIMARY KEY, kind TEXT NOT NULL, binding TEXT NOT NULL,
                expires REAL NOT NULL, used INTEGER NOT NULL DEFAULT 0);""")
        conn.commit()

    def has_credentials(self) -> bool:
        return self.conn.execute('SELECT 1 FROM owner_credentials LIMIT 1').fetchone() is not None

    def _issue(self, kind: str, binding: dict[str, Any]) -> str:
        challenge = b64u(secrets.token_bytes(32))
        self.conn.execute('INSERT INTO owner_challenges(challenge,kind,binding,expires) VALUES (?,?,?,?)',
                          (challenge, kind, json.dumps(binding, sort_keys=True), time.time() + self.cfg.challenge_ttl_s))
        self.conn.commit()
        return challenge

    def _consume(self, kind: str, challenge: str) -> dict[str, Any]:
        """Atomic, before verification: a failed attempt burns the challenge."""
        cur = self.conn.execute(
            'UPDATE owner_challenges SET used=1 WHERE challenge=? AND kind=? AND used=0 AND expires>=?',
            (challenge, kind, time.time()))
        self.conn.commit()
        if cur.rowcount != 1:
            raise IdentityError('Unknown, used or expired challenge')
        return json.loads(self.conn.execute('SELECT binding FROM owner_challenges WHERE challenge=?',
                                            (challenge,)).fetchone()[0])

    def begin_enrollment(self) -> str:
        return self._issue('enroll', {})

    def finish_enrollment(self, challenge: str, client_json: str, attestation: str) -> str:
        self._consume('enroll', challenge)
        cred_id, x, y, count = verify_registration(client_json, attestation, challenge, self.cfg)
        try:
            self.conn.execute('INSERT INTO owner_credentials VALUES (?,?,?,?,?)', (cred_id, x, y, count, time.time()))
            self.conn.commit()
        except sqlite3.IntegrityError as exc:
            raise IdentityError('Credential already enrolled') from exc
        return cred_id

    def begin_decision(self, binding: dict[str, Any]) -> str:
        return self._issue('decide', binding)

    def verify_decision(self, challenge: str, binding: dict[str, Any], credential_id: str,
                        client_json: str, authenticator_data: str, signature: str) -> None:
        issued = self._consume('decide', challenge)
        if issued != json.loads(json.dumps(binding, sort_keys=True)):
            raise IdentityError('Challenge was issued for a different decision')
        row = self.conn.execute('SELECT x,y,sign_count FROM owner_credentials WHERE credential_id=?',
                                (credential_id,)).fetchone()
        if row is None:
            raise IdentityError('Credential not enrolled')
        _check_client(client_json, 'webauthn.get', challenge, self.cfg)
        ad = unb64u(authenticator_data)
        flags, count, _ = _auth_data(ad, self.cfg)
        if not (flags & UP and flags & UV):
            raise IdentityError('User presence and verification required')
        signed = ad + hashlib.sha256(unb64u(client_json)).digest()
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import ec
        try:
            _public_key(row[0], row[1]).verify(unb64u(signature), signed, ec.ECDSA(hashes.SHA256()))
        except InvalidSignature as exc:
            raise IdentityError('Bad assertion signature') from exc
        if (count or row[2]) and count <= row[2]:
            raise IdentityError('Authenticator counter did not advance (possible cloned credential)')
        self.conn.execute('UPDATE owner_credentials SET sign_count=? WHERE credential_id=?', (count, credential_id))
        self.conn.commit()
