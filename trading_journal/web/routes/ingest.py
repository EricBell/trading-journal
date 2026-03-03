"""Ingest route: GET/POST /upload."""

import os
import tempfile
import logging
from pathlib import Path

from flask import Blueprint, flash, redirect, render_template, request, url_for

from ..auth import login_required
from ...authorization import AuthContext
from ...csv_parser import CsvParser
from ...ingestion import NdjsonIngester, IngestionError
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

        # Parse CSVs
        parser = CsvParser(include_rolling=include_rolling)
        records = parser.parse_files(saved_paths)

        # Ingest into DB
        ingester = NdjsonIngester()
        result = ingester.ingest_records(records)

        # Process trades
        engine = TradeCompletionEngine()
        proc = engine.process_completed_trades()

        flash(
            f"Imported {result['inserts']} new, updated {result['updates']}. "
            f"{proc.get('completed_trades', 0)} trades completed.",
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
