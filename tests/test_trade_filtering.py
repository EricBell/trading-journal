"""Tests for trade completion filtering and user isolation."""

import pytest
from datetime import datetime, date, timedelta
from decimal import Decimal

from trading_journal.models import CompletedTrade, User, Trade
from trading_journal.trade_completion import TradeCompletionEngine
from trading_journal.authorization import AuthContext
from trading_journal.database import db_manager


@pytest.fixture
def user1(db_session):
    """Create first test user."""
    user = User(
        username="user1",
        email="user1@example.com",
        auth_method="api_key",
        is_active=True
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def user2(db_session):
    """Create second test user for isolation testing."""
    user = User(
        username="user2",
        email="user2@example.com",
        auth_method="api_key",
        is_active=True
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def setup_auth(user1):
    """Set up authentication context for user1."""
    from trading_journal.auth import AuthUser
    auth_user = AuthUser(
        user_id=user1.user_id,
        username=user1.username,
        email=user1.email,
        is_admin=user1.is_admin,
        is_active=user1.is_active,
        auth_method=user1.auth_method
    )
    AuthContext.set_current_user(auth_user)
    yield
    AuthContext.clear()


@pytest.fixture
def multi_date_trades(db_session, user1, user2):
    """Create completed trades across multiple dates for both users."""
    # User 1 trades
    trades_user1 = [
        # Nov 20, 2025
        CompletedTrade(
            user_id=user1.user_id,
            symbol="AAPL",
            instrument_type="EQUITY",
            total_qty=100,
            entry_avg_price=Decimal("150.00"),
            exit_avg_price=Decimal("155.00"),
            gross_proceeds=Decimal("15500.00"),
            gross_cost=Decimal("15000.00"),
            net_pnl=Decimal("500.00"),
            opened_at=datetime(2025, 11, 20, 9, 30),
            closed_at=datetime(2025, 11, 20, 10, 30),
            trade_type="LONG",
            is_winning_trade=True
        ),
        # Nov 25, 2025
        CompletedTrade(
            user_id=user1.user_id,
            symbol="MSFT",
            instrument_type="EQUITY",
            total_qty=50,
            entry_avg_price=Decimal("380.00"),
            exit_avg_price=Decimal("375.00"),
            gross_proceeds=Decimal("18750.00"),
            gross_cost=Decimal("19000.00"),
            net_pnl=Decimal("-250.00"),
            opened_at=datetime(2025, 11, 25, 9, 30),
            closed_at=datetime(2025, 11, 25, 11, 0),
            trade_type="LONG",
            is_winning_trade=False
        ),
        # Nov 28, 2025
        CompletedTrade(
            user_id=user1.user_id,
            symbol="TSLA",
            instrument_type="EQUITY",
            total_qty=20,
            entry_avg_price=Decimal("250.00"),
            exit_avg_price=Decimal("260.00"),
            gross_proceeds=Decimal("5200.00"),
            gross_cost=Decimal("5000.00"),
            net_pnl=Decimal("200.00"),
            opened_at=datetime(2025, 11, 28, 10, 0),
            closed_at=datetime(2025, 11, 28, 14, 30),
            trade_type="LONG",
            is_winning_trade=True
        ),
        # Dec 1, 2025
        CompletedTrade(
            user_id=user1.user_id,
            symbol="GOOGL",
            instrument_type="EQUITY",
            total_qty=30,
            entry_avg_price=Decimal("140.00"),
            exit_avg_price=Decimal("145.00"),
            gross_proceeds=Decimal("4350.00"),
            gross_cost=Decimal("4200.00"),
            net_pnl=Decimal("150.00"),
            opened_at=datetime(2025, 12, 1, 9, 30),
            closed_at=datetime(2025, 12, 1, 15, 0),
            trade_type="LONG",
            is_winning_trade=True
        ),
    ]

    # User 2 trades (different dates, should NOT be visible to user1)
    trades_user2 = [
        CompletedTrade(
            user_id=user2.user_id,
            symbol="NVDA",
            instrument_type="EQUITY",
            total_qty=40,
            entry_avg_price=Decimal("500.00"),
            exit_avg_price=Decimal("520.00"),
            gross_proceeds=Decimal("20800.00"),
            gross_cost=Decimal("20000.00"),
            net_pnl=Decimal("800.00"),
            opened_at=datetime(2025, 11, 25, 9, 30),
            closed_at=datetime(2025, 11, 25, 12, 0),
            trade_type="LONG",
            is_winning_trade=True
        ),
        CompletedTrade(
            user_id=user2.user_id,
            symbol="AMD",
            instrument_type="EQUITY",
            total_qty=100,
            entry_avg_price=Decimal("110.00"),
            exit_avg_price=Decimal("105.00"),
            gross_proceeds=Decimal("10500.00"),
            gross_cost=Decimal("11000.00"),
            net_pnl=Decimal("-500.00"),
            opened_at=datetime(2025, 11, 28, 10, 0),
            closed_at=datetime(2025, 11, 28, 13, 0),
            trade_type="LONG",
            is_winning_trade=False
        ),
    ]

    for trade in trades_user1 + trades_user2:
        db_session.add(trade)
    db_session.commit()

    return {
        "user1_trades": trades_user1,
        "user2_trades": trades_user2
    }


class TestTradeFiltering:
    """Test trade filtering and user isolation in TradeCompletionEngine."""

    def test_get_trades_no_date_filter(self, db_session, multi_date_trades, setup_auth):
        """Test getting all trades without date filter."""
        engine = TradeCompletionEngine()
        result = engine.get_completed_trades_summary()

        # Should get all 4 user1 trades, NOT user2 trades
        assert result["total_trades"] == 4
        assert result["winning_trades"] == 3
        assert result["losing_trades"] == 1
        assert len(result["trades"]) == 4

        # Verify symbols are from user1 only
        symbols = {t["symbol"] for t in result["trades"]}
        assert symbols == {"AAPL", "MSFT", "TSLA", "GOOGL"}
        assert "NVDA" not in symbols  # user2's trade
        assert "AMD" not in symbols   # user2's trade

    def test_get_trades_with_start_date_only(self, db_session, multi_date_trades, setup_auth):
        """Test filtering with start_date only."""
        engine = TradeCompletionEngine()
        result = engine.get_completed_trades_summary(
            start_date=date(2025, 11, 25)
        )

        # Should get trades from Nov 25 onwards (MSFT, TSLA, GOOGL)
        assert result["total_trades"] == 3
        symbols = {t["symbol"] for t in result["trades"]}
        assert symbols == {"MSFT", "TSLA", "GOOGL"}
        assert "AAPL" not in symbols  # Nov 20, before start_date

    def test_get_trades_with_end_date_only(self, db_session, multi_date_trades, setup_auth):
        """Test filtering with end_date only."""
        engine = TradeCompletionEngine()
        result = engine.get_completed_trades_summary(
            end_date=date(2025, 11, 28)
        )

        # Should get trades up to and including Nov 28 (AAPL, MSFT, TSLA)
        assert result["total_trades"] == 3
        symbols = {t["symbol"] for t in result["trades"]}
        assert symbols == {"AAPL", "MSFT", "TSLA"}
        assert "GOOGL" not in symbols  # Dec 1, after end_date

    def test_get_trades_with_date_range(self, db_session, multi_date_trades, setup_auth):
        """Test filtering with both start_date and end_date."""
        engine = TradeCompletionEngine()
        result = engine.get_completed_trades_summary(
            start_date=date(2025, 11, 25),
            end_date=date(2025, 11, 28)
        )

        # Should get only trades in the range (MSFT, TSLA)
        assert result["total_trades"] == 2
        symbols = {t["symbol"] for t in result["trades"]}
        assert symbols == {"MSFT", "TSLA"}
        assert "AAPL" not in symbols   # Nov 20, before range
        assert "GOOGL" not in symbols  # Dec 1, after range

    def test_get_trades_single_day(self, db_session, multi_date_trades, setup_auth):
        """Test filtering for a single specific day."""
        engine = TradeCompletionEngine()
        result = engine.get_completed_trades_summary(
            start_date=date(2025, 11, 28),
            end_date=date(2025, 11, 28)
        )

        # Should get only Nov 28 trade (TSLA)
        assert result["total_trades"] == 1
        assert result["trades"][0]["symbol"] == "TSLA"

    def test_get_trades_no_results_in_range(self, db_session, multi_date_trades, setup_auth):
        """Test filtering with date range that has no trades."""
        engine = TradeCompletionEngine()
        result = engine.get_completed_trades_summary(
            start_date=date(2025, 11, 21),
            end_date=date(2025, 11, 24)
        )

        # Should return message indicating no trades found
        assert "message" in result
        assert "No completed trades found" in result["message"]

    def test_get_trades_with_symbol_filter(self, db_session, multi_date_trades, setup_auth):
        """Test symbol filtering combined with date filtering."""
        engine = TradeCompletionEngine()
        result = engine.get_completed_trades_summary(
            symbol="MSFT",
            start_date=date(2025, 11, 20),
            end_date=date(2025, 11, 30)
        )

        # Should get only MSFT trade
        assert result["total_trades"] == 1
        assert result["trades"][0]["symbol"] == "MSFT"

    def test_user_isolation_strict(self, db_session, multi_date_trades, user2):
        """Test that switching users shows only that user's trades."""
        # First check user1's trades (already authenticated in setup_auth)
        from trading_journal.auth import AuthUser
        auth_user1 = AuthUser(
            user_id=multi_date_trades["user1_trades"][0].user_id,
            username="user1",
            email="user1@example.com",
            is_admin=False,
            is_active=True,
            auth_method="api_key"
        )
        AuthContext.set_current_user(auth_user1)

        engine = TradeCompletionEngine()
        result_user1 = engine.get_completed_trades_summary()
        assert result_user1["total_trades"] == 4

        # Switch to user2
        auth_user2 = AuthUser(
            user_id=user2.user_id,
            username=user2.username,
            email=user2.email,
            is_admin=user2.is_admin,
            is_active=user2.is_active,
            auth_method=user2.auth_method
        )
        AuthContext.set_current_user(auth_user2)

        result_user2 = engine.get_completed_trades_summary()

        # User2 should see only their 2 trades
        assert result_user2["total_trades"] == 2
        symbols_user2 = {t["symbol"] for t in result_user2["trades"]}
        assert symbols_user2 == {"NVDA", "AMD"}

        # Cleanup
        AuthContext.clear()

    def test_end_date_includes_full_day(self, db_session, multi_date_trades, setup_auth):
        """Test that end_date includes trades through end of day (23:59:59)."""
        # Add a late-night trade on Nov 28
        user_id = multi_date_trades["user1_trades"][0].user_id
        late_trade = CompletedTrade(
            user_id=user_id,
            symbol="LATENIGHT",
            instrument_type="EQUITY",
            total_qty=10,
            entry_avg_price=Decimal("100.00"),
            exit_avg_price=Decimal("101.00"),
            gross_proceeds=Decimal("1010.00"),
            gross_cost=Decimal("1000.00"),
            net_pnl=Decimal("10.00"),
            opened_at=datetime(2025, 11, 28, 22, 0),
            closed_at=datetime(2025, 11, 28, 23, 45),  # Late at night
            trade_type="LONG",
            is_winning_trade=True
        )
        db_session.add(late_trade)
        db_session.commit()

        engine = TradeCompletionEngine()
        result = engine.get_completed_trades_summary(
            start_date=date(2025, 11, 28),
            end_date=date(2025, 11, 28)
        )

        # Should include both the regular TSLA trade and the late-night trade
        assert result["total_trades"] == 2
        symbols = {t["symbol"] for t in result["trades"]}
        assert "TSLA" in symbols
        assert "LATENIGHT" in symbols

    def test_pnl_calculations_with_filtering(self, db_session, multi_date_trades, setup_auth):
        """Test that P&L calculations are correct for filtered trades."""
        engine = TradeCompletionEngine()
        result = engine.get_completed_trades_summary(
            start_date=date(2025, 11, 25),
            end_date=date(2025, 11, 28)
        )

        # MSFT: -250, TSLA: +200
        assert result["total_trades"] == 2
        assert result["winning_trades"] == 1
        assert result["losing_trades"] == 1
        assert result["total_pnl"] == Decimal("-50.00")
        assert result["average_win"] == Decimal("200.00")
        assert result["average_loss"] == Decimal("-250.00")

    def test_no_authentication_raises_error(self, db_session, multi_date_trades):
        """Test that accessing trades without authentication raises error."""
        # Ensure no user is authenticated
        AuthContext.clear()

        engine = TradeCompletionEngine()

        with pytest.raises(RuntimeError, match="No authenticated user"):
            engine.get_completed_trades_summary()
