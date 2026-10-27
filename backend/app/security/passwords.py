"""PBKDF2 password hashing for the additive account login (stdlib only).

PBKDF2-HMAC-SHA256 with a per-user random salt and an iteration count
carried inside the stored string, so the cost can be raised later without
invalidating existing hashes. Verification is constant-time.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

ALGORITHM = "pbkdf2_sha256"
ITERATIONS = 260_000
SALT_BYTES = 16


def hash_password(password: str) -> str:
    """Return `pbkdf2_sha256$<iterations>$<salt_hex>$<digest_hex>`."""
    salt = secrets.token_bytes(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
    return f"{ALGORITHM}${ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time check; malformed/expired encodings fail closed."""
    try:
        algorithm, iterations_s, salt_hex, digest_hex = stored.split("$")
        if algorithm != ALGORITHM:
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            int(iterations_s),
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, AttributeError):
        return False


__all__ = ["hash_password", "verify_password"]
