"""Trade routes: /trades, /trades/<id>, /trades/<id>/annotate."""

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from sqlalchemy import asc, desc
from sqlalchemy.orm import joinedload

from ..auth import login_required
from ...authorization import AuthContext
from ...database import db_manager
from ...models import Account, CompletedTrade, HgAnalysisResult, SetupPattern, SetupSource, Trade, TradeAnnotation
from ...positions import PositionTracker

bp = Blueprint('trades', __name__)


def _get_or_create_annotation(session, trade):
    """Load the TradeAnnotation for a trade, creating one if it doesn't exist yet.

    Looks up by completed_trade_id first, then falls back to the natural key
    (user_id, symbol, opened_at) to handle the case where a completed_trades
    rebuild has NULLed the FK but the annotation row still exists.
    """
    ann = session.query(TradeAnnotation).filter_by(
        completed_trade_id=trade.completed_trade_id
    ).one_or_none()
    if ann is None:
        ann = session.query(TradeAnnotation).filter_by(
            user_id=trade.user_id,
            symbol=trade.symbol,
            opened_at=trade.opened_at,
        ).one_or_none()
        if ann is not None:
            ann.completed_trade_id = trade.completed_trade_id
    if ann is None:
        ann = TradeAnnotation(
            completed_trade_id=trade.completed_trade_id,
            user_id=trade.user_id,
            symbol=trade.symbol,
            opened_at=trade.opened_at,
        )
        session.add(ann)
    return ann

