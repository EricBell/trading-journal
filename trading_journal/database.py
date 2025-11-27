"""Database engine and session management."""

import logging
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, Engine, text
from sqlalchemy.orm import sessionmaker, Session

from .config import db_config
from .models import Base

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages database connections and sessions."""

    def __init__(self) -> None:
        self._engine: Engine = create_engine(
            db_config.url,
            echo=False,  # Set to True for SQL debugging
            pool_pre_ping=True,
            pool_recycle=3600,
        )
        self._session_factory = sessionmaker(bind=self._engine)

    @property
    def engine(self) -> Engine:
        """Get database engine."""
        return self._engine

    def create_tables(self) -> None:
        """Create all database tables."""
        logger.info("Creating database tables...")
        Base.metadata.create_all(self._engine)
        logger.info("Database tables created successfully")

    def drop_tables(self) -> None:
        """Drop all database tables."""
        logger.warning("Dropping all database tables...")
        Base.metadata.drop_all(self._engine)
        logger.warning("Database tables dropped")

    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """Context manager for database sessions."""
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def test_connection(self) -> bool:
        """Test database connection."""
        try:
            with self._engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("Database connection successful")
            return True
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            return False


# Global database manager instance
db_manager = DatabaseManager()