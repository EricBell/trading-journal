"""Command-line interface for trading journal."""

import logging
from pathlib import Path

import click
from alembic import command
from alembic.config import Config

from .database import db_manager
from .config import logging_config

# Set up logging
logging.basicConfig(
    level=getattr(logging, logging_config.level),
    format=logging_config.format,
    handlers=[
        logging.FileHandler(logging_config.file),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


@click.group()
@click.version_option()
def main() -> None:
    """Trading Journal - PostgreSQL-based trading data ingestion and analysis."""
    pass


@main.group()
def db() -> None:
    """Database management commands."""
    pass


@db.command()
def migrate() -> None:
    """Run database migrations."""
    try:
        # Get Alembic configuration
        alembic_cfg = Config("alembic.ini")

        # Run migrations
        command.upgrade(alembic_cfg, "head")
        click.echo("✅ Database migrations completed successfully")

    except Exception as e:
        click.echo(f"❌ Migration failed: {e}")
        raise click.Abort()


@db.command()
def status() -> None:
    """Check database connection and migration status."""
    try:
        # Test database connection
        if db_manager.test_connection():
            click.echo("✅ Database connection: OK")
        else:
            click.echo("❌ Database connection: FAILED")
            raise click.Abort()

        # Check current migration version
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


@db.command()
@click.option('--symbol', help='Process only specific symbol')
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


@ingest.command("file")
@click.argument('file_path', type=click.Path(exists=True, path_type=Path))
@click.option('--dry-run', is_flag=True, help='Validate without database changes')
@click.option('--verbose', is_flag=True, help='Enable verbose output')
def ingest_file(file_path: Path, dry_run: bool, verbose: bool) -> None:
    """Ingest a single NDJSON file."""
    from .ingestion import NdjsonIngester, IngestionError

    if dry_run:
        click.echo("🔍 DRY RUN MODE - No database changes will be made")

    try:
        ingester = NdjsonIngester()
        result = ingester.process_file(file_path, dry_run=dry_run, verbose=verbose)

        # Display results
        click.echo(f"📁 File: {result['file_path']}")
        click.echo(f"✅ Records processed: {result['records_processed']}")
        click.echo(f"❌ Records failed: {result['records_failed']}")

        if result['validation_errors']:
            click.echo(f"⚠️  Validation errors:")
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


@ingest.command("batch")
@click.argument('pattern', default='*.ndjson')
@click.option('--output-summary', is_flag=True, help='Show processing summary')
@click.option('--dry-run', is_flag=True, help='Validate without database changes')
def ingest_batch(pattern: str, output_summary: bool, dry_run: bool) -> None:
    """Ingest multiple NDJSON files matching pattern."""
    from .ingestion import NdjsonIngester, IngestionError

    if dry_run:
        click.echo("🔍 DRY RUN MODE - No database changes will be made")

    try:
        ingester = NdjsonIngester()
        result = ingester.process_batch(pattern, dry_run=dry_run, verbose=output_summary)

        # Display batch summary
        click.echo(f"\n📊 Batch Processing Summary")
        click.echo(f"📁 Files processed: {result['files_processed']}")
        click.echo(f"❌ Files failed: {result['files_failed']}")
        click.echo(f"✅ Total records processed: {result['total_records_processed']}")
        click.echo(f"❌ Total records failed: {result['total_records_failed']}")

        if output_summary:
            click.echo(f"\n📋 File Details:")
            for file_result in result['results']:
                if 'error' in file_result:
                    click.echo(f"   ❌ {file_result['file_path']}: {file_result['error']}")
                else:
                    click.echo(f"   ✅ {file_result['file_path']}: {file_result['records_processed']} records")

        if result['files_failed'] == 0:
            click.echo("🎉 Batch processing completed successfully")
        else:
            click.echo("⚠️  Batch processing completed with errors")

    except IngestionError as e:
        click.echo(f"❌ Batch ingestion failed: {e}")
        raise click.Abort()
    except Exception as e:
        click.echo(f"❌ Unexpected error: {e}")
        raise click.Abort()


@main.group()
def report() -> None:
    """Reporting commands."""
    pass


@report.command()
@click.option('--date-range', help='Date range in format YYYY-MM-DD,YYYY-MM-DD')
def dashboard(date_range: str) -> None:
    """Generate dashboard metrics."""
    try:
        # TODO: Implement dashboard reporting
        click.echo("📊 Dashboard Report")
        click.echo("⚠️  Dashboard reporting not yet implemented")

    except Exception as e:
        click.echo(f"❌ Dashboard generation failed: {e}")
        raise click.Abort()


@report.command()
@click.option('--symbol', help='Filter by symbol')
@click.option('--date-range', help='Date range in format YYYY-MM-DD,YYYY-MM-DD')
@click.option('--format', 'output_format', default='table', type=click.Choice(['table', 'json', 'csv']))
def trades(symbol: str, date_range: str, output_format: str) -> None:
    """List completed trades."""
    try:
        from .trade_completion import TradeCompletionEngine

        engine = TradeCompletionEngine()
        summary = engine.get_completed_trades_summary(symbol)

        if "message" in summary:
            click.echo(summary["message"])
            return

        click.echo("📋 Completed Trades Report")
        if symbol:
            click.echo(f"Symbol: {symbol}")

        click.echo(f"\n📊 Summary:")
        click.echo(f"   Total Trades: {summary['total_trades']}")
        click.echo(f"   Winning Trades: {summary['winning_trades']}")
        click.echo(f"   Losing Trades: {summary['losing_trades']}")
        click.echo(f"   Win Rate: {summary['win_rate']:.1f}%")
        click.echo(f"   Total P&L: ${summary['total_pnl']:.2f}")
        click.echo(f"   Average Win: ${summary['average_win']:.2f}")
        click.echo(f"   Average Loss: ${summary['average_loss']:.2f}")

        if output_format == 'json':
            import json
            click.echo(json.dumps(summary, indent=2, default=str))
        else:
            # Table format
            click.echo(f"\n📋 Trade Details:")
            for trade in summary['trades']:
                status = "🟢 WIN" if trade['pnl'] > 0 else "🔴 LOSS"
                click.echo(f"   {status} {trade['symbol']} {trade['type']}")
                click.echo(f"      Qty: {trade['qty']}")
                click.echo(f"      Entry: ${trade['entry_price']:.4f}")
                click.echo(f"      Exit: ${trade['exit_price']:.4f}")
                click.echo(f"      P&L: ${trade['pnl']:.2f}")
                if trade['setup_pattern']:
                    click.echo(f"      Pattern: {trade['setup_pattern']}")
                if trade['notes']:
                    click.echo(f"      Notes: {trade['notes']}")

    except Exception as e:
        click.echo(f"❌ Trade listing failed: {e}")
        raise click.Abort()


@report.command()
@click.option('--open-only', is_flag=True, help='Show only open positions')
@click.option('--symbol', help='Filter by symbol')
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
def pattern() -> None:
    """Setup pattern management commands."""
    pass


@pattern.command()
@click.option('--completed-trade-id', type=int, help='Completed trade ID to annotate')
@click.option('--symbol', help='Symbol to annotate (for bulk operations)')
@click.option('--date', help='Date in YYYY-MM-DD format (for bulk operations)')
@click.option('--pattern', required=True, help='Setup pattern name')
def annotate(completed_trade_id: int, symbol: str, date: str, pattern: str) -> None:
    """Annotate completed trades with setup patterns."""
    try:
        # TODO: Implement pattern annotation
        if completed_trade_id:
            click.echo(f"Annotating trade {completed_trade_id} with pattern: {pattern}")
        elif symbol and date:
            click.echo(f"Annotating {symbol} trades on {date} with pattern: {pattern}")
        else:
            click.echo("Please specify either --completed-trade-id or both --symbol and --date")
            return

        click.echo("⚠️  Pattern annotation not yet implemented")

    except Exception as e:
        click.echo(f"❌ Pattern annotation failed: {e}")
        raise click.Abort()


@pattern.command("list")
def list_patterns() -> None:
    """List all unique patterns used."""
    try:
        # TODO: Implement pattern listing
        click.echo("📝 Setup Patterns")
        click.echo("⚠️  Pattern listing not yet implemented")

    except Exception as e:
        click.echo(f"❌ Pattern listing failed: {e}")
        raise click.Abort()


@main.group()
def notes() -> None:
    """Trade notes management commands."""
    pass


@notes.command("add")
@click.option('--completed-trade-id', type=int, required=True, help='Completed trade ID')
@click.option('--text', required=True, help='Note text')
def add_note(completed_trade_id: int, text: str) -> None:
    """Add notes to a completed trade."""
    try:
        # TODO: Implement note addition
        click.echo(f"Adding note to trade {completed_trade_id}: {text}")
        click.echo("⚠️  Note addition not yet implemented")

    except Exception as e:
        click.echo(f"❌ Note addition failed: {e}")
        raise click.Abort()


@notes.command("show")
@click.option('--completed-trade-id', type=int, required=True, help='Completed trade ID')
def show_notes(completed_trade_id: int) -> None:
    """Show notes for a completed trade."""
    try:
        # TODO: Implement note display
        click.echo(f"Notes for trade {completed_trade_id}:")
        click.echo("⚠️  Note display not yet implemented")

    except Exception as e:
        click.echo(f"❌ Note display failed: {e}")
        raise click.Abort()


if __name__ == "__main__":
    main()