"""Notepad routes: /notepad — pre- and post-trade thought capture (issue #33)."""

import zoneinfo
from datetime import timezone as dt_timezone

from flask import Blueprint, flash, redirect, render_template, request, url_for

from ..auth import login_required
from ...annotation_service import merge_notepad_entry
from ...authorization import AuthContext
from ...database import db_manager
from ...models import Account, CompletedTrade, NotepadEntry
from .trades import _build_trades_query

bp = Blueprint('notepad', __name__, url_prefix='/notepad')


def _to_user_tz(dt, user):
    """Convert a naive UTC datetime to the user's local timezone."""
    if dt is None:
        return None
    user_tz = zoneinfo.ZoneInfo(user.timezone or 'US/Eastern')
    return dt.replace(tzinfo=dt_timezone.utc).astimezone(user_tz)


def _entry_to_dict(entry, user):
    return {
        'notepad_id': entry.notepad_id,
        'symbol': entry.symbol,
        'account_id': entry.account_id,
        'body': entry.body,
        'created_at': _to_user_tz(entry.created_at, user),
        'updated_at': _to_user_tz(entry.updated_at, user),
        'matched_trade_id': entry.matched_trade_id,
        'matched_symbol': entry.matched_symbol,
        'matched_opened_at': _to_user_tz(entry.matched_opened_at, user),
        'matched_at': _to_user_tz(entry.matched_at, user),
        'is_matched': entry.matched_at is not None,
    }


@bp.route('/')
@login_required
def index():
    user = AuthContext.require_user()
    status_filter = request.args.get('status', '').strip() or 'all'
    symbol_filter = (request.args.get('symbol', '').strip().upper()) or None

    with db_manager.get_session() as session:
        query = session.query(NotepadEntry).filter(NotepadEntry.user_id == user.user_id)
        if status_filter == 'unmatched':
            query = query.filter(NotepadEntry.matched_at.is_(None))
        elif status_filter == 'matched':
            query = query.filter(NotepadEntry.matched_at.isnot(None))
        if symbol_filter:
            query = query.filter(NotepadEntry.symbol == symbol_filter)

        entries = query.order_by(NotepadEntry.created_at.desc()).all()
        entries_data = [_entry_to_dict(e, user) for e in entries]

    return render_template(
        'notepad/index.html',
        user=AuthContext.get_current_user(),
        entries=entries_data,
        status_filter=status_filter,
        symbol_filter=symbol_filter or '',
    )


@bp.route('/new', methods=['GET'])
@login_required
def new():
    user = AuthContext.require_user()
    prefill_symbol = (request.args.get('symbol', '').strip().upper()) or None
    with db_manager.get_session() as session:
        accounts = (
            session.query(Account)
            .filter_by(user_id=user.user_id)
            .order_by(Account.account_name)
            .all()
        )
    return render_template(
        'notepad/detail.html',
        user=AuthContext.get_current_user(),
        entry=None,
        accounts=accounts,
        prefill_symbol=prefill_symbol,
    )


@bp.route('/new', methods=['POST'])
@login_required
def create():
    user = AuthContext.require_user()
    symbol = request.form.get('symbol', '').strip().upper() or None
    account_id_raw = request.form.get('account_id', '').strip()
    body = request.form.get('body', '').strip()

    if not body:
        flash('Note body cannot be empty.', 'warning')
        return redirect(url_for('notepad.new'))

    account_id = None
    if account_id_raw:
        try:
            account_id = int(account_id_raw)
        except ValueError:
            account_id = None

    with db_manager.get_session() as session:
        entry = NotepadEntry(user_id=user.user_id, symbol=symbol, account_id=account_id, body=body)
        session.add(entry)
        session.flush()
        notepad_id = entry.notepad_id
        session.commit()

    flash('Notepad entry saved.', 'success')
    return redirect(url_for('notepad.detail', notepad_id=notepad_id))


@bp.route('/<int:notepad_id>', methods=['GET'])
@login_required
def detail(notepad_id):
    user = AuthContext.require_user()
    with db_manager.get_session() as session:
        entry = session.query(NotepadEntry).filter_by(
            notepad_id=notepad_id, user_id=user.user_id
        ).one_or_none()
        if entry is None:
            flash('Notepad entry not found.', 'danger')
            return redirect(url_for('notepad.index'))

        accounts = (
            session.query(Account)
            .filter_by(user_id=user.user_id)
            .order_by(Account.account_name)
            .all()
        )
        entry_data = _entry_to_dict(entry, user)

    return render_template(
        'notepad/detail.html',
        user=AuthContext.get_current_user(),
        entry=entry_data,
        accounts=accounts,
    )


