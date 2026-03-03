"""Command-line interface for trading journal."""

import json
import logging
from pathlib import Path

import click
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from .database import db_manager
from .config import logging_config
from .config_manager import get_config_manager
from .setup_wizard import run_wizard
from .models import CompletedTrade
from .cli_auth import require_authentication, AuthContext
from .user_management import UserManager
from .report_configs import (
    TRADE_COLUMN_DEFS,
    TRADE_REPORT_LAYOUTS,
)


# Set up logging
# Ensure log directory exists
log_file_path = Path(logging_config.file)
log_file_path.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=getattr(logging, logging_config.level),
    format=logging_config.format,
    handlers=[
        logging.FileHandler(logging_config.file),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


@click.group(invoke_without_command=True)
@click.option(
    '--overview',
    is_flag=True,
    help='Display project overview and exit',
)
@click.pass_context
@click.version_option()
def main(ctx: click.Context, overview: bool) -> None:
    """Trading Journal - PostgreSQL-based trading data ingestion and analysis."""
    # Handle --overview flag
    if overview:
        click.echo("\n" + "=" * 80)
        click.echo("TRADING JOURNAL - OVERVIEW")
        click.echo("=" * 80 + "\n")
        click.echo("A comprehensive trading journal application that ingests CSV trade data")
        click.echo("from brokerage platforms and provides profit/loss analysis, position tracking,")
        click.echo("and performance reporting. Built with Python, PostgreSQL, and SQLAlchemy.")
        click.echo("\n" + "=" * 80 + "\n")
        ctx.exit(0)

    # If no command provided and no --overview flag, show help
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())
        ctx.exit(0)

    ctx.ensure_object(dict)

    # Check if we're running a config command (skip config check for those)
    if ctx.invoked_subcommand in ['config']:
        return

    # Check if configuration exists (except for config commands)
    config_manager = get_config_manager()
    if not config_manager.config_exists():
        # Skip the wizard when env vars supply a complete DB connection (e.g. Docker)
        import os
        has_env_config = all(os.environ.get(v) for v in ('DB_HOST', 'DB_NAME', 'DB_USER', 'DB_PASSWORD'))
        if not has_env_config:
            click.echo("⚠️  No configuration found.")
            click.echo(f"Config file should be at: {config_manager.app_config_path}")
            click.echo("\nRun the setup wizard to create your configuration:")
            click.echo("  $ trading-journal config setup")

            if click.confirm("\nRun setup wizard now?", default=True):
                if run_wizard():
                    click.echo("\n✓ Configuration created successfully!")
                    get_config_manager(reset=True)
                else:
                    raise click.Abort()
            else:
                raise click.Abort()


@main.group()
def config() -> None:
    """Configuration management commands."""
    pass


@config.command('setup')
@click.option('--force', is_flag=True, help='Force reconfiguration even if config exists')
def config_setup(force: bool) -> None:
    """Run interactive setup wizard."""
    try:
        if run_wizard(force=force):
            click.echo("\n✅ Configuration setup completed successfully")
        else:
            click.echo("\n⚠️  Configuration setup cancelled")
    except Exception as e:
        click.echo(f"❌ Setup failed: {e}")
        raise click.Abort()


@config.command('show')
@click.option('--profile', help='Profile to display (overrides default)')
@click.option(
    '--format',
    type=click.Choice(['text', 'json', 'toml'], case_sensitive=False),
    default='text',
    help='Output format'
)
@click.pass_context
def config_show(ctx: click.Context, profile: str, format: str) -> None:
    """Show current configuration."""
    try:
        config_manager = get_config_manager(profile=profile, reset=True)

        if not config_manager.config_exists():
            click.echo("❌ No configuration found. Run: trading-journal config setup")
            raise click.Abort()

        full_config = config_manager.get_all_config()
        active_profile = config_manager.get_active_profile()

        if format == 'json':
            # Convert to JSON (mask password)
            config_copy = full_config.copy()
            if 'database' in config_copy and 'password' in config_copy['database']:
                if config_copy['database']['password']:
                    config_copy['database']['password'] = '********'
            click.echo(json.dumps(config_copy, indent=2))

        elif format == 'toml':
            import tomli_w
            config_copy = full_config.copy()
            if 'database' in config_copy and 'password' in config_copy['database']:
                if config_copy['database']['password']:
                    config_copy['database']['password'] = '********'
            click.echo(tomli_w.dumps(config_copy))

        else:  # text format
            click.echo(f"\nActive Profile: {active_profile}")
            click.echo(f"Config File: {config_manager.app_config_path}")
            click.echo("\nDatabase Configuration:")
            db_config = config_manager.get_database_config()
            click.echo(f"  Host: {db_config.host}")
            click.echo(f"  Port: {db_config.port}")
            click.echo(f"  Database: {db_config.database}")
            click.echo(f"  User: {db_config.user}")
            click.echo(f"  Password: {'********' if db_config.password else '(not set)'}")

            click.echo("\nLogging Configuration:")
            log_config = config_manager.get_logging_config()
            click.echo(f"  Level: {log_config.level}")
            click.echo(f"  File: {log_config.file}")

            click.echo("\nApplication Configuration:")
            app_config = config_manager.get_application_config()
            click.echo(f"  P&L Method: {app_config.pnl_method}")
            click.echo(f"  Timezone: {app_config.timezone}")
            click.echo(f"  Batch Size: {app_config.batch_size}")
            click.echo(f"  Max Retries: {app_config.max_retries}")

    except Exception as e:
        click.echo(f"❌ Failed to show configuration: {e}")
        raise click.Abort()


