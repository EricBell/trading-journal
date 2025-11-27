"""Test database models."""

import pytest
from sqlalchemy import create_engine, JSON
from sqlalchemy.orm import sessionmaker

from trading_journal.models import Base, Trade, CompletedTrade, Position


@pytest.fixture
def engine():
    """Create in-memory SQLite database for testing."""
    # For testing, we'll use SQLite but need to handle JSONB differently
    return create_engine("sqlite:///:memory:")


@pytest.fixture
def session(engine):
    """Create database session for testing."""
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_trade_model_creation(session):
    """Test creating a trade record."""
    trade = Trade(
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

    session.add(trade)
    session.commit()

    assert trade.trade_id is not None
    assert trade.symbol == "AAPL"
    assert trade.instrument_type == "EQUITY"


def test_completed_trade_model_creation(session):
    """Test creating a completed trade record."""
    completed_trade = CompletedTrade(
        symbol="AAPL",
        instrument_type="EQUITY",
        # Skip option_details for SQLite compatibility
        total_qty=100,
        entry_avg_price=150.00,
        exit_avg_price=155.00,
        net_pnl=500.00,
        setup_pattern="5min ORB",
        trade_notes="Good entry timing",
        is_winning_trade=True
    )

    session.add(completed_trade)
    session.commit()

    assert completed_trade.completed_trade_id is not None
    assert completed_trade.setup_pattern == "5min ORB"
    assert completed_trade.is_winning_trade is True


def test_position_model_creation(session):
    """Test creating a position record."""
    position = Position(
        symbol="AAPL",
        instrument_type="EQUITY",
        current_qty=100,
        avg_cost_basis=150.25,
        total_cost=15025.00
    )

    session.add(position)
    session.commit()

    assert position.position_id is not None
    assert position.symbol == "AAPL"
    assert position.current_qty == 100


def test_trade_completed_trade_relationship(session):
    """Test relationship between trades and completed trades."""
    # Create completed trade
    completed_trade = CompletedTrade(
        symbol="AAPL",
        instrument_type="EQUITY",
        total_qty=100,
        net_pnl=500.00
    )
    session.add(completed_trade)
    session.flush()  # Get the ID without committing

    # Create executions linked to completed trade
    trade1 = Trade(
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
        unique_key="exec_2",
        event_type="fill",
        symbol="AAPL",
        instrument_type="EQUITY",
        side="SELL",
        qty=-100,
        raw_data="sell execution",
        completed_trade_id=completed_trade.completed_trade_id
    )

    session.add_all([trade1, trade2])
    session.commit()

    # Test relationship
    assert len(completed_trade.executions) == 2
    assert trade1.completed_trade == completed_trade
    assert trade2.completed_trade == completed_trade