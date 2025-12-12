"""
Configuration Manager for Trading Journal.

Implements a two-tier TOML configuration system:
1. Shared Postgres Config: ~/.config/postgres/default.toml
2. App-Specific Config: ~/.config/trading-journal/config.toml

Configuration Priority (Highest to Lowest):
1. Environment Variables
2. Profile-specific settings (--profile or TRADING_JOURNAL_PROFILE)
3. User config file (~/.config/trading-journal/config.toml)
4. Shared postgres config (~/.config/postgres/default.toml)
5. Legacy .env file (deprecated)
6. Built-in defaults
"""

import os
import sys
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

# Python 3.11+ has built-in tomllib for reading TOML
if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib  # type: ignore
    except ImportError:
        raise ImportError(
            "tomli is required for Python < 3.11. Install with: pip install tomli"
        )

import tomli_w
from dotenv import dotenv_values


@dataclass
class DatabaseConfig:
    """Database configuration with validation."""

    host: str = "localhost"
    port: int = 5432
    database: str = "trading_journal"
    user: str = "postgres"
    password: Optional[str] = None

    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        if not isinstance(self.port, int):
            try:
                self.port = int(self.port)
            except (ValueError, TypeError):
                raise ValueError(f"Database port must be an integer, got: {self.port}")

        if not (1 <= self.port <= 65535):
            raise ValueError(f"Database port must be between 1-65535, got: {self.port}")

        if not self.host:
            raise ValueError("Database host cannot be empty")

        if not self.database:
            raise ValueError("Database name cannot be empty")

        if not self.user:
            raise ValueError("Database user cannot be empty")

    @property
    def url(self) -> str:
        """Build database URL for SQLAlchemy."""
        if self.password:
            return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"
        return f"postgresql://{self.user}@{self.host}:{self.port}/{self.database}"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "host": self.host,
            "port": self.port,
            "database": self.database,
            "user": self.user,
            "password": self.password,
        }


@dataclass
class LoggingConfig:
    """Logging configuration settings."""

    level: str = "INFO"
    file: str = "~/.local/share/trading-journal/trading_journal.log"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    def __post_init__(self) -> None:
        """Expand file path."""
        self.file = os.path.expanduser(self.file)


@dataclass
class ApplicationConfig:
    """Application-specific configuration settings."""

    pnl_method: str = "average_cost"
    timezone: str = "US/Eastern"
    batch_size: int = 1000
    max_retries: int = 3


