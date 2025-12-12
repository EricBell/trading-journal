# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **Trading Journal** application designed to ingest and analyze trading data from brokerage platforms. The project has **completed Phase 3 (MVP)** and is now in **Phase 4 (Production Features)**. See `PRD.md` for complete specifications.

**Bonus Features Implemented:**
- Multi-user support with user authentication
- API key authentication system
- Admin mode for development/testing
- Comprehensive dashboard analytics

### Architecture Philosophy

**Three-Tier Data Hierarchy:**
1. **EXECUTIONS** (`trades` table) - Individual broker fills/partial fills from NDJSON input
2. **TRADES** (`completed_trades` table) - Complete round-trip business transactions (entry + exit)
3. **POSITIONS** (`positions` table) - Running totals and average cost basis per symbol

**Key Relationships:**
- Multiple executions → One completed trade
- Multiple completed trades → One position (per symbol)
- Setup patterns and notes belong at the **TRADE** level, not execution level

## Configuration System

The application uses a **two-tier TOML configuration system** designed for:
- `uv tools install` support (isolated environments)
- Shared PostgreSQL config across multiple applications
- Multiple deployment profiles (dev/prod/test)
- Environment variable overrides for CI/CD

### Configuration Architecture

**Tier 1: Shared Postgres Config** (Cross-Application)
- Location: `~/.config/postgres/default.toml`
- Purpose: Share DB server credentials across multiple apps
- Format: TOML with `[server]` section

**Tier 2: App-Specific Config**
- Location: `~/.config/trading-journal/config.toml`
- Purpose: Profiles, app settings, references to shared postgres config
- Format: TOML with `[profiles.{name}]` sections

### Configuration Priority (Highest to Lowest)

1. **Environment Variables** - `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `LOG_LEVEL`, etc.
2. **Profile-specific settings** - From `--profile` flag or `TRADING_JOURNAL_PROFILE` env var
3. **User config file** - `~/.config/trading-journal/config.toml`
4. **Shared postgres config** - `~/.config/postgres/default.toml`
5. **Legacy .env file** - Deprecated, backward compatibility only (shows warning)
6. **Built-in defaults** - Fallback values

### First-Time Setup

On first run, the application will automatically prompt you to run the interactive setup wizard:

```bash
# Explicit setup (or re-configuration)
trading-journal config setup

# Or just run any command and you'll be prompted
trading-journal db status
```

The wizard will guide you through:
1. PostgreSQL server configuration (or reuse existing shared config)
2. Database connection testing
3. Database creation (prod/dev/test)
4. Application settings (timezone, log level)
5. Profile configuration

Configuration files are created with secure permissions (0600 for files, 0700 for directories).

### Using Profiles

```bash
# Use default profile (usually "prod")
trading-journal db status

# Use development profile
trading-journal --profile dev db migrate
trading-journal --profile dev ingest file data.ndjson

# Or set via environment variable
export TRADING_JOURNAL_PROFILE=dev
trading-journal db status

# Show active profile and configuration
trading-journal config show
trading-journal config show --profile prod --format json
```

### Configuration Commands

```bash
# Run interactive setup wizard
trading-journal config setup
trading-journal config setup --force  # Reconfigure even if config exists

# Display current configuration
trading-journal config show                    # Text format
trading-journal config show --format json      # JSON format
trading-journal config show --format toml      # TOML format
trading-journal config show --profile dev      # Specific profile

# Validate configuration and test database connection
trading-journal config validate

# Migrate from legacy .env file to TOML
trading-journal config migrate
```

### Configuration File Locations

- **App Config**: `~/.config/trading-journal/config.toml`
- **Shared Postgres**: `~/.config/postgres/default.toml`
- **Legacy .env**: `./env` (deprecated, shows warning when used)

### Example Configuration Files

**~/.config/postgres/default.toml:**
```toml
[server]
host = "192.168.1.249"
port = 32768
user = "postgres"
password = "your_password_here"

[metadata]
created_at = "2025-12-12T10:00:00Z"
description = "Main PostgreSQL server"
```

**~/.config/trading-journal/config.toml:**
```toml
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
```

### Migrating from .env

If you have an existing `.env` file, use the migration command:

```bash
trading-journal config migrate
```

This will:
1. Read your existing `.env` file
2. Run the setup wizard with pre-populated values
3. Create TOML configuration files
4. Backup `.env` to `.env.backup`

The old `.env` file will continue to work (with deprecation warnings) until you're ready to remove it.

## Development Commands

### Project Setup
```bash
# Install dependencies with uv
uv sync

# Run migrations
uv run python main.py db migrate

# Create first user (requires admin mode)
export ADMIN_MODE_ENABLED=true
export ADMIN_MODE_USER_ID=1
uv run python create_user.py

# Set API key for subsequent commands
export TRADING_JOURNAL_API_KEY=your_api_key_here
```

### Development Commands

#### Typical Workflow (Two-Step Process)

**IMPORTANT**: The application requires a two-step process to see trades in reports:

```bash
# Step 1: Ingest NDJSON file (stores executions in trades table)
uv run python main.py ingest file ../schwab-csv-to-json/output.ndjson

# Step 2: Process completed trades (matches buys with sells)
uv run python main.py db process-trades

# Step 3: View reports
uv run python main.py report trades
uv run python main.py report positions
```

#### Database Operations
```bash
# Run migrations
uv run python main.py db migrate

# Check database status
uv run python main.py db status

# Reset database (with confirmation)
uv run python main.py db reset --confirm

# Process completed trades (required after ingestion)
uv run python main.py db process-trades
uv run python main.py db process-trades --symbol AAPL
```

#### Data Ingestion
```bash
# Single file ingestion
uv run python main.py ingest file data.ndjson

# Batch processing
uv run python main.py ingest batch *.ndjson --output-summary