def _resolve_grail_record(trade, annotation) -> dict | None:
    """Determine the grail plan for a trade, respecting manual overrides.

    Priority:
      1. annotation.grail_plan_rejected=True  → None (user explicitly rejected all plans)
      2. annotation.grail_plan_id is set      → fetch that specific plan by ID
      3. Otherwise                             → auto-match by symbol/date/direction
    """
    from ...grail_connector import fetch_grail_by_id, find_grail_match

    if annotation is not None and annotation.grail_plan_rejected:
        return None
    if annotation is not None and annotation.grail_plan_id is not None:
        return fetch_grail_by_id(annotation.grail_plan_id)
    match_symbol = trade.symbol.split()[0] if trade.instrument_type == 'OPTION' else trade.symbol
    return find_grail_match(match_symbol, trade.opened_at, trade.trade_type)


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
            .options(
                joinedload(CompletedTrade.account),
                joinedload(CompletedTrade.trade_annotation),
            )
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

    # Build grail plan indicators for the current page (one batch query to grail_files)
    from datetime import timezone as _tz
    from ...grail_connector import batch_grail_coverage

    def _utc_date(dt):
        if dt is None:
            return None
        return dt.astimezone(_tz.utc).date() if dt.tzinfo else dt.date()

    symbol_date_directions = []
    for t in trades:
        ms = t.symbol.split()[0] if t.instrument_type == 'OPTION' else t.symbol
        td = _utc_date(t.opened_at)
        if td is not None:
            symbol_date_directions.append((ms, td, t.trade_type))

    coverage = batch_grail_coverage(symbol_date_directions)

    grail_indicators: dict[int, str] = {}
    for t in trades:
        ann = t.trade_annotation
        if ann is not None and ann.grail_plan_rejected:
            grail_indicators[t.completed_trade_id] = '!'  # decision made: skip all plans
        elif ann is not None and ann.grail_plan_id is not None:
            grail_indicators[t.completed_trade_id] = '!'
        else:
            ms = t.symbol.split()[0] if t.instrument_type == 'OPTION' else t.symbol
            td = _utc_date(t.opened_at)
            cov = coverage.get((ms, td), {})
            if cov.get('has_match'):
                grail_indicators[t.completed_trade_id] = '!'
            elif cov.get('has_candidates'):
                grail_indicators[t.completed_trade_id] = '?'
            else:
                grail_indicators[t.completed_trade_id] = ''

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
        grail_indicators=grail_indicators,
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

        # Load most recent HG analysis result for this trade (if any)
        hg_analysis = (
            db_session.query(HgAnalysisResult)
            .filter_by(completed_trade_id=trade_id)
            .order_by(HgAnalysisResult.evaluated_at.desc())
            .first()
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

    from ...grail_connector import list_grail_candidates
    match_symbol = trade.symbol.split()[0] if trade.instrument_type == 'OPTION' else trade.symbol
    grail_record = _resolve_grail_record(trade, annotation)
    grail_candidates = list_grail_candidates(match_symbol, trade.opened_at)

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
        grail_candidates=grail_candidates,
        hg_analysis=hg_analysis,
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
        annotation = session.query(TradeAnnotation).filter_by(
            completed_trade_id=trade_id
        ).one_or_none()

    grail_record = _resolve_grail_record(trade, annotation)
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
@login_required
def delete(trade_id: int):
    user = AuthContext.require_user()
    symbol = None
    with db_manager.get_session() as db_session:
        trade = db_session.query(CompletedTrade).filter_by(
            completed_trade_id=trade_id, user_id=user.user_id
        ).one_or_none()
        if trade is None:
            flash('Trade not found.', 'warning')
            return redirect(url_for('trades.index'))

        symbol = trade.symbol  # capture before delete

        # Delete underlying raw executions first, then the completed trade
        db_session.query(Trade).filter_by(completed_trade_id=trade_id).delete()
        db_session.delete(trade)
        db_session.commit()

    # Reprocess positions for only the affected symbol so P&L stays correct
    PositionTracker().reprocess_positions_for_symbols(user.user_id, {symbol})

    flash(f'Trade #{trade_id} and its executions have been deleted.', 'success')
    return redirect(url_for('trades.index'))


@bp.route('/trades/bulk-delete', methods=['POST'])
@login_required
def bulk_delete():
    user = AuthContext.require_user()
    raw_ids = request.form.getlist('trade_ids')
    try:
        trade_ids = [int(i) for i in raw_ids if i.strip()]
    except ValueError:
        flash('Invalid trade selection.', 'danger')
        return redirect(url_for('trades.index'))

    if not trade_ids:
        flash('No trades selected.', 'warning')
        return redirect(url_for('trades.index'))

    affected_symbols: set = set()

    with db_manager.get_session() as db_session:
        trades = (
            db_session.query(CompletedTrade)
            .filter(
                CompletedTrade.completed_trade_id.in_(trade_ids),
                CompletedTrade.user_id == user.user_id,
            )
            .all()
        )

        if not trades:
            flash('No matching trades found.', 'warning')
            return redirect(url_for('trades.index'))

        confirmed_ids = [t.completed_trade_id for t in trades]
        affected_symbols = {t.symbol for t in trades}

        # Delete annotations (they would be orphaned; ON DELETE SET NULL keeps the row)
        db_session.query(TradeAnnotation).filter(
            TradeAnnotation.completed_trade_id.in_(confirmed_ids)
        ).delete(synchronize_session=False)

        # Delete underlying executions (Tier 1)
        db_session.query(Trade).filter(
            Trade.completed_trade_id.in_(confirmed_ids)
        ).delete(synchronize_session=False)

        # Delete completed trades (Tier 2)
        db_session.query(CompletedTrade).filter(
            CompletedTrade.completed_trade_id.in_(confirmed_ids)
        ).delete(synchronize_session=False)

        db_session.commit()

    # Reprocess positions for affected symbols so P&L stays correct
    PositionTracker().reprocess_positions_for_symbols(user.user_id, affected_symbols)

    flash(f'Deleted {len(confirmed_ids)} trade(s) and their executions.', 'success')
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

        ann.atm_engaged = request.form.get('atm_engaged', '').strip() or None
        ann.exit_reason = request.form.get('exit_reason', '').strip() or None

        underlying_raw = request.form.get('underlying_at_entry', '').strip()
        if underlying_raw:
            try:
                ann.underlying_at_entry = float(underlying_raw)
            except ValueError:
                flash('Invalid underlying price — must be a number.', 'warning')
                return redirect(url_for('trades.detail', trade_id=trade_id))
        else:
            ann.underlying_at_entry = None

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


@bp.route('/trades/<int:trade_id>/analyze-hg', methods=['POST'])
@login_required
def analyze_hg(trade_id: int):
    """Hydrate bars and evaluate the linked HG plan for this trade."""
    from ...hg_evaluator import evaluate_hg_plan
    from ...hg_hydration import hydrate_hg_plan

    user = AuthContext.require_user()

    with db_manager.get_session() as session:
        trade = session.query(CompletedTrade).filter_by(
            completed_trade_id=trade_id, user_id=user.user_id
        ).one_or_none()
        if trade is None:
            flash('Trade not found.', 'warning')
            return redirect(url_for('trades.index'))
        annotation = session.query(TradeAnnotation).filter_by(
            completed_trade_id=trade_id
        ).one_or_none()

    grail_record = _resolve_grail_record(trade, annotation)
    if grail_record is None:
        flash('No grail plan found for this trade.', 'warning')
        return redirect(url_for('trades.detail', trade_id=trade_id))

    grail_plan_id = str(grail_record['id'])

    hydration = hydrate_hg_plan(user.user_id, grail_plan_id, completed_trade_id=trade_id)
    if hydration['status'] == 'failed':
        flash(f"Bar fetch failed: {hydration['message']}", 'danger')
        return redirect(url_for('trades.detail', trade_id=trade_id))

    evaluation = evaluate_hg_plan(hydration['request_id'])
    if evaluation['status'] == 'failed':
        flash(f"Evaluation failed: {evaluation['message']}", 'danger')
        return redirect(url_for('trades.detail', trade_id=trade_id))

    touch = evaluation['entry_touch_type'].replace('_', ' ')
    tp1_icon = '✓' if evaluation['tp1_reached'] else '✗'
    tp2_icon = '✓' if evaluation['tp2_reached'] else '✗'
    msg = (
        f"HG Analysis complete — entry: {touch} | TP1: {tp1_icon} | TP2: {tp2_icon}"
        f" ({evaluation['bars_scanned']} bars scanned)"
    )
    flash(msg, 'success' if evaluation['entry_touched'] else 'info')
    return redirect(url_for('trades.detail', trade_id=trade_id))


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
                val = float(stop_raw)
                ann.stop_price = val if val != 0.0 else None
            except ValueError:
                flash('Invalid stop price — must be a number.', 'warning')
                return redirect(url_for('trades.detail', trade_id=trade_id))
        else:
            ann.stop_price = None
        session.commit()

    return redirect(url_for('trades.detail', trade_id=trade_id))


@bp.route('/trades/<int:trade_id>/set-grail-plan', methods=['POST'])
@login_required
def set_grail_plan(trade_id: int):
    """Override the grail plan matched to a trade, or reject all matches."""
    user = AuthContext.require_user()
    action = request.form.get('action', '').strip()

    with db_manager.get_session() as session:
        trade = session.query(CompletedTrade).filter_by(
            completed_trade_id=trade_id, user_id=user.user_id
        ).one_or_none()
        if trade is None:
            flash('Trade not found.', 'warning')
            return redirect(url_for('trades.index'))

        ann = _get_or_create_annotation(session, trade)

        if action == 'select':
            plan_id_raw = request.form.get('grail_plan_id', '').strip()
            try:
                ann.grail_plan_id = int(plan_id_raw)
                ann.grail_plan_rejected = False
            except (ValueError, TypeError):
                flash('Invalid plan ID.', 'warning')
                return redirect(url_for('trades.detail', trade_id=trade_id))
        elif action == 'reject':
            ann.grail_plan_id = None
            ann.grail_plan_rejected = True
        elif action == 'reset':
            ann.grail_plan_id = None
            ann.grail_plan_rejected = False
        else:
            flash('Unknown action.', 'warning')
            return redirect(url_for('trades.detail', trade_id=trade_id))

        session.commit()

    return redirect(url_for('trades.detail', trade_id=trade_id))
