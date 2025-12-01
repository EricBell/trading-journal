"""Test P&L engine functionality."""

import pytest
from datetime import datetime, date
from decimal import Decimal

from trading_journal.models import Trade, Position, CompletedTrade
from trading_journal.positions import PositionTracker, get_contract_multiplier
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


def test_contract_multiplier():
    """Test contract multiplier function."""
    assert get_contract_multiplier("EQUITY") == 1
    assert get_contract_multiplier("OPTION") == 100


def test_option_position_opening():
    """Test options position opening with 100x multiplier."""
    # Create options buy trade - 1 contract at $2.50 should cost $250
    option_trade = Trade(
        trade_id=1,
        unique_key="test_option_buy_1",
        exec_timestamp=datetime(2025, 1, 15, 10, 0),
        event_type="fill",
        symbol="SPY",
        instrument_type="OPTION",
        side="BUY",
        qty=1,
        pos_effect="TO OPEN",
        net_price=2.50,
        raw_data="test option buy",
        exp_date=date(2025, 1, 21),
        strike_price=Decimal('673.0'),
        option_type="CALL"
    )

    position = Position(
        symbol="SPY",
        instrument_type="OPTION",
        current_qty=0,
        avg_cost_basis=Decimal('0'),
        total_cost=Decimal('0'),
        realized_pnl=Decimal('0')
    )

    tracker = PositionTracker()
    tracker._handle_position_open(position, option_trade)

    # 1 contract at $2.50 premium = $250 total cost
    assert position.current_qty == 1
    assert position.avg_cost_basis == Decimal('250.00')  # $2.50 * 100
    assert position.total_cost == Decimal('250.00')  # $2.50 * 1 * 100


def test_option_position_closing_with_profit():
    """Test options position closing with profit and 100x multiplier."""
    # Start with long 1 SPY call position at $250 cost basis
    position = Position(
        symbol="SPY",
        instrument_type="OPTION",
        current_qty=1,
        avg_cost_basis=Decimal('250.00'),
        total_cost=Decimal('250.00'),
        realized_pnl=Decimal('0')
    )

    # Sell the contract for $3.00 premium ($300 proceeds)
    sell_trade = Trade(
        trade_id=2,
        unique_key="test_option_sell_1",
        exec_timestamp=datetime(2025, 1, 16, 15, 0),
        event_type="fill",
        symbol="SPY",
        instrument_type="OPTION",
        side="SELL",
        qty=1,
        pos_effect="TO CLOSE",
        net_price=3.00,
        raw_data="test option sell",
        exp_date=date(2025, 1, 21),
        strike_price=Decimal('673.0'),
        option_type="CALL"
    )

    tracker = PositionTracker()
    tracker._handle_position_close(position, sell_trade)

    # P&L should be $300 (proceeds) - $250 (cost basis) = $50 profit
    assert sell_trade.realized_pnl == 50.0
    assert position.current_qty == 0
    assert position.realized_pnl == Decimal('50.0')


def test_option_position_closing_with_loss():
    """Test options position closing with loss and 100x multiplier."""
    # Start with long 2 SPY call position at $500 total cost basis
    position = Position(
        symbol="SPY",
        instrument_type="OPTION",
        current_qty=2,
        avg_cost_basis=Decimal('250.00'),  # $2.50 * 100 per contract
        total_cost=Decimal('500.00'),  # 2 contracts * $250 each
        realized_pnl=Decimal('0')
    )

    # Sell 1 contract for $1.50 premium ($150 proceeds)
    sell_trade = Trade(
        trade_id=3,
        unique_key="test_option_sell_2",
        exec_timestamp=datetime(2025, 1, 16, 15, 0),
        event_type="fill",
        symbol="SPY",
        instrument_type="OPTION",
        side="SELL",
        qty=1,
        pos_effect="TO CLOSE",
        net_price=1.50,
        raw_data="test option sell",
        exp_date=date(2025, 1, 21),
        strike_price=Decimal('673.0'),
        option_type="CALL"
    )

    tracker = PositionTracker()
    tracker._handle_position_close(position, sell_trade)

    # P&L should be $150 (proceeds) - $250 (cost basis for 1 contract) = -$100 loss
    assert sell_trade.realized_pnl == -100.0
    assert position.current_qty == 1  # 1 contract remaining
    assert position.realized_pnl == Decimal('-100.0')
    assert position.total_cost == Decimal('250.0')  # Cost for remaining 1 contract


def test_equity_vs_option_multiplier_difference():
    """Test that equity and options use different multipliers."""
    # Equity trade - no multiplier
    equity_position = Position(
        symbol="AAPL",
        instrument_type="EQUITY",
        current_qty=0,
        avg_cost_basis=Decimal('0'),
        total_cost=Decimal('0'),
        realized_pnl=Decimal('0')
    )

    equity_trade = Trade(
        trade_id=4,
        unique_key="equity_test",
        exec_timestamp=datetime(2025, 1, 15, 10, 0),
        event_type="fill",
        symbol="AAPL",
        instrument_type="EQUITY",
        side="BUY",
        qty=100,
        pos_effect="TO OPEN",
        net_price=150.00,
        raw_data="equity test"
    )

    # Options trade - 100x multiplier
    option_position = Position(
        symbol="SPY",
        instrument_type="OPTION",
        current_qty=0,
        avg_cost_basis=Decimal('0'),
        total_cost=Decimal('0'),
        realized_pnl=Decimal('0')
    )

    option_trade = Trade(
        trade_id=5,
        unique_key="option_test",
        exec_timestamp=datetime(2025, 1, 15, 10, 0),
        event_type="fill",
        symbol="SPY",
        instrument_type="OPTION",
        side="BUY",
        qty=1,
        pos_effect="TO OPEN",
        net_price=1.50,
        raw_data="option test"
    )

    tracker = PositionTracker()
    tracker._handle_position_open(equity_position, equity_trade)
    tracker._handle_position_open(option_position, option_trade)

    # Equity: 100 shares * $150 = $15,000 total cost
    assert equity_position.total_cost == Decimal('15000.00')
    assert equity_position.avg_cost_basis == Decimal('150.00')

    # Option: 1 contract * $1.50 * 100 = $150 total cost
    assert option_position.total_cost == Decimal('150.00')
    assert option_position.avg_cost_basis == Decimal('150.00')

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