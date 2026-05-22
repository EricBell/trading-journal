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
from ...observability import UploadPerfLogger

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

    ul = UploadPerfLogger.from_env()
    session_id = UploadPerfLogger.new_session_id()

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

        user_id = AuthContext.require_user().user_id
        total_file_bytes = sum(os.path.getsize(p) for p in saved_paths)

        ul.event('upload_received', {
            'upload_session_id': session_id,
            'user_id': user_id,
            'file_count': len(saved_paths),
            'filenames': [Path(p).name for p in saved_paths],
            'file_size_bytes': total_file_bytes,
            'dry_run': dry_run,
        })

        # Parse CSVs — detect NinjaTrader exec files and route to the right parser
        schwab_paths = []
        records = []
        with ul.stage("csv_parse", upload_session_id=session_id, user_id=user_id,
                      file_count=len(saved_paths)) as ctx:
            for path in saved_paths:
                if is_ninjatrader_exec_file(path):
                    records.extend(NinjaTraderParser().parse_file(path))
                else:
                    schwab_paths.append(path)
            if schwab_paths:
                records.extend(CsvParser(include_rolling=include_rolling).parse_files(schwab_paths))
            ctx['records_emitted'] = len(records)
            ctx['fills'] = sum(1 for r in records if r.get('event_type') == 'fill')

        # Ingest into DB (dry_run=True skips all writes)
        ingester = NdjsonIngester()
        result = ingester.ingest_records(
            records,
            dry_run=dry_run,
            upload_logger=ul,
            upload_session_id=session_id,
        )

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
        engine = TradeCompletionEngine()
        with ul.stage("completed_trade_rebuild", upload_session_id=session_id, user_id=user_id) as ctx:
            proc = engine.reprocess_all_completed_trades(user_id)
            ctx['completed_trades'] = proc.get('completed_trades', 0)

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

        ul.event('upload_complete', {
            'upload_session_id': session_id,
            'user_id': user_id,
            'records_inserted': result['inserts'],
            'records_updated': result['updates'],
            'completed_trades': proc.get('completed_trades', 0),
            **ul.summary(),
        })

        flash(
            f"Imported {result['inserts']} new, updated {result['updates']}. "
            f"{proc.get('completed_trades', 0)} trades completed.{enrichment_msg}",
            'success',
        )
        if result['validation_errors']:
            for err in result['validation_errors'][:5]:
                flash(f"Warning: {err}", 'warning')

        return redirect(url_for('trades.index'))

    except (IngestionError, Exception) as e:
        is_ingestion_err = isinstance(e, IngestionError)
        if is_ingestion_err:
            logger.error(f"Ingestion error: {e}")
        else:
            logger.exception("Unexpected upload error")

        ul.event('upload_failed', {
            'upload_session_id': session_id,
            'error_type': type(e).__name__,
            'error_message': str(e),
        })

        flash(f"{'Ingestion' if is_ingestion_err else 'Unexpected'} error: {e}", 'danger')
        return redirect(url_for('ingest.upload_form'))
    finally:
        # Clean up temp dir
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)
