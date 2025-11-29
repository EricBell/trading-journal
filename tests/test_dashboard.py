"""Tests for dashboard metrics and analytics."""

import pytest
from datetime import datetime, date
from decimal import Decimal

from trading_journal.models import CompletedTrade, Position, User
from trading_journal.dashboard import DashboardEngine
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


@pytest.fixture
def sample_trades(db_session, test_user):
    """Create sample completed trades for testing."""
    trades = [
        CompletedTrade(
            user_id=test_user.user_id,
            symbol="AAPL",
            instrument_type="EQUITY",
            total_qty=100,
            entry_avg_price=Decimal('150.00'),
            exit_avg_price=Decimal('155.00'),
            gross_cost=Decimal('15000.00'),
            gross_proceeds=Decimal('15500.00'),
            net_pnl=Decimal('500.00'),
            opened_at=datetime(2025, 1, 10, 10, 0, 0),
            closed_at=datetime(2025, 1, 10, 15, 0, 0),
            is_winning_trade=True,
            trade_type="LONG",
            setup_pattern="MACD Scalp"
        ),
        CompletedTrade(
            user_id=test_user.user_id,
            symbol="TSLA",
            instrument_type="EQUITY",
            total_qty=50,
            entry_avg_price=Decimal('200.00'),
            exit_avg_price=Decimal('195.00'),
            gross_cost=Decimal('10000.00'),
            gross_proceeds=Decimal('9750.00'),
            net_pnl=Decimal('-250.00'),
            opened_at=datetime(2025, 1, 11, 10, 0, 0),
            closed_at=datetime(2025, 1, 11, 15, 0, 0),
            is_winning_trade=False,
            trade_type="LONG",
            setup_pattern="MACD Scalp"
        ),
        CompletedTrade(
            user_id=test_user.user_id,
            symbol="GOOGL",
            instrument_type="EQUITY",
            total_qty=30,
            entry_avg_price=Decimal('100.00'),
            exit_avg_price=Decimal('110.00'),
            gross_cost=Decimal('3000.00'),
            gross_proceeds=Decimal('3300.00'),
            net_pnl=Decimal('300.00'),
            opened_at=datetime(2025, 1, 12, 10, 0, 0),
            closed_at=datetime(2025, 1, 12, 15, 0, 0),
            is_winning_trade=True,
            trade_type="LONG",
            setup_pattern="5min ORB"
        ),
        CompletedTrade(
            user_id=test_user.user_id,
            symbol="MSFT",
            instrument_type="EQUITY",
            total_qty=40,
            entry_avg_price=Decimal('250.00'),
            exit_avg_price=Decimal('248.00'),
            gross_cost=Decimal('10000.00'),
            gross_proceeds=Decimal('9920.00'),
            net_pnl=Decimal('-80.00'),
            opened_at=datetime(2025, 1, 13, 10, 0, 0),
            closed_at=datetime(2025, 1, 13, 15, 0, 0),
            is_winning_trade=False,
            trade_type="LONG",
            setup_pattern="5min ORB"
        ),
        CompletedTrade(
            user_id=test_user.user_id,
            symbol="NVDA",
            instrument_type="EQUITY",
            total_qty=25,
            entry_avg_price=Decimal('400.00'),
            exit_avg_price=Decimal('420.00'),
            gross_cost=Decimal('10000.00'),
            gross_proceeds=Decimal('10500.00'),
            net_pnl=Decimal('500.00'),
            opened_at=datetime(2025, 1, 14, 10, 0, 0),
            closed_at=datetime(2025, 1, 14, 15, 0, 0),
            is_winning_trade=True,
            trade_type="LONG",
            setup_pattern="MACD Scalp"
        )
    ]

    for trade in trades:
        db_session.add(trade)

    db_session.commit()

    return trades


def test_dashboard_core_metrics(sample_trades):
    """Test core dashboard metrics calculation."""
    engine = DashboardEngine()
    dashboard = engine.generate_dashboard()

    assert "core_metrics" in dashboard
    core = dashboard["core_metrics"]

    # Basic counts
    assert core["total_trades"] == 5
    assert core["winning_trades"] == 3
    assert core["losing_trades"] == 2

    # Win rate
    assert core["win_rate_pct"] == 60.0

    # P&L
    total_pnl = 500 + (-250) + 300 + (-80) + 500
    assert core["total_pnl"] == float(total_pnl)
    assert core["total_pnl"] == 970.0

    # Averages
    assert core["average_win"] == pytest.approx((500 + 300 + 500) / 3, rel=0.01)
    assert core["average_loss"] == pytest.approx((-250 + -80) / 2, rel=0.01)

    # Largest win/loss
    assert core["largest_win"] == 500.0
    assert core["largest_loss"] == -250.0


