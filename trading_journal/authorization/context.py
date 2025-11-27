"""User context management using contextvars for thread-safe user tracking."""

from contextvars import ContextVar
from typing import Optional

from ..auth.base import AuthUser


# Thread-safe context variable for current user
_current_user: ContextVar[Optional[AuthUser]] = ContextVar('current_user', default=None)


class AuthContext:
    """Manages authentication context for the current execution context."""

    @staticmethod
    def set_current_user(user: Optional[AuthUser]) -> None:
        """
        Set the current authenticated user in the context.

        This should be called after successful authentication.

        Args:
            user: AuthUser instance or None to clear context.
        """
        _current_user.set(user)

    @staticmethod
    def get_current_user() -> Optional[AuthUser]:
        """
        Get the current authenticated user from the context.

        Returns:
            AuthUser if a user is authenticated, None otherwise.
        """
        return _current_user.get()

    @staticmethod
    def clear() -> None:
        """Clear the current user context."""
        _current_user.set(None)

    @staticmethod
    def require_user() -> AuthUser:
        """
        Get the current user, raising an error if not authenticated.

        Returns:
            AuthUser instance.

        Raises:
            RuntimeError: If no user is authenticated.
        """
        user = _current_user.get()
        if user is None:
            raise RuntimeError(
                "No authenticated user in context. "
                "Call AuthContext.set_current_user() after authentication."
            )
        return user

    @staticmethod
    def is_authenticated() -> bool:
        """
        Check if a user is currently authenticated.

        Returns:
            True if a user is authenticated, False otherwise.
        """
        return _current_user.get() is not None

    @staticmethod
    def is_admin() -> bool:
        """
        Check if the current user is an admin.

        Returns:
            True if current user is an admin, False otherwise.
        """
        user = _current_user.get()
        return user.is_admin if user else False

    @staticmethod
    def get_user_id() -> Optional[int]:
        """
        Get the current user's ID.

        Returns:
            User ID if authenticated, None otherwise.
        """
        user = _current_user.get()
        return user.user_id if user else None
