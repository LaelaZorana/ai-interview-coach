"""Password hashing and signed session cookies, using only the stdlib.

Avoiding bcrypt/passlib keeps the dependency surface minimal and guarantees the
app runs anywhere Python does. Passwords are hashed with PBKDF2-HMAC-SHA256
(310k iterations) and a per-password salt; sessions are stateless, signed cookies
(itsdangerous-style) so no server-side session store is needed.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Optional

from app.config import get_settings

_PBKDF2_ROUNDS = 310_000
_ALGO = "pbkdf2_sha256"


# -- password hashing --------------------------------------------------------

def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ROUNDS)
    return f"{_ALGO}${_PBKDF2_ROUNDS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, rounds_s, salt_hex, hash_hex = stored.split("$")
        if algo != _ALGO:
            return False
        rounds = int(rounds_s)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except (ValueError, AttributeError):
        return False
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, rounds)
    return hmac.compare_digest(dk, expected)


# -- signed session tokens ---------------------------------------------------

def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64d(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def _sign(payload_b64: str) -> str:
    key = get_settings().secret_key.encode("utf-8")
    sig = hmac.new(key, payload_b64.encode("ascii"), hashlib.sha256).digest()
    return _b64e(sig)


def make_session_token(user_id: int) -> str:
    payload = {"uid": user_id, "iat": int(time.time())}
    payload_b64 = _b64e(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    return f"{payload_b64}.{_sign(payload_b64)}"


def read_session_token(token: Optional[str]) -> Optional[int]:
    """Return the user id if the token is valid and unexpired, else None."""
    if not token or "." not in token:
        return None
    payload_b64, sig = token.rsplit(".", 1)
    if not hmac.compare_digest(sig, _sign(payload_b64)):
        return None
    try:
        payload = json.loads(_b64d(payload_b64))
    except (ValueError, json.JSONDecodeError):
        return None
    iat = payload.get("iat", 0)
    if time.time() - iat > get_settings().session_max_age:
        return None
    uid = payload.get("uid")
    return int(uid) if isinstance(uid, int) else None
