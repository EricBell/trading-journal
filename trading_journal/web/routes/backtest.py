"""Backtest routes: /backtest, /backtest/new, /backtest/<id>."""

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from sqlalchemy import asc, desc, func

from ..auth import login_required
from ...authorization import AuthContext
from ...database import db_manager
from ...models import BacktestRun, BacktestStrategyType, BacktestUnderlying

bp = Blueprint('backtest', __name__)

SORT_COLUMNS = {
    'strategy':      BacktestRun.strategy_type_id,
    'underlying':    BacktestRun.underlying_id,
    'entry_time':    BacktestRun.entry_time,
    'width':         BacktestRun.spread_width_pts,
    'dte':           BacktestRun.dte_at_entry,
    'trades':        BacktestRun.trade_count,
    'win_rate':      BacktestRun.win_rate_pct,
    'profit_factor': BacktestRun.profit_factor,
    'avg_pnl':       BacktestRun.avg_pnl_per_trade,
    'total_pnl':     BacktestRun.total_pnl,
    'date_start':    BacktestRun.date_range_start,
    'created':       BacktestRun.created_at,
}
DEFAULT_SORT, DEFAULT_DIR = 'created', 'desc'
PER_PAGE_OPTIONS = [10, 25, 50, 100]


def _build_query(db_session, user_id, strategy_id, underlying_id, entry_time, spread_width, sort_col, sort_dir):
    query = db_session.query(BacktestRun).filter_by(user_id=user_id)

    if strategy_id:
        try:
            query = query.filter(BacktestRun.strategy_type_id == int(strategy_id))
        except ValueError:
            pass
    if underlying_id:
        try:
            query = query.filter(BacktestRun.underlying_id == int(underlying_id))
        except ValueError:
            pass
    if entry_time:
        query = query.filter(BacktestRun.entry_time == entry_time)
    if spread_width:
        try:
            query = query.filter(BacktestRun.spread_width_pts == int(spread_width))
        except ValueError:
            pass

    col = SORT_COLUMNS.get(sort_col, SORT_COLUMNS[DEFAULT_SORT])
    order_fn = asc if sort_dir == 'asc' else desc
    return query.order_by(order_fn(col))


@bp.route('/backtest')
@login_required
def index():
    user = AuthContext.require_user()

    strategy_id  = request.args.get('strategy', '').strip() or None
    underlying_id = request.args.get('underlying', '').strip() or None
    entry_time   = request.args.get('entry_time', '').strip() or None
    spread_width = request.args.get('width', '').strip() or None

    sort_col = request.args.get('sort', DEFAULT_SORT)
    if sort_col not in SORT_COLUMNS:
        sort_col = DEFAULT_SORT
    sort_dir = request.args.get('dir', DEFAULT_DIR)
    if sort_dir not in ('asc', 'desc'):
        sort_dir = DEFAULT_DIR

    if 'per_page' in request.args:
        try:
            pp = int(request.args['per_page'])
            if pp in PER_PAGE_OPTIONS:
                session['backtest_per_page'] = pp
        except ValueError:
            pass
    per_page = session.get('backtest_per_page', 25)

    try:
        page = max(1, int(request.args.get('page', 1)))
    except ValueError:
        page = 1

    with db_manager.get_session() as db_session:
        query = _build_query(
            db_session, user.user_id,
            strategy_id, underlying_id, entry_time, spread_width,
            sort_col, sort_dir,
        )

        total = query.count()
        total_pages = max(1, (total + per_page - 1) // per_page)
        page = min(page, total_pages)

        runs = (
            query
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )

        # Summary stats across all filtered rows (not just current page)
        from sqlalchemy import func as sqlfunc
        stats = db_session.query(
            sqlfunc.max(BacktestRun.win_rate_pct).label('best_win_rate'),
            sqlfunc.max(BacktestRun.profit_factor).label('best_profit_factor'),
            sqlfunc.avg(BacktestRun.win_rate_pct).label('avg_win_rate'),
        ).filter(
            BacktestRun.user_id == user.user_id,
            *([BacktestRun.strategy_type_id == int(strategy_id)] if strategy_id else []),
            *([BacktestRun.underlying_id == int(underlying_id)] if underlying_id else []),
            *([BacktestRun.entry_time == entry_time] if entry_time else []),
            *([BacktestRun.spread_width_pts == int(spread_width)] if spread_width else []),
        ).one()

        strategy_types = (
            db_session.query(BacktestStrategyType)
            .filter_by(user_id=user.user_id, is_active=True)
            .order_by(BacktestStrategyType.strategy_name)
            .all()
        )
        underlyings = (
            db_session.query(BacktestUnderlying)
            .filter_by(user_id=user.user_id, is_active=True)
            .order_by(BacktestUnderlying.underlying_name)
            .all()
        )

        # Build name lookup maps for display in template
        strategy_map = {s.strategy_type_id: s.strategy_name for s in strategy_types}
        underlying_map = {u.underlying_id: u.underlying_name for u in underlyings}

    return render_template(
        'backtest/index.html',
        runs=runs,
        total=total,
        page=page,
        total_pages=total_pages,
        per_page=per_page,
        per_page_options=PER_PAGE_OPTIONS,
        sort_col=sort_col,
        sort_dir=sort_dir,
        strategy_id=strategy_id,
        underlying_id=underlying_id,
        entry_time=entry_time or '',
        spread_width=spread_width or '',
        strategy_types=strategy_types,
        underlyings=underlyings,
        strategy_map=strategy_map,
        underlying_map=underlying_map,
        stats=stats,
    )


@bp.route('/backtest/new', methods=['GET', 'POST'])
@login_required
def new():
    # Placeholder — implemented in issue #15
    flash('Create form coming soon.', 'info')
    return redirect(url_for('backtest.index'))


@bp.route('/backtest/<int:run_id>', methods=['GET', 'POST'])
@login_required
def detail(run_id):
    # Placeholder — implemented in issue #15
    flash('Detail/edit form coming soon.', 'info')
    return redirect(url_for('backtest.index'))
