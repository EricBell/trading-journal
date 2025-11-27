"""Authentication and authorization module."""

from .base import AuthUser, AuthenticationProvider
from .api_key import APIKeyAuthenticationProvider
from .manager import AuthenticationManager
from .admin_mode import AdminModeAuth
from .utils import generate_api_key, hash_api_key, verify_api_key
from .exceptions import (
    AuthenticationError,
    InvalidCredentialsError,
    UserNotFoundError,
    UserInactiveError,
    InvalidAPIKeyError,
    AuthenticationProviderError,
)

__all__ = [
    # Base classes
    "AuthUser",
    "AuthenticationProvider",
    # Providers
    "APIKeyAuthenticationProvider",
    # Manager
    "AuthenticationManager",
    # Admin Mode
    "AdminModeAuth",
    # Utilities
    "generate_api_key",
    "hash_api_key",
    "verify_api_key",
    # Exceptions
    "AuthenticationError",
    "InvalidCredentialsError",
    "UserNotFoundError",
    "UserInactiveError",
    "InvalidAPIKeyError",
    "AuthenticationProviderError",
]
