"""Test P&L engine functionality."""

import pytest
from datetime import datetime, date
from decimal import Decimal

from trading_journal.models import Trade, Position, CompletedTrade
from trading_journal.positions import PositionTracker
from trading_journal.trade_completion import TradeCompletionEngine
from trading_journal.schemas import NdjsonRecord, OptionDetails


@pytest.fixture
def position_tracker():
    """Create position tracker instance."""
    return PositionTracker()


@pytest.fixture
def trade_engine():
    """Create trade completion engine instance."""
    return TradeCompletionEngine()


def test_basic_long_position_tracking():
    """Test basic long position tracking with average cost."""
    # Create buy trade
    buy_trade = Trade(
        trade_id=1,
        unique_key="test_buy_1",
        exec_timestamp=datetime(2025, 1, 15, 10, 0),
        event_type="fill",
        symbol="AAPL",
        instrument_type="EQUITY",
        side="BUY",
        qty=100,
        pos_effect="TO OPEN",
        net_price=150.00,
        raw_data="test buy"
    )

    position = Position(
        symbol="AAPL",
        instrument_type="EQUITY",
        current_qty=0,
        avg_cost_basis=Decimal('0'),
        total_cost=Decimal('0'),
        realized_pnl=Decimal('0')
    )

    tracker = PositionTracker()
    tracker._handle_position_open(position, buy_trade)

    assert position.current_qty == 100
    assert position.avg_cost_basis == Decimal('150.00')
    assert position.total_cost == Decimal('15000.00')


def test_average_cost_calculation():
    """Test average cost calculation with multiple buys."""
    position = Position(
        symbol="AAPL",
        instrument_type="EQUITY",
        current_qty=100,
        avg_cost_basis=Decimal('150.00'),
        total_cost=Decimal('15000.00'),
        realized_pnl=Decimal('0')
    )

    # Second buy at different price
    buy_trade2 = Trade(
        trade_id=2,
        unique_key="test_buy_2",
        exec_timestamp=datetime(2025, 1, 16, 10, 0),
        event_type="fill",
        symbol="AAPL",
        instrument_type="EQUITY",
        side="BUY",
        qty=50,
        pos_effect="TO OPEN",
        net_price=160.00,
        raw_data="test buy 2"
    )

    tracker = PositionTracker()
    tracker._handle_position_open(position, buy_trade2)

    # New average: (15000 + 8000) / 150 = $153.33
    assert position.current_qty == 150
    assert abs(position.avg_cost_basis - Decimal('153.333333')) < Decimal('0.001')
    assert position.total_cost == Decimal('23000.00')


def test_position_close_with_pnl():
    """Test position closing and P&L calculation."""
    position = Position(
        symbol="AAPL",
        instrument_type="EQUITY",
        current_qty=150,
        avg_cost_basis=Decimal('153.333333'),
        total_cost=Decimal('23000.00'),
        realized_pnl=Decimal('0')
    )

    # Sell half position at profit
    sell_trade = Trade(
        trade_id=3,
        unique_key="test_sell_1",
        exec_timestamp=datetime(2025, 1, 17, 10, 0),
        event_type="fill",
        symbol="AAPL",
        instrument_type="EQUITY",
        side="SELL",
        qty=75,
        pos_effect="TO CLOSE",
        net_price=160.00,
        raw_data="test sell"
    )

    tracker = PositionTracker()
    tracker._handle_position_close(position, sell_trade)

    # P&L calculation: 75 * (160 - 153.33) = $500
    expected_pnl = 75 * (160.00 - 153.333333)
    assert abs(sell_trade.realized_pnl - expected_pnl) < 0.01

    # Remaining position
    assert position.current_qty == 75
    assert abs(position.avg_cost_basis - Decimal('153.333333')) < Decimal('0.001')


def test_short_position():
    """Test short position tracking."""
    position = Position(
        symbol="AAPL",
        instrument_type="EQUITY",
        current_qty=0,
        avg_cost_basis=Decimal('0'),
        total_cost=Decimal('0'),
        realized_pnl=Decimal('0')
    )

    # Sell short
    short_trade = Trade(
        trade_id=4,
        unique_key="test_short_1",
        exec_timestamp=datetime(2025, 1, 18, 10, 0),
        event_type="fill",
        symbol="AAPL",
        instrument_type="EQUITY",
        side="SELL",
        qty=100,
        pos_effect="TO OPEN",
        net_price=150.00,
        raw_data="test short"
    )

    tracker = PositionTracker()
    tracker._handle_position_open(position, short_trade)

    assert position.current_qty == -100  # Negative for short
    assert position.avg_cost_basis == Decimal('150.00')


