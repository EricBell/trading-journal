"""Test options trade completion with 100x multiplier."""

import pytest
from datetime import datetime, date
from decimal import Decimal

from trading_journal.models import Trade, CompletedTrade, User
from trading_journal.trade_completion import TradeCompletionEngine
from trading_journal.authorization import AuthContext


@pytest.fixture
def test_user(db_session):
    """Create a test user and set auth context."""
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


@pytest.fixture
def trade_engine():
    """Create trade completion engine instance."""
    return TradeCompletionEngine()


def create_option_trade(user_id, trade_id, side, qty, pos_effect, net_price, timestamp, symbol="SPY",
                       exp_date="2025-01-21", strike=673.0, option_type="CALL"):
    """Helper to create option trades."""
    return Trade(
        user_id=user_id,
        trade_id=trade_id,
        unique_key=f"test_option_{trade_id}",
        exec_timestamp=timestamp,
        event_type="fill",
        symbol=symbol,
        instrument_type="OPTION",
        side=side,
        qty=qty,
        pos_effect=pos_effect,
        net_price=net_price,
        raw_data=f"test option {side}",
        exp_date=date.fromisoformat(exp_date),
        strike_price=Decimal(str(strike)),
        option_type=option_type,
        option_data={
            "exp_date": exp_date,
            "strike": strike,
            "right": option_type
        }
    )


def test_basic_option_trade_completion_with_profit(db_session, test_user):
    """Test basic options trade completion with 100x multiplier - profit scenario."""
    # Create a complete option trade cycle: BUY TO OPEN -> SELL TO CLOSE

    # Buy 2 SPY calls at $2.50 each
    buy_trade = create_option_trade(
        user_id=test_user.user_id,
        trade_id=1,
        side="BUY",
        qty=2,
        pos_effect="TO OPEN",
        net_price=2.50,
        timestamp=datetime(2025, 1, 15, 10, 0)
    )

    # Sell 2 SPY calls at $3.50 each (profit)
    sell_trade = create_option_trade(
        user_id=test_user.user_id,
        trade_id=2,
        side="SELL",
        qty=2,
        pos_effect="TO CLOSE",
        net_price=3.50,
        timestamp=datetime(2025, 1, 16, 15, 0)
    )

    # Add trades to database
    db_session.add_all([buy_trade, sell_trade])
    db_session.commit()

    # Process completed trades
    engine = TradeCompletionEngine()
    result = engine.process_completed_trades()

    assert result["completed_trades"] == 1

    # Check the completed trade
    completed_trade = db_session.query(CompletedTrade).first()
    assert completed_trade is not None
    assert completed_trade.symbol == "SPY"
    assert completed_trade.instrument_type == "OPTION"
    assert completed_trade.total_qty == 2

    # Entry cost: 2 contracts * $2.50 * 100 = $500
    # Exit proceeds: 2 contracts * $3.50 * 100 = $700
    # Net P&L: $700 - $500 = $200
    assert completed_trade.gross_cost == 500.0
    assert completed_trade.gross_proceeds == 700.0
    assert completed_trade.net_pnl == 200.0
    assert completed_trade.is_winning_trade is True
    assert completed_trade.trade_type == "LONG"

    # Average prices should reflect the multiplied values
    assert completed_trade.entry_avg_price == 250.0  # $2.50 * 100
    assert completed_trade.exit_avg_price == 350.0   # $3.50 * 100


def test_option_trade_completion_with_loss(db_session, test_user):
    """Test options trade completion with loss."""
    # Buy 1 SPY call at $4.00
    buy_trade = create_option_trade(
        user_id=test_user.user_id,
        trade_id=3,
        side="BUY",
        qty=1,
        pos_effect="TO OPEN",
        net_price=4.00,
        timestamp=datetime(2025, 1, 15, 10, 0)
    )

    # Sell 1 SPY call at $2.25 (loss)
    sell_trade = create_option_trade(
        user_id=test_user.user_id,
        trade_id=4,
        side="SELL",
        qty=1,
        pos_effect="TO CLOSE",
        net_price=2.25,
        timestamp=datetime(2025, 1, 16, 15, 0)
    )

    db_session.add_all([buy_trade, sell_trade])
    db_session.commit()

    engine = TradeCompletionEngine()
    result = engine.process_completed_trades()

    assert result["completed_trades"] == 1

    completed_trade = db_session.query(CompletedTrade).first()

    # Entry cost: 1 contract * $4.00 * 100 = $400
    # Exit proceeds: 1 contract * $2.25 * 100 = $225
    # Net P&L: $225 - $400 = -$175 (loss)
    assert completed_trade.gross_cost == 400.0
    assert completed_trade.gross_proceeds == 225.0
    assert completed_trade.net_pnl == -175.0
    assert completed_trade.is_winning_trade is False


def test_short_option_trade_completion(db_session, test_user):
    """Test short options trade completion."""
    # Sell to open (short) 3 SPY calls at $3.00 each
    sell_open_trade = create_option_trade(
        user_id=test_user.user_id,
        trade_id=5,
        side="SELL",
        qty=3,
        pos_effect="TO OPEN",
        net_price=3.00,
        timestamp=datetime(2025, 1, 15, 10, 0)
    )

    # Buy to close at $2.00 each (profit on short)
    buy_close_trade = create_option_trade(
        user_id=test_user.user_id,
        trade_id=6,
        side="BUY",
        qty=3,
        pos_effect="TO CLOSE",
        net_price=2.00,
        timestamp=datetime(2025, 1, 16, 15, 0)
    )

    db_session.add_all([sell_open_trade, buy_close_trade])
    db_session.commit()

    engine = TradeCompletionEngine()
    result = engine.process_completed_trades()

    assert result["completed_trades"] == 1

    completed_trade = db_session.query(CompletedTrade).first()

    # For short trades: P&L = cost - proceeds
    # Open proceeds (credit): 3 contracts * $3.00 * 100 = $900
    # Close cost: 3 contracts * $2.00 * 100 = $600
    # Net P&L: $900 - $600 = $300 profit
    assert completed_trade.gross_cost == 900.0  # What we collected selling
    assert completed_trade.gross_proceeds == 600.0  # What we paid to close
    assert completed_trade.net_pnl == 300.0  # Profit from short
    assert completed_trade.is_winning_trade is True
    assert completed_trade.trade_type == "SHORT"


