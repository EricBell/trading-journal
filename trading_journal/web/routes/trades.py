"""Trade routes: /trades, /trades/<id>, /trades/<id>/annotate."""

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from sqlalchemy import asc, desc
from sqlalchemy.orm import joinedload

from ..auth import admin_required, login_required
from ...authorization import AuthContext
from ...database import db_manager
from ...models import Account, CompletedTrade, SetupPattern, SetupSource, Trade, TradeAnnotation
from ...positions import PositionTracker

bp = Blueprint('trades', __name__)


def _get_or_create_annotation(session, trade):
    """Load the TradeAnnotation for a trade, creating one if it doesn't exist yet."""
    ann = session.query(TradeAnnotation).filter_by(
        completed_trade_id=trade.completed_trade_id
    ).one_or_none()
    if ann is None:
        ann = TradeAnnotation(
            completed_trade_id=trade.completed_trade_id,
            user_id=trade.user_id,
            symbol=trade.symbol,
            opened_at=trade.opened_at,
        )
        session.add(ann)
    return ann

SORT_COLUMNS = {
    'id':      CompletedTrade.completed_trade_id,
    'symbol':  CompletedTrade.symbol,
    'type':    CompletedTrade.trade_type,
    'qty':     CompletedTrade.total_qty,
    'entry':   CompletedTrade.entry_avg_price,
    'exit':    CompletedTrade.exit_avg_price,
    'opened':  CompletedTrade.opened_at,
    'closed':  CompletedTrade.closed_at,
    'pnl':     CompletedTrade.net_pnl,
    'pattern': SetupPattern.pattern_name,
}
DEFAULT_SORT, DEFAULT_DIR = 'closed', 'desc'
PER_PAGE_OPTIONS = [10, 25, 50, 100]


def _build_trades_query(db_session, user_id, symbol, range_filter, account_filter, sort_col, sort_dir):
    """Return a filtered+sorted CompletedTrade query with no pagination applied."""
    from datetime import date, timedelta
    query = db_session.query(CompletedTrade).filter_by(user_id=user_id)

    if symbol:
        query = query.filter(CompletedTrade.symbol == symbol)

    if account_filter:
        try:
            query = query.filter(CompletedTrade.account_id == int(account_filter))
        except ValueError:
            pass

    if range_filter and range_filter.endswith('d'):
        today = date.today()
        try:
            days = int(range_filter[:-1])
            cutoff = today - timedelta(days=days - 1)
            query = query.filter(CompletedTrade.closed_at >= cutoff)
        except ValueError:
            pass

    col = SORT_COLUMNS.get(sort_col, SORT_COLUMNS[DEFAULT_SORT])
    order_fn = asc if sort_dir == 'asc' else desc

    if sort_col == 'pattern':
        query = (
            query
            .outerjoin(TradeAnnotation,
                       TradeAnnotation.completed_trade_id == CompletedTrade.completed_trade_id)
            .outerjoin(SetupPattern,
                       SetupPattern.pattern_id == TradeAnnotation.setup_pattern_id)
            .order_by(order_fn(SetupPattern.pattern_name))
        )
    else:
        query = query.order_by(order_fn(col))

    return query