def test_etf_position_tracking():
    """Test ETF position tracking (ETF maps to EQUITY instrument_type)."""
    # Create ETF buy trade
    etf_buy_trade = Trade(
        trade_id=5,
        unique_key="test_etf_buy_1",
        exec_timestamp=datetime(2025, 1, 20, 10, 0),
        event_type="fill",
        symbol="SPY",
        instrument_type="EQUITY",  # ETF maps to EQUITY
        side="BUY",
        qty=50,
        pos_effect="TO OPEN",
        net_price=450.00,
        raw_data="test etf buy"
    )

    position = Position(
        symbol="SPY",
        instrument_type="EQUITY",
        current_qty=0,
        avg_cost_basis=Decimal('0'),
        total_cost=Decimal('0'),
        realized_pnl=Decimal('0')
    )

    tracker = PositionTracker()
    tracker._handle_position_open(position, etf_buy_trade)

    # Verify position tracking works identically to stocks
    assert position.current_qty == 50
    assert position.avg_cost_basis == Decimal('450.00')
    assert position.total_cost == Decimal('22500.00')

    # Test ETF sell
    etf_sell_trade = Trade(
        trade_id=6,
        unique_key="test_etf_sell_1",
        exec_timestamp=datetime(2025, 1, 20, 14, 0),
        event_type="fill",
        symbol="SPY",
        instrument_type="EQUITY",
        side="SELL",
        qty=50,
        pos_effect="TO CLOSE",
        net_price=455.00,
        raw_data="test etf sell"
    )

    tracker._handle_position_close(position, etf_sell_trade)

    # Verify P&L calculation works correctly
    assert position.current_qty == 0
    assert position.realized_pnl == Decimal('250.00')  # (455 - 450) * 50


def test_ndjson_record_validation():
    """Test NDJSON record schema validation."""
    # Valid equity record
    valid_record = {
        "section": "Filled Orders",
        "row_index": 10,
        "raw": "test raw data",
        "issues": [],
        "exec_time": "2025-01-15T10:00:00",
        "side": "BUY",
        "qty": 100,
        "pos_effect": "TO OPEN",
        "symbol": "AAPL",
        "type": "STOCK",
        "net_price": 150.00,
        "event_type": "fill",
        "asset_type": "STOCK",
        "source_file": "test.ndjson"
    }

    record = NdjsonRecord(**valid_record)
    assert record.is_fill is True
    assert record.is_equity is True
    assert record.is_option is False
    assert record.symbol == "AAPL"
    assert record.unique_key.startswith("test.ndjson:10:")


def test_etf_record_validation():
    """Test ETF NDJSON record validation."""
    etf_record = {
        "section": "Filled Orders",
        "row_index": 12,
        "raw": "test etf data",
        "issues": [],
        "exec_time": "2025-01-15T10:00:00",
        "side": "BUY",
        "qty": 50,
        "pos_effect": "TO OPEN",
        "symbol": "SPY",
        "type": "STOCK",
        "net_price": 450.00,
        "event_type": "fill",
        "asset_type": "ETF",  # Key: ETF asset type
        "source_file": "test.ndjson"
    }

    record = NdjsonRecord(**etf_record)
    assert record.is_fill is True
    assert record.is_equity is True  # ETF should be equity
    assert record.is_option is False
    assert record.symbol == "SPY"
    assert record.asset_type == "ETF"
    assert record.unique_key.startswith("test.ndjson:12:")


def test_option_record_validation():
    """Test options NDJSON record validation."""
    option_record = {
        "section": "Filled Orders",
        "row_index": 11,
        "raw": "test option data",
        "issues": [],
        "exec_time": "2025-01-15T10:00:00",
        "side": "BUY",
        "qty": 3,
        "pos_effect": "TO OPEN",
        "symbol": "SPY",
        "type": "CALL",
        "exp": "2025-01-21",
        "strike": 673.0,
        "net_price": 2.50,
        "event_type": "fill",
        "asset_type": "OPTION",
        "option": {
            "exp_date": "2025-01-21",
            "strike": 673.0,
            "right": "CALL"
        },
        "source_file": "test.ndjson"
    }

    record = NdjsonRecord(**option_record)
    assert record.is_fill is True
    assert record.is_equity is False
    assert record.is_option is True
    assert record.option.right == "CALL"
    assert record.option.strike == 673.0