def test_multiple_option_contracts_different_prices(db_session, test_user):
    """Test trade completion with multiple option fills at different prices."""
    # Buy 1 contract at $2.50
    buy1_trade = create_option_trade(
        user_id=test_user.user_id,
        trade_id=7,
        side="BUY",
        qty=1,
        pos_effect="TO OPEN",
        net_price=2.50,
        timestamp=datetime(2025, 1, 15, 10, 0)
    )

    # Buy 2 more contracts at $3.00 (different price)
    buy2_trade = create_option_trade(
        user_id=test_user.user_id,
        trade_id=8,
        side="BUY",
        qty=2,
        pos_effect="TO OPEN",
        net_price=3.00,
        timestamp=datetime(2025, 1, 15, 11, 0)
    )

    # Sell all 3 contracts at $4.25
    sell_trade = create_option_trade(
        user_id=test_user.user_id,
        trade_id=9,
        side="SELL",
        qty=3,
        pos_effect="TO CLOSE",
        net_price=4.25,
        timestamp=datetime(2025, 1, 16, 15, 0)
    )

    db_session.add_all([buy1_trade, buy2_trade, sell_trade])
    db_session.commit()

    engine = TradeCompletionEngine()
    result = engine.process_completed_trades()

    assert result["completed_trades"] == 1

    completed_trade = db_session.query(CompletedTrade).first()

    # Total cost: (1 * $2.50 * 100) + (2 * $3.00 * 100) = $250 + $600 = $850
    # Total proceeds: 3 * $4.25 * 100 = $1,275
    # Net P&L: $1,275 - $850 = $425
    assert completed_trade.gross_cost == 850.0
    assert completed_trade.gross_proceeds == 1275.0
    assert completed_trade.net_pnl == 425.0
    assert completed_trade.is_winning_trade is True

    # Weighted average entry: $850 / 3 contracts = $283.33 per contract
    # Exit average: $1,275 / 3 contracts = $425 per contract
    assert abs(float(completed_trade.entry_avg_price) - 283.33) < 0.01
    assert abs(float(completed_trade.exit_avg_price) - 425.00) < 0.01


def test_option_vs_equity_trade_completion_comparison(db_session, test_user):
    """Test that the same trade with equity vs option has different P&L due to multiplier."""
    # Create identical trades but with different instrument types

    # Equity trade: Buy 100 shares at $2.50, sell at $3.50
    equity_buy = Trade(
        user_id=test_user.user_id,
        trade_id=10,
        unique_key="equity_buy_10",
        exec_timestamp=datetime(2025, 1, 15, 10, 0),
        event_type="fill",
        symbol="AAPL",
        instrument_type="EQUITY",
        side="BUY",
        qty=100,
        pos_effect="TO OPEN",
        net_price=2.50,
        raw_data="equity test"
    )

    equity_sell = Trade(
        user_id=test_user.user_id,
        trade_id=11,
        unique_key="equity_sell_11",
        exec_timestamp=datetime(2025, 1, 16, 15, 0),
        event_type="fill",
        symbol="AAPL",
        instrument_type="EQUITY",
        side="SELL",
        qty=100,
        pos_effect="TO CLOSE",
        net_price=3.50,
        raw_data="equity test"
    )

    # Option trade: Buy 1 contract at $2.50, sell at $3.50
    option_buy = create_option_trade(
        user_id=test_user.user_id,
        trade_id=12,
        side="BUY",
        qty=1,
        pos_effect="TO OPEN",
        net_price=2.50,
        timestamp=datetime(2025, 1, 15, 10, 0),
        symbol="SPY"
    )

    option_sell = create_option_trade(
        user_id=test_user.user_id,
        trade_id=13,
        side="SELL",
        qty=1,
        pos_effect="TO CLOSE",
        net_price=3.50,
        timestamp=datetime(2025, 1, 16, 15, 0),
        symbol="SPY"
    )

    db_session.add_all([equity_buy, equity_sell, option_buy, option_sell])
    db_session.commit()

    engine = TradeCompletionEngine()
    result = engine.process_completed_trades()

    assert result["completed_trades"] == 2

    completed_trades = db_session.query(CompletedTrade).order_by(CompletedTrade.symbol).all()
    equity_trade = completed_trades[0]  # AAPL
    option_trade = completed_trades[1]  # SPY

    # Equity: 100 shares * ($3.50 - $2.50) = $100 profit
    assert equity_trade.net_pnl == 100.0
    assert equity_trade.gross_cost == 250.0  # 100 * $2.50
    assert equity_trade.gross_proceeds == 350.0  # 100 * $3.50

    # Option: 1 contract * ($3.50 - $2.50) * 100 = $100 profit (same $1.00 move but multiplied)
    assert option_trade.net_pnl == 100.0
    assert option_trade.gross_cost == 250.0   # 1 * $2.50 * 100
    assert option_trade.gross_proceeds == 350.0  # 1 * $3.50 * 100