@config.command('validate')
@click.pass_context
def config_validate(ctx: click.Context) -> None:
    """Validate configuration and test database connection."""
    try:
        config_manager = get_config_manager(reset=True)

        if not config_manager.config_exists():
            click.echo("❌ No configuration found. Run: trading-journal config setup")
            raise click.Abort()

        click.echo("Validating configuration...")

        # Validate database config
        db_config = config_manager.get_database_config()
        click.echo(f"✓ Database config valid: {db_config.database}@{db_config.host}:{db_config.port}")

        # Test database connection
        click.echo("\nTesting database connection...")
        try:
            import psycopg2
            conn = psycopg2.connect(
                host=db_config.host,
                port=db_config.port,
                user=db_config.user,
                password=db_config.password or "",
                database=db_config.database,
                connect_timeout=5,
            )
            conn.close()
            click.echo("✓ Database connection successful")
        except Exception as e:
            click.echo(f"❌ Database connection failed: {e}")
            raise click.Abort()

        # Validate logging config
        log_config = config_manager.get_logging_config()
        click.echo(f"✓ Logging config valid: {log_config.level} -> {log_config.file}")

        # Validate app config
        app_config = config_manager.get_application_config()
        click.echo(f"✓ Application config valid: {app_config.pnl_method}")

        click.echo("\n✅ All configuration validation passed")

    except click.Abort:
        raise
    except Exception as e:
        click.echo(f"❌ Validation failed: {e}")
        raise click.Abort()


@config.command('migrate')
def config_migrate() -> None:
    """Migrate from .env to new TOML configuration."""
    try:
        env_path = Path.cwd() / ".env"

        if not env_path.exists():
            click.echo("❌ No .env file found to migrate")
            raise click.Abort()

        click.echo("Migrating .env to TOML configuration...")
        click.echo(f"Source: {env_path}")

        # Load existing .env
        from dotenv import dotenv_values
        env_values = dotenv_values(env_path)

        # Extract values
        postgres_config = {
            "host": env_values.get("DB_HOST", "localhost"),
            "port": int(env_values.get("DB_PORT", "5432")),
            "user": env_values.get("DB_USER", "postgres"),
            "password": env_values.get("DB_PASSWORD"),
        }
        database_name = env_values.get("DB_NAME", "trading_journal")
        log_level = env_values.get("LOG_LEVEL", "INFO")
        timezone = env_values.get("TIMEZONE", "US/Eastern")
        pnl_method = env_values.get("PNL_METHOD", "average_cost")

        # Create wizard with prepopulated values
        wizard = run_wizard(force=False)

        if wizard:
            # Backup .env file
            backup_path = env_path.with_suffix(".env.backup")
            env_path.rename(backup_path)
            click.echo(f"✓ Backed up .env to: {backup_path}")
            click.echo("✅ Migration completed successfully")
            click.echo("\nYou can now delete the .env.backup file if everything works correctly")
        else:
            click.echo("⚠️  Migration cancelled")

    except Exception as e:
        click.echo(f"❌ Migration failed: {e}")
        raise click.Abort()


@main.group()
def db() -> None:
    """Database management commands."""
    pass


@db.command()
def migrate() -> None:
    """Run database migrations."""
    try:
        alembic_cfg = Config("alembic.ini")
        command.upgrade(alembic_cfg, "head")
        click.echo("✅ Database migrations completed successfully")
    except Exception as e:
        click.echo(f"❌ Migration failed: {e}")
        raise click.Abort()


@db.command()
def status() -> None:
    """Check database connection and migration status."""
    try:
        if db_manager.test_connection():
            click.echo("✅ Database connection: OK")
        else:
            click.echo("❌ Database connection: FAILED")
            raise click.Abort()
        alembic_cfg = Config("alembic.ini")
        command.current(alembic_cfg)
    except Exception as e:
        click.echo(f"❌ Status check failed: {e}")
        raise click.Abort()


@db.command()
@click.option('--confirm', is_flag=True, help='Confirm database reset')
def reset(confirm: bool) -> None:
    """Reset database (drop all tables)."""
    if not confirm:
        if not click.confirm('This will delete ALL data. Are you sure?'):
            click.echo("Operation cancelled")
            return
    try:
        db_manager.drop_tables()
        click.echo("✅ Database reset completed")
    except Exception as e:
        click.echo(f"❌ Database reset failed: {e}")
        raise click.Abort()


@db.command("verify-schema")
def verify_schema() -> None:
    """Verify database schema constraints for multi-user support."""
    try:
        with db_manager.engine.connect() as conn:
            # Check trades table constraints
            result = conn.execute(text("""
                SELECT constraint_name, constraint_type
                FROM information_schema.table_constraints
                WHERE table_name = 'trades'
                AND constraint_name IN ('unique_trade_per_user', 'trades_unique_key_key')
            """))
            constraints = result.fetchall()

            click.echo("\n" + "=" * 80)
            click.echo("DATABASE SCHEMA VERIFICATION")
            click.echo("=" * 80 + "\n")

            click.echo("Trades Table Constraints:")
            if not constraints:
                click.echo("  ⚠️  No relevant constraints found")
            else:
                for constraint in constraints:
                    status = "✅" if constraint[0] == 'unique_trade_per_user' else "❌ OLD"
                    click.echo(f"  {status} {constraint[0]} ({constraint[1]})")

            # Check for old global constraint
            has_old = any(c[0] == 'trades_unique_key_key' for c in constraints)
            has_new = any(c[0] == 'unique_trade_per_user' for c in constraints)

            click.echo("\n" + "-" * 80 + "\n")

            if has_old and not has_new:
                click.echo("STATUS: ❌ OLD SCHEMA DETECTED")
                click.echo("\nProblem: Using global unique_key constraint (not per-user)")
                click.echo("This prevents different users from ingesting the same source files.")
                click.echo("\nFix: Run database migrations to update to per-user constraints:")
                click.echo("  uv run python main.py db migrate")
            elif has_old and has_new:
                click.echo("STATUS: ⚠️  MIXED CONSTRAINTS")
                click.echo("\nProblem: Both old and new constraints exist")
                click.echo("\nFix: Drop old constraint or re-run migrations:")
                click.echo("  uv run alembic downgrade -1")
                click.echo("  uv run alembic upgrade head")
            elif has_new:
                click.echo("STATUS: ✅ SCHEMA IS CURRENT")
                click.echo("\nPer-user unique constraints are properly configured.")
                click.echo("Each user can independently ingest the same source files.")
            else:
                click.echo("STATUS: ⚠️  NO UNIQUE CONSTRAINT FOUND")
                click.echo("\nProblem: Missing unique constraint on trades table")
                click.echo("\nFix: Run database migrations:")
                click.echo("  uv run python main.py db migrate")

            click.echo("\n" + "=" * 80 + "\n")

    except Exception as e:
        click.echo(f"❌ Schema verification failed: {e}", err=True)
        raise click.Abort()


