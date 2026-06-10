"""Backtest routes: /backtest, /backtest/new, /backtest/<id>."""

from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for
from sqlalchemy import asc, desc, func

from ..auth import login_required
from ...authorization import AuthContext
from ...database import db_manager
from ...models import BacktestLegRule, BacktestRun, BacktestStrategyType, BacktestUnderlying

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

_DEFAULT_STRATEGIES = [
    'Vertical Put Debit', 'Vertical Put Credit', 'Iron Condor', 'Butterfly',
]
_DEFAULT_UNDERLYINGS = ['SPX', 'SPY', 'QQQ', 'NDX']


def _seed_defaults_if_empty(db_session, user_id):
    """Seed strategy types and underlyings on first use."""
    if not db_session.query(BacktestStrategyType).filter_by(user_id=user_id).first():
        for name in _DEFAULT_STRATEGIES:
            db_session.add(BacktestStrategyType(user_id=user_id, strategy_name=name))
    if not db_session.query(BacktestUnderlying).filter_by(user_id=user_id).first():
        for name in _DEFAULT_UNDERLYINGS:
            db_session.add(BacktestUnderlying(user_id=user_id, underlying_name=name))


def _load_dropdowns(db_session, user_id):
    strategy_types = (
        db_session.query(BacktestStrategyType)
        .filter_by(user_id=user_id, is_active=True)
        .order_by(BacktestStrategyType.strategy_name)
        .all()
    )
    underlyings = (
        db_session.query(BacktestUnderlying)
        .filter_by(user_id=user_id, is_active=True)
        .order_by(BacktestUnderlying.underlying_name)
        .all()
    )
    return strategy_types, underlyings


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


def _int_or_none(val):
    try:
        return int(val) if val else None
    except (ValueError, TypeError):
        return None


def _decimal_or_none(val):
    try:
        from decimal import Decimal
        return Decimal(val) if val else None
    except Exception:
        return None


def _resolve_inline_strategy(db_session, user_id, strategy_id_raw, new_name_raw):
    """Return strategy_type_id, creating a new row if __new__ was chosen."""
    if strategy_id_raw == '__new__':
        name = (new_name_raw or '').strip()
        if not name:
            return None
        existing = (
            db_session.query(BacktestStrategyType)
            .filter(
                BacktestStrategyType.user_id == user_id,
                func.lower(BacktestStrategyType.strategy_name) == name.lower(),
            )
            .first()
        )
        if existing:
            return existing.strategy_type_id
        row = BacktestStrategyType(user_id=user_id, strategy_name=name)
        db_session.add(row)
        db_session.flush()
        return row.strategy_type_id
    return _int_or_none(strategy_id_raw)


def _resolve_inline_underlying(db_session, user_id, underlying_id_raw, new_name_raw):
    """Return underlying_id, creating a new row if __new__ was chosen."""
    if underlying_id_raw == '__new__':
        name = (new_name_raw or '').strip()
        if not name:
            return None
        existing = (
            db_session.query(BacktestUnderlying)
            .filter(
                BacktestUnderlying.user_id == user_id,
                func.lower(BacktestUnderlying.underlying_name) == name.lower(),
            )
            .first()
        )
        if existing:
            return existing.underlying_id
        row = BacktestUnderlying(user_id=user_id, underlying_name=name)
        db_session.add(row)
        db_session.flush()
        return row.underlying_id
    return _int_or_none(underlying_id_raw)


def _apply_run_form(run, form, db_session, user_id):
    """Write form values onto a BacktestRun instance."""
    run.strategy_type_id = _resolve_inline_strategy(
        db_session, user_id,
        form.get('strategy_type_id', ''),
        form.get('new_strategy_name', ''),
    )
    run.underlying_id = _resolve_inline_underlying(
        db_session, user_id,
        form.get('underlying_id', ''),
        form.get('new_underlying_name', ''),
    )
    run.entry_time    = form.get('entry_time', '').strip() or None
    run.entry_style   = form.get('entry_style', 'simultaneous')
    run.spread_width_pts = _int_or_none(form.get('spread_width_pts'))
    run.dte_at_entry     = _int_or_none(form.get('dte_at_entry'))
    run.strike_selection = form.get('strike_selection', '').strip() or None
    run.profit_target_pct = _decimal_or_none(form.get('profit_target_pct'))
    run.stop_loss_rule    = form.get('stop_loss_rule', '').strip() or None
    run.date_range_start  = form.get('date_range_start') or None
    run.date_range_end    = form.get('date_range_end') or None
    run.backtest_tool     = form.get('backtest_tool', '').strip() or None
    run.notes             = form.get('notes', '').strip() or None
    run.status            = form.get('status', 'draft')
    run.trade_count       = _int_or_none(form.get('trade_count'))
    run.win_rate_pct      = _decimal_or_none(form.get('win_rate_pct'))
    run.avg_pnl_per_trade = _decimal_or_none(form.get('avg_pnl_per_trade'))
    run.total_pnl         = _decimal_or_none(form.get('total_pnl'))
    run.avg_win           = _decimal_or_none(form.get('avg_win'))
    run.avg_loss          = _decimal_or_none(form.get('avg_loss'))
    run.profit_factor     = _decimal_or_none(form.get('profit_factor'))
    run.max_win           = _decimal_or_none(form.get('max_win'))
    run.max_loss          = _decimal_or_none(form.get('max_loss'))
    run.max_drawdown      = _decimal_or_none(form.get('max_drawdown'))


