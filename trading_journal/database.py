"""Database engine and session management."""

import logging
from contextlib import contextmanager
from typing import Generator, Optional

from sqlalchemy import create_engine, Engine, text
from sqlalchemy.orm import sessionmaker, Session

from .config import db_config, DatabaseConfig
from .models import Base

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages database connections and sessions."""

    def __init__(self, config: Optional[DatabaseConfig] = None) -> None:
        """
        Initialize database manager.

        Args:
            config: Optional DatabaseConfig instance. If not provided, uses global config.
        """
        if config is None:
            # Use global config for backward compatibility
            config = db_config._get_config()  # type: ignore

        self._config = config
        self._engine: Engine = create_engine(
            config.url,
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
        """Drop all database tables, including the Alembic version table."""
        logger.warning("Dropping all database tables...")
        Base.metadata.drop_all(self._engine)
        
        # Also drop the alembic_version table, which is not part of Base.metadata
        with self._engine.connect() as conn:
            conn.execute(text("DROP TABLE IF EXISTS alembic_version"))
            conn.commit()
            
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
_db_manager: Optional[DatabaseManager] = None


def get_db_manager(config: Optional[DatabaseConfig] = None, reset: bool = False) -> DatabaseManager:
    """
    Get the global DatabaseManager singleton.

    Args:
        config: Optional DatabaseConfig instance. Only used on first call or if reset=True.
        reset: Force reset of singleton (for testing or config changes).

    Returns:
        DatabaseManager instance
    """
    global _db_manager

    if reset or _db_manager is None:
        _db_manager = DatabaseManager(config=config)

    return _db_manager


# Backward compatibility: maintain db_manager at module level
# This lazy-loads on first access
class _DBManagerProxy:
    """Lazy-loading proxy for backward compatibility with db_manager."""

    def __getattr__(self, name: str):
        """Proxy all attribute access to the global DatabaseManager."""
        return getattr(get_db_manager(), name)


db_manager = _DBManagerProxy()  # type: ignore