"""Data filtering utilities for user-based data isolation."""

from typing import Type, Optional
from sqlalchemy.orm import Query

from ..models import Base
from .context import AuthContext


class DataFilter:
    """Utilities for filtering data by user_id."""

    @staticmethod
    def apply_user_filter(query: Query, model: Type[Base]) -> Query:
        """
        Apply user-based filtering to a SQLAlchemy query.

        This method filters the query to only return records belonging to the
        current authenticated user, unless the user is an admin.

        Args:
            query: SQLAlchemy Query object.
            model: SQLAlchemy model class to filter.

        Returns:
            Filtered Query object.

        Raises:
            RuntimeError: If no user is authenticated.

        Example:
            >>> from trading_journal.models import Trade
            >>> from trading_journal.database import db_manager
            >>>
            >>> with db_manager.get_session() as session:
            ...     query = session.query(Trade)
            ...     filtered_query = DataFilter.apply_user_filter(query, Trade)
            ...     trades = filtered_query.all()
        """
        user = AuthContext.require_user()

        # Admin users see all data
        if user.is_admin:
            return query

        # Regular users only see their own data
        if hasattr(model, 'user_id'):
            return query.filter(model.user_id == user.user_id)

        # If model doesn't have user_id, return empty results for safety
        return query.filter(False)

    @staticmethod
    def get_user_id_for_insert() -> int:
        """
        Get the user_id to use for inserting new records.

        Returns:
            User ID of the current authenticated user.

        Raises:
            RuntimeError: If no user is authenticated.

        Example:
            >>> new_trade = Trade(
            ...     user_id=DataFilter.get_user_id_for_insert(),
            ...     symbol="AAPL",
            ...     ...
            ... )
        """
        user = AuthContext.require_user()
        return user.user_id

    @staticmethod
    def can_access_record(record: Base) -> bool:
        """
        Check if the current user can access a specific record.

        Args:
            record: SQLAlchemy model instance.

        Returns:
            True if user can access the record, False otherwise.

        Example:
            >>> trade = session.query(Trade).filter(Trade.trade_id == 123).first()
            >>> if DataFilter.can_access_record(trade):
            ...     print(f"Can access trade {trade.trade_id}")
        """
        user = AuthContext.get_current_user()

        if not user:
            return False

        # Admin can access all records
        if user.is_admin:
            return True

        # Check if record belongs to current user
        if hasattr(record, 'user_id'):
            return record.user_id == user.user_id

        # If record doesn't have user_id, deny access for safety
        return False

    @staticmethod
    def require_record_access(record: Base) -> None:
        """
        Require that the current user can access a specific record.

        Args:
            record: SQLAlchemy model instance.

        Raises:
            PermissionError: If user cannot access the record.

        Example:
            >>> trade = session.query(Trade).filter(Trade.trade_id == 123).first()
            >>> DataFilter.require_record_access(trade)  # Raises if no access
        """
        if not DataFilter.can_access_record(record):
            user = AuthContext.get_current_user()
            user_info = f"user {user.username}" if user else "unauthenticated user"
            raise PermissionError(
                f"Access denied: {user_info} cannot access this record"
            )
