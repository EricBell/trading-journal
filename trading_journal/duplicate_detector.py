"""Duplicate detection service for cross-user and per-user duplicate checking."""

import logging
from typing import List, Dict, Any, Set
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Trade, User
from .schemas import NdjsonRecord
from .database import db_manager

logger = logging.getLogger(__name__)


class DuplicateDetectionResult:
    """Results from duplicate detection check."""

    def __init__(self):
        self.has_duplicates: bool = False
        self.duplicate_count: int = 0
        self.duplicates_by_user: Dict[int, Dict[str, Any]] = {}  # user_id -> {username, unique_keys}
        self.duplicate_unique_keys: Set[str] = set()

    def add_duplicate(self, user_id: int, username: str, unique_key: str):
        """Add a duplicate record."""
        self.has_duplicates = True
        self.duplicate_count += 1
        self.duplicate_unique_keys.add(unique_key)

        if user_id not in self.duplicates_by_user:
            self.duplicates_by_user[user_id] = {
                'username': username,
                'unique_keys': []
            }
        self.duplicates_by_user[user_id]['unique_keys'].append(unique_key)


class DuplicateDetector:
    """Handles duplicate detection across users and per-user."""

    def __init__(self, session: Session = None):
        self.session = session
        self._should_close_session = False

        if self.session is None:
            self.session = db_manager.get_session().__enter__()
            self._should_close_session = True

    def __del__(self):
        if self._should_close_session and self.session:
            self.session.close()

    def check_duplicates_cross_user(
        self,
        records: List[NdjsonRecord],
        current_user_id: int
    ) -> DuplicateDetectionResult:
        """
        Check if any records already exist in the database across ALL users.

        Args:
            records: List of NdjsonRecord to check
            current_user_id: Current user's ID (for context, not filtering)

        Returns:
            DuplicateDetectionResult with details of any duplicates found
        """
        result = DuplicateDetectionResult()

        if not records:
            return result

        # Extract unique keys from records
        unique_keys = [record.unique_key for record in records]

        # Query database for existing trades with these keys (ANY user)
        stmt = select(
            Trade.unique_key,
            Trade.user_id,
            User.username
        ).join(
            User, Trade.user_id == User.user_id
        ).where(
            Trade.unique_key.in_(unique_keys)
        )

        existing_trades = self.session.execute(stmt).all()

        # Group duplicates by user
        for unique_key, user_id, username in existing_trades:
            result.add_duplicate(user_id, username, unique_key)

        return result

    def check_duplicates_per_user(
        self,
        records: List[NdjsonRecord],
        user_id: int
    ) -> DuplicateDetectionResult:
        """
        Check if any records already exist for THIS USER ONLY.

        Args:
            records: List of NdjsonRecord to check
            user_id: User ID to check against

        Returns:
            DuplicateDetectionResult with details of duplicates for this user
        """
        result = DuplicateDetectionResult()

        if not records:
            return result

        # Extract unique keys
        unique_keys = [record.unique_key for record in records]

        # Query for this user only
        stmt = select(
            Trade.unique_key,
            Trade.user_id,
            User.username
        ).join(
            User, Trade.user_id == User.user_id
        ).where(
            Trade.user_id == user_id,
            Trade.unique_key.in_(unique_keys)
        )

        existing_trades = self.session.execute(stmt).all()

        for unique_key, user_id, username in existing_trades:
            result.add_duplicate(user_id, username, unique_key)

        return result

    def format_duplicate_report(
        self,
        result: DuplicateDetectionResult,
        current_user_id: int
    ) -> str:
        """Format duplicate detection result into human-readable report."""
        if not result.has_duplicates:
            return "No duplicates found."

        lines = [
            f"\n⚠️  WARNING: Found {result.duplicate_count} duplicate record(s):\n"
        ]

        for user_id, info in result.duplicates_by_user.items():
            username = info['username']
            unique_keys = info['unique_keys']

            if user_id == current_user_id:
                lines.append(f"  📂 YOUR DATA ({username}):")
            else:
                lines.append(f"  👤 User: {username} (ID: {user_id}):")

            lines.append(f"     - {len(unique_keys)} duplicate(s)")
            if len(unique_keys) <= 5:
                for key in unique_keys[:5]:
                    # Show shortened version of unique_key
                    short_key = key if len(key) <= 60 else key[:57] + "..."
                    lines.append(f"       • {short_key}")
            else:
                for key in unique_keys[:3]:
                    short_key = key if len(key) <= 60 else key[:57] + "..."
                    lines.append(f"       • {short_key}")
                lines.append(f"       ... and {len(unique_keys) - 3} more")
            lines.append("")  # Empty line between users

        return "\n".join(lines)
