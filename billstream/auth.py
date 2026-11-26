"""Secure tenant API key generation and SHA-256 hashing utilities."""

import hashlib
import secrets


def generate_api_key() -> str:
    """Generate a high-entropy tenant API key."""
    return f"bs_live_{secrets.token_urlsafe(24)}"


def hash_api_key(raw_key: str) -> str:
    """Hash a raw API key with SHA-256 before storing or querying in the database."""
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def key_prefix(raw_key: str) -> str:
    """Return a non-sensitive display prefix for audit logs and tenant listings."""
    return raw_key[:14]
