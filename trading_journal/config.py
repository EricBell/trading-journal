"""
Configuration management for trading journal.

DEPRECATED: This module provides backward compatibility with the old config system.
New code should use config_manager.ConfigManager directly.

This module uses lazy loading via proxy classes to maintain backward compatibility
with existing code while using the new ConfigManager under the hood.
"""

from typing import Any

from .config_manager import (
    get_config_manager,
    DatabaseConfig as _DatabaseConfig,
    LoggingConfig as _LoggingConfig,
    ApplicationConfig as _ApplicationConfig,
)


class _ConfigProxy:
    """
    Lazy-loading proxy for configuration objects.

    Maintains backward compatibility by allowing attribute access like:
        from .config import db_config
        db_config.host  # Works transparently
    """

    def __init__(self, config_type: str):
        """
        Initialize proxy.

        Args:
            config_type: Type of config to proxy ('database', 'logging', 'application')
        """
        self._config_type = config_type
        self._config_obj = None

    def _get_config(self) -> Any:
        """Lazy load configuration object."""
        if self._config_obj is None:
            config_manager = get_config_manager()

            if self._config_type == "database":
                self._config_obj = config_manager.get_database_config()
            elif self._config_type == "logging":
                self._config_obj = config_manager.get_logging_config()
            elif self._config_type == "application":
                self._config_obj = config_manager.get_application_config()
            else:
                raise ValueError(f"Unknown config type: {self._config_type}")

        return self._config_obj

    def __getattr__(self, name: str) -> Any:
        """Proxy attribute access to the underlying config object."""
        return getattr(self._get_config(), name)

    def __repr__(self) -> str:
        """String representation."""
        return repr(self._get_config())


# Export original config classes for type hints
DatabaseConfig = _DatabaseConfig
LoggingConfig = _LoggingConfig
ApplicationConfig = _ApplicationConfig

# Global configuration instances (using lazy-loading proxies)
db_config = _ConfigProxy("database")
logging_config = _ConfigProxy("logging")
app_config = _ConfigProxy("application")