@bp.route('/<int:notepad_id>', methods=['POST'])
@login_required
def update(notepad_id):
    user = AuthContext.require_user()
    symbol = request.form.get('symbol', '').strip().upper() or None
    account_id_raw = request.form.get('account_id', '').strip()
    body = request.form.get('body', '').strip()

    if not body:
        flash('Note body cannot be empty.', 'warning')
        return redirect(url_for('notepad.detail', notepad_id=notepad_id))

    account_id = None
    if account_id_raw:
        try:
            account_id = int(account_id_raw)
        except ValueError:
            account_id = None

    with db_manager.get_session() as session:
        entry = session.query(NotepadEntry).filter_by(
            notepad_id=notepad_id, user_id=user.user_id
        ).one_or_none()
        if entry is None:
            flash('Notepad entry not found.', 'danger')
            return redirect(url_for('notepad.index'))
        entry.symbol = symbol
        entry.account_id = account_id
        entry.body = body
        session.commit()

    flash('Notepad entry saved.', 'success')
    return redirect(url_for('notepad.detail', notepad_id=notepad_id))


@bp.route('/<int:notepad_id>/delete', methods=['POST'])
@login_required
def delete(notepad_id):
    user = AuthContext.require_user()
    with db_manager.get_session() as session:
        entry = session.query(NotepadEntry).filter_by(
            notepad_id=notepad_id, user_id=user.user_id
        ).one_or_none()
        if entry is None:
            flash('Notepad entry not found.', 'danger')
            return redirect(url_for('notepad.index'))
        session.delete(entry)
        session.commit()

    flash('Notepad entry deleted.', 'success')
    return redirect(url_for('notepad.index'))


@bp.route('/<int:notepad_id>/match', methods=['GET'])
@login_required
def match_picker(notepad_id):
    user = AuthContext.require_user()
    with db_manager.get_session() as session:
        entry = session.query(NotepadEntry).filter_by(
            notepad_id=notepad_id, user_id=user.user_id
        ).one_or_none()
        if entry is None:
            flash('Notepad entry not found.', 'danger')
            return redirect(url_for('notepad.index'))

        symbol = (request.args.get('symbol', '').strip().upper()) or entry.symbol
        range_filter = request.args.get('range', '').strip() or None

        query = _build_trades_query(
            session, user.user_id, symbol, range_filter, None, 'opened', 'desc'
        )
        candidates = query.limit(100).all()
        candidates_data = [
            {
                'completed_trade_id': t.completed_trade_id,
                'symbol': t.symbol,
                'trade_type': t.trade_type,
                'opened_at': t.opened_at,
                'closed_at': t.closed_at,
                'net_pnl': t.net_pnl,
            }
            for t in candidates
        ]
        entry_data = _entry_to_dict(entry, user)

    return render_template(
        'notepad/match.html',
        user=AuthContext.get_current_user(),
        entry=entry_data,
        candidates=candidates_data,
        symbol=symbol or '',
        range_filter=range_filter or '',
    )


@bp.route('/<int:notepad_id>/match', methods=['POST'])
@login_required
def match(notepad_id):
    user = AuthContext.require_user()
    trade_id_raw = request.form.get('trade_id', '').strip()

    with db_manager.get_session() as session:
        entry = session.query(NotepadEntry).filter_by(
            notepad_id=notepad_id, user_id=user.user_id
        ).one_or_none()
        if entry is None:
            flash('Notepad entry not found.', 'danger')
            return redirect(url_for('notepad.index'))

        trade = None
        if trade_id_raw:
            trade = session.query(CompletedTrade).filter_by(
                completed_trade_id=int(trade_id_raw), user_id=user.user_id
            ).one_or_none()
        if trade is None:
            flash('Trade not found.', 'warning')
            return redirect(url_for('notepad.match_picker', notepad_id=notepad_id))

        merge_notepad_entry(session, entry, trade, user)
        session.commit()

    flash('Notepad entry attached to trade.', 'success')
    return redirect(url_for('notepad.detail', notepad_id=notepad_id))
