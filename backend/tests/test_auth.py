"""
Unit tests for the auth service (token creation and verification).
"""
from datetime import timezone, datetime

import pytest
from jose import jwt

from app.config import settings
from app.services.auth_service import (
    create_access_token,
    create_refresh_token,
    create_link_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_hash_and_verify_password():
    password = "super_secret_123"
    hashed = hash_password(password)
    assert hashed != password
    assert verify_password(password, hashed)


def test_wrong_password_fails():
    hashed = hash_password("correct_password")
    assert not verify_password("wrong_password", hashed)


def test_access_token_has_correct_type():
    token = create_access_token("user-123")
    payload = decode_token(token)
    assert payload is not None
    assert payload["type"] == "access"
    assert payload["sub"] == "user-123"


def test_refresh_token_has_correct_type():
    token = create_refresh_token("user-456")
    payload = decode_token(token)
    assert payload is not None
    assert payload["type"] == "refresh"
    assert payload["sub"] == "user-456"


def test_link_token_has_correct_type():
    token = create_link_token("patient:some-uuid")
    payload = decode_token(token)
    assert payload is not None
    assert payload["type"] == "telegram_link"
    assert payload["sub"] == "patient:some-uuid"


def test_invalid_token_returns_none():
    result = decode_token("this.is.not.a.valid.token")
    assert result is None


def test_tampered_token_returns_none():
    token = create_access_token("user-789")
    tampered = token + "tampered"
    assert decode_token(tampered) is None


def test_access_token_expires_in_future():
    token = create_access_token("user-111")
    payload = decode_token(token)
    exp = payload["exp"]
    now = datetime.now(timezone.utc).timestamp()
    assert exp > now


def test_short_link_code():
    from app.services.auth_service import generate_short_link_code, verify_short_link_code
    subject = "patient:some-uuid"
    code = generate_short_link_code(subject)
    
    # 6 digit code format
    assert len(code) == 6
    assert code.isdigit()
    
    # Success verify
    verified_subject = verify_short_link_code(code)
    assert verified_subject == subject
    
    # Single-use (verify second time should return None)
    assert verify_short_link_code(code) is None


def test_short_link_code_invalid():
    from app.services.auth_service import verify_short_link_code
    assert verify_short_link_code("999999") is None

