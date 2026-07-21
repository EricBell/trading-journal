"""Tests for multi-leg spread trade completion (issue #23 regression)."""

import pytest
from datetime import datetime, date
from decimal import Decimal

from trading_journal.models import Trade, CompletedTrade, User
from trading_journal.trade_completion import TradeCompletionEngine
from trading_journal.authorization import AuthContext


@pytest.fixture
def test_user(db_session):
    user = User(
        username="testuser",
        email="test@example.com",
        auth_method="api_key",
        is_active=True
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

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
    return TradeCompletionEngine()


def create_spread_leg(user_id, trade_id, side, qty, pos_effect, net_price, timestamp,
                       spread_order_tag, symbol="SPX", exp_date="2026-04-21",
                       strike=7110.0, option_type="PUT"):
    return Trade(
        user_id=user_id,
        trade_id=trade_id,
        unique_key=f"test_spread_{trade_id}",
        exec_timestamp=timestamp,
        event_type="fill",
        symbol=symbol,
        instrument_type="OPTION",
        side=side,
        qty=qty,
        pos_effect=pos_effect,
        net_price=net_price,
        raw_data=f"test spread leg {side}",
        exp_date=date.fromisoformat(exp_date),
        strike_price=Decimal(str(strike)),
        option_type=option_type,
        spread_order_tag=spread_order_tag,
        spread_type="VERTICAL",
        option_data={"exp_date": exp_date, "strike": strike, "right": option_type},
    )


def test_matched_quantity_spread_completes_correctly(db_session, test_user, trade_engine):
    """A single-leg 'spread' (matched open/close qty) still completes with correct P&L."""
    open_leg = create_spread_leg(
        test_user.user_id, 201, "BUY", 2, "TO OPEN", 1.70,
        datetime(2026, 7, 21, 15, 28, 42), spread_order_tag="file.csv:10",
    )
    close_leg = create_spread_leg(
        test_user.user_id, 202, "SELL", 2, "TO CLOSE", 1.58,
        datetime(2026, 7, 21, 15, 28, 50), spread_order_tag="file.csv:11",
    )
    db_session.add_all([open_leg, close_leg])
    db_session.commit()

    result = trade_engine.process_completed_trades()

    assert result["completed_trades"] == 1
    ct = db_session.query(CompletedTrade).first()
    assert float(ct.entry_avg_price) == pytest.approx(170.0)
    assert float(ct.exit_avg_price) == pytest.approx(158.0)
    assert float(ct.net_pnl) == pytest.approx(-24.0)


def test_partial_close_quantity_mismatch_is_skipped_not_fabricated(db_session, test_user, trade_engine):
    """Regression for issue #23: when a 'spread' open (qty 2) is only partially closed
    (qty 1), zip()-based pairing must NOT fabricate a completed trade with wrong P&L —
    it should skip the mismatched pair and leave the executions unlinked."""
    open_leg = create_spread_leg(
        test_user.user_id, 301, "BUY", 2, "TO OPEN", 1.82,
        datetime(2026, 7, 21, 15, 30, 30), spread_order_tag="file.csv:20",
    )
    close_leg = create_spread_leg(
        test_user.user_id, 302, "SELL", 1, "TO CLOSE", 1.80,
        datetime(2026, 7, 21, 15, 32, 44), spread_order_tag="file.csv:21",
    )
    db_session.add_all([open_leg, close_leg])
    db_session.commit()

    result = trade_engine.process_completed_trades()

    assert result["completed_trades"] == 0
    assert db_session.query(CompletedTrade).count() == 0

    db_session.refresh(open_leg)
    db_session.refresh(close_leg)
    assert open_leg.completed_trade_id is None
    assert close_leg.completed_trade_id is None
