"""Authentication manager for handling multiple auth providers."""

from typing import Dict, Any, Optional, Type
from sqlalchemy.orm import Session

from .base import AuthenticationProvider, AuthUser
from .api_key import APIKeyAuthenticationProvider
from .exceptions import AuthenticationProviderError


class AuthenticationManager:
    """Manager for handling multiple authentication providers."""

    def __init__(self, session: Session, default_provider: str = "api_key"):
        """
        Initialize authentication manager.

        Args:
            session: SQLAlchemy database session.
            default_provider: Name of the default provider to use.
        """
        self.session = session
        self.default_provider_name = default_provider
        self._providers: Dict[str, AuthenticationProvider] = {}

        # Register built-in providers
        self._register_provider("api_key", APIKeyAuthenticationProvider(session))

    def _register_provider(self, name: str, provider: AuthenticationProvider) -> None:
        """
        Register an authentication provider.

        Args:
            name: Provider name.
            provider: AuthenticationProvider instance.
        """
        self._providers[name] = provider

    def register_provider(self, provider: AuthenticationProvider) -> None:
        """
        Register a custom authentication provider.

        Args:
            provider: AuthenticationProvider instance.
        """
        self._register_provider(provider.provider_name, provider)

    def get_provider(self, name: Optional[str] = None) -> AuthenticationProvider:
        """
        Get an authentication provider by name.

        Args:
            name: Provider name. If None, returns default provider.

        Returns:
            AuthenticationProvider instance.

        Raises:
            AuthenticationProviderError: If provider not found.
        """
        provider_name = name or self.default_provider_name

        if provider_name not in self._providers:
            raise AuthenticationProviderError(
                f"Authentication provider '{provider_name}' not found"
            )

        return self._providers[provider_name]

    def authenticate(
        self,
        credentials: Dict[str, Any],
        provider_name: Optional[str] = None
    ) -> AuthUser:
        """
        Authenticate user using specified provider.

        Args:
            credentials: Authentication credentials.
            provider_name: Name of the provider to use. If None, uses default.

        Returns:
            AuthUser if authentication succeeds.

        Raises:
            AuthenticationError: If authentication fails.
            AuthenticationProviderError: If provider not found.
        """
        provider = self.get_provider(provider_name)
        return provider.authenticate(credentials)

    def validate_token(
        self,
        token: str,
        provider_name: Optional[str] = None
    ) -> Optional[AuthUser]:
        """
        Validate authentication token using specified provider.

        Args:
            token: Authentication token.
            provider_name: Name of the provider to use. If None, uses default.

        Returns:
            AuthUser if token is valid, None otherwise.

        Raises:
            AuthenticationProviderError: If provider not found.
        """
        provider = self.get_provider(provider_name)
        return provider.validate_token(token)

    def list_providers(self) -> list[str]:
        """
        List all registered provider names.

        Returns:
            List of provider names.
        """
        return list(self._providers.keys())
