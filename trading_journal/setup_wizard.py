"""
Interactive setup wizard for Trading Journal configuration.

Guides users through creating configuration files with:
- Shared postgres configuration
- App-specific configuration
- Profile creation (prod/dev/test)
- Database connection testing
"""

import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import click
import tomli_w

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib  # type: ignore
    except ImportError:
        raise ImportError(
            "tomli is required for Python < 3.11. Install with: pip install tomli"
        )


class SetupWizard:
    """Interactive setup wizard for first-time configuration."""

    def __init__(
        self,
        config_dir: Optional[Path] = None,
        postgres_config_dir: Optional[Path] = None,
    ):
        """
        Initialize setup wizard.

        Args:
            config_dir: Override app config directory (for testing)
            postgres_config_dir: Override postgres config directory (for testing)
        """
        base_config = config_dir or Path.home() / ".config"
        self.app_config_dir = base_config / "trading-journal"
        self.postgres_config_dir = postgres_config_dir or (base_config / "postgres")
        self.app_config_path = self.app_config_dir / "config.toml"
        self.postgres_config_path = self.postgres_config_dir / "default.toml"

    def _find_existing_postgres_configs(self) -> List[Tuple[str, Path]]:
        """Find existing postgres configuration files."""
        if not self.postgres_config_dir.exists():
            return []

        configs = []
        for file in self.postgres_config_dir.glob("*.toml"):
            try:
                with open(file, "rb") as f:
                    data = tomllib.load(f)
                    desc = data.get("metadata", {}).get("description", "No description")
                    configs.append((desc, file))
            except Exception:
                continue

        return configs

    def _test_database_connection(
        self, host: str, port: int, user: str, password: str, database: str = "postgres"
    ) -> Tuple[bool, Optional[str]]:
        """
        Test database connection.

        Returns:
            (success, error_message)
        """
        try:
            import psycopg2

            conn = psycopg2.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                database=database,
                connect_timeout=5,
            )
            conn.close()
            return (True, None)
        except ImportError:
            return (False, "psycopg2 not installed. Install with: uv pip install psycopg2-binary")
        except Exception as e:
            return (False, str(e))

    def _create_database_if_not_exists(
        self, host: str, port: int, user: str, password: str, database: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Create database if it doesn't exist.

        Returns:
            (success, error_message)
        """
        try:
            import psycopg2
            from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

            # Connect to postgres database to create new database
            conn = psycopg2.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                database="postgres",
            )
            conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
            cursor = conn.cursor()

            # Check if database exists
            cursor.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s", (database,)
            )
            exists = cursor.fetchone() is not None

            if not exists:
                cursor.execute(f'CREATE DATABASE "{database}"')
                click.echo(f"  ✓ Created database: {database}")
            else:
                click.echo(f"  ✓ Database already exists: {database}")

            cursor.close()
            conn.close()
            return (True, None)
        except Exception as e:
            return (False, str(e))

    def _write_config_file(self, path: Path, data: Dict) -> None:
        """Write configuration file with secure permissions."""
        # Create directory with secure permissions
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)

        # Write TOML file
        with open(path, "wb") as f:
            tomli_w.dump(data, f)

        # Set secure file permissions
        path.chmod(0o600)

    def _prompt_postgres_config(self) -> Dict[str, str]:
        """Prompt for postgres configuration details."""
        click.echo("\n" + "=" * 60)
        click.echo("PostgreSQL Server Configuration")
        click.echo("=" * 60)

        host = click.prompt("Database host", default="localhost", type=str)
        port = click.prompt("Database port", default=5432, type=int)
        user = click.prompt("Database user", default="postgres", type=str)
        password = click.prompt("Database password", hide_input=True, default="", type=str)
        if not password:
            password = None

        return {
            "host": host,
            "port": port,
            "user": user,
            "password": password,
        }

    def _prompt_app_config(self) -> Dict[str, str]:
        """Prompt for application configuration."""
        click.echo("\n" + "=" * 60)
        click.echo("Application Configuration")
        click.echo("=" * 60)

        timezone = click.prompt(
            "Timezone",
            default="US/Eastern",
            type=str,
        )

        log_level = click.prompt(
            "Log level",
            default="INFO",
            type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"], case_sensitive=False),
        )

        return {
            "timezone": timezone,
            "log_level": log_level,
        }

    def run(self, force: bool = False) -> bool:
        """
        Run the interactive setup wizard.

        Args:
            force: Force setup even if config exists

        Returns:
            True if setup completed successfully
        """
        # Check if config already exists
        if not force and self.app_config_path.exists():
            click.echo(f"⚠️  Configuration already exists at: {self.app_config_path}")
            if not click.confirm("Do you want to reconfigure?"):
                return False

        click.echo("\n" + "=" * 60)
        click.echo("Trading Journal - Configuration Setup Wizard")
        click.echo("=" * 60)
        click.echo("\nThis wizard will help you configure:")
        click.echo("  1. PostgreSQL database connection")
        click.echo("  2. Application settings")
        click.echo("  3. Environment profiles (prod/dev/test)")
        click.echo("\nConfiguration will be stored in:")
        click.echo(f"  • App config: {self.app_config_path}")
        click.echo(f"  • Postgres config: {self.postgres_config_path}")

        if not click.confirm("\nContinue with setup?", default=True):
            click.echo("Setup cancelled.")
            return False

        # Step 1: Choose postgres configuration mode
        click.echo("\n" + "=" * 60)
        click.echo("Step 1: PostgreSQL Configuration")
        click.echo("=" * 60)

        existing_configs = self._find_existing_postgres_configs()
        postgres_config = None
        use_existing = False

        if existing_configs:
            click.echo("\nFound existing PostgreSQL configurations:")
            for i, (desc, path) in enumerate(existing_configs, 1):
                click.echo(f"  {i}. {path.stem} - {desc}")

            choice = click.prompt(
                "\nChoose an option",
                type=click.Choice(["new", "existing"], case_sensitive=False),
                default="existing",
                show_choices=True,
            )

            if choice == "existing":
                use_existing = True
                if len(existing_configs) == 1:
                    selected = existing_configs[0][1]
                else:
                    idx = click.prompt(
                        "Select configuration number",
                        type=click.IntRange(1, len(existing_configs)),
                    )
                    selected = existing_configs[idx - 1][1]

                # Load existing postgres config
                with open(selected, "rb") as f:
                    postgres_data = tomllib.load(f)
                    postgres_config = postgres_data.get("server", {})

                click.echo(f"\n✓ Using existing postgres config: {selected}")

        if not use_existing:
            postgres_config = self._prompt_postgres_config()

            # Test connection
            click.echo("\nTesting database connection...")
            success, error = self._test_database_connection(
                host=postgres_config["host"],
                port=postgres_config["port"],
                user=postgres_config["user"],
                password=postgres_config["password"] or "",
            )

            if not success:
                click.echo(f"❌ Connection failed: {error}")
                if not click.confirm("Continue anyway?", default=False):
                    return False
            else:
                click.echo("✓ Connection successful!")

        # Step 2: Database name for production
        click.echo("\n" + "=" * 60)
        click.echo("Step 2: Database Configuration")
        click.echo("=" * 60)

        prod_database = click.prompt(
            "Production database name",
            default="trading_journal",
            type=str,
        )

        # Create production database
        if postgres_config:
            click.echo(f"\nCreating database: {prod_database}")
            success, error = self._create_database_if_not_exists(
                host=postgres_config["host"],
                port=postgres_config["port"],
                user=postgres_config["user"],
                password=postgres_config["password"] or "",
                database=prod_database,
            )
            if not success:
                click.echo(f"⚠️  Could not create database: {error}")

        # Step 3: Additional profiles
        create_dev = click.confirm(
            "\nCreate development profile?",
            default=True,
        )
        create_test = click.confirm(
            "Create test profile?",
            default=True,
        )

        dev_database = None
        test_database = None

        if create_dev:
            dev_database = click.prompt(
                "Development database name",
                default="trading_journal_dev",
                type=str,
            )
            if postgres_config:
                self._create_database_if_not_exists(
                    host=postgres_config["host"],
                    port=postgres_config["port"],
                    user=postgres_config["user"],
                    password=postgres_config["password"] or "",
                    database=dev_database,
                )

        if create_test:
            test_database = click.prompt(
                "Test database name",
                default="trading_journal_test",
                type=str,
            )
            if postgres_config:
                self._create_database_if_not_exists(
                    host=postgres_config["host"],
                    port=postgres_config["port"],
                    user=postgres_config["user"],
                    password=postgres_config["password"] or "",
                    database=test_database,
                )

        # Step 4: Application settings
        app_settings = self._prompt_app_config()

        # Step 5: Write configuration files
        click.echo("\n" + "=" * 60)
        click.echo("Writing Configuration Files")
        click.echo("=" * 60)

        # Write shared postgres config (if new)
        if not use_existing and postgres_config:
            postgres_data = {
                "server": {
                    "host": postgres_config["host"],
                    "port": postgres_config["port"],
                    "user": postgres_config["user"],
                    "password": postgres_config["password"],
                },
                "metadata": {
                    "created_at": datetime.now().isoformat(),
                    "description": "Main PostgreSQL server",
                },
            }
            self._write_config_file(self.postgres_config_path, postgres_data)
            click.echo(f"✓ Created: {self.postgres_config_path}")

        # Write app config
        app_config_data: Dict = {
            "default_profile": "prod",
            "app": {
                "timezone": app_settings["timezone"],
                "pnl_method": "average_cost",
            },
            "logging": {
                "level": app_settings["log_level"],
                "file": "~/.local/share/trading-journal/trading_journal.log",
            },
            "profiles": {
                "prod": {
                    "database_name": prod_database,
                    "postgres_config": "default",
                    "description": "Production environment",
                }
            },
        }

        if create_dev:
            app_config_data["profiles"]["dev"] = {
                "database_name": dev_database,
                "postgres_config": "default",
                "log_level": "DEBUG",
                "description": "Development environment",
            }

        if create_test:
            app_config_data["profiles"]["test"] = {
                "database_name": test_database,
                "postgres_config": "default",
                "log_level": "WARNING",
                "description": "Test environment",
            }

        self._write_config_file(self.app_config_path, app_config_data)
        click.echo(f"✓ Created: {self.app_config_path}")

        # Step 6: Next steps
        click.echo("\n" + "=" * 60)
        click.echo("Setup Complete!")
        click.echo("=" * 60)
        click.echo("\n✓ Configuration files created with secure permissions (0600)")
        click.echo("\nNext steps:")
        click.echo("  1. Run database migrations:")
        click.echo("     $ trading-journal db migrate")
        click.echo("\n  2. Create your first user:")
        click.echo("     $ export ADMIN_MODE_ENABLED=true")
        click.echo("     $ export ADMIN_MODE_USER_ID=1")
        click.echo("     $ uv run python create_user.py")
        click.echo("\n  3. Ingest trading data:")
        click.echo("     $ export TRADING_JOURNAL_API_KEY=your_api_key")
        click.echo("     $ trading-journal ingest file data.ndjson")
        click.echo("\n  4. Process completed trades:")
        click.echo("     $ trading-journal db process-trades")
        click.echo("\n  5. View reports:")
        click.echo("     $ trading-journal report dashboard")

        if create_dev:
            click.echo("\nTo use the development profile:")
            click.echo("  $ trading-journal --profile dev db status")

        return True


def run_wizard(force: bool = False) -> bool:
    """
    Run the setup wizard.

    Args:
        force: Force setup even if config exists

    Returns:
        True if setup completed successfully
    """
    wizard = SetupWizard()
    return wizard.run(force=force)
