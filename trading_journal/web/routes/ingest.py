"""Ingest route: GET/POST /upload."""

import os
import tempfile
import logging
from pathlib import Path

from flask import Blueprint, flash, redirect, render_template, request, url_for

from ..auth import login_required
from ...authorization import AuthContext
from ...csv_parser import CsvParser
from ...ninjatrader_parser import NinjaTraderParser, is_ninjatrader_exec_file
from ...ingestion import NdjsonIngester, IngestionError
from ...market_data import enrich_missing_underlying_prices
from ...trade_completion import TradeCompletionEngine

bp = Blueprint('ingest', __name__)
logger = logging.getLogger(__name__)


@bp.route('/upload', methods=['GET'])
@login_required
def upload_form():
    return render_template('ingest/upload.html', user=AuthContext.get_current_user())


@bp.route('/upload', methods=['POST'])
@login_required
def upload():
    files = request.files.getlist('files')
    if not files or all(f.filename == '' for f in files):
        flash('No files selected.', 'warning')
        return redirect(url_for('ingest.upload_form'))

    include_rolling = bool(request.form.get('include_rolling'))
    dry_run = bool(request.form.get('dry_run'))
    tmpdir = tempfile.mkdtemp()
    saved_paths = []

    try:
        # Save uploaded files to temp dir
        for f in files:
            if f.filename:
                dest = os.path.join(tmpdir, Path(f.filename).name)
                f.save(dest)
                saved_paths.append(dest)

        if not saved_paths:
            flash('No valid files to process.', 'warning')
            return redirect(url_for('ingest.upload_form'))

        # Parse CSVs — detect NinjaTrader exec files and route to the right parser
        schwab_paths = []
        records = []
        for path in saved_paths:
            if is_ninjatrader_exec_file(path):
                records.extend(NinjaTraderParser().parse_file(path))
            else:
                schwab_paths.append(path)
        if schwab_paths:
            records.extend(CsvParser(include_rolling=include_rolling).parse_files(schwab_paths))

        # Ingest into DB (dry_run=True skips all writes)
        ingester = NdjsonIngester()
        result = ingester.ingest_records(records, dry_run=dry_run)

        if dry_run:
            # Build per-symbol breakdown from parsed fills
            fills = [r for r in records if r.get('event_type') == 'fill']
            by_symbol = {}
            for r in fills:
                sym = r.get('symbol', 'UNKNOWN')
                if sym not in by_symbol:
                    by_symbol[sym] = {'buys': 0, 'sells': 0, 'net_qty': 0}
                side = r.get('side', '')
                qty = abs(r.get('qty', 0) or 0)
                if side == 'BUY':
                    by_symbol[sym]['buys'] += 1
                    by_symbol[sym]['net_qty'] += qty
                elif side == 'SELL':
                    by_symbol[sym]['sells'] += 1
                    by_symbol[sym]['net_qty'] -= qty

            dry_run_results = {
                'file_count': len(saved_paths),
                'file_names': [Path(p).name for p in saved_paths],
                'fill_count': len(fills),
                'records_processed': result['records_processed'],
                'records_failed': result['records_failed'],
                'validation_errors': result['validation_errors'],
                'success': result['success'],
                'by_symbol': sorted(by_symbol.items()),
                'include_rolling': include_rolling,
            }
            return render_template(
                'ingest/upload.html',
                user=AuthContext.get_current_user(),
                dry_run_results=dry_run_results,
                include_rolling=include_rolling,
            )

        # Reprocess all completed trades from scratch (idempotent on re-uploads)
        user_id = AuthContext.require_user().user_id
        engine = TradeCompletionEngine()
        proc = engine.reprocess_all_completed_trades(user_id)

        # Auto-populate underlying_at_entry for option trades (background, fire-and-forget)
        import threading
        from ...market_data import enrich_missing_underlying_prices as _enrich
        client_enabled = bool(os.environ.get('MASSIVE_API_KEY'))
        if client_enabled:
            threading.Thread(
                target=_enrich, args=(user_id,), daemon=True
            ).start()
            enrichment_msg = " Enrichment running in background."
        else:
            enrichment_msg = ""

        flash(
            f"Imported {result['inserts']} new, updated {result['updates']}. "
            f"{proc.get('completed_trades', 0)} trades completed.{enrichment_msg}",
            'success',
        )
        if result['validation_errors']:
            for err in result['validation_errors'][:5]:
                flash(f"Warning: {err}", 'warning')

        return redirect(url_for('trades.index'))

    except IngestionError as e:
        logger.error(f"Ingestion error: {e}")
        flash(f"Ingestion failed: {e}", 'danger')
        return redirect(url_for('ingest.upload_form'))
    except Exception as e:
        logger.exception("Unexpected upload error")
        flash(f"Unexpected error: {e}", 'danger')
        return redirect(url_for('ingest.upload_form'))
    finally:
        # Clean up temp dir
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)
