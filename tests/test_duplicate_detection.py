"""Test suite for duplicate detection functionality."""

import json
import pytest
from datetime import datetime

from trading_journal.duplicate_detector import DuplicateDetector, DuplicateDetectionResult
from trading_journal.models import User, Trade
from trading_journal.schemas import NdjsonRecord
from trading_journal.auth.utils import hash_api_key


@pytest.fixture
def user1(db_session):
    """Create first test user."""
    user = User(
        username='user1',
        email='user1@test.com',
        is_admin=False,
        is_active=True,
        api_key_hash=hash_api_key('key1'),
        api_key_created_at=datetime.utcnow()
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def user2(db_session):
    """Create second test user."""
    user = User(
        username='user2',
        email='user2@test.com',
        is_admin=False,
        is_active=True,
        api_key_hash=hash_api_key('key2'),
        api_key_created_at=datetime.utcnow()
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def user3(db_session):
    """Create third test user."""
    user = User(
        username='user3',
        email='user3@test.com',
        is_admin=False,
        is_active=True,
        api_key_hash=hash_api_key('key3'),
        api_key_created_at=datetime.utcnow()
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def sample_trade_data():
    """Sample trade data for creating test trades."""
    return {
        'unique_key': 'test-file.csv::1::2025-01-15T10:00::AAPL::BUY::100',
        'exec_timestamp': datetime(2025, 1, 15, 10, 0),
        'event_type': 'fill',
        'symbol': 'AAPL',
        'instrument_type': 'EQUITY',
        'side': 'BUY',
        'qty': 100,
        'pos_effect': 'TO OPEN',
        'price': 150.00,
        'net_price': 150.00,
        'order_type': 'LIMIT',
        'source_file_path': 'test-file.csv',
        'source_file_index': 1,
        'raw_data': json.dumps({'test': 'data'}),
        'processing_timestamp': datetime.utcnow()
    }


@pytest.fixture
def sample_ndjson_record():
    """Sample NdjsonRecord for testing."""
    return NdjsonRecord(
        section='test-section',
        row_index=1,
        raw=json.dumps({'test': 'data'}),
        exec_time=datetime(2025, 1, 15, 10, 0),
        event_type='fill',
        symbol='AAPL',
        side='BUY',
        qty=100,
        pos_effect='TO OPEN',
        price=150.00,
        net_price=150.00,
        order_type='LIMIT',
        source_file='test-file.csv',
        source_file_index=1
    )


class TestDuplicateDetectionResult:
    """Test DuplicateDetectionResult class."""

    def test_initial_state(self):
        """Test initial state of result object."""
        result = DuplicateDetectionResult()

        assert result.has_duplicates is False
        assert result.duplicate_count == 0
        assert len(result.duplicates_by_user) == 0
        assert len(result.duplicate_unique_keys) == 0

    def test_add_duplicate_single(self):
        """Test adding a single duplicate."""
        result = DuplicateDetectionResult()
        result.add_duplicate(1, 'user1', 'unique_key_1')

        assert result.has_duplicates is True
        assert result.duplicate_count == 1
        assert 'unique_key_1' in result.duplicate_unique_keys
        assert 1 in result.duplicates_by_user
        assert result.duplicates_by_user[1]['username'] == 'user1'
        assert result.duplicates_by_user[1]['unique_keys'] == ['unique_key_1']

    def test_add_multiple_duplicates_same_user(self):
        """Test adding multiple duplicates for same user."""
        result = DuplicateDetectionResult()
        result.add_duplicate(1, 'user1', 'unique_key_1')
        result.add_duplicate(1, 'user1', 'unique_key_2')

        assert result.has_duplicates is True
        assert result.duplicate_count == 2
        assert len(result.duplicate_unique_keys) == 2
        assert len(result.duplicates_by_user) == 1
        assert len(result.duplicates_by_user[1]['unique_keys']) == 2

    def test_add_duplicates_multiple_users(self):
        """Test adding duplicates across multiple users."""
        result = DuplicateDetectionResult()
        result.add_duplicate(1, 'user1', 'unique_key_1')
        result.add_duplicate(2, 'user2', 'unique_key_2')
        result.add_duplicate(3, 'user3', 'unique_key_3')

        assert result.duplicate_count == 3
        assert len(result.duplicates_by_user) == 3
        assert result.duplicates_by_user[1]['username'] == 'user1'
        assert result.duplicates_by_user[2]['username'] == 'user2'
        assert result.duplicates_by_user[3]['username'] == 'user3'


class TestDuplicateDetector:
    """Test DuplicateDetector class."""

    def test_empty_database_no_duplicates(self, db_session, sample_ndjson_record):
        """Test detection with empty database."""
        detector = DuplicateDetector(db_session)
        records = [sample_ndjson_record]

        result = detector.check_duplicates_cross_user(records, 1)

        assert result.has_duplicates is False
        assert result.duplicate_count == 0

    def test_empty_records_list(self, db_session):
        """Test detection with empty records list."""
        detector = DuplicateDetector(db_session)

        result = detector.check_duplicates_cross_user([], 1)

        assert result.has_duplicates is False
        assert result.duplicate_count == 0

    def test_cross_user_duplicate_detected(self, db_session, user1, user2, sample_trade_data, sample_ndjson_record):
        """Test cross-user duplicate detection finds existing trade."""
        # Create trade for user1
        trade = Trade(**sample_trade_data, user_id=user1.user_id)
        db_session.add(trade)
        db_session.commit()

        # Check if user2 has duplicates (should find user1's trade)
        detector = DuplicateDetector(db_session)
        records = [sample_ndjson_record]

        result = detector.check_duplicates_cross_user(records, user2.user_id)

        assert result.has_duplicates is True
        assert result.duplicate_count == 1
        assert user1.user_id in result.duplicates_by_user
        assert result.duplicates_by_user[user1.user_id]['username'] == 'user1'

    def test_cross_user_multiple_users_with_same_trade(self, db_session, user1, user2, user3, sample_trade_data, sample_ndjson_record):
        """Test detection when multiple users have the same trade."""
        # Create same trade for user1 and user2
        trade1 = Trade(**sample_trade_data, user_id=user1.user_id)
        trade2 = Trade(**sample_trade_data, user_id=user2.user_id)
        db_session.add_all([trade1, trade2])
        db_session.commit()

        # Check if user3 has duplicates (should find both)
        detector = DuplicateDetector(db_session)
        records = [sample_ndjson_record]

        result = detector.check_duplicates_cross_user(records, user3.user_id)

        assert result.has_duplicates is True
        assert result.duplicate_count == 2
        assert len(result.duplicates_by_user) == 2
        assert user1.user_id in result.duplicates_by_user
        assert user2.user_id in result.duplicates_by_user

    def test_per_user_duplicate_own_data(self, db_session, user1, sample_trade_data, sample_ndjson_record):
        """Test per-user detection finds user's own duplicate."""
        # Create trade for user1
        trade = Trade(**sample_trade_data, user_id=user1.user_id)
        db_session.add(trade)
        db_session.commit()

        # Check if user1 has duplicates (should find their own)
        detector = DuplicateDetector(db_session)
        records = [sample_ndjson_record]

        result = detector.check_duplicates_per_user(records, user1.user_id)

        assert result.has_duplicates is True
        assert result.duplicate_count == 1
        assert user1.user_id in result.duplicates_by_user

    def test_per_user_no_duplicate_other_user(self, db_session, user1, user2, sample_trade_data, sample_ndjson_record):
        """Test per-user detection doesn't find other user's trades."""
        # Create trade for user1
        trade = Trade(**sample_trade_data, user_id=user1.user_id)
        db_session.add(trade)
        db_session.commit()

        # Check if user2 has duplicates (should NOT find user1's)
        detector = DuplicateDetector(db_session)
        records = [sample_ndjson_record]

        result = detector.check_duplicates_per_user(records, user2.user_id)

        assert result.has_duplicates is False
        assert result.duplicate_count == 0

    def test_multiple_records_partial_duplicates(self, db_session, user1, user2, sample_trade_data):
        """Test detection with multiple records, some duplicates."""
        # Create one trade for user1
        trade = Trade(**sample_trade_data, user_id=user1.user_id)
        db_session.add(trade)
        db_session.commit()

        # Create records: one duplicate, one new
        record1 = NdjsonRecord(
            section='test-section',
            row_index=1,
            raw=json.dumps({'test': 'data'}),
            exec_time=datetime(2025, 1, 15, 10, 0),
            event_type='fill',
            symbol='AAPL',
            side='BUY',
            qty=100,
            pos_effect='TO OPEN',
            price=150.00,
            net_price=150.00,
            order_type='LIMIT',
            source_file='test-file.csv',
            source_file_index=1
        )

        record2 = NdjsonRecord(
            section='test-section',
            row_index=2,
            raw=json.dumps({'test': 'data2'}),
            exec_time=datetime(2025, 1, 15, 11, 0),
            event_type='fill',
            symbol='MSFT',
            side='BUY',
            qty=50,
            pos_effect='TO OPEN',
            price=300.00,
            net_price=300.00,
            order_type='LIMIT',
            source_file='test-file.csv',
            source_file_index=2
        )

        detector = DuplicateDetector(db_session)
        records = [record1, record2]

        result = detector.check_duplicates_cross_user(records, user2.user_id)

        assert result.has_duplicates is True
        assert result.duplicate_count == 1  # Only record1 is duplicate
        assert sample_trade_data['unique_key'] in result.duplicate_unique_keys

    def test_format_report_no_duplicates(self, db_session):
        """Test report formatting with no duplicates."""
        result = DuplicateDetectionResult()
        detector = DuplicateDetector(db_session)

        report = detector.format_duplicate_report(result, 1)

        assert report == "No duplicates found."

    def test_format_report_single_user(self, db_session):
        """Test report formatting for single user with duplicates."""
        result = DuplicateDetectionResult()
        result.add_duplicate(1, 'user1', 'unique_key_1')
        result.add_duplicate(1, 'user1', 'unique_key_2')

        detector = DuplicateDetector(db_session)
        report = detector.format_duplicate_report(result, 2)

        assert "2 duplicate record(s)" in report
        assert "user1" in report
        assert "unique_key_1" in report
        assert "unique_key_2" in report

    def test_format_report_current_user_highlighted(self, db_session):
        """Test report formatting highlights current user's data."""
        result = DuplicateDetectionResult()
        result.add_duplicate(1, 'user1', 'unique_key_1')
        result.add_duplicate(2, 'user2', 'unique_key_2')

        detector = DuplicateDetector(db_session)
        report = detector.format_duplicate_report(result, 2)

        assert "YOUR DATA" in report  # Current user (2) highlighted
        assert "user1" in report  # Other user shown

    def test_format_report_many_duplicates_truncated(self, db_session):
        """Test report formatting truncates long list of duplicates."""
        result = DuplicateDetectionResult()
        for i in range(10):
            result.add_duplicate(1, 'user1', f'unique_key_{i}')

        detector = DuplicateDetector(db_session)
        report = detector.format_duplicate_report(result, 2)

        assert "10 duplicate(s)" in report
        assert "and" in report  # Should show "and X more"
        assert "more" in report

    def test_format_report_long_keys_shortened(self, db_session):
        """Test report formatting shortens very long unique keys."""
        result = DuplicateDetectionResult()
        long_key = "a" * 100  # Very long key
        result.add_duplicate(1, 'user1', long_key)

        detector = DuplicateDetector(db_session)
        report = detector.format_duplicate_report(result, 2)

        assert "..." in report  # Long key should be truncated

    def test_detector_session_management(self, db_session):
        """Test detector can be created with or without session."""
        # With session
        detector1 = DuplicateDetector(db_session)
        assert detector1.session is not None

        # Without session (creates its own)
        detector2 = DuplicateDetector()
        assert detector2.session is not None


class TestDuplicateDetectionIntegration:
    """Integration tests for duplicate detection in realistic scenarios."""

    def test_realistic_ingestion_scenario(self, db_session, user1, user2):
        """Test realistic scenario: user1 ingests, then user2 tries same file."""
        # User1 ingests trades
        trades_user1 = [
            Trade(
                unique_key='file.csv::1::2025-01-15T10:00::AAPL::BUY::100',
                user_id=user1.user_id,
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
                source_file_index=1,
                raw_data={'test': 'data'},
                processing_timestamp=datetime.utcnow()
            ),
            Trade(
                unique_key='file.csv::2::2025-01-15T11:00::MSFT::BUY::50',
                user_id=user1.user_id,
                exec_timestamp=datetime(2025, 1, 15, 11, 0),
                event_type='fill',
                symbol='MSFT',
                instrument_type='EQUITY',
                side='BUY',
                qty=50,
                pos_effect='TO OPEN',
                price=300.00,
                net_price=300.00,
                order_type='LIMIT',
                source_file_path='file.csv',
                source_file_index=2,
                raw_data={'test': 'data2'},
                processing_timestamp=datetime.utcnow()
            )
        ]
        db_session.add_all(trades_user1)
        db_session.commit()

        # User2 tries to ingest same file
        records_user2 = [
            NdjsonRecord(
                exec_time=datetime(2025, 1, 15, 10, 0),
                event_type='fill',
                symbol='AAPL',
                side='BUY',
                qty=100,
                pos_effect='TO OPEN',
                price=150.00,
                net_price=150.00,
                order_type='LIMIT',
                source_file='file.csv',
                source_file_index=1,
                raw={'test': 'data'}
            ),
            NdjsonRecord(
                exec_time=datetime(2025, 1, 15, 11, 0),
                event_type='fill',
                symbol='MSFT',
                side='BUY',
                qty=50,
                pos_effect='TO OPEN',
                price=300.00,
                net_price=300.00,
                order_type='LIMIT',
                source_file='file.csv',
                source_file_index=2,
                raw={'test': 'data2'}
            )
        ]

        detector = DuplicateDetector(db_session)
        result = detector.check_duplicates_cross_user(records_user2, user2.user_id)

        # Should detect both as duplicates from user1
        assert result.has_duplicates is True
        assert result.duplicate_count == 2
        assert user1.user_id in result.duplicates_by_user
        assert len(result.duplicates_by_user[user1.user_id]['unique_keys']) == 2

    def test_user_re_ingesting_own_data(self, db_session, user1):
        """Test scenario: user tries to re-ingest their own data."""
        # User1 ingests trade
        trade = Trade(
            unique_key='file.csv::1::2025-01-15T10:00::AAPL::BUY::100',
            user_id=user1.user_id,
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
            source_file_index=1,
            raw_data={'test': 'data'},
            processing_timestamp=datetime.utcnow()
        )
        db_session.add(trade)
        db_session.commit()

        # User1 tries to re-ingest
        record = NdjsonRecord(
            exec_time=datetime(2025, 1, 15, 10, 0),
            event_type='fill',
            symbol='AAPL',
            side='BUY',
            qty=100,
            pos_effect='TO OPEN',
            price=150.00,
            net_price=150.00,
            order_type='LIMIT',
            source_file='file.csv',
            source_file_index=1,
            raw={'test': 'data'}
        )

        detector = DuplicateDetector(db_session)

        # Cross-user check should find own data
        cross_result = detector.check_duplicates_cross_user([record], user1.user_id)
        assert cross_result.has_duplicates is True
        assert user1.user_id in cross_result.duplicates_by_user

        # Per-user check should also find own data
        per_user_result = detector.check_duplicates_per_user([record], user1.user_id)
        assert per_user_result.has_duplicates is True
