"""Tests for password hashing and signed session tokens."""
from __future__ import annotations

import app.config as config
from app.security import (
    hash_password,
    make_session_token,
    read_session_token,
    verify_password,
)


def test_password_round_trip():
    h = hash_password("correcthorse")
    assert h != "correcthorse"  # never stored in plaintext
    assert verify_password("correcthorse", h)
    assert not verify_password("wrong", h)


def test_password_hashes_are_salted():
    # Same password -> different stored hashes (random salt).
    assert hash_password("samepass") != hash_password("samepass")


def test_verify_rejects_malformed_hash():
    assert not verify_password("x", "not-a-valid-hash")
    assert not verify_password("x", "")


def test_session_token_round_trip(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "unit-secret")
    config.get_settings.cache_clear()
    token = make_session_token(42)
    assert read_session_token(token) == 42


def test_session_token_rejects_tampering(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "unit-secret")
    config.get_settings.cache_clear()
    token = make_session_token(42)
    payload, sig = token.rsplit(".", 1)
    forged = payload + "." + ("0" * len(sig))
    assert read_session_token(forged) is None
    assert read_session_token(None) is None
    assert read_session_token("garbage") is None


def test_session_token_rejects_wrong_secret(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "secret-a")
    config.get_settings.cache_clear()
    token = make_session_token(7)

    monkeypatch.setenv("SECRET_KEY", "secret-b")
    config.get_settings.cache_clear()
    assert read_session_token(token) is None
