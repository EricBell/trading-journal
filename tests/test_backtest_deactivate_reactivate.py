"""Tests for backtest strategy-type/underlying soft-deactivate + reactivate (issue #45).

Previously, deactivating a BacktestStrategyType/BacktestUnderlying was hard-blocked
whenever any BacktestRun referenced it, and there was no reactivate route at all. This
also covers the two dropdown-population bugs that a real soft-deactivate would
otherwise expose: the /backtest list showing "-" instead of the real name for a run
referencing a deactivated type, and the /backtest/<id> edit form silently dropping a
run's current (now-inactive) type from its <select>.
"""

import pytest
from decimal import Decimal

from trading_journal.models import BacktestRun, BacktestStrategyType, BacktestUnderlying, User
from trading_journal.web import create_app


@pytest.fixture
def test_user(db_session):
    user = User(
        username="backtest_deactivate_user",
        email="backtest_deactivate@example.com",
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


def test_deactivate_succeeds_while_referenced_by_a_run(db_session, test_user, client):
    strategy = BacktestStrategyType(user_id=test_user.user_id, strategy_name="Iron Condor")
    db_session.add(strategy)
    db_session.commit()
    db_session.refresh(strategy)

    run = BacktestRun(user_id=test_user.user_id, strategy_type_id=strategy.strategy_type_id)
    db_session.add(run)
    db_session.commit()

    _logged_in(client, test_user.user_id)
    resp = client.post(
        f"/settings/backtest-strategy-types/{strategy.strategy_type_id}/deactivate",
        follow_redirects=True,
    )
    assert resp.status_code == 200

    db_session.refresh(strategy)
    assert strategy.is_active is False


def test_list_page_still_shows_name_for_deactivated_referenced_strategy(db_session, test_user, client):
    strategy = BacktestStrategyType(user_id=test_user.user_id, strategy_name="Butterfly", is_active=False)
    db_session.add(strategy)
    db_session.commit()
    db_session.refresh(strategy)

    run = BacktestRun(
        user_id=test_user.user_id,
        strategy_type_id=strategy.strategy_type_id,
        total_pnl=Decimal("100.00"),
    )
    db_session.add(run)
    db_session.commit()

    _logged_in(client, test_user.user_id)
    resp = client.get("/backtest")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Butterfly" in body
    # The old bug rendered "&mdash;" (the "-" placeholder) in the strategy column
    # instead of the real name.


def test_edit_form_preselects_deactivated_strategy_for_its_run(db_session, test_user, client):
    strategy = BacktestStrategyType(user_id=test_user.user_id, strategy_name="Vertical Put Credit", is_active=False)
    db_session.add(strategy)
    db_session.commit()
    db_session.refresh(strategy)

    run = BacktestRun(user_id=test_user.user_id, strategy_type_id=strategy.strategy_type_id)
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)

    _logged_in(client, test_user.user_id)
    resp = client.get(f"/backtest/{run.run_id}")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)

    assert "Vertical Put Credit" in body
    assert "(inactive)" in body
    # The option for this run's own strategy type must be selected, not silently
    # dropped from the <select> (which would default-submit a different value on save).
    marker = f'value="{strategy.strategy_type_id}"'
    option_start = body.index(marker)
    option_end = body.index("</option>", option_start)
    assert "selected" in body[option_start:option_end]


def test_reactivate_restores_strategy_to_new_run_dropdown(db_session, test_user, client):
    strategy = BacktestStrategyType(user_id=test_user.user_id, strategy_name="Vertical Put Debit", is_active=False)
    db_session.add(strategy)
    db_session.commit()
    db_session.refresh(strategy)

    _logged_in(client, test_user.user_id)

    resp = client.get("/backtest/new")
    assert "Vertical Put Debit" not in resp.get_data(as_text=True)

    resp = client.post(
        f"/settings/backtest-strategy-types/{strategy.strategy_type_id}/reactivate",
        follow_redirects=True,
    )
    assert resp.status_code == 200

    db_session.refresh(strategy)
    assert strategy.is_active is True

    resp = client.get("/backtest/new")
    assert "Vertical Put Debit" in resp.get_data(as_text=True)


def test_underlying_deactivate_and_reactivate_mirror_strategy_behavior(db_session, test_user, client):
    underlying = BacktestUnderlying(user_id=test_user.user_id, underlying_name="NDX")
    db_session.add(underlying)
    db_session.commit()
    db_session.refresh(underlying)

    run = BacktestRun(user_id=test_user.user_id, underlying_id=underlying.underlying_id)
    db_session.add(run)
    db_session.commit()

    _logged_in(client, test_user.user_id)

    resp = client.post(
        f"/settings/backtest-underlyings/{underlying.underlying_id}/deactivate",
        follow_redirects=True,
    )
    assert resp.status_code == 200
    db_session.refresh(underlying)
    assert underlying.is_active is False

    resp = client.get("/backtest")
    assert "NDX" in resp.get_data(as_text=True)

    resp = client.post(
        f"/settings/backtest-underlyings/{underlying.underlying_id}/reactivate",
        follow_redirects=True,
    )
    assert resp.status_code == 200
    db_session.refresh(underlying)
    assert underlying.is_active is True