@db.command()
@click.option('--symbol', help='Process only specific symbol')
@require_authentication
def process_trades(symbol: str) -> None:
    """Process completed trades from executions."""
    try:
        from .trade_completion import TradeCompletionEngine
        engine = TradeCompletionEngine()
        result = engine.process_completed_trades(symbol)
        click.echo(f"🔄 Trade Processing Results:")
        click.echo(f"✅ Completed trades created: {result['completed_trades']}")
        click.echo(f"📝 {result['message']}")
    except Exception as e:
        click.echo(f"❌ Trade processing failed: {e}")
        raise click.Abort()


@main.group()
def ingest() -> None:
    """Data ingestion commands."""
    pass


@ingest.command("csv")
@click.argument('files', nargs=-1, required=True, type=click.Path(exists=True))
@click.option('--include-rolling', is_flag=True, help='Include Rolling Strategies section')
@click.option('--encoding', default='utf-8', show_default=True, help='CSV file encoding')
@click.option('--dry-run', is_flag=True, help='Validate without database changes')
@click.option('--verbose', is_flag=True, help='Enable verbose output')
@require_authentication
def ingest_csv(
    files: tuple,
    include_rolling: bool,
    encoding: str,
    dry_run: bool,
    verbose: bool,
) -> None:
    """Ingest one or more Schwab CSV trade activity files."""
    from .csv_parser import CsvParser
    from .ingestion import NdjsonIngester, IngestionError

    if dry_run:
        click.echo("🔍 DRY RUN MODE - No database changes will be made")

    try:
        parser = CsvParser(include_rolling=include_rolling, encoding=encoding)
        records = parser.parse_files(list(files))

        if verbose:
            fill_count = sum(1 for r in records if r.get('event_type') == 'fill')
            click.echo(f"📄 Parsed {len(records)} total records ({fill_count} fills) from {len(files)} file(s)")

        ingester = NdjsonIngester()
        result = ingester.ingest_records(records, dry_run=dry_run, verbose=verbose)

        click.echo(f"✅ Records processed: {result['records_processed']}")
        click.echo(f"❌ Records failed: {result['records_failed']}")

        if not dry_run:
            click.echo(f"➕ New records inserted: {result['inserts']}")
            click.echo(f"🔄 Existing records updated: {result['updates']}")

        if result['validation_errors']:
            click.echo("\n⚠️  Validation errors:")
            for error in result['validation_errors']:
                click.echo(f"   {error}")

        if result['success']:
            click.echo("🎉 Ingestion completed successfully")
        else:
            click.echo("⚠️  Ingestion completed with errors")

    except IngestionError as e:
        click.echo(f"❌ Ingestion failed: {e}")
        raise click.Abort()
    except Exception as e:
        click.echo(f"❌ Unexpected error: {e}")
        raise click.Abort()


@main.group()
def report() -> None:
    """Reporting commands."""
    pass


@main.group()
def trades() -> None:
    """Completed trade management commands."""
    pass


@trades.command("show")
@click.option('--id', type=int, required=True, help='Completed trade ID')
@require_authentication
def show_trade(id: int) -> None:
    """Show details for a single completed trade and its executions."""
    try:
        user_id = AuthContext.require_user().user_id
        with db_manager.get_session() as session:
            trade = session.query(CompletedTrade).filter_by(
                completed_trade_id=id,
                user_id=user_id
            ).one_or_none()

            if not trade:
                click.echo(f"❌ Error: Completed trade with ID {id} not found.", err=True)
                raise click.Abort()

            click.echo(f"📋 Details for Completed Trade ID: {trade.completed_trade_id}")
            click.echo(f"   Symbol: {trade.symbol} ({trade.instrument_type})")
            click.echo(f"   Type: {trade.trade_type}")
            click.echo(f"   Quantity: {trade.total_qty}")
            click.echo(f"   P&L: ${trade.net_pnl:.2f}")
            click.echo(f"   Opened: {trade.opened_at}")
            click.echo(f"   Closed: {trade.closed_at}")
            click.echo(f"   Duration: {trade.hold_duration}")
            click.echo(f"   Pattern: {trade.setup_pattern or 'N/A'}")
            click.echo(f"   Notes: {trade.trade_notes or 'N/A'}")
            
            click.echo("\n   Executions:")
            for exec in sorted(trade.executions, key=lambda e: e.exec_timestamp):
                click.echo(f"      - {exec.exec_timestamp} | {exec.side} {exec.qty} @ {exec.net_price:.4f}")

    except Exception as e:
        click.echo(f"❌ Trade display failed: {e}", err=True)
        raise click.Abort()


