"""Pytest configuration and fixtures."""

import pytest
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from trading_journal.models import Base


@pytest.fixture(scope="session")
def db_engine():
    """Create a test database engine."""
    # Build test database URL from production config with test database name
    # Or use TEST_DATABASE_URL if explicitly provided
    test_db_url = os.getenv("TEST_DATABASE_URL")

    if not test_db_url:
        from trading_journal.config import db_config
        # Use production DB server but with _test database suffix
        host = db_config.host
        port = db_config.port
        user = db_config.user
        password = db_config.password if db_config.password else "postgres"
        test_db_name = f"{db_config.database}_test"

        test_db_url = f"postgresql://{user}:{password}@{host}:{port}/{test_db_name}"

    engine = create_engine(test_db_url)

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
