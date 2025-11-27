"""API key authentication provider."""

from typing import Dict, Any, Optional
from datetime import datetime

from sqlalchemy.orm import Session

from .base import AuthenticationProvider, AuthUser
from .exceptions import (
    InvalidAPIKeyError,
    UserNotFoundError,
    UserInactiveError,
)
from .utils import verify_api_key
from ..models import User


class APIKeyAuthenticationProvider(AuthenticationProvider):
    """Authentication provider using API keys."""

    def __init__(self, session: Session):
        """
        Initialize API key authentication provider.

        Args:
            session: SQLAlchemy database session.
        """
        self.session = session

    def authenticate(self, credentials: Dict[str, Any]) -> Optional[AuthUser]:
        """
        Authenticate user with API key.

        Args:
            credentials: Dictionary with 'api_key' field.

        Returns:
            AuthUser if authentication succeeds.

        Raises:
            InvalidAPIKeyError: If API key is missing or invalid.
            UserNotFoundError: If user is not found.
            UserInactiveError: If user account is inactive.
        """
        api_key = credentials.get('api_key')
        if not api_key:
            raise InvalidAPIKeyError("API key is required")

        # Find user by API key hash
        user = self._find_user_by_api_key(api_key)

        if not user:
            raise InvalidAPIKeyError("Invalid API key")

        if not user.is_active:
            raise UserInactiveError(f"User account '{user.username}' is inactive")

        # Update last login timestamp
        user.last_login_at = datetime.utcnow()
        self.session.commit()

        return self._user_to_auth_user(user)

    def validate_token(self, token: str) -> Optional[AuthUser]:
        """
        Validate an API key token.

        This is an alias for authenticate() with API key in token format.

        Args:
            token: The API key to validate.

        Returns:
            AuthUser if token is valid, None otherwise.
        """
        try:
            return self.authenticate({'api_key': token})
        except (InvalidAPIKeyError, UserInactiveError):
            return None

    def _find_user_by_api_key(self, api_key: str) -> Optional[User]:
        """
        Find user by API key.

        Args:
            api_key: Raw API key to search for.

        Returns:
            User if found, None otherwise.
        """
        # Get all users with API keys
        users = self.session.query(User).filter(
            User.api_key_hash.isnot(None)
        ).all()

        # Verify the API key against each user's hash
        for user in users:
            if verify_api_key(api_key, user.api_key_hash):
                return user

        return None

    def _user_to_auth_user(self, user: User) -> AuthUser:
        """
        Convert User model to AuthUser dataclass.

        Args:
            user: SQLAlchemy User model.

        Returns:
            AuthUser dataclass.
        """
        return AuthUser(
            user_id=user.user_id,
            username=user.username,
            email=user.email,
            is_admin=user.is_admin,
            is_active=user.is_active,
            auth_method=user.auth_method,
        )

    @property
    def provider_name(self) -> str:
        """Return the provider name."""
        return "api_key"