@bp.route('/trades')
@login_required
def index():
    user = AuthContext.require_user()
    symbol = (request.args.get('symbol', '').strip().upper()) or None
    range_filter = request.args.get('range', '').strip() or None
    account_filter = request.args.get('account', '').strip() or None

    # Sorting
    sort_col = request.args.get('sort', DEFAULT_SORT)
    if sort_col not in SORT_COLUMNS:
        sort_col = DEFAULT_SORT
    sort_dir = request.args.get('dir', DEFAULT_DIR)
    if sort_dir not in ('asc', 'desc'):
        sort_dir = DEFAULT_DIR

    # Pagination
    if 'per_page' in request.args:
        try:
            per_page = int(request.args['per_page'])
            if per_page in PER_PAGE_OPTIONS:
                session['trades_per_page'] = per_page
        except ValueError:
            pass
    per_page = session.get('trades_per_page', 25)

    try:
        page = max(1, int(request.args.get('page', 1)))
    except ValueError:
        page = 1

    with db_manager.get_session() as db_session:
        query = _build_trades_query(
            db_session, user.user_id, symbol, range_filter, account_filter, sort_col, sort_dir
        )

        total = query.count()
        total_pages = max(1, (total + per_page - 1) // per_page)
        page = min(page, total_pages)
        trades = (
            query
            .options(joinedload(CompletedTrade.account))
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )

        # Fetch user patterns for filter dropdown (from setup_patterns table)
        pattern_names_rows = (
            db_session.query(SetupPattern.pattern_name)
            .filter_by(user_id=user.user_id, is_active=True)
            .order_by(SetupPattern.pattern_name)
            .all()
        )
        pattern_names = [p[0] for p in pattern_names_rows]

        # Fetch user accounts for filter dropdown
        accounts = (
            db_session.query(Account)
            .filter_by(user_id=user.user_id)
            .order_by(Account.account_name)
            .all()
        )

    return render_template(
        'trades/index.html',
        trades=trades,
        user=user,
        symbol=symbol or '',
        range_filter=range_filter or '',
        account_filter=account_filter or '',
        accounts=accounts,
        pattern_names=pattern_names,
        sort_col=sort_col,
        sort_dir=sort_dir,
        page=page,
        per_page=per_page,
        total=total,
        total_pages=total_pages,
        per_page_options=PER_PAGE_OPTIONS,
    )


@bp.route('/trades/<int:trade_id>')
@login_required
def detail(trade_id: int):
    user = AuthContext.require_user()

    # Read list-context params (passed from index page)
    sort_col = request.args.get('sort', DEFAULT_SORT)
    if sort_col not in SORT_COLUMNS:
        sort_col = DEFAULT_SORT
    sort_dir = request.args.get('dir', DEFAULT_DIR)
    if sort_dir not in ('asc', 'desc'):
        sort_dir = DEFAULT_DIR
    symbol = (request.args.get('symbol', '').strip().upper()) or None
    range_filter = request.args.get('range', '').strip() or None
    account_filter = request.args.get('account', '').strip() or None

    with db_manager.get_session() as db_session:
        trade = db_session.query(CompletedTrade).options(
            joinedload(CompletedTrade.account)
        ).filter_by(
            completed_trade_id=trade_id, user_id=user.user_id
        ).one_or_none()
        if trade is None:
            flash('Trade not found.', 'warning')
            return redirect(url_for('trades.index'))

        executions = sorted(trade.executions, key=lambda e: e.exec_timestamp or '')

        annotation = db_session.query(TradeAnnotation).filter_by(
            completed_trade_id=trade_id
        ).one_or_none()

        patterns = (
            db_session.query(SetupPattern)
            .filter_by(user_id=user.user_id, is_active=True)
            .order_by(SetupPattern.pattern_name)
            .all()
        )

        sources = (
            db_session.query(SetupSource)
            .filter_by(user_id=user.user_id, is_active=True)
            .order_by(SetupSource.source_name)
            .all()
        )

        # Build navigation: fetch ordered IDs for the current filter/sort context
        nav_query = _build_trades_query(
            db_session, user.user_id, symbol, range_filter, account_filter, sort_col, sort_dir
        )
        all_ids = [
            row[0]
            for row in nav_query.with_entities(CompletedTrade.completed_trade_id).all()
        ]

    try:
        pos = all_ids.index(trade_id)
    except ValueError:
        pos = None

    # Params carried on every nav link
    list_params = {'sort': sort_col, 'dir': sort_dir}
    if symbol:
        list_params['symbol'] = symbol
    if range_filter:
        list_params['range'] = range_filter
    if account_filter:
        list_params['account'] = account_filter

    nav_total = len(all_ids)

    def _nav_url(tid):
        return url_for('trades.detail', trade_id=tid, **list_params)

    if pos is not None and nav_total > 1:
        nav = {
            'total': nav_total,
            'position': pos + 1,
            'first_url': _nav_url(all_ids[0]) if pos > 0 else None,
            'prev_url':  _nav_url(all_ids[pos - 1]) if pos > 0 else None,
            'next_url':  _nav_url(all_ids[pos + 1]) if pos < nav_total - 1 else None,
            'last_url':  _nav_url(all_ids[-1]) if pos < nav_total - 1 else None,
        }
    else:
        nav = {
            'total': nav_total,
            'position': (pos + 1) if pos is not None else None,
            'first_url': None, 'prev_url': None, 'next_url': None, 'last_url': None,
        }

    from ...grail_connector import find_grail_match
    grail_record = find_grail_match(trade.symbol, trade.opened_at)

    back_url = url_for('trades.index', **list_params)
    annotate_url = url_for('trades.annotate', trade_id=trade_id, **list_params)

    return render_template(
        'trades/detail.html',
        trade=trade,
        annotation=annotation,
        executions=executions,
        patterns=patterns,
        sources=sources,
        user=user,
        grail_record=grail_record,
        nav=nav,
        back_url=back_url,
        annotate_url=annotate_url,
    )


@bp.route('/trades/<int:trade_id>/grail-plan')
@login_required
def grail_plan(trade_id: int):
    user = AuthContext.require_user()
    with db_manager.get_session() as session:
        trade = session.query(CompletedTrade).filter_by(
            completed_trade_id=trade_id, user_id=user.user_id
        ).one_or_none()
        if trade is None:
            flash('Trade not found.', 'warning')
            return redirect(url_for('trades.index'))

    from ...grail_connector import find_grail_match
    grail_record = find_grail_match(trade.symbol, trade.opened_at)
    if grail_record is None:
        flash('No trade plan found for this trade.', 'warning')
        return redirect(url_for('trades.detail', trade_id=trade_id))

    return render_template(
        'trades/grail_plan.html',
        trade=trade,
        grail_record=grail_record,
        user=user,
    )


@bp.route('/trades/<int:trade_id>/delete', methods=['POST'])
@admin_required
def delete(trade_id: int):
    user = AuthContext.require_user()
    with db_manager.get_session() as db_session:
        trade = db_session.query(CompletedTrade).filter_by(
            completed_trade_id=trade_id, user_id=user.user_id
        ).one_or_none()
        if trade is None:
            flash('Trade not found.', 'warning')
            return redirect(url_for('trades.index'))

        # Delete underlying raw executions first, then the completed trade
        db_session.query(Trade).filter_by(completed_trade_id=trade_id).delete()
        db_session.delete(trade)
        db_session.commit()

    # Reprocess positions so P&L stays correct
    PositionTracker().reprocess_all_positions(user.user_id)

    flash(f'Trade #{trade_id} and its executions have been deleted.', 'success')
    return redirect(url_for('trades.index'))


@bp.route('/trades/<int:trade_id>/annotate', methods=['POST'])
@login_required
def annotate(trade_id: int):
    from sqlalchemy import func as sa_func
    user = AuthContext.require_user()
    with db_manager.get_session() as session:
        trade = session.query(CompletedTrade).filter_by(
            completed_trade_id=trade_id, user_id=user.user_id
        ).one_or_none()
        if trade is None:
            flash('Trade not found.', 'warning')
            return redirect(url_for('trades.index'))

        ann = _get_or_create_annotation(session, trade)

        # Resolve setup_pattern_id
        pattern_id_raw = request.form.get('setup_pattern_id', '').strip()
        if pattern_id_raw == '__new__':
            new_name = request.form.get('new_pattern_name', '').strip()
            if new_name:
                existing = session.query(SetupPattern).filter(
                    SetupPattern.user_id == user.user_id,
                    sa_func.lower(SetupPattern.pattern_name) == new_name.lower()
                ).first()
                if existing:
                    ann.setup_pattern_id = existing.pattern_id
                else:
                    new_pattern = SetupPattern(
                        user_id=user.user_id,
                        pattern_name=new_name,
                        is_active=True,
                    )
                    session.add(new_pattern)
                    session.flush()
                    ann.setup_pattern_id = new_pattern.pattern_id
            else:
                ann.setup_pattern_id = None
        elif pattern_id_raw:
            try:
                ann.setup_pattern_id = int(pattern_id_raw)
            except ValueError:
                ann.setup_pattern_id = None
        else:
            ann.setup_pattern_id = None

        # Resolve setup_source_id
        source_id_raw = request.form.get('setup_source_id', '').strip()
        if source_id_raw == '__new__':
            new_name = request.form.get('new_source_name', '').strip()
            if new_name:
                existing = session.query(SetupSource).filter(
                    SetupSource.user_id == user.user_id,
                    sa_func.lower(SetupSource.source_name) == new_name.lower()
                ).first()
                if existing:
                    ann.setup_source_id = existing.source_id
                else:
                    new_source = SetupSource(
                        user_id=user.user_id,
                        source_name=new_name,
                        is_active=True,
                    )
                    session.add(new_source)
                    session.flush()
                    ann.setup_source_id = new_source.source_id
            else:
                ann.setup_source_id = None
        elif source_id_raw:
            try:
                ann.setup_source_id = int(source_id_raw)
            except ValueError:
                ann.setup_source_id = None
        else:
            ann.setup_source_id = None

        ann.trade_notes = request.form.get('trade_notes', '').strip() or None
        session.commit()
        flash('Trade updated.', 'success')

    # Preserve list-context params so nav survives the POST/redirect
    sort_col = request.args.get('sort', DEFAULT_SORT)
    if sort_col not in SORT_COLUMNS:
        sort_col = DEFAULT_SORT
    sort_dir = request.args.get('dir', DEFAULT_DIR)
    if sort_dir not in ('asc', 'desc'):
        sort_dir = DEFAULT_DIR
    detail_kwargs = {'trade_id': trade_id, 'sort': sort_col, 'dir': sort_dir}
    for _p in ('symbol', 'range', 'account'):
        _v = request.args.get(_p, '').strip()
        if _v:
            detail_kwargs[_p] = _v
    return redirect(url_for('trades.detail', **detail_kwargs))


@bp.route('/trades/<int:trade_id>/set-stop', methods=['POST'])
@login_required
def set_stop(trade_id: int):
    user = AuthContext.require_user()
    with db_manager.get_session() as session:
        trade = session.query(CompletedTrade).filter_by(
            completed_trade_id=trade_id, user_id=user.user_id
        ).one_or_none()
        if trade is None:
            flash('Trade not found.', 'warning')
            return redirect(url_for('trades.index'))

        stop_raw = request.form.get('stop_price', '').strip()
        ann = _get_or_create_annotation(session, trade)
        if stop_raw:
            try:
                ann.stop_price = float(stop_raw)
            except ValueError:
                flash('Invalid stop price — must be a number.', 'warning')
                return redirect(url_for('trades.detail', trade_id=trade_id))
        else:
            ann.stop_price = None
        session.commit()

    return redirect(url_for('trades.detail', trade_id=trade_id))
