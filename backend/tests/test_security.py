from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.core.config import get_settings
from app.core.errors import AuthenticationError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_password_hash_is_not_plaintext_and_verifies() -> None:
    password_hash = hash_password("correct horse battery staple")

    assert password_hash != "correct horse battery staple"
    assert password_hash.startswith("$argon2id$")
    assert verify_password("correct horse battery staple", password_hash)


def test_wrong_password_is_rejected() -> None:
    password_hash = hash_password("secret-one")

    assert not verify_password("secret-two", password_hash)


def test_same_password_hashes_differently_each_time() -> None:
    assert hash_password("same") != hash_password("same")


def test_garbage_hash_returns_false_instead_of_raising() -> None:
    assert not verify_password("anything", "not-a-real-hash")


def test_access_token_roundtrip() -> None:
    token = create_access_token("user-123")

    claims = decode_token(token, "access")

    assert claims["sub"] == "user-123"
    assert claims["type"] == "access"


def test_refresh_token_cannot_be_used_as_access_token() -> None:
    issued = create_refresh_token("user-123")

    with pytest.raises(AuthenticationError):
        decode_token(issued.token, "access")
    assert decode_token(issued.token, "refresh")["jti"] == issued.jti


def test_tampered_token_is_rejected() -> None:
    token = create_access_token("user-123")
    tampered = token[:-4] + ("AAAA" if not token.endswith("AAAA") else "BBBB")

    with pytest.raises(AuthenticationError):
        decode_token(tampered, "access")


def test_expired_token_is_rejected() -> None:
    now = datetime.now(timezone.utc)
    expired = jwt.encode(
        {
            "sub": "user-123",
            "type": "access",
            "iat": now - timedelta(hours=2),
            "exp": now - timedelta(hours=1),
            "jti": "x",
        },
        get_settings().secret_key,
        algorithm="HS256",
    )

    with pytest.raises(AuthenticationError):
        decode_token(expired, "access")


def test_token_signed_with_other_key_is_rejected() -> None:
    now = datetime.now(timezone.utc)
    forged = jwt.encode(
        {
            "sub": "user-123",
            "type": "access",
            "iat": now,
            "exp": now + timedelta(minutes=5),
            "jti": "x",
        },
        "a-completely-different-secret-key-0123456789",
        algorithm="HS256",
    )

    with pytest.raises(AuthenticationError):
        decode_token(forged, "access")
