"""Authentication exceptions."""


class AuthenticationError(Exception):
    """Base exception for authentication errors."""
    pass


class InvalidCredentialsError(AuthenticationError):
    """Raised when credentials are invalid."""
    pass


class UserNotFoundError(AuthenticationError):
    """Raised when user is not found."""
    pass


class UserInactiveError(AuthenticationError):
    """Raised when user account is inactive."""
    pass


class InvalidAPIKeyError(AuthenticationError):
    """Raised when API key is invalid."""
    pass


class AuthenticationProviderError(AuthenticationError):
    """Raised when authentication provider encounters an error."""
    pass