@report.command()
@click.option('--date-range', help=(
    'Date range filter. Formats: "today", "7d" (last 7 days), '
    '"YYYY-MM-DD/YYYY-MM-DD", "YYYY-MM-DD/" (to today), "/YYYY-MM-DD" (up to date).'
))
@click.option('--symbol', help='Filter by symbol')
@require_authentication
def dashboard(date_range: str, symbol: str) -> None:
    """Generate dashboard metrics."""
    try:
        from .dashboard import DashboardEngine

        engine = DashboardEngine()

        # Parse date range
        start_date, end_date = None, None
        if date_range:
            try:
                start_date, end_date = engine.parse_date_range(date_range)
            except ValueError as e:
                click.echo(f"❌ Invalid date range: {e}", err=True)
                raise click.Abort()

        # Generate dashboard
        dashboard_data = engine.generate_dashboard(
            start_date=start_date,
            end_date=end_date,
            symbol=symbol
        )

        # Check if no trades found
        if "message" in dashboard_data:
            click.echo(f"ℹ️  {dashboard_data['message']}")
            return

        _display_dashboard_summary(dashboard_data)

    except Exception as e:
        click.echo(f"❌ Dashboard generation failed: {e}", err=True)
        logger.exception("Dashboard generation error")
        raise click.Abort()


def _display_dashboard_summary(data: dict, detailed: bool = False) -> None:
    """Display dashboard in formatted text output."""
    click.echo("\n" + "="*70)
    click.echo("📊 TRADING DASHBOARD")
    click.echo("="*70)

    # Period info
    period = data.get("period", {})
    click.echo(f"\n📅 Period:")
    if period.get("start_date") and period.get("end_date"):
        click.echo(f"   {period['start_date']} to {period['end_date']}")
    elif period.get("first_trade") and period.get("last_trade"):
        click.echo(f"   {period['first_trade'][:10]} to {period['last_trade'][:10]}")
    else:
        click.echo(f"   All time")
    if period.get("symbol"):
        click.echo(f"   Symbol: {period['symbol']}")

    # Core metrics
    core = data.get("core_metrics", {})
    if core:
        click.echo(f"\n💰 Performance Summary:")
        click.echo(f"   Total Trades: {core['total_trades']}")
        click.echo(f"   Winning Trades: {core['winning_trades']} ({core['win_rate_pct']:.1f}%)")
        click.echo(f"   Losing Trades: {core['losing_trades']}")
        click.echo(f"\n   Total P&L: ${core['total_pnl']:,.2f}")

        # Color code P&L
        pnl_color = "🟢" if core['total_pnl'] > 0 else "🔴"
        click.echo(f"   {pnl_color} Net Result: ${core['total_pnl']:,.2f}")

        click.echo(f"\n   Average Win: ${core['average_win']:,.2f}")
        click.echo(f"   Average Loss: ${core['average_loss']:,.2f}")
        click.echo(f"   Average Trade: ${core['average_trade']:,.2f}")

        if core.get('profit_factor'):
            click.echo(f"   Profit Factor: {core['profit_factor']:.2f}")

        click.echo(f"\n   Largest Win: ${core['largest_win']:,.2f}")
        click.echo(f"   Largest Loss: ${core['largest_loss']:,.2f}")

        click.echo(f"\n   Max Win Streak: {core['max_win_streak']}")
        click.echo(f"   Max Loss Streak: {core['max_loss_streak']}")

    # Max drawdown
    dd = data.get("max_drawdown", {})
    if dd and dd.get("max_drawdown") != 0:
        click.echo(f"\n📉 Risk Metrics:")
        click.echo(f"   Max Drawdown: ${dd['max_drawdown']:,.2f} ({dd['max_drawdown_pct']:.2f}%)")
        if dd.get('peak_date'):
            click.echo(f"   Peak: ${dd['peak_value']:,.2f} on {dd['peak_date'][:10]}")
            click.echo(f"   Trough: ${dd['trough_value']:,.2f} on {dd['trough_date'][:10]}")

    # Pattern analysis
    patterns = data.get("pattern_analysis", {})
    if patterns and patterns.get("by_pattern"):
        click.echo(f"\n🎯 Pattern Analysis:")

        top_pattern = patterns.get("top_pattern")
        worst_pattern = patterns.get("worst_pattern")

        if top_pattern:
            click.echo(f"   🥇 Best Pattern: {top_pattern['pattern']}")
            click.echo(f"      Trades: {top_pattern['total_trades']}, P&L: ${top_pattern['total_pnl']:,.2f}, Win Rate: {top_pattern['win_rate_pct']:.1f}%")

        if worst_pattern and worst_pattern != top_pattern:
            click.echo(f"   🥉 Worst Pattern: {worst_pattern['pattern']}")
            click.echo(f"      Trades: {worst_pattern['total_trades']}, P&L: ${worst_pattern['total_pnl']:,.2f}, Win Rate: {worst_pattern['win_rate_pct']:.1f}%")

        if detailed:
            click.echo(f"\n   All Patterns:")
            for pattern in patterns["by_pattern"]:
                click.echo(f"   • {pattern['pattern']}: {pattern['total_trades']} trades, ${pattern['total_pnl']:,.2f} P&L, {pattern['win_rate_pct']:.1f}% win rate")

    # Position summary
    positions = data.get("positions", {})
    if positions:
        click.echo(f"\n💼 Position Summary:")
        click.echo(f"   Open Positions: {positions['open_positions']}")
        click.echo(f"   Closed Positions: {positions['closed_positions']}")
        click.echo(f"   Total Open Value: ${positions['total_open_value']:,.2f}")
        click.echo(f"   Total Realized P&L: ${positions['total_realized_pnl']:,.2f}")

    # Equity curve (detailed only)
    if detailed:
        curve = data.get("equity_curve", [])
        if curve:
            click.echo(f"\n📈 Recent Equity Curve (last 10 trades):")
            for point in curve[-10:]:
                trade_result = "🟢" if point['trade_pnl'] > 0 else "🔴"
                click.echo(f"   {point['timestamp'][:10]} | {point['symbol']:6} | {trade_result} ${point['trade_pnl']:8,.2f} | Cumulative: ${point['cumulative_pnl']:,.2f}")

    click.echo("\n" + "="*70 + "\n")


