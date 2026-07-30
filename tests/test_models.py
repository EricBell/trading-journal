"""Test database models."""

import pytest
from trading_journal.models import Trade, CompletedTrade, NotepadEntry, Position, User


def test_trade_model_creation(db_session):
    """Test creating a trade record."""
    # Create test user first
    user = User(
        username="testuser",
        email="test@example.com",
        auth_method="api_key",
        is_active=True
    )
    db_session.add(user)
    db_session.commit()

    trade = Trade(
        user_id=user.user_id,
        unique_key="test_trade_1",
        event_type="fill",
        symbol="AAPL",
        instrument_type="EQUITY",
        side="BUY",
        qty=100,
        pos_effect="TO OPEN",
        net_price=150.25,
        raw_data="test raw data"
    )

    db_session.add(trade)
    db_session.commit()

    assert trade.trade_id is not None
    assert trade.symbol == "AAPL"
    assert trade.instrument_type == "EQUITY"


def test_completed_trade_model_creation(db_session):
    """Test creating a completed trade record."""
    # Create test user first
    user = User(
        username="testuser2",
        email="test2@example.com",
        auth_method="api_key",
        is_active=True
    )
    db_session.add(user)
    db_session.commit()

    from trading_journal.models import SetupPattern
    pattern = SetupPattern(
        user_id=user.user_id,
        pattern_name="5min ORB",
        is_active=True,
    )
    db_session.add(pattern)
    db_session.flush()

    completed_trade = CompletedTrade(
        user_id=user.user_id,
        symbol="AAPL",
        instrument_type="EQUITY",
        total_qty=100,
        entry_avg_price=150.00,
        exit_avg_price=155.00,
        net_pnl=500.00,
        setup_pattern_id=pattern.pattern_id,
        trade_notes="Good entry timing",
        is_winning_trade=True
    )

    db_session.add(completed_trade)
    db_session.commit()

    assert completed_trade.completed_trade_id is not None
    assert completed_trade.setup_pattern_rel.pattern_name == "5min ORB"
    assert completed_trade.is_winning_trade is True


def test_position_model_creation(db_session):
    """Test creating a position record."""
    # Create test user first
    user = User(
        username="testuser3",
        email="test3@example.com",
        auth_method="api_key",
        is_active=True
    )
    db_session.add(user)
    db_session.commit()

    position = Position(
        user_id=user.user_id,
        symbol="AAPL",
        instrument_type="EQUITY",
        current_qty=100,
        avg_cost_basis=150.25,
        total_cost=15025.00
    )

    db_session.add(position)
    db_session.commit()

    assert position.position_id is not None
    assert position.symbol == "AAPL"
    assert position.current_qty == 100


def test_trade_completed_trade_relationship(db_session):
    """Test relationship between trades and completed trades."""
    # Create test user first
    user = User(
        username="testuser4",
        email="test4@example.com",
        auth_method="api_key",
        is_active=True
    )
    db_session.add(user)
    db_session.commit()

    # Create completed trade
    completed_trade = CompletedTrade(
        user_id=user.user_id,
        symbol="AAPL",
        instrument_type="EQUITY",
        total_qty=100,
        net_pnl=500.00
    )
    db_session.add(completed_trade)
    db_session.flush()  # Get the ID without committing

    # Create executions linked to completed trade
    trade1 = Trade(
        user_id=user.user_id,
        unique_key="exec_1",
        event_type="fill",
        symbol="AAPL",
        instrument_type="EQUITY",
        side="BUY",
        qty=100,
        raw_data="buy execution",
        completed_trade_id=completed_trade.completed_trade_id
    )

    trade2 = Trade(
        user_id=user.user_id,
        unique_key="exec_2",
        event_type="fill",
        symbol="AAPL",
        instrument_type="EQUITY",
        side="SELL",
        qty=-100,
        raw_data="sell execution",
        completed_trade_id=completed_trade.completed_trade_id
    )

    db_session.add_all([trade1, trade2])
    db_session.commit()

    # Test relationship
    assert len(completed_trade.executions) == 2
    assert trade1.completed_trade == completed_trade
    assert trade2.completed_trade == completed_trade


def test_notepad_entry_model_creation(db_session):
    """Test creating an unmatched notepad entry."""
    user = User(
        username="testuser5",
        email="test5@example.com",
        auth_method="api_key",
        is_active=True
    )
    db_session.add(user)
    db_session.commit()

    entry = NotepadEntry(
        user_id=user.user_id,
        symbol="AAPL",
        body="Watching for a breakout above 150.",
    )
    db_session.add(entry)
    db_session.commit()

    assert entry.notepad_id is not None
    assert entry.symbol == "AAPL"
    assert entry.matched_trade_id is None
    assert entry.matched_at is None


def test_notepad_entry_natural_key_fallback_after_fk_nulled(db_session):
    """A matched entry should still be findable by (matched_symbol, matched_opened_at)
    even if matched_trade_id has been nulled out by a completed_trades rebuild."""
    from datetime import datetime, timezone

    user = User(
        username="testuser6",
        email="test6@example.com",
        auth_method="api_key",
        is_active=True
    )
    db_session.add(user)
    db_session.commit()

    opened_at = datetime(2026, 7, 1, 9, 30, tzinfo=timezone.utc)
    completed_trade = CompletedTrade(
        user_id=user.user_id,
        symbol="AAPL",
        instrument_type="EQUITY",
        total_qty=100,
        net_pnl=500.00,
        opened_at=opened_at,
    )
    db_session.add(completed_trade)
    db_session.flush()

    entry = NotepadEntry(
        user_id=user.user_id,
        symbol="AAPL",
        body="Entry thesis.",
        matched_trade_id=completed_trade.completed_trade_id,
        matched_symbol="AAPL",
        matched_opened_at=opened_at,
        matched_at=datetime.now(timezone.utc),
    )
    db_session.add(entry)
    db_session.commit()

    # Simulate a completed_trades rebuild nulling the FK (ON DELETE SET NULL)
    db_session.delete(completed_trade)
    db_session.commit()
    db_session.refresh(entry)

    assert entry.matched_trade_id is None
    assert entry.matched_symbol == "AAPL"
    assert entry.matched_opened_at == opened_at