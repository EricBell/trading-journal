"""Basic functionality tests."""

import pytest

def test_imports():
    """Test that all modules can be imported."""
    from trading_journal import __version__
    from trading_journal.config import db_config, logging_config, app_config
    from trading_journal.cli import main

    assert __version__ == "0.1.0"
    assert db_config is not None
    assert logging_config is not None
    assert app_config is not None
    assert main is not None


def test_database_config():
    """Test database configuration."""
    from trading_journal.config import db_config

    # Test that config is properly structured (not specific values)
    url = db_config.url
    assert "postgresql://" in url
    assert isinstance(db_config.host, str)
    assert len(db_config.host) > 0
    assert isinstance(db_config.port, int)
    assert db_config.port > 0
    assert db_config.port < 65536
    assert isinstance(db_config.database, str)
    assert len(db_config.database) > 0


def test_application_config():
    """Test application configuration."""
    from trading_journal.config import app_config

    assert app_config.pnl_method == "average_cost"
    assert app_config.timezone == "US/Eastern"
    assert app_config.batch_size == 1000
    assert app_config.max_retries == 3