@report.command()
@click.argument(
    'report_name',
    type=click.Choice(sorted(TRADE_REPORT_LAYOUTS.keys())),
)
@click.option('--symbol', help='Filter by symbol')
@click.option('--date-range', help=(
    'Date range filter. Formats: "today", "7d" (last 7 days), '
    '"YYYY-MM-DD/YYYY-MM-DD", "YYYY-MM-DD/" (to today), "/YYYY-MM-DD" (up to date).'
))
@require_authentication
def trades(report_name: str, symbol: str, date_range: str) -> None:
    """List completed trades using a named report layout."""
    try:
        from .trade_completion import TradeCompletionEngine
        from .dashboard import DashboardEngine
        from datetime import datetime

        # Parse date range if provided
        start_date, end_date = None, None
        if date_range:
            try:
                dashboard_engine = DashboardEngine()
                start_date, end_date = dashboard_engine.parse_date_range(date_range)
            except ValueError as e:
                click.echo(f"❌ Invalid date range: {e}", err=True)
                raise click.Abort()

        engine = TradeCompletionEngine()
        summary = engine.get_completed_trades_summary(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date
        )
        if "message" in summary:
            click.echo(summary["message"])
            return

        trades_list = summary.get("trades", []) or []

        # Load report layout
        layout = TRADE_REPORT_LAYOUTS.get(report_name)
        if not layout:
            available = ", ".join(sorted(TRADE_REPORT_LAYOUTS.keys()))
            click.echo(f"❌ Unknown trades report layout: '{report_name}'", err=True)
            click.echo(f"   Available layouts: {available}", err=True)
            raise click.Abort()

        layout_sort = layout.get("default_sort") or []

        if layout_sort:
            def _parse_ts(ts: str):
                if not ts:
                    return None
                try:
                    return datetime.fromisoformat(ts)
                except Exception:
                    return None

            def _sort_value(trade: dict, key: str):
                if key == "id":
                    return trade.get("id") or 0
                if key == "symbol":
                    return (trade.get("symbol") or "").upper()
                if key == "instrument_type":
                    return (trade.get("instrument_type") or "").upper()
                if key == "type":
                    return trade.get("type") or ""
                if key == "qty":
                    return trade.get("qty") or 0
                if key in ("date", "entm", "extm"):
                    opened = _parse_ts(trade.get("opened_at"))
                    closed = _parse_ts(trade.get("closed_at"))
                    if key == "date":
                        dt = opened or closed
                    elif key == "entm":
                        dt = opened
                    else:  # extm
                        dt = closed
                    return dt or datetime.min
                if key == "entry":
                    return trade.get("entry_price") or 0.0
                if key == "exit":
                    return trade.get("exit_price") or 0.0
                if key == "pnl":
                    return trade.get("pnl") or 0.0
                if key == "result":
                    return (trade.get("pnl") or 0.0) > 0
                if key == "pattern":
                    return (trade.get("setup_pattern") or "").lower()
                return 0

            sort_key_list = [k.lower() for k in layout_sort]
            trades_list = sorted(trades_list, key=lambda t: tuple(_sort_value(t, k) for k in sort_key_list))

        click.echo("📋 Completed Trades Report")
        if symbol:
            click.echo(f"Symbol: {symbol}")
        if date_range:
            click.echo(f"Date Range: {date_range}")
        click.echo(f"\n📊 Summary:")
        click.echo(f"   Total Trades: {summary['total_trades']}")
        click.echo(f"   Winning Trades: {summary['winning_trades']}")
        click.echo(f"   Losing Trades: {summary['losing_trades']}")
        click.echo(f"   Win Rate: {summary['win_rate']:.1f}%")
        click.echo(f"   Total P&L: ${summary['total_pnl']:.2f}")
        click.echo(f"   Average Win: ${summary['average_win']:.2f}")
        click.echo(f"   Average Loss: ${summary['average_loss']:.2f}")
        click.echo(f"\n📋 Trade Details:")
        # Table header based on layout columns
        header_cells = []
        for col_key in layout["columns"]:
            col_def = TRADE_COLUMN_DEFS.get(col_key)
            if not col_def:
                continue
            label = str(col_def.get("label", col_key))
            width = int(col_def.get("width", len(label)))
            align = str(col_def.get("align", "<"))
            header_cells.append(f"{label:{align}{width}}")
        click.echo(" | ".join(header_cells))
        # Separator line length roughly matches header length
        click.echo("-" * min(160, sum(int(TRADE_COLUMN_DEFS[c]["width"]) + 3 for c in layout["columns"] if c in TRADE_COLUMN_DEFS)))

        # Helper to format timestamps
        def _format_ts(ts: str):
            if not ts:
                return "", ""
            try:
                dt = datetime.fromisoformat(ts)
            except Exception:
                return "", ""
            return dt.strftime("%y%m%d"), dt.strftime("%H%M")

        # Table rows
        for trade in trades_list:
            status_emoji = "🟢" if trade['pnl'] > 0 else "🔴"
            result_label = "WIN" if trade['pnl'] > 0 else "LOSS"
            pattern = (trade.get('setup_pattern') or "")[:20]

            open_date, open_time = _format_ts(trade.get('opened_at'))
            close_date, close_time = _format_ts(trade.get('closed_at'))
            date_str = open_date or close_date
            entry_time = open_time
            exit_time = close_time

            row_cells = []
            for col_key in layout["columns"]:
                col_def = TRADE_COLUMN_DEFS.get(col_key)
                if not col_def:
                    continue
                width = int(col_def.get("width", 8))
                align = str(col_def.get("align", "<"))

                if col_key == "id":
                    value = str(trade.get("id", ""))
                elif col_key == "symbol":
                    value = str(trade.get("symbol", ""))
                elif col_key == "instrument_type":
                    value = str(trade.get("instrument_type") or "")
                elif col_key == "type":
                    value = str(trade.get("type", ""))
                elif col_key == "qty":
                    value = str(trade.get("qty") or "")
                elif col_key == "date":
                    value = date_str or ""
                elif col_key == "entm":
                    value = entry_time or ""
                elif col_key == "entry":
                    value = f"{trade.get('entry_price', 0.0):.4f}"
                elif col_key == "extm":
                    value = exit_time or ""
                elif col_key == "exit":
                    value = f"{trade.get('exit_price', 0.0):.4f}"
                elif col_key == "pnl":
                    value = f"{trade.get('pnl', 0.0):.2f}"
                elif col_key == "result":
                    value = f"{status_emoji} {result_label}"
                elif col_key == "pattern":
                    value = pattern
                else:
                    value = ""

                row_cells.append(f"{value:{align}{width}}")

            click.echo(" | ".join(row_cells))
    except Exception as e:
        click.echo(f"❌ Trade listing failed: {e}")
        raise click.Abort()


