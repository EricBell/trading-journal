"""CLI authentication helpers."""

import os
import sys
import logging
from typing import Optional

import click

from .auth import AdminModeAuth, AuthenticationManager, AuthUser
from .authorization import AuthContext
from .database import db_manager

logger = logging.getLogger(__name__)


def authenticate_cli() -> AuthUser:
    """
    Authenticate the user for CLI operations.

    Priority:
    1. Admin mode (if enabled via ADMIN_MODE_ENABLED=true)
    2. API key from TRADING_JOURNAL_API_KEY environment variable
    3. Prompt user for API key

    Returns:
        AuthUser instance for the authenticated user.

    Raises:
        click.Abort: If authentication fails.
    """
    # Check for admin mode
    if AdminModeAuth.is_enabled():
        admin_user = AdminModeAuth.get_admin_user()
        if admin_user:
            AuthContext.set_current_user(admin_user)
            logger.info(f"Admin mode enabled: logged in as {admin_user.username}")
            return admin_user

    # Try API key from environment variable
    api_key = os.getenv("TRADING_JOURNAL_API_KEY")

    # If no API key in environment, prompt user
    if not api_key:
        api_key = click.prompt(
            "Enter your API key",
            hide_input=True,
            err=True  # Print prompt to stderr to keep stdout clean
        )

    # Authenticate with API key
    try:
        with db_manager.get_session() as session:
            auth_manager = AuthenticationManager(session)
            user = auth_manager.authenticate({'api_key': api_key})

            # Set user in context
            AuthContext.set_current_user(user)
            logger.info(f"Authenticated as user: {user.username}")

            return user

    except Exception as e:
        click.echo(f"❌ Authentication failed: {e}", err=True)
        raise click.Abort()


def require_authentication(func):
    """
    Decorator to require authentication for a CLI command.

    Usage:
        @cli.command()
        @require_authentication
        def my_command():
            # Command implementation
            pass
    """
    def wrapper(*args, **kwargs):
        try:
            # Authenticate user and set context
            authenticate_cli()

            # Call the actual command
            return func(*args, **kwargs)

        finally:
            # Clean up auth context
            AuthContext.clear()

    wrapper.__name__ = func.__name__
    wrapper.__doc__ = func.__doc__
    return wrapper


def get_current_user_info() -> str:
    """
    Get a string describing the current authenticated user.

    Returns:
        String describing the current user, or "Not authenticated".
    """
    user = AuthContext.get_current_user()
    if not user:
        return "Not authenticated"

    admin_badge = " [ADMIN]" if user.is_admin else ""
    return f"{user.username}{admin_badge} ({user.email})"


def warn_admin_mode_at_startup():
    """
    Print a warning if admin mode is enabled.

    This should be called at CLI startup (in main()).
    """
    AdminModeAuth.warn_if_enabled()
