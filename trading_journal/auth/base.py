"""Base authentication classes and interfaces."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Any, Optional


@dataclass
class AuthUser:
    """Authenticated user data."""

    user_id: int
    username: str
    email: str
    is_admin: bool
    is_active: bool
    auth_method: str

    def __post_init__(self):
        """Validate user data."""
        if not self.is_active:
            raise ValueError(f"User {self.username} is inactive")


class AuthenticationProvider(ABC):
    """Abstract base class for authentication providers."""

    @abstractmethod
    def authenticate(self, credentials: Dict[str, Any]) -> Optional[AuthUser]:
        """
        Authenticate user with provided credentials.

        Args:
            credentials: Dictionary containing authentication credentials.
                        Format depends on the provider implementation.

        Returns:
            AuthUser if authentication succeeds, None otherwise.

        Raises:
            AuthenticationError: If authentication fails with a specific error.
        """
        pass

    @abstractmethod
    def validate_token(self, token: str) -> Optional[AuthUser]:
        """
        Validate an authentication token.

        Args:
            token: Authentication token to validate.

        Returns:
            AuthUser if token is valid, None otherwise.

        Raises:
            AuthenticationError: If validation fails with a specific error.
        """
        pass

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """
        Return the name of this authentication provider.

        Returns:
            Provider name as a string.
        """
        pass