@report.command()
@click.option('--open-only', is_flag=True, help='Show only open positions')
@click.option('--symbol', help='Filter by symbol')
@require_authentication
def positions(open_only: bool, symbol: str) -> None:
    """Show position report."""
    try:
        from .positions import PositionTracker
        tracker = PositionTracker()
        summary = tracker.get_position_summary(symbol)
        click.echo("💼 Positions Report")
        if symbol:
            click.echo(f"Symbol: {symbol}")
        click.echo(f"📊 Summary:")
        click.echo(f"   Open Positions: {summary['open_positions']}")
        click.echo(f"   Closed Positions: {summary['closed_positions']}")
        click.echo(f"   Total Realized P&L: ${summary['total_realized_pnl']:.2f}")
        click.echo(f"   Total Open Value: ${summary['total_open_value']:.2f}")
        if summary['positions']:
            click.echo(f"\n📋 Position Details:")
            for pos in summary['positions']:
                if open_only and not pos['is_open']:
                    continue
                status = "🟢 OPEN" if pos['is_open'] else "🔴 CLOSED"
                click.echo(f"   {status} {pos['symbol']} ({pos['instrument_type']})")
                click.echo(f"      Qty: {pos['current_qty']}")
                click.echo(f"      Avg Cost: ${pos['avg_cost_basis']:.4f}")
                click.echo(f"      Market Value: ${pos['market_value']:.2f}")
                click.echo(f"      Realized P&L: ${pos['realized_pnl']:.2f}")
        else:
            click.echo("No positions found")
    except Exception as e:
        click.echo(f"❌ Position reporting failed: {e}")
        raise click.Abort()



@main.group()
def users() -> None:
    """User management commands (admin-only)."""
    pass


@users.command("list")
@click.option('--all', 'include_inactive', is_flag=True, help='Include inactive users')
@click.option('--format', 'output_format', type=click.Choice(['table', 'json', 'csv']), default='table', help='Output format')
@require_authentication
def list_users(include_inactive: bool, output_format: str) -> None:
    """List all users with trade counts."""
    # Check admin
    if not AuthContext.is_admin():
        click.echo("❌ Error: This command requires administrator privileges.", err=True)
        raise click.Abort()

    try:
        with db_manager.get_session() as session:
            manager = UserManager(session)
            users_list = manager.list_users(include_inactive=include_inactive)

            if output_format == 'json':
                import json
                output = {
                    'users': users_list,
                    'total_users': len(users_list),
                    'showing_inactive': include_inactive
                }
                click.echo(json.dumps(output, indent=2, default=str))
            elif output_format == 'csv':
                import csv
                import sys
                writer = csv.DictWriter(sys.stdout, fieldnames=[
                    'user_id', 'username', 'email', 'is_active', 'is_admin',
                    'trade_count', 'created_at', 'last_login_at'
                ])
                writer.writeheader()
                writer.writerows(users_list)
            else:  # table format
                click.echo("\n" + "=" * 80)
                click.echo("👥 USER MANAGEMENT")
                click.echo("=" * 80)

                active_count = sum(1 for u in users_list if u['is_active'])
                total_count = len(users_list)

                if include_inactive:
                    click.echo(f"\nAll Users ({active_count} active, {total_count - active_count} inactive)")
                else:
                    click.echo(f"\nActive Users ({active_count} of {total_count} total)")

                click.echo()
                click.echo(f"{'User ID':<8} | {'Username':<20} | {'Email':<30} | {'Admin':<6} | {'Active':<7} | {'Trades':<7} | {'Last Login':<20}")
                click.echo("-" * 80)

                for user in users_list:
                    user_id = str(user['user_id'])
                    username = user['username'][:20]
                    email = user['email'][:30]
                    is_admin = 'Yes' if user['is_admin'] else 'No'
                    is_active = 'Yes' if user['is_active'] else 'No'
                    trade_count = str(user['trade_count'])
                    last_login = user['last_login_at'].strftime('%Y-%m-%d %H:%M') if user['last_login_at'] else 'Never'

                    click.echo(f"{user_id:<8} | {username:<20} | {email:<30} | {is_admin:<6} | {is_active:<7} | {trade_count:<7} | {last_login:<20}")

                if not include_inactive:
                    click.echo(f"\nTo include inactive users: users list --all")
                click.echo()

    except Exception as e:
        click.echo(f"❌ User listing failed: {e}", err=True)
        raise click.Abort()


