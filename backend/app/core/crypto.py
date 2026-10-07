"""Encryption for secrets stored in the database (third-party OAuth tokens).

A database leak must not hand out working access to people's Gmail and Drive, so
tokens are stored encrypted (Fernet: AES-128-CBC with HMAC) and decrypted only at
the moment they are used.
"""

import base64
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.config import get_settings


class DecryptionError(Exception):
    """The stored value can't be decrypted (wrong or changed key, or corrupted)."""


@lru_cache
def _fernet(configured_key: str, secret_key: str) -> Fernet:
    if configured_key:
        return Fernet(configured_key.encode())
    # No dedicated key: derive one from SECRET_KEY, separated from its other uses
    derived = HKDF(
        algorithm=hashes.SHA256(), length=32, salt=None, info=b"veluntra-integration-tokens"
    ).derive(secret_key.encode())
    return Fernet(base64.urlsafe_b64encode(derived))


def _current() -> Fernet:
    settings = get_settings()
    return _fernet(settings.integration_encryption_key, settings.secret_key)


def encrypt(plaintext: str) -> str:
    return _current().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    try:
        return _current().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise DecryptionError("stored secret cannot be decrypted") from exc