# ─── List ──────────────────────────────────────────────────────────────────

@bp.route('/backtest')
@login_required
def index():
    user = AuthContext.require_user()

    strategy_id   = request.args.get('strategy', '').strip() or None
    underlying_id = request.args.get('underlying', '').strip() or None
    entry_time    = request.args.get('entry_time', '').strip() or None
    spread_width  = request.args.get('width', '').strip() or None

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
        runs = query.offset((page - 1) * per_page).limit(per_page).all()

        stats = db_session.query(
            func.max(BacktestRun.win_rate_pct).label('best_win_rate'),
            func.max(BacktestRun.profit_factor).label('best_profit_factor'),
            func.avg(BacktestRun.win_rate_pct).label('avg_win_rate'),
        ).filter(
            BacktestRun.user_id == user.user_id,
            *([BacktestRun.strategy_type_id == int(strategy_id)] if strategy_id else []),
            *([BacktestRun.underlying_id == int(underlying_id)] if underlying_id else []),
            *([BacktestRun.entry_time == entry_time] if entry_time else []),
            *([BacktestRun.spread_width_pts == int(spread_width)] if spread_width else []),
        ).one()

        strategy_types, underlyings = _load_dropdowns(db_session, user.user_id)
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


# ─── Create ────────────────────────────────────────────────────────────────

@bp.route('/backtest/new', methods=['GET', 'POST'])
@login_required
def new():
    user = AuthContext.require_user()

    if request.method == 'POST':
        with db_manager.get_session() as db_session:
            _seed_defaults_if_empty(db_session, user.user_id)
            run = BacktestRun(user_id=user.user_id)
            _apply_run_form(run, request.form, db_session, user.user_id)
            db_session.add(run)
            db_session.commit()
            run_id = run.run_id
        flash('Backtest run created.', 'success')
        return redirect(url_for('backtest.detail', run_id=run_id))

    with db_manager.get_session() as db_session:
        _seed_defaults_if_empty(db_session, user.user_id)
        db_session.commit()
        strategy_types, underlyings = _load_dropdowns(db_session, user.user_id)

    return render_template(
        'backtest/detail.html',
        run=None,
        leg_rules=[],
        strategy_types=strategy_types,
        underlyings=underlyings,
    )


# ─── Detail / Edit ─────────────────────────────────────────────────────────

@bp.route('/backtest/<int:run_id>', methods=['GET', 'POST'])
@login_required
def detail(run_id):
    user = AuthContext.require_user()

    if request.method == 'POST':
        with db_manager.get_session() as db_session:
            run = (
                db_session.query(BacktestRun)
                .filter_by(run_id=run_id, user_id=user.user_id)
                .one_or_none()
            )
            if run is None:
                flash('Run not found.', 'warning')
                return redirect(url_for('backtest.index'))
            _apply_run_form(run, request.form, db_session, user.user_id)
            db_session.commit()
        flash('Run saved.', 'success')
        return redirect(url_for('backtest.detail', run_id=run_id))

    with db_manager.get_session() as db_session:
        run = (
            db_session.query(BacktestRun)
            .filter_by(run_id=run_id, user_id=user.user_id)
            .one_or_none()
        )
        if run is None:
            flash('Run not found.', 'warning')
            return redirect(url_for('backtest.index'))

        leg_rules = (
            db_session.query(BacktestLegRule)
            .filter_by(run_id=run_id)
            .order_by(BacktestLegRule.sort_order, BacktestLegRule.rule_id)
            .all()
        )

        # Snapshot plain dicts so they survive session close
        run_data = {c.name: getattr(run, c.name) for c in run.__table__.columns}
        leg_rules_data = [
            {c.name: getattr(r, c.name) for c in r.__table__.columns}
            for r in leg_rules
        ]

        _seed_defaults_if_empty(db_session, user.user_id)
        db_session.commit()
        strategy_types, underlyings = _load_dropdowns(db_session, user.user_id)

    # Reconstruct lightweight objects the template can use
    class _Row:
        def __init__(self, d):
            self.__dict__.update(d)

    run_obj = _Row(run_data)
    leg_rule_objs = [_Row(d) for d in leg_rules_data]

    return render_template(
        'backtest/detail.html',
        run=run_obj,
        leg_rules=leg_rule_objs,
        strategy_types=strategy_types,
        underlyings=underlyings,
    )