@users.command("create")
@click.option('--username', prompt=True, help='Username (3-100 chars, alphanumeric + underscore/hyphen)')
@click.option('--email', prompt=True, help='Email address')
@click.option('--admin', is_flag=True, help='Grant admin privileges')
@click.option('--password', default=None, help='Web login password (optional; prompted if omitted)')
@require_authentication
def create_user(username: str, email: str, admin: bool, password: str) -> None:
    """Create a new user with automatic API key generation."""
    from werkzeug.security import generate_password_hash

    # Check admin
    if not AuthContext.is_admin():
        click.echo("❌ Error: This command requires administrator privileges.", err=True)
        raise click.Abort()

    # Prompt for password if not supplied
    if password is None:
        password = click.prompt(
            "Web login password (leave blank to skip)",
            default='',
            hide_input=True,
            confirmation_prompt=False,
        )

    try:
        with db_manager.get_session() as session:
            manager = UserManager(session)
            user, raw_api_key = manager.create_user(username, email, is_admin=admin)

            if password:
                user.password_hash = generate_password_hash(password)

            session.commit()

            click.echo(f"\n✅ Successfully created user '{username}' (ID: {user.user_id})")
            if admin:
                click.echo("   Admin privileges: Granted")
            if password:
                click.echo("   Web login password: set")

            click.echo("\n" + "=" * 80)
            click.echo("🔑 API KEY - SAVE THIS NOW (shown only once)")
            click.echo("=" * 80)
            click.echo(f"\n{raw_api_key}\n")
            click.echo("⚠️  This API key will NOT be shown again. Save it securely.")
            click.echo("=" * 80 + "\n")

    except ValueError as e:
        click.echo(f"❌ Error: {e}", err=True)
        raise click.Abort()
    except Exception as e:
        click.echo(f"❌ User creation failed: {e}", err=True)
        raise click.Abort()


@users.command("deactivate")
@click.option('--user-id', type=int, required=True, help='User ID to deactivate')
@require_authentication
def deactivate_user(user_id: int) -> None:
    """Deactivate a user account."""
    # Check admin
    if not AuthContext.is_admin():
        click.echo("❌ Error: This command requires administrator privileges.", err=True)
        raise click.Abort()

    try:
        with db_manager.get_session() as session:
            manager = UserManager(session)
            user = manager.deactivate_user(user_id)
            session.commit()
            click.echo(f"✅ Successfully deactivated user '{user.username}' (ID: {user_id})")

    except ValueError as e:
        click.echo(f"❌ Error: {e}", err=True)
        raise click.Abort()
    except Exception as e:
        click.echo(f"❌ User deactivation failed: {e}", err=True)
        raise click.Abort()


@users.command("reactivate")
@click.option('--user-id', type=int, required=True, help='User ID to reactivate')
@require_authentication
def reactivate_user(user_id: int) -> None:
    """Reactivate a previously deactivated user account."""
    # Check admin
    if not AuthContext.is_admin():
        click.echo("❌ Error: This command requires administrator privileges.", err=True)
        raise click.Abort()

    try:
        with db_manager.get_session() as session:
            manager = UserManager(session)
            user = manager.reactivate_user(user_id)
            session.commit()
            click.echo(f"✅ Successfully reactivated user '{user.username}' (ID: {user_id})")

    except ValueError as e:
        click.echo(f"❌ Error: {e}", err=True)
        raise click.Abort()
    except Exception as e:
        click.echo(f"❌ User reactivation failed: {e}", err=True)
        raise click.Abort()


@users.command("make-admin")
@click.option('--user-id', type=int, required=True, help='User ID to grant admin privileges')
@require_authentication
def make_admin(user_id: int) -> None:
    """Grant admin privileges to a user."""
    # Check admin
    if not AuthContext.is_admin():
        click.echo("❌ Error: This command requires administrator privileges.", err=True)
        raise click.Abort()

    try:
        with db_manager.get_session() as session:
            manager = UserManager(session)
            user = manager.make_admin(user_id)
            session.commit()
            click.echo(f"✅ Successfully granted admin privileges to user '{user.username}' (ID: {user_id})")

    except ValueError as e:
        click.echo(f"❌ Error: {e}", err=True)
        raise click.Abort()
    except Exception as e:
        click.echo(f"❌ Admin privilege grant failed: {e}", err=True)
        raise click.Abort()


@users.command("revoke-admin")
@click.option('--user-id', type=int, required=True, help='User ID to revoke admin privileges')
@require_authentication
def revoke_admin(user_id: int) -> None:
    """Revoke admin privileges from a user."""
    # Check admin
    if not AuthContext.is_admin():
        click.echo("❌ Error: This command requires administrator privileges.", err=True)
        raise click.Abort()

    try:
        with db_manager.get_session() as session:
            manager = UserManager(session)
            user = manager.revoke_admin(user_id)
            session.commit()
            click.echo(f"✅ Successfully revoked admin privileges from user '{user.username}' (ID: {user_id})")

    except ValueError as e:
        click.echo(f"❌ Error: {e}", err=True)
        raise click.Abort()
    except Exception as e:
        click.echo(f"❌ Admin privilege revocation failed: {e}", err=True)
        raise click.Abort()


@users.command("delete")
@click.option('--user-id', type=int, required=True, help='User ID to delete')
@click.option('--confirm', is_flag=True, help='Skip confirmation prompt')
@require_authentication
def delete_user(user_id: int, confirm: bool) -> None:
    """Delete a user account (prevents deletion if user has trades)."""
    # Check admin
    if not AuthContext.is_admin():
        click.echo("❌ Error: This command requires administrator privileges.", err=True)
        raise click.Abort()

    try:
        with db_manager.get_session() as session:
            manager = UserManager(session)
            user = manager.get_user_or_raise(user_id)

            # Confirmation prompt
            if not confirm:
                if not click.confirm(f"⚠️  Are you sure you want to delete user '{user.username}' (ID: {user_id})?"):
                    click.echo("Delete operation cancelled.")
                    return

            manager.delete_user(user_id)
            session.commit()
            click.echo(f"✅ Successfully deleted user '{user.username}' (ID: {user_id})")

    except ValueError as e:
        click.echo(f"❌ Error: {e}", err=True)
        raise click.Abort()
    except Exception as e:
        click.echo(f"❌ User deletion failed: {e}", err=True)
        raise click.Abort()


