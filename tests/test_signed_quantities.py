"""Tests for handling signed quantities in NDJSON ingestion."""

import pytest
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import json
import tempfile

from trading_journal.models import User, Trade
from trading_journal.ingestion import NdjsonIngester
from trading_journal.authorization import AuthContext
from trading_journal.database import db_manager


@pytest.fixture
def test_user(db_session):
    """Create a test user."""
    user = User(
        username="testuser",
        email="test@example.com",
        auth_method="api_key",
        is_active=True
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    # Set auth context
    from trading_journal.auth import AuthUser
    auth_user = AuthUser(
        user_id=user.user_id,
        username=user.username,
        email=user.email,
        is_admin=user.is_admin,
        is_active=user.is_active,
        auth_method=user.auth_method
    )
    AuthContext.set_current_user(auth_user)

    yield user

    AuthContext.clear()


def create_ndjson_file(records: list) -> Path:
    """Helper to create a temporary NDJSON file."""
    temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.ndjson', delete=False)
    for record in records:
        # Add default required fields if not present
        if "section" not in record:
            record["section"] = "Filled Orders"
        if "row_index" not in record:
            record["row_index"] = 1
        temp_file.write(json.dumps(record) + '\n')
    temp_file.flush()
    return Path(temp_file.name)


class TestSignedQuantities:
    """Test handling of signed vs unsigned quantities."""

    def test_unsigned_quantities_positive(self, db_session, test_user):
        """Test that unsigned (positive) quantities are stored correctly."""
        records = [
            {
                "exec_time": "2025-12-01T10:00:00",
                "side": "BUY",
                "qty": 100,  # Positive (correct format)
                "pos_effect": "TO OPEN",
                "symbol": "TEST",
                "type": "STOCK",
                "spread": "STOCK",
                "net_price": 50.00,
                "event_type": "fill",
                "asset_type": "STOCK",
                "source_file": "test.csv",
                "raw": "test data"
            }
        ]

        file_path = create_ndjson_file(records)
        ingester = NdjsonIngester()
        result = ingester.process_file(file_path, force=True)

        assert result["success"]
        assert result["records_processed"] == 1

        # Check database
        trade = db_session.query(Trade).filter_by(symbol="TEST").first()
        assert trade is not None
        assert trade.qty == 100  # Should be positive
        assert trade.side == "BUY"

        file_path.unlink()

    def test_signed_quantities_negative_converted_to_positive(self, db_session, test_user):
        """Test that signed (negative) quantities are converted to positive."""
        records = [
            {
                "exec_time": "2025-12-01T10:00:00",
                "side": "SELL",
                "qty": -50,  # Negative (incorrect format from converter)
                "pos_effect": "TO CLOSE",
                "symbol": "TEST2",
                "type": "STOCK",
                "spread": "STOCK",
                "net_price": 55.00,
                "event_type": "fill",
                "asset_type": "STOCK",
                "source_file": "test.csv",
                "raw": "test data"
            }
        ]

        file_path = create_ndjson_file(records)
        ingester = NdjsonIngester()
        result = ingester.process_file(file_path, force=True)

        assert result["success"]
        assert result["records_processed"] == 1

        # Check database - qty should be positive!
        trade = db_session.query(Trade).filter_by(symbol="TEST2").first()
        assert trade is not None
        assert trade.qty == 50  # Should be converted to positive
        assert trade.side == "SELL"

        file_path.unlink()

    def test_complete_trade_cycle_with_signed_quantities(self, db_session, test_user):
        """Test a complete trade cycle using signed quantities from converter."""
        records = [
            # BUY TO OPEN (positive qty)
            {
                "exec_time": "2025-12-01T09:00:00",
                "side": "BUY",
                "qty": 100,
                "pos_effect": "TO OPEN",
                "symbol": "CYCLE",
                "type": "STOCK",
                "spread": "STOCK",
                "net_price": 10.00,
                "event_type": "fill",
                "asset_type": "STOCK",
                "source_file": "test.csv",
                "raw": "test data"
            },
            # SELL TO CLOSE (negative qty from converter)
            {
                "exec_time": "2025-12-01T10:00:00",
                "side": "SELL",
                "qty": -100,  # Negative from converter
                "pos_effect": "TO CLOSE",
                "symbol": "CYCLE",
                "type": "STOCK",
                "spread": "STOCK",
                "net_price": 12.00,
                "event_type": "fill",
                "asset_type": "STOCK",
                "source_file": "test.csv",
                "raw": "test data"
            }
        ]

        file_path = create_ndjson_file(records)
        ingester = NdjsonIngester()
        result = ingester.process_file(file_path, force=True)

        assert result["success"]
        assert result["records_processed"] == 2

        # Check both trades have positive quantities
        trades = db_session.query(Trade).filter_by(symbol="CYCLE").order_by(Trade.exec_timestamp).all()
        assert len(trades) == 2
        assert trades[0].qty == 100  # BUY
        assert trades[1].qty == 100  # SELL (converted from -100)

        file_path.unlink()

    def test_upsert_updates_negative_quantity_to_positive(self, db_session, test_user):
        """Test that re-ingesting with UPSERT fixes negative quantities in existing records."""
        # First ingestion with negative qty (simulating old data)
        records_v1 = [
            {
                "exec_time": "2025-12-01T10:00:00",
                "side": "SELL",
                "qty": -50,  # Negative (will be converted to positive with fix)
                "pos_effect": "TO CLOSE",
                "symbol": "UPSERT_TEST",
                "type": "STOCK",
                "spread": "STOCK",
                "net_price": 55.00,
                "event_type": "fill",
                "asset_type": "STOCK",
                "source_file": "test_v1.csv",
                "raw": "test data v1"
            }
        ]

        file_path_v1 = create_ndjson_file(records_v1)
        ingester = NdjsonIngester()
        result_v1 = ingester.process_file(file_path_v1, force=True)

        assert result_v1["success"]

        # Verify first ingestion converted to positive
        trade_v1 = db_session.query(Trade).filter_by(symbol="UPSERT_TEST").first()
        assert trade_v1 is not None
        assert trade_v1.qty == 50  # Should be positive after fix

        # Second ingestion - same record (UPSERT should update qty)
        records_v2 = [
            {
                "exec_time": "2025-12-01T10:00:00",
                "side": "SELL",
                "qty": -50,  # Still negative from converter
                "pos_effect": "TO CLOSE",
                "symbol": "UPSERT_TEST",
                "type": "STOCK",
                "spread": "STOCK",
                "net_price": 56.00,  # Updated price
                "event_type": "fill",
                "asset_type": "STOCK",
                "source_file": "test_v1.csv",  # Same source file for UPSERT to work
                "raw": "test data v1"  # Same raw for same unique_key
            }
        ]

        file_path_v2 = create_ndjson_file(records_v2)
        result_v2 = ingester.process_file(file_path_v2, force=True)

        assert result_v2["success"]

        # Verify UPSERT maintained positive qty
        db_session.expire_all()  # Clear cache to get fresh data
        trade_v2 = db_session.query(Trade).filter_by(symbol="UPSERT_TEST").first()
        assert trade_v2 is not None
        assert trade_v2.qty == 50  # Should still be positive
        assert trade_v2.net_price == 56.00  # Price should be updated

        # Verify only one record exists (UPSERT, not duplicate)
        trade_count = db_session.query(Trade).filter_by(symbol="UPSERT_TEST").count()
        assert trade_count == 1

        file_path_v1.unlink()
        file_path_v2.unlink()