# ─── Delete run ────────────────────────────────────────────────────────────

@bp.route('/backtest/<int:run_id>/delete', methods=['POST'])
@login_required
def delete(run_id):
    user = AuthContext.require_user()
    with db_manager.get_session() as db_session:
        run = (
            db_session.query(BacktestRun)
            .filter_by(run_id=run_id, user_id=user.user_id)
            .one_or_none()
        )
        if run is None:
            flash('Run not found.', 'warning')
            return redirect(url_for('backtest.index'))
        db_session.delete(run)
        db_session.commit()
    flash('Backtest run deleted.', 'success')
    return redirect(url_for('backtest.index'))


# ─── Leg rules ─────────────────────────────────────────────────────────────

@bp.route('/backtest/<int:run_id>/leg-rules/add', methods=['POST'])
@login_required
def add_leg_rule(run_id):
    user = AuthContext.require_user()
    leg_target        = request.form.get('leg_target', '').strip()
    trigger_condition = request.form.get('trigger_condition', '').strip()
    action            = request.form.get('action', '').strip()

    if not leg_target or not trigger_condition or not action:
        flash('All three rule fields are required.', 'danger')
        return redirect(url_for('backtest.detail', run_id=run_id))

    with db_manager.get_session() as db_session:
        run = (
            db_session.query(BacktestRun)
            .filter_by(run_id=run_id, user_id=user.user_id)
            .one_or_none()
        )
        if run is None:
            flash('Run not found.', 'warning')
            return redirect(url_for('backtest.index'))

        max_order = (
            db_session.query(func.max(BacktestLegRule.sort_order))
            .filter_by(run_id=run_id)
            .scalar() or 0
        )
        rule = BacktestLegRule(
            run_id=run_id,
            user_id=user.user_id,
            leg_target=leg_target,
            trigger_condition=trigger_condition,
            action=action,
            sort_order=max_order + 1,
        )
        db_session.add(rule)
        db_session.commit()

    return redirect(url_for('backtest.detail', run_id=run_id))


@bp.route('/backtest/<int:run_id>/leg-rules/<int:rule_id>/edit', methods=['POST'])
@login_required
def edit_leg_rule(run_id, rule_id):
    user = AuthContext.require_user()
    leg_target        = request.form.get('leg_target', '').strip()
    trigger_condition = request.form.get('trigger_condition', '').strip()
    action            = request.form.get('action', '').strip()

    if not leg_target or not trigger_condition or not action:
        flash('All three rule fields are required.', 'danger')
        return redirect(url_for('backtest.detail', run_id=run_id))

    with db_manager.get_session() as db_session:
        rule = (
            db_session.query(BacktestLegRule)
            .filter_by(rule_id=rule_id, run_id=run_id, user_id=user.user_id)
            .one_or_none()
        )
        if rule is None:
            flash('Rule not found.', 'warning')
            return redirect(url_for('backtest.detail', run_id=run_id))
        rule.leg_target        = leg_target
        rule.trigger_condition = trigger_condition
        rule.action            = action
        db_session.commit()

    return redirect(url_for('backtest.detail', run_id=run_id))


@bp.route('/backtest/<int:run_id>/leg-rules/<int:rule_id>/delete', methods=['POST'])
@login_required
def delete_leg_rule(run_id, rule_id):
    user = AuthContext.require_user()
    with db_manager.get_session() as db_session:
        rule = (
            db_session.query(BacktestLegRule)
            .filter_by(rule_id=rule_id, run_id=run_id, user_id=user.user_id)
            .one_or_none()
        )
        if rule is None:
            flash('Rule not found.', 'warning')
            return redirect(url_for('backtest.detail', run_id=run_id))
        db_session.delete(rule)
        db_session.commit()

    return redirect(url_for('backtest.detail', run_id=run_id))
