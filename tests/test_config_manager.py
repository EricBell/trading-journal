"""Unit tests for ConfigManager."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
import tomli_w

from trading_journal.config_manager import (
    ConfigManager,
    DatabaseConfig,
    LoggingConfig,
    ApplicationConfig,
    get_config_manager,
)


class TestDatabaseConfig:
    """Test DatabaseConfig validation and functionality."""

    def test_valid_config(self):
        """Test valid database configuration."""
        config = DatabaseConfig(
            host="localhost",
            port=5432,
            database="test_db",
            user="test_user",
            password="test_pass",
        )
        assert config.host == "localhost"
        assert config.port == 5432
        assert config.database == "test_db"
        assert config.user == "test_user"
        assert config.password == "test_pass"

    def test_url_with_password(self):
        """Test database URL generation with password."""
        config = DatabaseConfig(
            host="localhost",
            port=5432,
            database="test_db",
            user="test_user",
            password="secret",
        )
        assert config.url == "postgresql://test_user:secret@localhost:5432/test_db"

    def test_url_without_password(self):
        """Test database URL generation without password."""
        config = DatabaseConfig(
            host="localhost",
            port=5432,
            database="test_db",
            user="test_user",
        )
        assert config.url == "postgresql://test_user@localhost:5432/test_db"

    def test_port_validation_invalid_type(self):
        """Test port validation rejects non-integer types."""
        with pytest.raises(ValueError, match="must be an integer"):
            DatabaseConfig(
                host="localhost",
                port="invalid",  # type: ignore
                database="test_db",
                user="test_user",
            )

    def test_port_validation_out_of_range(self):
        """Test port validation rejects out-of-range ports."""
        with pytest.raises(ValueError, match="must be between 1-65535"):
            DatabaseConfig(
                host="localhost",
                port=99999,
                database="test_db",
                user="test_user",
            )

    def test_port_string_conversion(self):
        """Test port converts from string to int."""
        config = DatabaseConfig(
            host="localhost",
            port="5432",  # type: ignore
            database="test_db",
            user="test_user",
        )
        assert config.port == 5432
        assert isinstance(config.port, int)

    def test_empty_host(self):
        """Test validation rejects empty host."""
        with pytest.raises(ValueError, match="Database host cannot be empty"):
            DatabaseConfig(
                host="",
                port=5432,
                database="test_db",
                user="test_user",
            )

    def test_empty_database(self):
        """Test validation rejects empty database name."""
        with pytest.raises(ValueError, match="Database name cannot be empty"):
            DatabaseConfig(
                host="localhost",
                port=5432,
                database="",
                user="test_user",
            )

    def test_empty_user(self):
        """Test validation rejects empty user."""
        with pytest.raises(ValueError, match="Database user cannot be empty"):
            DatabaseConfig(
                host="localhost",
                port=5432,
                database="test_db",
                user="",
            )


class TestConfigManager:
    """Test ConfigManager configuration loading and priority."""

    @pytest.fixture
    def temp_config_dir(self):
        """Create temporary config directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def config_manager(self, temp_config_dir):
        """Create ConfigManager with temporary config directory."""
        return ConfigManager(config_dir=temp_config_dir)

    def test_default_config(self, config_manager):
        """Test loading default configuration when no files exist."""
        # Mock dotenv_values to prevent loading .env from current directory
        with patch("trading_journal.config_manager.dotenv_values", return_value={}):
            # Clear any cached config
            config_manager._merged_config = None
            config_manager._database_config = None
            config_manager._logging_config = None
            config_manager._application_config = None

            db_config = config_manager.get_database_config()
            assert db_config.host == "localhost"
            assert db_config.port == 5432
            assert db_config.database == "trading_journal"
            assert db_config.user == "postgres"

            log_config = config_manager.get_logging_config()
            assert log_config.level == "INFO"

            app_config = config_manager.get_application_config()
            assert app_config.pnl_method == "average_cost"
            assert app_config.timezone == "US/Eastern"

    def test_postgres_config_loading(self, temp_config_dir):
        """Test loading shared postgres configuration."""
        postgres_dir = temp_config_dir / "postgres"
        postgres_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

        postgres_config = {
            "server": {
                "host": "192.168.1.100",
                "port": 32768,
                "user": "pguser",
                "password": "pgpass",
            }
        }

        postgres_file = postgres_dir / "default.toml"
        with open(postgres_file, "wb") as f:
            tomli_w.dump(postgres_config, f)

        config_manager = ConfigManager(config_dir=temp_config_dir)
        db_config = config_manager.get_database_config()

        assert db_config.host == "192.168.1.100"
        assert db_config.port == 32768
        assert db_config.user == "pguser"
        assert db_config.password == "pgpass"

    def test_app_config_loading(self, temp_config_dir):
        """Test loading app-specific configuration."""
        app_dir = temp_config_dir / "trading-journal"
        app_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

        app_config_data = {
            "default_profile": "prod",
            "app": {"timezone": "America/New_York", "pnl_method": "fifo"},
            "logging": {"level": "DEBUG", "file": "/var/log/trading.log"},
        }

        app_file = app_dir / "config.toml"
        with open(app_file, "wb") as f:
            tomli_w.dump(app_config_data, f)

        config_manager = ConfigManager(config_dir=temp_config_dir)

        app_config = config_manager.get_application_config()
        assert app_config.timezone == "America/New_York"
        assert app_config.pnl_method == "fifo"

        log_config = config_manager.get_logging_config()
        assert log_config.level == "DEBUG"
        assert log_config.file == "/var/log/trading.log"

    def test_profile_config_loading(self, temp_config_dir):
        """Test loading profile-specific configuration."""
        app_dir = temp_config_dir / "trading-journal"
        app_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

        app_config_data = {
            "default_profile": "prod",
            "profiles": {
                "prod": {
                    "database_name": "trading_prod",
                    "description": "Production",
                },
                "dev": {
                    "database_name": "trading_dev",
                    "log_level": "DEBUG",
                    "description": "Development",
                },
            },
        }

        app_file = app_dir / "config.toml"
        with open(app_file, "wb") as f:
            tomli_w.dump(app_config_data, f)

        # Test dev profile
        config_manager = ConfigManager(profile="dev", config_dir=temp_config_dir)
        db_config = config_manager.get_database_config()
        assert db_config.database == "trading_dev"

        log_config = config_manager.get_logging_config()
        assert log_config.level == "DEBUG"

    def test_environment_variable_override(self, temp_config_dir, config_manager):
        """Test that environment variables override all other config."""
        with patch.dict(
            os.environ,
            {
                "DB_HOST": "env-host",
                "DB_PORT": "9999",
                "DB_NAME": "env-db",
                "DB_USER": "env-user",
                "DB_PASSWORD": "env-pass",
                "LOG_LEVEL": "ERROR",
            },
        ):
            # Need to create a new manager after env vars are set
            manager = ConfigManager(config_dir=temp_config_dir)

            db_config = manager.get_database_config()
            assert db_config.host == "env-host"
            assert db_config.port == 9999
            assert db_config.database == "env-db"
            assert db_config.user == "env-user"
            assert db_config.password == "env-pass"

            log_config = manager.get_logging_config()
            assert log_config.level == "ERROR"

    def test_deep_merge(self, config_manager):
        """Test deep merge functionality."""
        base = {"a": 1, "b": {"x": 1, "y": 2}, "c": 3}
        override = {"b": {"y": 99, "z": 100}, "d": 4}

        result = config_manager._deep_merge(base, override)

        assert result["a"] == 1
        assert result["b"]["x"] == 1
        assert result["b"]["y"] == 99
        assert result["b"]["z"] == 100
        assert result["c"] == 3
        assert result["d"] == 4

    def test_deep_merge_ignores_none(self, config_manager):
        """Test that deep merge ignores None values in override."""
        base = {"a": 1, "b": 2}
        override = {"a": None, "b": 99, "c": None}

        result = config_manager._deep_merge(base, override)

        assert result["a"] == 1  # None didn't override
        assert result["b"] == 99
        assert "c" not in result  # None value not added

    def test_config_exists(self, temp_config_dir):
        """Test config_exists() method."""
        config_manager = ConfigManager(config_dir=temp_config_dir)
        assert not config_manager.config_exists()

        # Create app config
        app_dir = temp_config_dir / "trading-journal"
        app_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        app_file = app_dir / "config.toml"
        with open(app_file, "wb") as f:
            tomli_w.dump({"default_profile": "prod"}, f)

        assert config_manager.config_exists()

    def test_get_active_profile(self, temp_config_dir):
        """Test get_active_profile() method."""
        app_dir = temp_config_dir / "trading-journal"
        app_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

        app_config_data = {"default_profile": "production"}

        app_file = app_dir / "config.toml"
        with open(app_file, "wb") as f:
            tomli_w.dump(app_config_data, f)

        # Test default profile
        config_manager = ConfigManager(config_dir=temp_config_dir)
        assert config_manager.get_active_profile() == "production"

        # Test explicit profile
        config_manager = ConfigManager(profile="dev", config_dir=temp_config_dir)
        assert config_manager.get_active_profile() == "dev"

    def test_priority_hierarchy(self, temp_config_dir):
        """Test complete configuration priority hierarchy."""
        # Create shared postgres config
        postgres_dir = temp_config_dir / "postgres"
        postgres_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        with open(postgres_dir / "default.toml", "wb") as f:
            tomli_w.dump(
                {"server": {"host": "postgres-host", "port": 5432, "user": "pguser"}}, f
            )

        # Create app config
        app_dir = temp_config_dir / "trading-journal"
        app_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        with open(app_dir / "config.toml", "wb") as f:
            tomli_w.dump(
                {
                    "default_profile": "prod",
                    "app": {"timezone": "US/Pacific"},
                    "profiles": {
                        "prod": {
                            "database_name": "prod_db",
                            "postgres_config": "default",
                        }
                    },
                },
                f,
            )

        # Test with env var override
        with patch.dict(os.environ, {"DB_HOST": "env-override"}):
            config_manager = ConfigManager(config_dir=temp_config_dir)
            db_config = config_manager.get_database_config()

            # Env var should win
            assert db_config.host == "env-override"
            # Profile should provide database name
            assert db_config.database == "prod_db"
            # Postgres config should provide user
            assert db_config.user == "pguser"


class TestGetConfigManager:
    """Test get_config_manager singleton."""

    def test_singleton_behavior(self):
        """Test that get_config_manager returns same instance."""
        manager1 = get_config_manager()
        manager2 = get_config_manager()
        assert manager1 is manager2

    def test_reset_creates_new_instance(self):
        """Test that reset=True creates new instance."""
        manager1 = get_config_manager()
        manager2 = get_config_manager(reset=True)
        assert manager1 is not manager2


class TestLoggingConfig:
    """Test LoggingConfig."""

    def test_default_config(self):
        """Test default logging configuration."""
        config = LoggingConfig()
        assert config.level == "INFO"
        assert "trading_journal.log" in config.file

    def test_path_expansion(self):
        """Test that file path is expanded."""
        config = LoggingConfig(file="~/test.log")
        assert "~" not in config.file
        assert config.file.startswith("/")


class TestApplicationConfig:
    """Test ApplicationConfig."""

    def test_default_config(self):
        """Test default application configuration."""
        config = ApplicationConfig()
        assert config.pnl_method == "average_cost"
        assert config.timezone == "US/Eastern"
        assert config.batch_size == 1000
        assert config.max_retries == 3