def test_validation_errors():
    """Test schema validation errors."""
    invalid_record = {
        "section": "Filled Orders",
        "row_index": 12,
        "raw": "test data",
        "issues": [],
        "side": "INVALID_SIDE",  # Invalid value
        "event_type": "invalid_event"  # Invalid value
    }

    with pytest.raises(ValueError):
        NdjsonRecord(**invalid_record)

    # Test invalid asset_type
    invalid_asset_type_record = {
        "section": "Filled Orders",
        "row_index": 13,
        "raw": "test data",
        "issues": [],
        "exec_time": "2025-01-15T10:00:00",
        "side": "BUY",
        "qty": 100,
        "pos_effect": "TO OPEN",
        "symbol": "TEST",
        "net_price": 100.00,
        "event_type": "fill",
        "asset_type": "INVALID_ASSET",  # Invalid asset type
        "source_file": "test.ndjson"
    }

    with pytest.raises(ValueError, match="asset_type must be STOCK, OPTION, or ETF"):
        NdjsonRecord(**invalid_asset_type_record)

    # Verify that ETF asset_type is valid (should not raise error)
    valid_etf_record = {
        "section": "Filled Orders",
        "row_index": 14,
        "raw": "test etf data",
        "issues": [],
        "exec_time": "2025-01-15T10:00:00",
        "side": "BUY",
        "qty": 100,
        "pos_effect": "TO OPEN",
        "symbol": "SPY",
        "type": "STOCK",
        "net_price": 450.00,
        "event_type": "fill",
        "asset_type": "ETF",  # ETF should be valid
        "source_file": "test.ndjson"
    }

    # Should not raise an error
    etf_record = NdjsonRecord(**valid_etf_record)
    assert etf_record.asset_type == "ETF"
    assert etf_record.is_equity is True


def test_position_summary_calculation():
    """Test position summary calculations."""
    # Mock positions for testing
    positions = [
        {
            "symbol": "AAPL",
            "instrument_type": "EQUITY",
            "current_qty": 100,
            "avg_cost_basis": 150.00,
            "realized_pnl": 500.00,
            "is_open": True
        },
        {
            "symbol": "MSFT",
            "instrument_type": "EQUITY",
            "current_qty": 0,
            "avg_cost_basis": 0.00,
            "realized_pnl": -200.00,
            "is_open": False
        }
    ]

    # Test calculations
    open_positions = [p for p in positions if p["is_open"]]
    closed_positions = [p for p in positions if not p["is_open"]]

    total_realized_pnl = sum(p["realized_pnl"] for p in positions)
    total_open_value = sum(p["current_qty"] * p["avg_cost_basis"] for p in open_positions)

    assert len(open_positions) == 1
    assert len(closed_positions) == 1
    assert total_realized_pnl == 300.00
    assert total_open_value == 15000.00


def test_unique_key_generation():
    """Test unique key generation for different scenarios."""
    base_record = {
        "section": "Filled Orders",
        "row_index": 10,
        "raw": "test data",
        "issues": [],
        "source_file": "test.ndjson",
        "symbol": "AAPL"
    }

    # Fill record
    fill_record = base_record.copy()
    fill_record.update({
        "exec_time": "2025-01-15T10:00:00",
        "side": "BUY",
        "qty": 100,
        "event_type": "fill"
    })

    record1 = NdjsonRecord(**fill_record)
    key1 = record1.unique_key

    # Cancel record (different time)
    cancel_record = base_record.copy()
    cancel_record.update({
        "time_canceled": "2025-01-15T10:05:00",
        "side": "BUY",
        "qty": 100,
        "event_type": "cancel"
    })

    record2 = NdjsonRecord(**cancel_record)
    key2 = record2.unique_key

    assert key1 != key2  # Should have different unique keys
    assert "test.ndjson:10:" in key1
    assert "test.ndjson:10:" in key2


def test_decimal_precision():
    """Test decimal precision in P&L calculations."""
    # Test with precise decimal values
    cost_basis = Decimal('150.123456')
    exit_price = Decimal('155.987654')
    quantity = 100

    expected_pnl = (exit_price - cost_basis) * quantity
    assert abs(expected_pnl - Decimal('586.419800')) < Decimal('0.000001')

    # Test rounding behavior
    rounded_pnl = round(float(expected_pnl), 2)
    assert rounded_pnl == 586.42