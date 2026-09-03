"""Tests for the /positions/<id> fill-history detail view (issue #43): surfaces
partial-close fills that reduce a position without fully closing it, which
have no completed_trade row and were previously invisible anywhere in the UI.
"""

import pytest
from datetime import datetime
from decimal import Decimal

from trading_journal.models import Position, Trade, User
from trading_journal.web import create_app


@pytest.fixture
def test_user(db_session):
    user = User(
        username="positions_detail_user",
        email="positions_detail@example.com",
        auth_method="api_key",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def _logged_in(client, user_id):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    return client


def test_partial_close_fills_appear_in_position_detail(db_session, test_user, client):
    position = Position(
        user_id=test_user.user_id,
        symbol="CNH",
        instrument_type="EQUITY",
        current_qty=250,
        avg_cost_basis=Decimal("13.81822857"),
        total_cost=Decimal("3454.55714286"),
        opened_at=datetime(2026, 9, 3, 15, 47, 2),
        closed_at=None,
        realized_pnl=Decimal("23.43714286"),
    )
    db_session.add(position)
    db_session.commit()
    db_session.refresh(position)

    open_trade = Trade(
        user_id=test_user.user_id,
        unique_key="open-1",
        exec_timestamp=datetime(2026, 9, 3, 15, 47, 2),
        event_type="fill",
        symbol="CNH",
        instrument_type="EQUITY",
        side="BUY",
        qty=500,
        pos_effect="TO OPEN",
        net_price=Decimal("13.8121"),
        raw_data="test",
    )
    close_trade = Trade(
        user_id=test_user.user_id,
        unique_key="close-1",
        exec_timestamp=datetime(2026, 9, 3, 15, 50, 48),
        event_type="fill",
        symbol="CNH",
        instrument_type="EQUITY",
        side="SELL",
        qty=200,
        pos_effect="TO CLOSE",
        net_price=Decimal("13.831"),
        raw_data="test",
        realized_pnl=Decimal("3.78"),
        completed_trade_id=None,
    )
    db_session.add_all([open_trade, close_trade])
    db_session.commit()

    _logged_in(client, test_user.user_id)
    resp = client.get(f"/positions/{position.position_id}")

    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "$3.78" in html
    assert "still open" in html
    assert "300" in html  # running qty after the partial close


def test_missing_position_is_404(db_session, test_user, client):
    _logged_in(client, test_user.user_id)
    resp = client.get("/positions/999999999")
    assert resp.status_code == 404


def test_position_owned_by_other_user_is_404(db_session, test_user, client):
    other = User(
        username="other_positions_user",
        email="other_positions@example.com",
        auth_method="api_key",
        is_active=True,
    )
    db_session.add(other)
    db_session.commit()
    db_session.refresh(other)

    position = Position(
        user_id=other.user_id,
        symbol="AAPL",
        instrument_type="EQUITY",
        current_qty=10,
        avg_cost_basis=Decimal("100.00"),
        total_cost=Decimal("1000.00"),
        opened_at=datetime(2026, 9, 3, 10, 0, 0),
        realized_pnl=Decimal("0"),
    )
    db_session.add(position)
    db_session.commit()
    db_session.refresh(position)

    _logged_in(client, test_user.user_id)
    resp = client.get(f"/positions/{position.position_id}")
    assert resp.status_code == 404
