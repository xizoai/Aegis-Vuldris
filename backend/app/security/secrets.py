"""Encrypted secret storage utilities for Aegis Vuldris.

Credentials are encrypted at rest using Fernet, a authenticated symmetric
encryption scheme. The encryption key is derived from the application
``SECRET_KEY`` using PBKDF2-HMAC-SHA256 and is never persisted.
"""

import base64
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from app.core.config import get_settings

_SALT = b"aegisai-target-credentials-v1"
_PBKDF2_ITERATIONS = 200_000


def _derive_fernet_key(secret_key: str) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_SALT,
        iterations=_PBKDF2_ITERATIONS,
    )
    return base64.urlsafe_b64encode(kdf.derive(secret_key.encode("utf-8")))


class SecretStore:
    """Encrypts and decrypts secret values using Fernet."""

    def __init__(self, secret_key: str | None = None) -> None:
        if secret_key is None:
            secret_key = get_settings().secret_key
        if not secret_key.strip():
            raise RuntimeError("SECRET_KEY must be configured to use the secret store.")
        self._fernet = Fernet(_derive_fernet_key(secret_key))

    def encrypt(self, value: str) -> str:
        """Return an authenticated ciphertext for a plaintext secret."""

        return self._fernet.encrypt(value.encode("utf-8")).decode("utf-8")

    def decrypt(self, token: str) -> str:
        """Return the plaintext secret for a ciphertext token.

        Raises a ValueError when the token cannot be decrypted.
        """

        try:
            return self._fernet.decrypt(token.encode("utf-8")).decode("utf-8")
        except InvalidToken as exc:
            raise ValueError("credential could not be decrypted") from exc


@lru_cache
def get_secret_store() -> SecretStore:
    """Return the shared application secret store."""

    return SecretStore()
