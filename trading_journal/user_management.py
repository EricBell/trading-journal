"""User management business logic for admin operations."""

import re
from datetime import datetime
from typing import List, Dict, Any, Tuple, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from .models import User, CompletedTrade, Trade, Position, SetupPattern, ProcessingLog
from .auth.utils import generate_api_key, hash_api_key
from .authorization.context import AuthContext


class UserManager:
    """Handles user management operations with proper validation and safety checks."""

    # Validation patterns
    USERNAME_PATTERN = re.compile(r'^[a-zA-Z0-9_-]{3,100}$')
    EMAIL_PATTERN = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')

    def __init__(self, session: Session):
        """
        Initialize UserManager with database session.

        Args:
            session: SQLAlchemy database session.
        """
        self.session = session

    def list_users(self, include_inactive: bool = False) -> List[Dict[str, Any]]:
        """
        List all users with their trade counts using efficient database aggregation.

        Uses a single query with LEFT JOIN and GROUP BY to avoid N+1 query problems.

        Args:
            include_inactive: If True, include inactive users. Default False.

        Returns:
            List of dictionaries containing user information and trade counts.
            Each dict has: user_id, username, email, is_active, is_admin,
                          trade_count, created_at, last_login_at
        """
        # Build query with database-level aggregation
        query = self.session.query(
            User.user_id,
            User.username,
            User.email,
            User.is_active,
            User.is_admin,
            User.created_at,
            User.last_login_at,
            func.count(CompletedTrade.completed_trade_id).label('trade_count')
        ).outerjoin(
            CompletedTrade,
            CompletedTrade.user_id == User.user_id
        ).group_by(
            User.user_id,
            User.username,
            User.email,
            User.is_active,
            User.is_admin,
            User.created_at,
            User.last_login_at
        )

        # Filter by active status if requested
        if not include_inactive:
            query = query.filter(User.is_active == True)

        # Execute query and format results
        results = query.all()

        return [
            {
                'user_id': row.user_id,
                'username': row.username,
                'email': row.email,
                'is_active': row.is_active,
                'is_admin': row.is_admin,
                'trade_count': row.trade_count,
                'created_at': row.created_at,
                'last_login_at': row.last_login_at
            }
            for row in results
        ]

    def create_user(
        self,
        username: str,
        email: str,
        is_admin: bool = False
    ) -> Tuple[User, str]:
        """
        Create a new user with automatic API key generation.

        Args:
            username: Unique username (3-100 chars, alphanumeric + underscore/hyphen).
            email: Valid email address.
            is_admin: Whether to grant admin privileges. Default False.

        Returns:
            Tuple of (User object, raw_api_key).
            The raw API key should be shown to the user once and never stored.

        Raises:
            ValueError: If validation fails or username/email already exists.
        """
        # Validate username
        if not self.USERNAME_PATTERN.match(username):
            raise ValueError(
                "Username must be 3-100 characters long and contain only "
                "alphanumeric characters, underscores, or hyphens."
            )

        # Validate email
        if not self.EMAIL_PATTERN.match(email):
            raise ValueError("Invalid email format.")

        # Check for case-insensitive uniqueness
        existing_user = self.session.query(User).filter(
            func.lower(User.username) == username.lower()
        ).first()
        if existing_user:
            raise ValueError(f"Username '{username}' already exists.")

        existing_email = self.session.query(User).filter(
            func.lower(User.email) == email.lower()
        ).first()
        if existing_email:
            raise ValueError(f"Email '{email}' already exists.")

        # Generate API key
        raw_key, hashed_key = generate_api_key()

        # Create user
        user = User(
            username=username,
            email=email,
            is_admin=is_admin,
            is_active=True,
            api_key_hash=hashed_key,
            api_key_created_at=datetime.utcnow(),
            auth_method='api_key'
        )

        self.session.add(user)
        self.session.flush()  # Get user_id without committing

        return user, raw_key

    def deactivate_user(self, user_id: int) -> User:
        """
        Deactivate a user account.

        Args:
            user_id: ID of the user to deactivate.

        Returns:
            Updated User object.

        Raises:
            ValueError: If user not found, trying to deactivate self,
                       or trying to deactivate the last admin.
        """
        # Prevent self-deactivation
        current_user_id = AuthContext.get_user_id()
        if current_user_id == user_id:
            raise ValueError("You cannot deactivate your own account.")

        # Get user
        user = self.get_user_or_raise(user_id)

        # Check if this is the last active admin
        if user.is_admin:
            self._ensure_not_last_admin(user_id)

        # Deactivate
        user.is_active = False
        user.updated_at = datetime.utcnow()
        self.session.flush()

        return user

    def reactivate_user(self, user_id: int) -> User:
        """
        Reactivate a previously deactivated user account.

        Args:
            user_id: ID of the user to reactivate.

        Returns:
            Updated User object.

        Raises:
            ValueError: If user not found.
        """
        user = self.get_user_or_raise(user_id)
        user.is_active = True
        user.updated_at = datetime.utcnow()
        self.session.flush()

        return user

    def make_admin(self, user_id: int) -> User:
        """
        Grant admin privileges to a user.

        Args:
            user_id: ID of the user to make admin.

        Returns:
            Updated User object.

        Raises:
            ValueError: If user not found.
        """
        user = self.get_user_or_raise(user_id)
        user.is_admin = True
        user.updated_at = datetime.utcnow()
        self.session.flush()

        return user

    def revoke_admin(self, user_id: int) -> User:
        """
        Revoke admin privileges from a user.

        Args:
            user_id: ID of the user to revoke admin from.

        Returns:
            Updated User object.

        Raises:
            ValueError: If user not found, trying to revoke own admin,
                       or trying to revoke the last admin.
        """
        # Prevent self-demotion
        current_user_id = AuthContext.get_user_id()
        if current_user_id == user_id:
            raise ValueError("You cannot revoke your own admin privileges.")

        # Get user
        user = self.get_user_or_raise(user_id)

        # Check if already not an admin
        if not user.is_admin:
            raise ValueError(f"User {user_id} is not an admin.")

        # Check if this is the last admin
        self._ensure_not_last_admin(user_id)

        # Revoke admin
        user.is_admin = False
        user.updated_at = datetime.utcnow()
        self.session.flush()

        return user

    def delete_user(self, user_id: int) -> None:
        """
        Delete a user account.

        Prevents deletion if user has trades. Suggests deactivation instead.

        Args:
            user_id: ID of the user to delete.

        Raises:
            ValueError: If user not found, trying to delete self,
                       user has trades, or trying to delete the last admin.
        """
        # Prevent self-deletion
        current_user_id = AuthContext.get_user_id()
        if current_user_id == user_id:
            raise ValueError("You cannot delete your own account.")

        # Get user
        user = self.get_user_or_raise(user_id)

        # Check if user has trades
        trade_count = self.session.query(func.count(CompletedTrade.completed_trade_id)).filter(
            CompletedTrade.user_id == user_id
        ).scalar()

        if trade_count > 0:
            raise ValueError(
                f"Cannot delete user {user_id}: User has {trade_count} completed trade(s). "
                "Consider deactivating the user instead to preserve data integrity."
            )

        # Check if this is the last admin
        if user.is_admin:
            self._ensure_not_last_admin(user_id)

        # Delete user
        self.session.delete(user)
        self.session.flush()

    def purge_user_data(self, user_id: int, dry_run: bool = False) -> Dict[str, int]:
        """
        Purge all data for a specific user, preserving the user account.

        Deletes data in correct order to respect foreign key constraints:
        1. trades (references completed_trades)
        2. completed_trades
        3. positions
        4. setup_patterns
        5. processing_log

        Args:
            user_id: ID of the user whose data should be purged.
            dry_run: If True, only count records without deleting. Default False.

        Returns:
            Dictionary with counts per table and total:
            {
                'trades': count,
                'completed_trades': count,
                'positions': count,
                'setup_patterns': count,
                'processing_log': count,
                'total': sum
            }

        Raises:
            ValueError: If user not found or trying to purge own data.
        """
        # Prevent self-purge
        current_user_id = AuthContext.get_user_id()
        if current_user_id == user_id:
            raise ValueError("You cannot purge your own data.")

        # Verify user exists
        user = self.get_user_or_raise(user_id)

        # Count records in each table
        counts = {
            'trades': self.session.query(func.count(Trade.trade_id)).filter(
                Trade.user_id == user_id
            ).scalar() or 0,
            'completed_trades': self.session.query(func.count(CompletedTrade.completed_trade_id)).filter(
                CompletedTrade.user_id == user_id
            ).scalar() or 0,
            'positions': self.session.query(func.count(Position.position_id)).filter(
                Position.user_id == user_id
            ).scalar() or 0,
            'setup_patterns': self.session.query(func.count(SetupPattern.pattern_id)).filter(
                SetupPattern.user_id == user_id
            ).scalar() or 0,
            'processing_log': self.session.query(func.count(ProcessingLog.log_id)).filter(
                ProcessingLog.user_id == user_id
            ).scalar() or 0
        }

        counts['total'] = sum(counts.values())

        # If dry-run, return counts without deleting
        if dry_run:
            return counts

        # Delete in order (respecting foreign key constraints)
        # 1. Trades first (they reference completed_trades)
        self.session.query(Trade).filter(Trade.user_id == user_id).delete(synchronize_session=False)

        # 2. Completed trades
        self.session.query(CompletedTrade).filter(CompletedTrade.user_id == user_id).delete(synchronize_session=False)

        # 3. Positions
        self.session.query(Position).filter(Position.user_id == user_id).delete(synchronize_session=False)

        # 4. Setup patterns
        self.session.query(SetupPattern).filter(SetupPattern.user_id == user_id).delete(synchronize_session=False)

        # 5. Processing log
        self.session.query(ProcessingLog).filter(ProcessingLog.user_id == user_id).delete(synchronize_session=False)

        # Note: User account is preserved, only data is deleted

        return counts

    def regenerate_api_key(self, user_id: int) -> Tuple[User, str]:
        """
        Regenerate a user's API key, invalidating the old one.

        Args:
            user_id: ID of the user.

        Returns:
            Tuple of (User object, new_raw_api_key).
            The raw API key should be shown to the user once.

        Raises:
            ValueError: If user not found.
        """
        user = self.get_user_or_raise(user_id)

        # Generate new API key
        raw_key, hashed_key = generate_api_key()

        # Update user
        user.api_key_hash = hashed_key
        user.api_key_created_at = datetime.utcnow()
        user.updated_at = datetime.utcnow()
        self.session.flush()

        return user, raw_key

    def get_user_or_raise(self, user_id: int) -> User:
        """
        Get a user by ID or raise an error.

        Args:
            user_id: ID of the user to retrieve.

        Returns:
            User object.

        Raises:
            ValueError: If user not found.
        """
        user = self.session.query(User).filter(User.user_id == user_id).first()
        if not user:
            raise ValueError(f"User with ID {user_id} not found.")
        return user

    def _ensure_not_last_admin(self, user_id: int) -> None:
        """
        Ensure that the operation won't remove the last active admin.

        Args:
            user_id: ID of the user being modified.

        Raises:
            ValueError: If this is the last active admin.
        """
        # Count active admins excluding the target user
        active_admin_count = self.session.query(func.count(User.user_id)).filter(
            User.is_admin == True,
            User.is_active == True,
            User.user_id != user_id
        ).scalar()

        if active_admin_count == 0:
            raise ValueError(
                "Cannot perform this operation: At least one active admin must remain."
            )
