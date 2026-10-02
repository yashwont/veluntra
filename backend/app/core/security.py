import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import get_settings
from app.core.errors import AuthenticationError

TokenType = Literal["access", "refresh"]

_ALGORITHM = "HS256"
_password_hasher = PasswordHasher()


# --- Passwords ---------------------------------------------------------------


def hash_password(password: str) -> str:
    """Hash a password with Argon2id. A random salt is generated per hash."""
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Return True if the password matches the hash. Never raises on mismatch."""
    try:
        return _password_hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    """True if the hash uses outdated parameters and should be recomputed on login."""
    return _password_hasher.check_needs_rehash(password_hash)


# --- Tokens ------------------------------------------------------------------


def _create_token(subject: str, token_type: TokenType, lifetime: timedelta) -> str:
    now = datetime.now(timezone.utc)
    claims: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": now,
        "exp": now + lifetime,
        "jti": str(uuid.uuid4()),  # unique id, lets us revoke/rotate refresh tokens
    }
    return jwt.encode(claims, get_settings().secret_key, algorithm=_ALGORITHM)


def create_access_token(subject: str) -> str:
    minutes = get_settings().access_token_expire_minutes
    return _create_token(subject, "access", timedelta(minutes=minutes))


def create_refresh_token(subject: str) -> str:
    days = get_settings().refresh_token_expire_days
    return _create_token(subject, "refresh", timedelta(days=days))


def decode_token(token: str, expected_type: TokenType) -> dict[str, Any]:
    """Validate signature, expiry and token type; return the claims.

    Raises AuthenticationError for any problem, with a deliberately generic
    message so callers cannot learn why a token was rejected.
    """
    try:
        claims: dict[str, Any] = jwt.decode(
            token,
            get_settings().secret_key,
            algorithms=[_ALGORITHM],  # fixed list: never trust the token's own header
            options={"require": ["sub", "exp", "iat", "jti", "type"]},
        )
    except jwt.PyJWTError as exc:
        raise AuthenticationError("Invalid or expired token.") from exc

    if claims["type"] != expected_type:
        # Stops a refresh token being used as an access token, and vice versa
        raise AuthenticationError("Invalid or expired token.")
    return claims
