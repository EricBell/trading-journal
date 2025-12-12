   Configuration System Redesign for uv tools install

     Problem

     When installed via uv tools install ., the trading-journal app runs in an isolated environment and cannot access the project's .env file. Configuration needs to      
     work across multiple computers and be shared across multiple PostgreSQL-using applications.

     User Requirements

     1. ✅ Centralized Postgres config shared across multiple applications
     2. ✅ Configuration stored in user home directory (~/.config/)
     3. ✅ Interactive setup wizard for first-run experience
     4. ✅ Multiple named profiles (dev/prod/test) with --profile flag
     5. ✅ Works seamlessly with uv tools install
     6. ✅ Minimal user friction - just run trading-journal and it works

     Solution: Two-Tier TOML Configuration

     Configuration Architecture

     Tier 1: Shared Postgres Config (Cross-Application)
     - Location: ~/.config/postgres/default.toml
     - Purpose: Share DB server credentials across multiple apps
     - Format: TOML with [server] section

     Tier 2: App-Specific Config
     - Location: ~/.config/trading-journal/config.toml
     - Purpose: Profiles, app settings, references to shared postgres config
     - Format: TOML with [profiles.{name}] sections

     Configuration Priority (Highest to Lowest)

     1. Environment Variables (DB_HOST, DB_PORT, etc.)
     2. Profile-specific settings (from --profile or TRADING_JOURNAL_PROFILE)
     3. User config file (~/.config/trading-journal/config.toml)
     4. Shared postgres config (~/.config/postgres/default.toml)
     5. Legacy .env file (deprecated, backward compatibility only)
     6. Built-in defaults

     Example Configuration

     ~/.config/postgres/default.toml:
     [server]
     host = "192.168.1.249"
     port = 32768
     user = "postgres"
     password = "f96CW7u!JLb6sn"

     [metadata]
     created_at = "2025-12-12T10:00:00Z"
     description = "Main PostgreSQL server"

     ~/.config/trading-journal/config.toml:
     default_profile = "prod"

     [app]
     timezone = "US/Eastern"
     pnl_method = "average_cost"

     [logging]
     level = "INFO"
     file = "~/.local/share/trading-journal/trading_journal.log"

     [profiles.prod]
     database_name = "trading_journal"
     postgres_config = "default"  # References ~/.config/postgres/default.toml
     description = "Production environment"

     [profiles.dev]
     database_name = "trading_journal_dev"
     postgres_config = "default"
     log_level = "DEBUG"
     description = "Development environment"

     [profiles.test]
     database_name = "trading_journal_test"
     postgres_config = "default"
     log_level = "WARNING"
     description = "Test environment"

     Implementation Plan

     Phase 1: Core Configuration System

     1.1 Create ConfigManager (NEW FILE)

     File: trading_journal/config_manager.py

     Key Components:
     - DatabaseConfig dataclass with validation
     - ConfigManager class that:
       - Loads config from multiple sources
       - Implements priority hierarchy
       - Deep merges configurations
       - Validates settings
       - Lazy loads (don't load until needed)
     - get_config_manager() singleton function
     - Support for XDG Base Directory spec (~/.config, ~/.local/share)

     Critical Features:
     - Environment variable overrides (DB_HOST, DB_PORT, etc.)
     - Profile selection via --profile or TRADING_JOURNAL_PROFILE
     - Shared postgres config loading from ~/.config/postgres/{name}.toml
     - Legacy .env support with deprecation warning
     - Deep merge of nested dictionaries
     - Validation with helpful error messages

     1.2 Add TOML Writing Dependency

     File: pyproject.toml

     Change:
     Add to dependencies array:
     "tomli-w>=1.0.0",  # For writing TOML (Python 3.11+ has tomllib for reading)

     Phase 2: Setup Wizard

     2.1 Create Interactive Setup Wizard (NEW FILE)

     File: trading_journal/setup_wizard.py

     Key Features:
     - Detect existing postgres configs and offer to reuse them
     - Collect database connection details (host, port, user, password)
     - Test database connection before saving
     - Create databases if they don't exist
     - Generate config files with secure permissions (0600)
     - Support three modes:
       a. Use existing shared postgres config
       b. Create new shared postgres config
       c. App-only config (no sharing)

     Wizard Flow:
     1. Welcome and explain what will be created
     2. Choose postgres configuration mode
     3. Enter database connection details (if needed)
     4. Enter database name for production
     5. Optional: Create dev/test profiles
     6. Enter app settings (timezone, log level)
     7. Test connection and create databases
     8. Save configuration files with secure permissions
     9. Show next steps (db migrate, create user, ingest data)

     Phase 3: CLI Integration

     3.1 Update CLI Entry Point

     File: trading_journal/cli.py

     Changes:
     1. Add --profile global option to main() group
     2. Store profile in Click context for subcommands
     3. On startup (except for config commands):
       - Check if config exists
       - If not, offer to run setup wizard interactively
       - Validate configuration
       - Show helpful errors if validation fails

     New Commands:
     @main.group()
     def config():
         """Configuration management commands."""

     @config.command('setup')
     @click.option('--force', is_flag=True)
     def config_setup(force):
         """Run interactive setup wizard."""

     @config.command('show')
     @click.option('--profile')
     @click.option('--format', type=click.Choice(['text', 'json', 'toml']))
     def config_show(profile, format):
         """Show current configuration."""

     @config.command('validate')
     def config_validate():
         """Validate configuration and test DB connection."""

     @config.command('migrate')
     def config_migrate():
         """Migrate from .env to new TOML config."""

     3.2 Update config.py for Backward Compatibility

     File: trading_journal/config.py

     Changes:
     - Remove load_dotenv() at import time
     - Import ConfigManager
     - Create _ConfigProxy class for lazy loading
     - Modify module-level db_config, logging_config, app_config to use proxy
     - Existing code like db_config.host continues to work unchanged

     3.3 Update DatabaseManager

     File: trading_journal/database.py

     Changes:
     - Modify __init__() to accept optional DatabaseConfig parameter
     - If no config provided, get from get_config_manager().get_database_config()
     - Create get_db_manager() function for global instance
     - Maintain backward compatibility with existing db_manager import

     3.4 Update Alembic

     File: alembic/env.py

     Changes:
     - Import get_config_manager instead of db_config
     - Get database URL from ConfigManager
     - Set sqlalchemy.url in Alembic config

     Phase 4: Security & Migration

     4.1 File Permissions

     All config file creation must use:
     - Directories: mode=0o700 (rwx------)
     - Files: chmod(0o600) (rw-------)

     Implementation in all file writing:
     path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
     with open(path, 'wb') as f:
         tomli_w.dump(data, f)
     path.chmod(0o600)

     4.2 .gitignore Updates

     File: .gitignore

     Add:
     # Local configuration overrides
     *.local.toml
     .env.backup

     Note: .env already ignored at line 141

     4.3 Migration Support

     - Automatic .env detection with deprecation warning
     - trading-journal config migrate command to convert .env → TOML
     - Backup original .env as .env.backup
     - Maintain backward compatibility for 1-2 major versions

     Phase 5: Documentation Updates

     5.1 Update CLAUDE.md

     File: CLAUDE.md

     Add sections:
     - Configuration system overview
     - First-time setup instructions
     - Using profiles (--profile flag, TRADING_JOURNAL_PROFILE)
     - Configuration file locations
     - Migration from .env
     - Configuration commands reference

     5.2 Update PRD.md

     File: PRD.md

     Add to "Completed Features" or "Phase 4":
     - Multi-environment configuration system
     - Shared postgres configuration across applications
     - Interactive setup wizard
     - Profile-based deployment (dev/prod/test)

     Critical Files

     New Files

     - trading_journal/config_manager.py - Core configuration loading system
     - trading_journal/setup_wizard.py - Interactive first-run setup
     - ~/.config/postgres/default.toml - Shared postgres config (created by wizard)
     - ~/.config/trading-journal/config.toml - App config (created by wizard)

     Modified Files

     - pyproject.toml - Add tomli-w dependency
     - trading_journal/config.py - Lazy loading via ConfigManager
     - trading_journal/cli.py - Add --profile flag and config commands
     - trading_journal/database.py - Optional config parameter
     - alembic/env.py - Use ConfigManager for DB URL
     - .gitignore - Add *.local.toml, .env.backup
     - CLAUDE.md - Document new configuration system
     - PRD.md - Add configuration features to completed work

     User Experience

     First-Time Installation

     # Install globally
     uv tool install .

     # First run triggers setup wizard
     trading-journal db status

     # [Interactive wizard walks through config...]
     # [Tests connection, creates databases]
     # [Saves config to ~/.config/]

     # Subsequent runs just work
     trading-journal db migrate
     trading-journal ingest file data.ndjson

     Using Profiles

     # Default profile (prod)
     trading-journal report dashboard

     # Use dev profile
     trading-journal --profile dev db migrate

     # Or with environment variable
     export TRADING_JOURNAL_PROFILE=dev
     trading-journal report dashboard

     # Show current config
     trading-journal config show
     trading-journal config show --profile prod --format json

     Configuration Management

     # Validate config and test connection
     trading-journal config validate

     # Migrate from old .env file
     trading-journal config migrate

     # Re-run setup wizard
     trading-journal config setup --force

     Testing Strategy

     Unit Tests

     - tests/test_config_manager.py - Config loading, priority, validation
     - tests/test_setup_wizard.py - Wizard flow with mocked inputs

     Integration Tests

     - tests/test_config_integration.py - Profile switching, migration, uv tools install scenario

     Manual Testing

     1. Fresh install via uv tool install on clean machine
     2. Setup wizard complete flow
     3. Profile switching (dev/prod/test)
     4. Environment variable overrides
     5. Shared postgres config with multiple apps
     6. Migration from existing .env

     Success Criteria

     ✅ User can install via uv tool install . and run immediately
     ✅ Setup wizard is clear, helpful, and validates inputs
     ✅ Config files stored in ~/.config/ with proper permissions (0600)
     ✅ Profiles work seamlessly (--profile flag, env var)
     ✅ Environment variables still override everything (CI/CD compatible)
     ✅ Existing .env installations can migrate smoothly
     ✅ Shared postgres config works across multiple apps
     ✅ Error messages are helpful and actionable
     ✅ Documentation is clear and complete

     Implementation Order

     1. ConfigManager - Core system with tests
     2. pyproject.toml - Add tomli-w dependency
     3. Setup Wizard - Interactive config creation
     4. CLI Integration - Add --profile flag and config commands
     5. Backward Compatibility - Update config.py, database.py, alembic/env.py
     6. Security - File permissions audit
     7. Testing - Unit and integration tests
     8. Documentation - Update CLAUDE.md and PRD.md
     9. Migration - Test .env → TOML migration path
     10. End-to-End Testing - Fresh uv tool install on clean machine

