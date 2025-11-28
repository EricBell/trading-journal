"""Command-line interface for trading journal."""

import logging
from pathlib import Path

import click
from alembic import command
from alembic.config import Config

from .database import db_manager
from .config import logging_config
from .models import CompletedTrade
from .cli_auth import require_authentication, AuthContext
from .user_management import UserManager


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


@ingest.command("file")
@click.argument('file_path', type=click.Path(exists=True, path_type=Path))
@click.option('--dry-run', is_flag=True, help='Validate without database changes')
@click.option('--verbose', is_flag=True, help='Enable verbose output')
@require_authentication
def ingest_file(file_path: Path, dry_run: bool, verbose: bool) -> None:
    """Ingest a single NDJSON file."""
    from .ingestion import NdjsonIngester, IngestionError
    if dry_run:
        click.echo("🔍 DRY RUN MODE - No database changes will be made")
    try:
        ingester = NdjsonIngester()
        result = ingester.process_file(file_path, dry_run=dry_run, verbose=verbose)
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
@require_authentication
def ingest_batch(pattern: str, output_summary: bool, dry_run: bool) -> None:
    """Ingest multiple NDJSON files matching pattern."""
    from .ingestion import NdjsonIngester, IngestionError
    if dry_run:
        click.echo("🔍 DRY RUN MODE - No database changes will be made")
    try:
        ingester = NdjsonIngester()
        result = ingester.process_batch(pattern, dry_run=dry_run, verbose=output_summary)
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


@main.group()
def trades() -> None:
    """Completed trade management commands."""
    pass


@trades.command("show")
@click.option('--completed-trade-id', type=int, required=True, help='Completed trade ID')
@require_authentication
def show_trade(completed_trade_id: int) -> None:
    """Show details for a single completed trade and its executions."""
    try:
        user_id = AuthContext.require_user().user_id
        with db_manager.get_session() as session:
            trade = session.query(CompletedTrade).filter_by(
                completed_trade_id=completed_trade_id,
                user_id=user_id
            ).one_or_none()

            if not trade:
                click.echo(f"❌ Error: Completed trade with ID {completed_trade_id} not found.", err=True)
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
@click.option('--date-range', help='Date range in format YYYY-MM-DD,YYYY-MM-DD')
@click.option('--symbol', help='Filter by symbol')
@click.option('--format', 'output_format', default='summary', type=click.Choice(['summary', 'detailed', 'json']))
@require_authentication
def dashboard(date_range: str, symbol: str, output_format: str) -> None:
    """Generate dashboard metrics."""
    try:
        from .dashboard import DashboardEngine
        import json

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

        # Output format
        if output_format == 'json':
            click.echo(json.dumps(dashboard_data, indent=2, default=str))
            return

        # Summary or detailed format
        _display_dashboard_summary(dashboard_data, detailed=(output_format == 'detailed'))

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
            click.echo(f"\n📋 Trade Details:")
            for trade in summary['trades']:
                status = "🟢 WIN" if trade['pnl'] > 0 else "🔴 LOSS"
                click.echo(f"   Trade ID: {trade['id']} - {status} {trade['symbol']} {trade['type']}")
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
        if not completed_trade_id:
            click.echo("Error: --completed-trade-id is required for this operation.", err=True)
            raise click.Abort()
        with db_manager.get_session() as session:
            trade = session.query(CompletedTrade).filter_by(completed_trade_id=completed_trade_id).one_or_none()
            if not trade:
                click.echo(f"❌ Error: Completed trade with ID {completed_trade_id} not found.", err=True)
                raise click.Abort()
            trade.setup_pattern = pattern
            session.commit()
            click.echo(f"✅ Successfully annotated trade {completed_trade_id} with pattern: '{pattern}'")
    except Exception as e:
        click.echo(f"❌ Pattern annotation failed: {e}", err=True)
        raise click.Abort()


@pattern.command("list")


@require_authentication


def list_patterns() -> None:


    """List all unique patterns used."""


    try:


        user_id = AuthContext.require_user().user_id


        with db_manager.get_session() as session:


            patterns = session.query(CompletedTrade.setup_pattern).filter(


                CompletedTrade.user_id == user_id,


                CompletedTrade.setup_pattern.isnot(None),


                CompletedTrade.setup_pattern != ''


            ).distinct().all()





            if not patterns:


                click.echo("No setup patterns found.")


                return





            click.echo("📝 Unique Setup Patterns:")


            for (pattern,) in patterns:


                click.echo(f"- {pattern}")





    except Exception as e:


        click.echo(f"❌ Pattern listing failed: {e}", err=True)


        raise click.Abort()








@pattern.command("performance")


