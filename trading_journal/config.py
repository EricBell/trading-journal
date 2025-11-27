"""Configuration management for trading journal."""

import os
from typing import Optional

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class DatabaseConfig:
    """Database configuration settings."""

    host: str = os.getenv("DB_HOST", "localhost")
    port: int = int(os.getenv("DB_PORT", "5432"))
    database: str = os.getenv("DB_NAME", "trading_journal")
    user: str = os.getenv("DB_USER", "postgres")
    password: Optional[str] = os.getenv("DB_PASSWORD")

    @property
    def url(self) -> str:
        """Build database URL."""
        if self.password:
            return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"
        return f"postgresql://{self.user}@{self.host}:{self.port}/{self.database}"


class LoggingConfig:
    """Logging configuration settings."""

    level: str = os.getenv("LOG_LEVEL", "INFO")
    file: str = os.getenv("LOG_FILE", "trading_journal.log")
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


class ApplicationConfig:
    """Application-specific configuration settings."""

    pnl_method: str = os.getenv("PNL_METHOD", "average_cost")
    timezone: str = os.getenv("TIMEZONE", "US/Eastern")
    batch_size: int = int(os.getenv("BATCH_SIZE", "1000"))
    max_retries: int = int(os.getenv("MAX_RETRIES", "3"))


# Global configuration instances
db_config = DatabaseConfig()
logging_config = LoggingConfig()
app_config = ApplicationConfig()