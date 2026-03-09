# Trading Journal

PostgreSQL-based trading data ingestion and analysis system for day traders.

## Overview

A comprehensive trading journal application that ingests NDJSON trade data from brokerage platforms and provides profit/loss analysis, position tracking, and performance reporting. Built with Python, PostgreSQL, and SQLAlchemy.

## Features

- **Data Ingestion:** Import trade data from NDJSON files (Schwab CSV converter output)
- **Position Tracking:** Real-time position balances with average cost basis methodology
- **P&L Calculation:** Automatic profit/loss calculations for completed trades
- **Trade Completion:** Groups individual executions into round-trip trades
- **Pattern Analysis:** Annotate trades with setup patterns and analyze performance
- **Multi-User Support:** API key authentication with admin mode
- **Comprehensive CLI:** Full command-line interface for all operations

## Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL 14+
- uv (Python package manager)

### Installation

```bash
# Install dependencies
uv sync

# Create PostgreSQL database
createdb trading_journal

# Configure environment
cp .env.example .env
# Edit .env with your database credentials

# Run migrations
uv run python main.py db migrate
```

### Create Your First User

```bash
# Set admin mode for initial setup
export ADMIN_MODE_ENABLED=true
export ADMIN_MODE_USER_ID=1

# Create user and get API key
uv run python create_user.py
```

### Basic Usage

```bash
# Set your API key
export TRADING_JOURNAL_API_KEY=your_api_key_here

# Ingest trade data
uv run python main.py ingest file data.ndjson

# Process completed trades
uv run python main.py db process-trades

# View reports
uv run python main.py report trades
uv run python main.py report positions
```

## Documentation

- **[docs/OVERVIEW.md](docs/OVERVIEW.md)** - Authoritative system overview (architecture, design decisions, feature inventory)
- **[CLAUDE.md](CLAUDE.md)** - Development guidance for AI assistants
- **[docs/PRD.md](docs/PRD.md)** - Original product requirements (historical)
- **[docs/](docs/)** - Additional planning and implementation history

## Current Status

- **Phase 1:** ✅ Core Data Model - Complete
- **Phase 2:** ✅ P&L Engine - Complete
- **Phase 3:** ✅ MVP Reporting - **Complete** 🎉
- **Phase 4:** 🚧 Production Features - In Progress

## Technology Stack

- **Database:** PostgreSQL 14+ with JSONB support
- **Language:** Python 3.11+
- **ORM:** SQLAlchemy 2.0
- **Migrations:** Alembic
- **CLI:** Click framework
- **Testing:** pytest

## Project Structure

```
trading-journal/
├── trading_journal/          # Main application package
│   ├── models.py            # SQLAlchemy models
│   ├── cli.py               # Click CLI commands
│   ├── ingestion.py         # NDJSON ingestion logic
│   ├── positions.py         # Position tracking engine
│   ├── trade_completion.py  # Trade grouping algorithm
│   ├── auth/                # Authentication system
│   └── authorization/       # Authorization context
├── alembic/                 # Database migrations
├── tests/                   # Test suite
├── main.py                  # CLI entry point
└── PRD.md                   # Product requirements

```

## License

See [LICENSE](LICENSE) file for details.
