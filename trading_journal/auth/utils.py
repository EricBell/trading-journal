"""Authentication utility functions."""

import hashlib
import secrets
from typing import Tuple


def hash_api_key(api_key: str) -> str:
    """
    Hash an API key using SHA256.

    Args:
        api_key: The raw API key to hash.

    Returns:
        Hexadecimal string of the SHA256 hash.
    """
    return hashlib.sha256(api_key.encode('utf-8')).hexdigest()


def generate_api_key() -> Tuple[str, str]:
    """
    Generate a new API key and its hash.

    Returns:
        Tuple of (raw_api_key, hashed_api_key).
        The raw key should be shown to the user once and never stored.
        The hash should be stored in the database.
    """
    # Generate a 32-byte (256-bit) random API key
    raw_key = secrets.token_urlsafe(32)
    hashed_key = hash_api_key(raw_key)
    return raw_key, hashed_key


def verify_api_key(raw_key: str, hashed_key: str) -> bool:
    """
    Verify that a raw API key matches its hash.

    Args:
        raw_key: The raw API key provided by the user.
        hashed_key: The hashed API key stored in the database.

    Returns:
        True if the keys match, False otherwise.
    """
    return hash_api_key(raw_key) == hashed_key
