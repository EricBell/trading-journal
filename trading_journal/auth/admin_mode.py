"""Admin mode for development and testing convenience."""

import os
import logging
from typing import Optional

from .base import AuthUser

logger = logging.getLogger(__name__)


class AdminModeAuth:
    """
    Admin mode authentication for development convenience.

    WARNING: This should NEVER be enabled in production environments.
    Admin mode bypasses all authentication and grants full admin access.
    """

    @staticmethod
    def is_enabled() -> bool:
        """
        Check if admin mode is enabled via environment variable.

        Returns:
            True if admin mode is enabled, False otherwise.
        """
        return os.getenv("ADMIN_MODE_ENABLED", "false").lower() == "true"

    @staticmethod
    def get_admin_user() -> Optional[AuthUser]:
        """
        Get an admin user for admin mode.

        This method creates a synthetic admin user with full privileges.
        It should only be used when admin mode is enabled.

        Returns:
            AuthUser with admin privileges if admin mode is enabled.
            None if admin mode is disabled.

        Raises:
            RuntimeError: If admin mode is enabled but configuration is invalid.
        """
        if not AdminModeAuth.is_enabled():
            return None

        # Log loud warning
        logger.warning("=" * 80)
        logger.warning("ADMIN MODE IS ENABLED - AUTHENTICATION BYPASSED")
        logger.warning("This should NEVER be used in production!")
        logger.warning("=" * 80)

        # Get admin username from environment
        admin_username = os.getenv("ADMIN_USERNAME", "admin")
        admin_user_id_str = os.getenv("ADMIN_USER_ID", "1")

        try:
            admin_user_id = int(admin_user_id_str)
        except ValueError:
            raise RuntimeError(
                f"Invalid ADMIN_USER_ID: '{admin_user_id_str}'. Must be an integer."
            )

        # Create synthetic admin user
        return AuthUser(
            user_id=admin_user_id,
            username=admin_username,
            email=f"{admin_username}@admin.local",
            is_admin=True,
            is_active=True,
            auth_method="admin_mode",
        )

    @staticmethod
    def warn_if_enabled() -> None:
        """
        Print a warning if admin mode is enabled.

        This should be called at application startup to alert users.
        """
        if AdminModeAuth.is_enabled():
            print("=" * 80)
            print("WARNING: ADMIN MODE IS ENABLED")
            print("Authentication is bypassed. Do not use in production!")
            print("=" * 80)