@click.option('--pattern', required=True, help='The setup pattern to analyze.')


@require_authentication


def pattern_performance(pattern: str) -> None:


    """Analyze the performance of a specific setup pattern."""


    try:


        user_id = AuthContext.require_user().user_id


        with db_manager.get_session() as session:


            trades = session.query(CompletedTrade).filter(


                CompletedTrade.user_id == user_id,


                CompletedTrade.setup_pattern == pattern


            ).all()





            if not trades:


                click.echo(f"No trades found for pattern: '{pattern}'")


                return





            total_trades = len(trades)


            winning_trades = len([t for t in trades if t.is_winning_trade])


            losing_trades = total_trades - winning_trades


            win_rate = (winning_trades / total_trades) * 100 if total_trades > 0 else 0


            total_pnl = sum(t.net_pnl for t in trades)





            click.echo(f"📈 Performance for pattern: '{pattern}'")


            click.echo(f"   Total Trades: {total_trades}")


            click.echo(f"   Winning Trades: {winning_trades}")


            click.echo(f"   Losing Trades: {losing_trades}")


            click.echo(f"   Win Rate: {win_rate:.2f}%")


            click.echo(f"   Total P&L: ${total_pnl:.2f}")





    except Exception as e:


        click.echo(f"❌ Pattern performance analysis failed: {e}", err=True)


        raise click.Abort()








@main.group()


def notes() -> None:
    """Trade notes management commands."""
    pass


@notes.command("add")
@click.option('--completed-trade-id', type=int, required=True, help='Completed trade ID')
@click.option('--text', required=True, help='Note text')
@require_authentication
def add_note(completed_trade_id: int, text: str) -> None:
    """Add notes to a completed trade."""
    try:
        with db_manager.get_session() as session:
            trade = session.query(CompletedTrade).filter_by(completed_trade_id=completed_trade_id).one_or_none()
            if not trade:
                click.echo(f"❌ Error: Completed trade with ID {completed_trade_id} not found.", err=True)
                raise click.Abort()
            trade.trade_notes = text
            session.commit()
            click.echo(f"✅ Successfully added note to trade {completed_trade_id}.")
    except Exception as e:
        click.echo(f"❌ Note addition failed: {e}", err=True)
        raise click.Abort()


@notes.command("show")
@click.option('--completed-trade-id', type=int, required=True, help='Completed trade ID')
@require_authentication
def show_notes(completed_trade_id: int) -> None:
    """Show notes for a completed trade."""
    try:
        user_id = AuthContext.require_user().user_id
        with db_manager.get_session() as session:
            trade = session.query(CompletedTrade).filter_by(
                completed_trade_id=completed_trade_id,
                user_id=user_id
            ).one_or_none()
            if not trade:
                click.echo(f"❌ Error: Completed trade with ID {completed_trade_id} not found.", err=True)
                raise click.Abort()
            click.echo(f"🗒️ Notes for trade {completed_trade_id}:")
            if trade.trade_notes:
                click.echo(trade.trade_notes)
            else:
                click.echo("No notes found for this trade.")
    except Exception as e:
        click.echo(f"❌ Note display failed: {e}", err=True)
        raise click.Abort()


@notes.command("edit")
@click.option('--completed-trade-id', type=int, required=True, help='Completed trade ID')
@click.option('--text', required=True, help='New note text')
@require_authentication
def edit_note(completed_trade_id: int, text: str) -> None:
    """Edit the notes for a completed trade."""
    try:
        user_id = AuthContext.require_user().user_id
        with db_manager.get_session() as session:
            trade = session.query(CompletedTrade).filter_by(
                completed_trade_id=completed_trade_id,
                user_id=user_id
            ).one_or_none()

            if not trade:
                click.echo(f"❌ Error: Completed trade with ID {completed_trade_id} not found.", err=True)
                raise click.Abort()

            trade.trade_notes = text
            session.commit()
            click.echo(f"✅ Successfully edited note for trade {completed_trade_id}.")

    except Exception as e:
        click.echo(f"❌ Note editing failed: {e}", err=True)
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
@require_authentication
def create_user(username: str, email: str, admin: bool) -> None:
    """Create a new user with automatic API key generation."""
    # Check admin
    if not AuthContext.is_admin():
        click.echo("❌ Error: This command requires administrator privileges.", err=True)
        raise click.Abort()

    try:
        with db_manager.get_session() as session:
            manager = UserManager(session)
            user, raw_api_key = manager.create_user(username, email, is_admin=admin)
            session.commit()

            click.echo(f"\n✅ Successfully created user '{username}' (ID: {user.user_id})")
            if admin:
                click.echo("   Admin privileges: Granted")

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


if __name__ == "__main__":
    main()