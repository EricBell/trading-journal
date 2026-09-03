"""Tests for /trades date filtering (issue #41): single-date and date-range support
in `_build_trades_query`, reusing the shared `date_range.parse_date_range` grammar.
"""

import pytest
from datetime import datetime
from decimal import Decimal

from trading_journal.models import CompletedTrade, User
from trading_journal.authorization import AuthContext
from trading_journal.web.routes.trades import _build_trades_query


@pytest.fixture
def test_user(db_session):
    user = User(
        username="trades_filter_user",
        email="trades_filter@example.com",
        auth_method="api_key",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    from trading_journal.auth import AuthUser
    AuthContext.set_current_user(AuthUser(
        user_id=user.user_id,
        username=user.username,
        email=user.email,
        is_admin=user.is_admin,
        is_active=user.is_active,
        auth_method=user.auth_method,
    ))

    yield user

    AuthContext.clear()


@pytest.fixture
def dated_trades(db_session, test_user):
    """One completed trade per day, 2025-01-10 through 2025-01-14."""
    symbols = ["AAPL", "TSLA", "GOOGL", "MSFT", "NVDA"]
    trades = []
    for i, symbol in enumerate(symbols):
        day = 10 + i
        trades.append(CompletedTrade(
            user_id=test_user.user_id,
            symbol=symbol,
            instrument_type="EQUITY",
            total_qty=10,
            entry_avg_price=Decimal('100.00'),
            exit_avg_price=Decimal('101.00'),
            gross_cost=Decimal('1000.00'),
            gross_proceeds=Decimal('1010.00'),
            net_pnl=Decimal('10.00'),
            opened_at=datetime(2025, 1, day, 10, 0, 0),
            closed_at=datetime(2025, 1, day, 15, 0, 0),
            is_winning_trade=True,
            trade_type="LONG",
        ))
    db_session.add_all(trades)
    db_session.commit()
    return trades


def _symbols(db_session, test_user, range_filter):
    query = _build_trades_query(
        db_session, test_user.user_id, None, range_filter, None, 'closed', 'desc'
    )
    return {t.symbol for t in query.all()}


def test_single_date_filter(db_session, test_user, dated_trades):
    assert _symbols(db_session, test_user, '2025-01-12') == {'GOOGL'}


def test_date_range_filter(db_session, test_user, dated_trades):
    assert _symbols(db_session, test_user, '2025-01-11/2025-01-13') == {'TSLA', 'GOOGL', 'MSFT'}


def test_date_range_open_start(db_session, test_user, dated_trades):
    assert _symbols(db_session, test_user, '/2025-01-11') == {'AAPL', 'TSLA'}


def test_date_range_backwards_yields_no_rows(db_session, test_user, dated_trades):
    assert _symbols(db_session, test_user, '2025-01-13/2025-01-11') == set()


def test_relative_nd_filter_unchanged(db_session, test_user, dated_trades):
    # Regression check: existing "Nd" relative filtering still resolves through
    # the shared parser the same way it did with the old inline check.
    from datetime import date, timedelta
    from trading_journal.date_range import parse_date_range
    start, end = parse_date_range('2d')
    assert (start, end) == (date.today() - timedelta(days=1), date.today())


def test_invalid_range_filter_is_ignored(db_session, test_user, dated_trades):
    # Malformed range strings fail soft to "no date filter" rather than 500ing.
    assert _symbols(db_session, test_user, 'not-a-date') == {
        'AAPL', 'TSLA', 'GOOGL', 'MSFT', 'NVDA'
    }