@users.command("regenerate-key")
@click.option('--user-id', type=int, required=True, help='User ID to regenerate API key')
@require_authentication
def regenerate_key(user_id: int) -> None:
    """Regenerate a user's API key (invalidates old key)."""
    # Check admin
    if not AuthContext.is_admin():
        click.echo("❌ Error: This command requires administrator privileges.", err=True)
        raise click.Abort()

    try:
        with db_manager.get_session() as session:
            manager = UserManager(session)
            user, raw_api_key = manager.regenerate_api_key(user_id)
            session.commit()

            click.echo(f"\n✅ Successfully regenerated API key for user '{user.username}' (ID: {user_id})")

            click.echo("\n" + "=" * 80)
            click.echo("🔑 NEW API KEY - SAVE THIS NOW (shown only once)")
            click.echo("=" * 80)
            click.echo(f"\n{raw_api_key}\n")
            click.echo("⚠️  This API key will NOT be shown again. The old key is now invalid.")
            click.echo("=" * 80 + "\n")

    except ValueError as e:
        click.echo(f"❌ Error: {e}", err=True)
        raise click.Abort()
    except Exception as e:
        click.echo(f"❌ API key regeneration failed: {e}", err=True)
        raise click.Abort()


@users.command("purge-data")
@click.option('--user-id', type=int, required=True, help='User ID whose data should be purged')
@click.option('--force', is_flag=True, help='Skip confirmation prompts (dangerous!)')
@click.option('--dry-run', is_flag=True, help='Preview deletion counts without actually deleting')
@require_authentication
def purge_data(user_id: int, force: bool, dry_run: bool) -> None:
    """
    Purge all data for a specific user (ADMIN ONLY).

    This command deletes all trades, positions, completed trades, setup patterns,
    and processing logs for the specified user. The user account itself is preserved.

    ⚠️  WARNING: This operation is IRREVERSIBLE!
    """
    # Check admin
    if not AuthContext.is_admin():
        click.echo("❌ Error: This command requires administrator privileges.", err=True)
        raise click.Abort()

    try:
        with db_manager.get_session() as session:
            manager = UserManager(session)

            # Get user info for display
            user = manager.get_user_or_raise(user_id)

            # Get counts (dry-run mode to preview)
            counts = manager.purge_user_data(user_id, dry_run=True)

            # Display preview
            click.echo("\n" + "=" * 70)
            click.echo(f"Data Purge Preview for User: {user.username} (ID: {user_id})")
            click.echo("=" * 70)
            click.echo(f"  Trades (executions):        {counts['trades']:>6}")
            click.echo(f"  Completed Trades:           {counts['completed_trades']:>6}")
            click.echo(f"  Positions:                  {counts['positions']:>6}")
            click.echo(f"  Setup Patterns:             {counts['setup_patterns']:>6}")
            click.echo(f"  Processing Logs:            {counts['processing_log']:>6}")
            click.echo("-" * 70)
            click.echo(f"  TOTAL RECORDS:              {counts['total']:>6}")
            click.echo("=" * 70)

            # Dry-run mode: just show preview and exit
            if dry_run:
                click.echo("\n✅ DRY RUN: No data was deleted.")
                click.echo(f"   Use without --dry-run to actually purge {counts['total']} records.\n")
                return

            # Check if there's anything to delete
            if counts['total'] == 0:
                click.echo(f"\n✅ User '{user.username}' has no data to purge.\n")
                return

            # Triple confirmation for actual deletion
            click.echo(f"\n⚠️  WARNING: This operation is IRREVERSIBLE!")
            click.echo(f"All {counts['total']} records for user '{user.username}' will be permanently deleted.")
            click.echo(f"The user account will be preserved but will have no associated data.\n")

            # First confirmation: Yes/No prompt
            if not force:
                if not click.confirm("Are you absolutely sure you want to continue?"):
                    click.echo("\n❌ Operation cancelled.\n")
                    raise click.Abort()

                # Second confirmation: Type username
                click.echo(f"\nType the username '{user.username}' to confirm deletion:")
                confirmation = click.prompt("Username", type=str)

                if confirmation != user.username:
                    click.echo(f"\n❌ Username mismatch. Operation cancelled.\n")
                    raise click.Abort()

            # Perform the actual purge
            click.echo(f"\nPurging data for user {user_id}...")
            actual_counts = manager.purge_user_data(user_id, dry_run=False)
            session.commit()

            # Report success
            click.echo("\n" + "=" * 70)
            click.echo("✅ SUCCESS: Data Purge Complete")
            click.echo("=" * 70)
            click.echo(f"  Trades deleted:             {actual_counts['trades']:>6}")
            click.echo(f"  Completed Trades deleted:   {actual_counts['completed_trades']:>6}")
            click.echo(f"  Positions deleted:          {actual_counts['positions']:>6}")
            click.echo(f"  Setup Patterns deleted:     {actual_counts['setup_patterns']:>6}")
            click.echo(f"  Processing Logs deleted:    {actual_counts['processing_log']:>6}")
            click.echo("-" * 70)
            click.echo(f"  TOTAL DELETED:              {actual_counts['total']:>6}")
            click.echo("=" * 70)
            click.echo(f"\nUser account '{user.username}' (ID: {user_id}) still exists but has no data.\n")

    except ValueError as e:
        click.echo(f"❌ Error: {e}", err=True)
        raise click.Abort()
    except Exception as e:
        click.echo(f"❌ Data purge failed: {e}", err=True)
        raise click.Abort()


if __name__ == "__main__":
    main()