class ConfigManager:
    """
    Manages configuration loading from multiple sources with priority hierarchy.

    Supports:
    - Environment variables
    - Profile-based configurations
    - TOML config files (shared postgres + app-specific)
    - Legacy .env files
    - Built-in defaults
    """

    def __init__(
        self,
        profile: Optional[str] = None,
        config_dir: Optional[Path] = None,
    ) -> None:
        """
        Initialize ConfigManager.

        Args:
            profile: Profile name to use (dev/prod/test). Defaults to env var or config default.
            config_dir: Override config directory (for testing). Defaults to ~/.config.
        """
        self._profile = profile or os.getenv("TRADING_JOURNAL_PROFILE")
        self._config_dir = config_dir or Path.home() / ".config"
        self._app_config_dir = self._config_dir / "trading-journal"
        self._postgres_config_dir = self._config_dir / "postgres"

        # Lazy-loaded caches
        self._app_config_data: Optional[Dict[str, Any]] = None
        self._postgres_config_data: Optional[Dict[str, Any]] = None
        self._merged_config: Optional[Dict[str, Any]] = None
        self._database_config: Optional[DatabaseConfig] = None
        self._logging_config: Optional[LoggingConfig] = None
        self._application_config: Optional[ApplicationConfig] = None

    @property
    def app_config_path(self) -> Path:
        """Path to app-specific config file."""
        return self._app_config_dir / "config.toml"

    @property
    def postgres_config_path(self) -> Path:
        """Path to shared postgres config file."""
        return self._postgres_config_dir / "default.toml"

    def _load_toml_file(self, path: Path) -> Dict[str, Any]:
        """Load TOML file if it exists."""
        if not path.exists():
            return {}

        try:
            with open(path, "rb") as f:
                return tomllib.load(f)
        except Exception as e:
            warnings.warn(f"Failed to load {path}: {e}")
            return {}

    def _load_env_file(self) -> Dict[str, Any]:
        """Load legacy .env file with deprecation warning."""
        env_path = Path.cwd() / ".env"
        if not env_path.exists():
            return {}

        warnings.warn(
            "Using .env file is deprecated. Please migrate to TOML config with: "
            "trading-journal config migrate",
            DeprecationWarning,
            stacklevel=2,
        )

        env_values = dotenv_values(env_path)
        return {
            "database": {
                "host": env_values.get("DB_HOST"),
                "port": env_values.get("DB_PORT"),
                "database": env_values.get("DB_NAME"),
                "user": env_values.get("DB_USER"),
                "password": env_values.get("DB_PASSWORD"),
            },
            "logging": {
                "level": env_values.get("LOG_LEVEL"),
                "file": env_values.get("LOG_FILE"),
            },
            "app": {
                "pnl_method": env_values.get("PNL_METHOD"),
                "timezone": env_values.get("TIMEZONE"),
                "batch_size": env_values.get("BATCH_SIZE"),
                "max_retries": env_values.get("MAX_RETRIES"),
            },
        }

    def _load_env_vars(self) -> Dict[str, Any]:
        """Load configuration from environment variables."""
        return {
            "database": {
                "host": os.getenv("DB_HOST"),
                "port": os.getenv("DB_PORT"),
                "database": os.getenv("DB_NAME"),
                "user": os.getenv("DB_USER"),
                "password": os.getenv("DB_PASSWORD"),
            },
            "logging": {
                "level": os.getenv("LOG_LEVEL"),
                "file": os.getenv("LOG_FILE"),
            },
            "app": {
                "pnl_method": os.getenv("PNL_METHOD"),
                "timezone": os.getenv("TIMEZONE"),
                "batch_size": os.getenv("BATCH_SIZE"),
                "max_retries": os.getenv("MAX_RETRIES"),
            },
        }

    def _deep_merge(self, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """
        Deep merge two dictionaries, with override taking precedence.

        Only merges non-None values from override.
        """
        result = base.copy()

        for key, value in override.items():
            if value is None:
                continue

            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value

        return result

    def _load_postgres_config(self, config_name: str = "default") -> Dict[str, Any]:
        """Load shared postgres configuration."""
        if self._postgres_config_data is None:
            postgres_path = self._postgres_config_dir / f"{config_name}.toml"
            self._postgres_config_data = self._load_toml_file(postgres_path)

        # Extract server config if present
        if "server" in self._postgres_config_data:
            return {"database": self._postgres_config_data["server"]}

        return {}

    def _load_app_config(self) -> Dict[str, Any]:
        """Load app-specific configuration."""
        if self._app_config_data is None:
            self._app_config_data = self._load_toml_file(self.app_config_path)

        return self._app_config_data

    def _get_profile_config(self) -> Dict[str, Any]:
        """Get configuration for the current profile."""
        app_config = self._load_app_config()

        # Determine active profile
        profile = self._profile or app_config.get("default_profile", "prod")

        # Get profile-specific config
        profiles = app_config.get("profiles", {})
        if profile not in profiles:
            return {}

        profile_config = profiles[profile].copy()

        # Load referenced postgres config if specified
        postgres_ref = profile_config.pop("postgres_config", None)
        if postgres_ref:
            postgres_config = self._load_postgres_config(postgres_ref)
        else:
            postgres_config = {}

        # Merge postgres config with profile config
        result = {}

        # Handle database config
        if "database_name" in profile_config:
            result["database"] = {"database": profile_config.pop("database_name")}

        if "log_level" in profile_config:
            result["logging"] = {"level": profile_config.pop("log_level")}

        # Merge with postgres config
        result = self._deep_merge(postgres_config, result)

        return result

    def _load_merged_config(self) -> Dict[str, Any]:
        """
        Load and merge all configuration sources according to priority.

        Priority (highest to lowest):
        1. Environment variables
        2. Profile-specific settings
        3. App config file
        4. Shared postgres config
        5. Legacy .env file
        6. Built-in defaults
        """
        if self._merged_config is not None:
            return self._merged_config

        # Start with built-in defaults
        config: Dict[str, Any] = {
            "database": {
                "host": "localhost",
                "port": 5432,
                "database": "trading_journal",
                "user": "postgres",
                "password": None,
            },
            "logging": {
                "level": "INFO",
                "file": "~/.local/share/trading-journal/trading_journal.log",
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            },
            "app": {
                "pnl_method": "average_cost",
                "timezone": "US/Eastern",
                "batch_size": 1000,
                "max_retries": 3,
            },
        }

        # Layer 5: Legacy .env file
        config = self._deep_merge(config, self._load_env_file())

        # Layer 4: Shared postgres config
        config = self._deep_merge(config, self._load_postgres_config())

        # Layer 3: App config file (non-profile parts)
        app_config = self._load_app_config()
        if "app" in app_config:
            config = self._deep_merge(config, {"app": app_config["app"]})
        if "logging" in app_config:
            config = self._deep_merge(config, {"logging": app_config["logging"]})

        # Layer 2: Profile-specific settings
        config = self._deep_merge(config, self._get_profile_config())

        # Layer 1: Environment variables (highest priority)
        config = self._deep_merge(config, self._load_env_vars())

        self._merged_config = config
        return config

    def get_database_config(self) -> DatabaseConfig:
        """Get database configuration."""
        if self._database_config is None:
            config = self._load_merged_config()
            db_config = config.get("database", {})

            self._database_config = DatabaseConfig(
                host=db_config.get("host", "localhost"),
                port=int(db_config.get("port", 5432)),
                database=db_config.get("database", "trading_journal"),
                user=db_config.get("user", "postgres"),
                password=db_config.get("password"),
            )

        return self._database_config

    def get_logging_config(self) -> LoggingConfig:
        """Get logging configuration."""
        if self._logging_config is None:
            config = self._load_merged_config()
            log_config = config.get("logging", {})

            self._logging_config = LoggingConfig(
                level=log_config.get("level", "INFO"),
                file=log_config.get(
                    "file", "~/.local/share/trading-journal/trading_journal.log"
                ),
                format=log_config.get(
                    "format", "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
                ),
            )

        return self._logging_config

    def get_application_config(self) -> ApplicationConfig:
        """Get application configuration."""
        if self._application_config is None:
            config = self._load_merged_config()
            app_config = config.get("app", {})

            self._application_config = ApplicationConfig(
                pnl_method=app_config.get("pnl_method", "average_cost"),
                timezone=app_config.get("timezone", "US/Eastern"),
                batch_size=int(app_config.get("batch_size", 1000)),
                max_retries=int(app_config.get("max_retries", 3)),
            )

        return self._application_config

    def config_exists(self) -> bool:
        """Check if configuration files exist."""
        return self.app_config_path.exists() or self.postgres_config_path.exists()

    def get_active_profile(self) -> str:
        """Get the name of the active profile."""
        app_config = self._load_app_config()
        return self._profile or app_config.get("default_profile", "prod")

    def get_all_config(self) -> Dict[str, Any]:
        """Get complete merged configuration (for display/debugging)."""
        return self._load_merged_config()


# Global singleton instance
_config_manager: Optional[ConfigManager] = None


def get_config_manager(
    profile: Optional[str] = None,
    reset: bool = False,
) -> ConfigManager:
    """
    Get the global ConfigManager singleton.

    Args:
        profile: Profile name to use. Only used on first call.
        reset: Force reset of singleton (for testing).

    Returns:
        ConfigManager instance
    """
    global _config_manager

    if reset or _config_manager is None:
        _config_manager = ConfigManager(profile=profile)

    return _config_manager
