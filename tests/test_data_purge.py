"""Test suite for user data purge functionality."""

import pytest
from datetime import datetime

from trading_journal.user_management import UserManager
from trading_journal.models import (
    User, Trade, CompletedTrade, Position, SetupPattern, ProcessingLog
)
from trading_journal.authorization.context import AuthContext
from trading_journal.auth.base import AuthUser
from trading_journal.auth.utils import hash_api_key


@pytest.fixture
def admin_user(db_session):
    """Create an admin user and set in auth context."""
    admin = User(
        username='admin',
        email='admin@test.com',
        is_admin=True,
        is_active=True,
        api_key_hash=hash_api_key('admin_key'),
        api_key_created_at=datetime.utcnow()
    )
    db_session.add(admin)
    db_session.commit()
    db_session.refresh(admin)

    # Set auth context
    auth_user = AuthUser(
        user_id=admin.user_id,
        username=admin.username,
        is_admin=True,
        is_active=True
    )
    AuthContext.set_current_user(auth_user)

    yield admin

    # Cleanup
    AuthContext.clear()


@pytest.fixture
def target_user(db_session):
    """Create a target user whose data will be purged."""
    user = User(
        username='target_user',
        email='target@test.com',
        is_admin=False,
        is_active=True,
        api_key_hash=hash_api_key('target_key'),
        api_key_created_at=datetime.utcnow()
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def other_user(db_session):
    """Create another user whose data should not be affected."""
    user = User(
        username='other_user',
        email='other@test.com',
        is_admin=False,
        is_active=True,
        api_key_hash=hash_api_key('other_key'),
        api_key_created_at=datetime.utcnow()
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def create_sample_data(db_session, user_id):
    """Create sample data for a user."""
    # Create trades
    trades = [
        Trade(
            unique_key=f'file.csv::{i}::2025-01-15T10:00::AAPL::BUY::100',
            user_id=user_id,
            exec_timestamp=datetime(2025, 1, 15, 10, 0),
            event_type='fill',
            symbol='AAPL',
            instrument_type='EQUITY',
            side='BUY',
            qty=100,
            pos_effect='TO OPEN',
            price=150.00,
            net_price=150.00,
            order_type='LIMIT',
            source_file_path='file.csv',
            source_file_index=i,
            raw_data={'test': 'data'},
            processing_timestamp=datetime.utcnow()
        )
        for i in range(5)
    ]
    db_session.add_all(trades)

    # Create completed trades
    completed_trades = [
        CompletedTrade(
            user_id=user_id,
            symbol='AAPL',
            entry_timestamp=datetime(2025, 1, 15, 10, 0),
            exit_timestamp=datetime(2025, 1, 15, 11, 0),
            entry_price=150.00,
            exit_price=155.00,
            qty=100,
            pnl=500.00,
            pnl_percent=3.33,
            hold_duration_seconds=3600,
            instrument_type='EQUITY'
        )
        for _ in range(3)
    ]
    db_session.add_all(completed_trades)

    # Create positions
    positions = [
        Position(
            user_id=user_id,
            symbol='AAPL',
            qty=100,
            avg_cost=150.00,
            total_cost=15000.00,
            instrument_type='EQUITY',
            is_closed=False
        ),
        Position(
            user_id=user_id,
            symbol='MSFT',
            qty=50,
            avg_cost=300.00,
            total_cost=15000.00,
            instrument_type='EQUITY',
            is_closed=False
        )
    ]
    db_session.add_all(positions)

    # Create setup patterns
    patterns = [
        SetupPattern(
            user_id=user_id,
            pattern_name=f'Pattern_{i}',
            created_at=datetime.utcnow()
        )
        for i in range(2)
    ]
    db_session.add_all(patterns)

    # Create processing logs
    logs = [
        ProcessingLog(
            user_id=user_id,
            file_path=f'file_{i}.csv',
            processing_started_at=datetime.utcnow(),
            processing_completed_at=datetime.utcnow(),
            records_processed=10,
            records_failed=0,
            status='completed'
        )
        for i in range(4)
    ]
    db_session.add_all(logs)

    db_session.commit()

    return {
        'trades': len(trades),
        'completed_trades': len(completed_trades),
        'positions': len(positions),
        'setup_patterns': len(patterns),
        'processing_log': len(logs),
        'total': len(trades) + len(completed_trades) + len(positions) + len(patterns) + len(logs)
    }


class TestDataPurgeDryRun:
    """Test dry-run mode for data purge."""

    def test_dry_run_returns_counts(self, db_session, admin_user, target_user):
        """Test dry-run mode returns correct counts without deleting."""
        # Create sample data
        expected_counts = create_sample_data(db_session, target_user.user_id)

        manager = UserManager(db_session)
        counts = manager.purge_user_data(target_user.user_id, dry_run=True)

        # Verify counts match
        assert counts['trades'] == expected_counts['trades']
        assert counts['completed_trades'] == expected_counts['completed_trades']
        assert counts['positions'] == expected_counts['positions']
        assert counts['setup_patterns'] == expected_counts['setup_patterns']
        assert counts['processing_log'] == expected_counts['processing_log']
        assert counts['total'] == expected_counts['total']

        # Verify no data was deleted
        assert db_session.query(Trade).filter(Trade.user_id == target_user.user_id).count() == expected_counts['trades']
        assert db_session.query(CompletedTrade).filter(CompletedTrade.user_id == target_user.user_id).count() == expected_counts['completed_trades']
        assert db_session.query(Position).filter(Position.user_id == target_user.user_id).count() == expected_counts['positions']
        assert db_session.query(SetupPattern).filter(SetupPattern.user_id == target_user.user_id).count() == expected_counts['setup_patterns']
        assert db_session.query(ProcessingLog).filter(ProcessingLog.user_id == target_user.user_id).count() == expected_counts['processing_log']

    def test_dry_run_empty_user(self, db_session, admin_user, target_user):
        """Test dry-run mode with user that has no data."""
        manager = UserManager(db_session)
        counts = manager.purge_user_data(target_user.user_id, dry_run=True)

        assert counts['trades'] == 0
        assert counts['completed_trades'] == 0
        assert counts['positions'] == 0
        assert counts['setup_patterns'] == 0
        assert counts['processing_log'] == 0
        assert counts['total'] == 0


class TestDataPurgeActual:
    """Test actual data deletion."""

    def test_purge_deletes_all_user_data(self, db_session, admin_user, target_user):
        """Test that purge actually deletes all user data."""
        # Create sample data
        expected_counts = create_sample_data(db_session, target_user.user_id)

        manager = UserManager(db_session)
        counts = manager.purge_user_data(target_user.user_id, dry_run=False)

        # Verify returned counts match
        assert counts == expected_counts

        # Verify all data is deleted
        assert db_session.query(Trade).filter(Trade.user_id == target_user.user_id).count() == 0
        assert db_session.query(CompletedTrade).filter(CompletedTrade.user_id == target_user.user_id).count() == 0
        assert db_session.query(Position).filter(Position.user_id == target_user.user_id).count() == 0
        assert db_session.query(SetupPattern).filter(SetupPattern.user_id == target_user.user_id).count() == 0
        assert db_session.query(ProcessingLog).filter(ProcessingLog.user_id == target_user.user_id).count() == 0

    def test_purge_preserves_user_account(self, db_session, admin_user, target_user):
        """Test that purge preserves the user account itself."""
        # Create sample data
        create_sample_data(db_session, target_user.user_id)

        manager = UserManager(db_session)
        manager.purge_user_data(target_user.user_id, dry_run=False)

        # Verify user account still exists
        user = db_session.query(User).filter(User.user_id == target_user.user_id).first()
        assert user is not None
        assert user.username == 'target_user'
        assert user.email == 'target@test.com'

    def test_purge_does_not_affect_other_users(self, db_session, admin_user, target_user, other_user):
        """Test that purging one user's data doesn't affect other users."""
        # Create data for both users
        target_counts = create_sample_data(db_session, target_user.user_id)
        other_counts = create_sample_data(db_session, other_user.user_id)

        manager = UserManager(db_session)
        manager.purge_user_data(target_user.user_id, dry_run=False)

        # Verify target user's data is deleted
        assert db_session.query(Trade).filter(Trade.user_id == target_user.user_id).count() == 0

        # Verify other user's data is intact
        assert db_session.query(Trade).filter(Trade.user_id == other_user.user_id).count() == other_counts['trades']
        assert db_session.query(CompletedTrade).filter(CompletedTrade.user_id == other_user.user_id).count() == other_counts['completed_trades']
        assert db_session.query(Position).filter(Position.user_id == other_user.user_id).count() == other_counts['positions']
        assert db_session.query(SetupPattern).filter(SetupPattern.user_id == other_user.user_id).count() == other_counts['setup_patterns']
        assert db_session.query(ProcessingLog).filter(ProcessingLog.user_id == other_user.user_id).count() == other_counts['processing_log']

    def test_purge_empty_user_returns_zero_counts(self, db_session, admin_user, target_user):
        """Test purging user with no data returns zero counts."""
        manager = UserManager(db_session)
        counts = manager.purge_user_data(target_user.user_id, dry_run=False)

        assert counts['total'] == 0
        assert counts['trades'] == 0
        assert counts['completed_trades'] == 0
        assert counts['positions'] == 0
        assert counts['setup_patterns'] == 0
        assert counts['processing_log'] == 0


class TestDataPurgeSafetyChecks:
    """Test safety checks for data purge."""

    def test_cannot_purge_own_data(self, db_session, admin_user):
        """Test that user cannot purge their own data."""
        create_sample_data(db_session, admin_user.user_id)

        manager = UserManager(db_session)

        with pytest.raises(ValueError, match="You cannot purge your own data"):
            manager.purge_user_data(admin_user.user_id, dry_run=False)

        # Verify data still exists
        assert db_session.query(Trade).filter(Trade.user_id == admin_user.user_id).count() > 0

    def test_cannot_purge_own_data_dry_run(self, db_session, admin_user):
        """Test that user cannot even dry-run purge their own data."""
        manager = UserManager(db_session)

        with pytest.raises(ValueError, match="You cannot purge your own data"):
            manager.purge_user_data(admin_user.user_id, dry_run=True)

    def test_purge_nonexistent_user_raises_error(self, db_session, admin_user):
        """Test that purging non-existent user raises error."""
        manager = UserManager(db_session)

        with pytest.raises(ValueError, match="User with ID 99999 not found"):
            manager.purge_user_data(99999, dry_run=False)

    def test_purge_requires_valid_user(self, db_session, admin_user, target_user):
        """Test that purge verifies user exists before proceeding."""
        manager = UserManager(db_session)

        # Delete user first
        db_session.delete(target_user)
        db_session.commit()

        # Try to purge deleted user
        with pytest.raises(ValueError, match="User with ID .* not found"):
            manager.purge_user_data(target_user.user_id, dry_run=False)


class TestDataPurgeEdgeCases:
    """Test edge cases for data purge."""

    def test_purge_with_only_trades(self, db_session, admin_user, target_user):
        """Test purging user with only trades (no other data)."""
        # Create only trades
        trades = [
            Trade(
                unique_key=f'file.csv::{i}::2025-01-15T10:00::AAPL::BUY::100',
                user_id=target_user.user_id,
                exec_timestamp=datetime(2025, 1, 15, 10, 0),
                event_type='fill',
                symbol='AAPL',
                instrument_type='EQUITY',
                side='BUY',
                qty=100,
                pos_effect='TO OPEN',
                price=150.00,
                net_price=150.00,
                order_type='LIMIT',
                source_file_path='file.csv',
                source_file_index=i,
                raw_data={'test': 'data'},
                processing_timestamp=datetime.utcnow()
            )
            for i in range(3)
        ]
        db_session.add_all(trades)
        db_session.commit()

        manager = UserManager(db_session)
        counts = manager.purge_user_data(target_user.user_id, dry_run=False)

        assert counts['trades'] == 3
        assert counts['completed_trades'] == 0
        assert counts['positions'] == 0
        assert counts['setup_patterns'] == 0
        assert counts['processing_log'] == 0
        assert counts['total'] == 3

        # Verify deletion
        assert db_session.query(Trade).filter(Trade.user_id == target_user.user_id).count() == 0

    def test_purge_with_only_positions(self, db_session, admin_user, target_user):
        """Test purging user with only positions (no other data)."""
        # Create only positions
        position = Position(
            user_id=target_user.user_id,
            symbol='AAPL',
            qty=100,
            avg_cost=150.00,
            total_cost=15000.00,
            instrument_type='EQUITY',
            is_closed=False
        )
        db_session.add(position)
        db_session.commit()

        manager = UserManager(db_session)
        counts = manager.purge_user_data(target_user.user_id, dry_run=False)

        assert counts['trades'] == 0
        assert counts['completed_trades'] == 0
        assert counts['positions'] == 1
        assert counts['setup_patterns'] == 0
        assert counts['processing_log'] == 0
        assert counts['total'] == 1

        # Verify deletion
        assert db_session.query(Position).filter(Position.user_id == target_user.user_id).count() == 0

    def test_purge_large_dataset(self, db_session, admin_user, target_user):
        """Test purging user with large amount of data."""
        # Create many trades
        trades = [
            Trade(
                unique_key=f'file.csv::{i}::2025-01-15T10:00::AAPL::BUY::100',
                user_id=target_user.user_id,
                exec_timestamp=datetime(2025, 1, 15, 10, 0),
                event_type='fill',
                symbol='AAPL',
                instrument_type='EQUITY',
                side='BUY',
                qty=100,
                pos_effect='TO OPEN',
                price=150.00,
                net_price=150.00,
                order_type='LIMIT',
                source_file_path='file.csv',
                source_file_index=i,
                raw_data={'test': 'data'},
                processing_timestamp=datetime.utcnow()
            )
            for i in range(100)
        ]
        db_session.add_all(trades)
        db_session.commit()

        manager = UserManager(db_session)
        counts = manager.purge_user_data(target_user.user_id, dry_run=False)

        assert counts['trades'] == 100
        assert counts['total'] == 100

        # Verify all deleted
        assert db_session.query(Trade).filter(Trade.user_id == target_user.user_id).count() == 0

    def test_purge_twice_idempotent(self, db_session, admin_user, target_user):
        """Test that purging twice is safe (returns zero counts second time)."""
        # Create data
        create_sample_data(db_session, target_user.user_id)

        manager = UserManager(db_session)

        # First purge
        counts1 = manager.purge_user_data(target_user.user_id, dry_run=False)
        assert counts1['total'] > 0

        # Second purge
        counts2 = manager.purge_user_data(target_user.user_id, dry_run=False)
        assert counts2['total'] == 0
        assert counts2['trades'] == 0
        assert counts2['completed_trades'] == 0
        assert counts2['positions'] == 0
        assert counts2['setup_patterns'] == 0
        assert counts2['processing_log'] == 0


class TestDataPurgeIntegration:
    """Integration tests for data purge workflow."""

    def test_realistic_purge_workflow(self, db_session, admin_user, target_user):
        """Test realistic workflow: check counts, confirm, then purge."""
        # Create sample data
        expected_counts = create_sample_data(db_session, target_user.user_id)

        manager = UserManager(db_session)

        # Step 1: Dry-run to preview
        preview_counts = manager.purge_user_data(target_user.user_id, dry_run=True)
        assert preview_counts == expected_counts

        # Step 2: Verify data still exists
        assert db_session.query(Trade).filter(Trade.user_id == target_user.user_id).count() > 0

        # Step 3: Actual purge
        actual_counts = manager.purge_user_data(target_user.user_id, dry_run=False)
        assert actual_counts == expected_counts

        # Step 4: Verify deletion
        assert db_session.query(Trade).filter(Trade.user_id == target_user.user_id).count() == 0
        assert db_session.query(CompletedTrade).filter(CompletedTrade.user_id == target_user.user_id).count() == 0
        assert db_session.query(Position).filter(Position.user_id == target_user.user_id).count() == 0

        # Step 5: Verify user still exists
        user = db_session.query(User).filter(User.user_id == target_user.user_id).first()
        assert user is not None

    def test_multi_user_selective_purge(self, db_session, admin_user, target_user, other_user):
        """Test purging multiple users selectively."""
        # Create different amounts of data for each user
        user1_data = create_sample_data(db_session, target_user.user_id)
        user2_data = create_sample_data(db_session, other_user.user_id)

        manager = UserManager(db_session)

        # Purge only target_user
        purged_counts = manager.purge_user_data(target_user.user_id, dry_run=False)
        assert purged_counts == user1_data

        # Verify target_user data is gone
        assert db_session.query(Trade).filter(Trade.user_id == target_user.user_id).count() == 0

        # Verify other_user data is intact
        assert db_session.query(Trade).filter(Trade.user_id == other_user.user_id).count() == user2_data['trades']

        # Now purge other_user
        purged_counts2 = manager.purge_user_data(other_user.user_id, dry_run=False)
        assert purged_counts2 == user2_data

        # Verify other_user data is now gone
        assert db_session.query(Trade).filter(Trade.user_id == other_user.user_id).count() == 0
