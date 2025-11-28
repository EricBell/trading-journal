"""Pytest configuration and fixtures."""

import pytest
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from trading_journal.models import Base


@pytest.fixture(scope="session")
def db_engine():
    """Create a test database engine."""
    # Use test database URL from environment or default
    db_url = os.getenv(
        "TEST_DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/trading_journal_test"
    )

    engine = create_engine(db_url)

    # Create all tables
    Base.metadata.create_all(engine)

    yield engine

    # Drop all tables after tests
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture(scope="function")
def db_session(db_engine):
    """Create a new database session for a test."""
    SessionLocal = sessionmaker(bind=db_engine)
    session = SessionLocal()

    yield session

    # Rollback any uncommitted changes and close session
    session.rollback()
    session.close()

    # Clean up all tables for next test
    for table in reversed(Base.metadata.sorted_tables):
        session.execute(table.delete())
        session.commit()