def test_dashboard_pattern_analysis(sample_trades):
    """Test pattern analysis metrics."""
    engine = DashboardEngine()
    dashboard = engine.generate_dashboard()

    assert "pattern_analysis" in dashboard
    patterns = dashboard["pattern_analysis"]

    # Should have 2 patterns: MACD Scalp and 5min ORB
    assert len(patterns["by_pattern"]) == 2

    # MACD Scalp: 3 trades (500, -250, 500) = 750 P&L
    macd_pattern = next((p for p in patterns["by_pattern"] if p["pattern"] == "MACD Scalp"), None)
    assert macd_pattern is not None
    assert macd_pattern["total_trades"] == 3
    assert macd_pattern["total_pnl"] == 750.0
    assert macd_pattern["winning_trades"] == 2
    assert macd_pattern["losing_trades"] == 1

    # 5min ORB: 2 trades (300, -80) = 220 P&L
    orb_pattern = next((p for p in patterns["by_pattern"] if p["pattern"] == "5min ORB"), None)
    assert orb_pattern is not None
    assert orb_pattern["total_trades"] == 2
    assert orb_pattern["total_pnl"] == 220.0

    # Top pattern should be MACD Scalp (highest P&L)
    assert patterns["top_pattern"]["pattern"] == "MACD Scalp"


def test_dashboard_equity_curve(sample_trades):
    """Test equity curve calculation."""
    engine = DashboardEngine()
    dashboard = engine.generate_dashboard()

    assert "equity_curve" in dashboard
    curve = dashboard["equity_curve"]

    # Should have 5 points
    assert len(curve) == 5

    # Check cumulative P&L progression
    assert curve[0]["cumulative_pnl"] == 500.0  # First trade
    assert curve[1]["cumulative_pnl"] == 250.0  # 500 - 250
    assert curve[2]["cumulative_pnl"] == 550.0  # 250 + 300
    assert curve[3]["cumulative_pnl"] == 470.0  # 550 - 80
    assert curve[4]["cumulative_pnl"] == 970.0  # 470 + 500


def test_dashboard_max_drawdown(sample_trades):
    """Test max drawdown calculation."""
    engine = DashboardEngine()
    dashboard = engine.generate_dashboard()

    assert "max_drawdown" in dashboard
    dd = dashboard["max_drawdown"]

    # The equity curve goes: 500 -> 250 -> 550 -> 470 -> 970
    # Peak at 550, trough at 470, drawdown = 80
    assert dd["max_drawdown"] == pytest.approx(80.0, rel=0.01)
    assert dd["max_drawdown_pct"] == pytest.approx((80/550)*100, rel=0.01)
    assert dd["peak_value"] == 550.0
    assert dd["trough_value"] == 470.0


def test_dashboard_date_range_filter(sample_trades, test_user):
    """Test date range filtering."""
    engine = DashboardEngine()

    # Filter for Jan 10-11 (first 2 trades)
    dashboard = engine.generate_dashboard(
        start_date=date(2025, 1, 10),
        end_date=date(2025, 1, 11)
    )

    core = dashboard["core_metrics"]
    assert core["total_trades"] == 2
    assert core["total_pnl"] == 250.0  # 500 - 250


def test_dashboard_symbol_filter(sample_trades, test_user):
    """Test symbol filtering."""
    engine = DashboardEngine()

    # Filter for AAPL only
    dashboard = engine.generate_dashboard(symbol="AAPL")

    core = dashboard["core_metrics"]
    assert core["total_trades"] == 1
    assert core["total_pnl"] == 500.0


def test_parse_date_range():
    """Test date range parsing."""
    engine = DashboardEngine()

    # Valid range
    start, end = engine.parse_date_range("2025-01-01,2025-01-31")
    assert start == date(2025, 1, 1)
    assert end == date(2025, 1, 31)

    # None input
    start, end = engine.parse_date_range(None)
    assert start is None
    assert end is None

    # Invalid format
    with pytest.raises(ValueError):
        engine.parse_date_range("2025-01-01")


def test_dashboard_streaks(sample_trades):
    """Test win/loss streak calculation."""
    engine = DashboardEngine()
    dashboard = engine.generate_dashboard()

    core = dashboard["core_metrics"]

    # Trades: WIN, LOSS, WIN, LOSS, WIN
    # Max win streak: 1 (never 2 consecutive wins)
    # Max loss streak: 1 (never 2 consecutive losses)
    assert core["max_win_streak"] == 1
    assert core["max_loss_streak"] == 1


def test_dashboard_no_trades(test_user):
    """Test dashboard with no trades."""
    engine = DashboardEngine()
    dashboard = engine.generate_dashboard()

    assert "message" in dashboard
    assert "No completed trades" in dashboard["message"]


def test_dashboard_profit_factor(sample_trades):
    """Test profit factor calculation."""
    engine = DashboardEngine()
    dashboard = engine.generate_dashboard()

    core = dashboard["core_metrics"]

    # Winning P&L: 500 + 300 + 500 = 1300
    # Losing P&L: -250 + -80 = -330
    # Profit factor: 1300 / 330 = 3.94
    expected_profit_factor = 1300 / 330
    assert core["profit_factor"] == pytest.approx(expected_profit_factor, rel=0.01)