# Dry run (validation only)
uv run python main.py ingest file data.ndjson --dry-run

# Verbose processing
uv run python main.py ingest file data.ndjson --verbose
```

#### Reporting (Implemented)
```bash
# Dashboard analytics (comprehensive metrics)
uv run python main.py report dashboard
uv run python main.py report dashboard --date-range 2025-01-01,2025-01-31
uv run python main.py report dashboard --symbol AAPL
uv run python main.py report dashboard --format detailed  # Includes equity curve
uv run python main.py report dashboard --format json      # JSON export

# View completed trades
uv run python main.py report trades
uv run python main.py report trades --symbol AAPL
uv run python main.py report trades --format json

# View positions
uv run python main.py report positions
uv run python main.py report positions --open-only
uv run python main.py report positions --symbol AAPL
```

#### Pattern & Notes Management (Implemented)
```bash
# Pattern annotation
uv run python main.py pattern annotate --id 123 --pattern "MACD Scalp"
uv run python main.py pattern list
uv run python main.py pattern performance --pattern "MACD Scalp"

# Trade notes
uv run python main.py notes add --id 123 --text "Great entry timing"
uv run python main.py notes show --id 123
uv run python main.py notes edit --id 123 --text "Updated notes"
```

#### User Management (Admin-Only - Planned)
```bash
# List users with trade counts
uv run python main.py users list
uv run python main.py users list --all --format json

# Create users
uv run python main.py users create --username trader1 --email trader1@example.com
uv run python main.py users create --username admin2 --email admin2@example.com --admin

# Manage user status
uv run python main.py users deactivate --user-id 5
uv run python main.py users reactivate --user-id 5
uv run python main.py users make-admin --user-id 5
uv run python main.py users revoke-admin --user-id 5

# Delete users (with safety checks)
uv run python main.py users delete --user-id 5

# API key management
uv run python main.py users regenerate-key --user-id 5
```

## Technical Stack

- **Language**: Python 3.11+ (per pyproject.toml)
- **Database**: PostgreSQL 14+ with JSONB support
- **ORM**: SQLAlchemy 2.0 with Alembic migrations
- **CLI**: Click framework
- **Web Framework**: Flask (production version)
- **Testing**: pytest (TDD approach)
- **Dependency Management**: uv
- **Code Quality**: black, isort, mypy

## Data Input Format

The application consumes NDJSON files from an existing **Schwab CSV to JSON Converter** project located at `../schwab-csv-to-json`. Sample data structure:

```json
{
  "exec_time": "2025-11-04T10:17:00",
  "side": "BUY", "qty": 300, "pos_effect": "TO OPEN",
  "symbol": "RANI", "net_price": 2.489,
  "event_type": "fill",
  "asset_type": "STOCK",  // Valid values: STOCK, OPTION, ETF
  "source_file": "2025-11-04-TradeActivity.csv"
}
```

**Asset Type Mapping:**
- `STOCK` → `EQUITY` instrument_type
- `ETF` → `EQUITY` instrument_type (treated identically to STOCK)
- `OPTION` → `OPTION` instrument_type

## Database Schema Considerations

### Critical Tables (from PRD)
1. **`trades`** - Individual executions with `completed_trade_id` FK
2. **`completed_trades`** - Round-trip trades with `setup_pattern` and `trade_notes`
3. **`positions`** - Current holdings with average cost basis
4. **`setup_patterns`** - Managed dropdown patterns (production version)
5. **`processing_log`** - File processing audit trail

### P&L Methodology
Uses **Average Cost (Weighted Average)** method for position tracking and P&L calculations, chosen for computational efficiency and platform compatibility.

## Implementation Phases

**Current Status: Phase 1 - Core Data Model (Weeks 1-2)**
- Database schema creation and migrations
- Basic NDJSON ingestion (single file processing)
- Duplicate detection using unique_key
- TDD approach with comprehensive unit tests

**Next Phases:**
- Phase 2: P&L Engine (Weeks 3-4)
- Phase 3: MVP Reporting (Week 5)
- Phase 4: Production Features (Week 6)

## Task Management

This project uses a **tasks.md** file to enumerate all tasks required to implement the PRD. During implementation:
1. Create `tasks.md` with all implementation tasks broken down by phase
2. Mark tasks as complete using checkboxes as work progresses
3. Use this file to track progress and ensure comprehensive PRD implementation

## Key Development Guidelines

- **Test-Driven Development (TDD)**: All implementation must follow TDD methodology
- **Performance Target**: 10,000 records ingestion in < 5 seconds
- **Data Integrity**: Zero P&L calculation discrepancies on closed positions
- **Annotations**: Setup patterns and notes apply to completed trades, not individual executions
- **Error Handling**: Comprehensive transaction-based error recovery with rollback capabilities

## Version Management

**Versioning System**: Uses `version_manager.py` with `version.json` for automatic file tracking and version control.

### Version Increment Rules
- **Patch increment** (0.2.0 → 0.2.1): Every time work is completed and ready for testing
- **Minor increment** (0.2.0 → 0.3.0): When adding new features OR when existing features change significantly
- **Major increment** (0.x.x → 1.0.0): Breaking changes or major releases

### Version Management Commands
```bash
# Check current version
python version_manager.py status

# Check for file changes and auto-increment patch if needed
python version_manager.py check

# Manual version increments
python version_manager.py patch    # Increment patch version
python version_manager.py minor    # Increment minor version
python version_manager.py major    # Increment major version

# Reset to specific version
python version_manager.py reset 0 2 0    # Reset to v0.2.0
```

**Current Version**: Check with `python version_manager.py status`

## Related Projects

The application depends on output from the **Schwab CSV to JSON Converter** located at `../schwab-csv-to-json` for NDJSON input data.