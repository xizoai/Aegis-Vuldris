"""Password hashing utilities for Aegis Vuldris.

Uses Argon2id (via argon2-cffi) exclusively. Never implement password
hashing or verification manually.
"""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHash, VerifyMismatchError

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    """Hash a plaintext password using Argon2id."""

    return _hasher.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a stored Argon2 hash.

    Returns False for any mismatch or malformed hash rather than raising,
    so callers can treat authentication failure uniformly.
    """

    try:
        return _hasher.verify(hashed_password, password)
    except (VerifyMismatchError, InvalidHash):
        return False
