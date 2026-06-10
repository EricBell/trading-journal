"""Settings routes: /settings — manage setup patterns and sources."""

from flask import Blueprint, flash, redirect, render_template, request, url_for
from sqlalchemy import func

from ..auth import login_required
from ...authorization import AuthContext
from ...database import db_manager
from ...models import AtmOption, BacktestRun, BacktestStrategyType, BacktestUnderlying, TradeAnnotation, SetupPattern, SetupSource

bp = Blueprint('settings', __name__, url_prefix='/settings')


@bp.route('/')
@login_required
def index():
    user = AuthContext.require_user()
    with db_manager.get_session() as db_session:
        # Patterns with trade counts
        pattern_rows = (
            db_session.query(
                SetupPattern,
                func.count(TradeAnnotation.annotation_id).label('trade_count')
            )
            .outerjoin(
                TradeAnnotation,
                (TradeAnnotation.setup_pattern_id == SetupPattern.pattern_id) &
                (TradeAnnotation.user_id == user.user_id)
            )
            .filter(SetupPattern.user_id == user.user_id)
            .group_by(SetupPattern.pattern_id)
            .order_by(SetupPattern.pattern_name)
            .all()
        )

        # Sources with trade counts
        source_rows = (
            db_session.query(
                SetupSource,
                func.count(TradeAnnotation.annotation_id).label('trade_count')
            )
            .outerjoin(
                TradeAnnotation,
                (TradeAnnotation.setup_source_id == SetupSource.source_id) &
                (TradeAnnotation.user_id == user.user_id)
            )
            .filter(SetupSource.user_id == user.user_id)
            .group_by(SetupSource.source_id)
            .order_by(SetupSource.source_name)
            .all()
        )

        # ATM options with trade counts
        atm_rows = (
            db_session.query(
                AtmOption,
                func.count(TradeAnnotation.annotation_id).label('trade_count')
            )
            .outerjoin(
                TradeAnnotation,
                (TradeAnnotation.atm_option_id == AtmOption.option_id) &
                (TradeAnnotation.user_id == user.user_id)
            )
            .filter(AtmOption.user_id == user.user_id)
            .group_by(AtmOption.option_id)
            .order_by(AtmOption.option_name)
            .all()
        )

        # Backtest strategy types with run counts
        bt_strategy_rows = (
            db_session.query(
                BacktestStrategyType,
                func.count(BacktestRun.run_id).label('run_count')
            )
            .outerjoin(
                BacktestRun,
                (BacktestRun.strategy_type_id == BacktestStrategyType.strategy_type_id) &
                (BacktestRun.user_id == user.user_id)
            )
            .filter(BacktestStrategyType.user_id == user.user_id)
            .group_by(BacktestStrategyType.strategy_type_id)
            .order_by(BacktestStrategyType.strategy_name)
            .all()
        )

        # Backtest underlyings with run counts
        bt_underlying_rows = (
            db_session.query(
                BacktestUnderlying,
                func.count(BacktestRun.run_id).label('run_count')
            )
            .outerjoin(
                BacktestRun,
                (BacktestRun.underlying_id == BacktestUnderlying.underlying_id) &
                (BacktestRun.user_id == user.user_id)
            )
            .filter(BacktestUnderlying.user_id == user.user_id)
            .group_by(BacktestUnderlying.underlying_id)
            .order_by(BacktestUnderlying.underlying_name)
            .all()
        )

    return render_template(
        'settings/index.html',
        user=user,
        pattern_rows=pattern_rows,
        source_rows=source_rows,
        atm_rows=atm_rows,
        bt_strategy_rows=bt_strategy_rows,
        bt_underlying_rows=bt_underlying_rows,
    )


@bp.route('/patterns', methods=['POST'])
@login_required
def create_pattern():
    user = AuthContext.require_user()
    name = request.form.get('pattern_name', '').strip()
    if not name:
        flash('Pattern name cannot be empty.', 'danger')
        return redirect(url_for('settings.index'))

    with db_manager.get_session() as db_session:
        existing = (
            db_session.query(SetupPattern)
            .filter(
                SetupPattern.user_id == user.user_id,
                func.lower(SetupPattern.pattern_name) == name.lower()
            )
            .first()
        )
        if existing:
            flash(f'Pattern "{name}" already exists.', 'warning')
            return redirect(url_for('settings.index'))

        pattern = SetupPattern(
            user_id=user.user_id,
            pattern_name=name,
            is_active=True,
        )
        db_session.add(pattern)
        db_session.commit()
        flash(f'Pattern "{name}" created.', 'success')

    return redirect(url_for('settings.index'))


@bp.route('/patterns/<int:pattern_id>/edit', methods=['POST'])
@login_required
def edit_pattern(pattern_id: int):
    user = AuthContext.require_user()
    new_name = request.form.get('pattern_name', '').strip()
    if not new_name:
        flash('Pattern name cannot be empty.', 'danger')
        return redirect(url_for('settings.index'))

    with db_manager.get_session() as db_session:
        pattern = (
            db_session.query(SetupPattern)
            .filter_by(pattern_id=pattern_id, user_id=user.user_id)
            .one_or_none()
        )
        if pattern is None:
            flash('Pattern not found.', 'warning')
            return redirect(url_for('settings.index'))

        # Check for duplicate (case-insensitive), excluding self
        duplicate = (
            db_session.query(SetupPattern)
            .filter(
                SetupPattern.user_id == user.user_id,
                func.lower(SetupPattern.pattern_name) == new_name.lower(),
                SetupPattern.pattern_id != pattern_id
            )
            .first()
        )
        if duplicate:
            flash(f'Pattern "{new_name}" already exists.', 'warning')
            return redirect(url_for('settings.index'))

        old_name = pattern.pattern_name
        pattern.pattern_name = new_name
        db_session.commit()
        flash(f'Pattern "{old_name}" renamed to "{new_name}".', 'success')

    return redirect(url_for('settings.index'))


@bp.route('/patterns/<int:pattern_id>/deactivate', methods=['POST'])
@login_required
def deactivate_pattern(pattern_id: int):
    user = AuthContext.require_user()
    with db_manager.get_session() as db_session:
        pattern = (
            db_session.query(SetupPattern)
            .filter_by(pattern_id=pattern_id, user_id=user.user_id)
            .one_or_none()
        )
        if pattern is None:
            flash('Pattern not found.', 'warning')
            return redirect(url_for('settings.index'))

        trade_count = (
            db_session.query(func.count(TradeAnnotation.annotation_id))
            .filter(
                TradeAnnotation.user_id == user.user_id,
                TradeAnnotation.setup_pattern_id == pattern_id
            )
            .scalar() or 0
        )
        if trade_count > 0:
            flash(
                f'Cannot deactivate "{pattern.pattern_name}": {trade_count} trade(s) use this pattern.',
                'warning'
            )
            return redirect(url_for('settings.index'))

        pattern.is_active = False
        db_session.commit()
        flash(f'Pattern "{pattern.pattern_name}" deactivated.', 'success')

    return redirect(url_for('settings.index'))


@bp.route('/sources', methods=['POST'])
@login_required
def create_source():
    user = AuthContext.require_user()
    name = request.form.get('source_name', '').strip()
    if not name:
        flash('Source name cannot be empty.', 'danger')
        return redirect(url_for('settings.index'))

    with db_manager.get_session() as db_session:
        existing = (
            db_session.query(SetupSource)
            .filter(
                SetupSource.user_id == user.user_id,
                func.lower(SetupSource.source_name) == name.lower()
            )
            .first()
        )
        if existing:
            flash(f'Source "{name}" already exists.', 'warning')
            return redirect(url_for('settings.index'))

        source = SetupSource(
            user_id=user.user_id,
            source_name=name,
            is_active=True,
        )
        db_session.add(source)
        db_session.commit()
        flash(f'Source "{name}" created.', 'success')

    return redirect(url_for('settings.index'))


@bp.route('/sources/<int:source_id>/edit', methods=['POST'])
@login_required
def edit_source(source_id: int):
    user = AuthContext.require_user()
    new_name = request.form.get('source_name', '').strip()
    if not new_name:
        flash('Source name cannot be empty.', 'danger')
        return redirect(url_for('settings.index'))

    with db_manager.get_session() as db_session:
        source = (
            db_session.query(SetupSource)
            .filter_by(source_id=source_id, user_id=user.user_id)
            .one_or_none()
        )
        if source is None:
            flash('Source not found.', 'warning')
            return redirect(url_for('settings.index'))

        duplicate = (
            db_session.query(SetupSource)
            .filter(
                SetupSource.user_id == user.user_id,
                func.lower(SetupSource.source_name) == new_name.lower(),
                SetupSource.source_id != source_id
            )
            .first()
        )
        if duplicate:
            flash(f'Source "{new_name}" already exists.', 'warning')
            return redirect(url_for('settings.index'))

        old_name = source.source_name
        source.source_name = new_name
        db_session.commit()
        flash(f'Source "{old_name}" renamed to "{new_name}".', 'success')

    return redirect(url_for('settings.index'))


@bp.route('/sources/<int:source_id>/deactivate', methods=['POST'])
@login_required
def deactivate_source(source_id: int):
    user = AuthContext.require_user()
    with db_manager.get_session() as db_session:
        source = (
            db_session.query(SetupSource)
            .filter_by(source_id=source_id, user_id=user.user_id)
            .one_or_none()
        )
        if source is None:
            flash('Source not found.', 'warning')
            return redirect(url_for('settings.index'))

        trade_count = (
            db_session.query(func.count(TradeAnnotation.annotation_id))
            .filter(
                TradeAnnotation.user_id == user.user_id,
                TradeAnnotation.setup_source_id == source_id
            )
            .scalar() or 0
        )
        if trade_count > 0:
            flash(
                f'Cannot deactivate "{source.source_name}": {trade_count} trade(s) use this source.',
                'warning'
            )
            return redirect(url_for('settings.index'))

        source.is_active = False
        db_session.commit()
        flash(f'Source "{source.source_name}" deactivated.', 'success')

    return redirect(url_for('settings.index'))


@bp.route('/atm-options', methods=['POST'])
@login_required
def create_atm_option():
    user = AuthContext.require_user()
    name = request.form.get('option_name', '').strip()
    if not name:
        flash('ATM option name cannot be empty.', 'danger')
        return redirect(url_for('settings.index'))

    with db_manager.get_session() as db_session:
        existing = (
            db_session.query(AtmOption)
            .filter(
                AtmOption.user_id == user.user_id,
                func.lower(AtmOption.option_name) == name.lower()
            )
            .first()
        )
        if existing:
            flash(f'ATM option "{name}" already exists.', 'warning')
            return redirect(url_for('settings.index'))

        option = AtmOption(user_id=user.user_id, option_name=name, is_active=True)
        db_session.add(option)
        db_session.commit()
        flash(f'ATM option "{name}" created.', 'success')

    return redirect(url_for('settings.index'))


@bp.route('/atm-options/<int:option_id>/edit', methods=['POST'])
@login_required
def edit_atm_option(option_id: int):
    user = AuthContext.require_user()
    new_name = request.form.get('option_name', '').strip()
    if not new_name:
        flash('ATM option name cannot be empty.', 'danger')
        return redirect(url_for('settings.index'))

    with db_manager.get_session() as db_session:
        option = (
            db_session.query(AtmOption)
            .filter_by(option_id=option_id, user_id=user.user_id)
            .one_or_none()
        )
        if option is None:
            flash('ATM option not found.', 'warning')
            return redirect(url_for('settings.index'))

        duplicate = (
            db_session.query(AtmOption)
            .filter(
                AtmOption.user_id == user.user_id,
                func.lower(AtmOption.option_name) == new_name.lower(),
                AtmOption.option_id != option_id
            )
            .first()
        )
        if duplicate:
            flash(f'ATM option "{new_name}" already exists.', 'warning')
            return redirect(url_for('settings.index'))

        old_name = option.option_name
        option.option_name = new_name
        db_session.commit()
        flash(f'ATM option "{old_name}" renamed to "{new_name}".', 'success')

    return redirect(url_for('settings.index'))


@bp.route('/atm-options/<int:option_id>/deactivate', methods=['POST'])
@login_required
def deactivate_atm_option(option_id: int):
    user = AuthContext.require_user()
    with db_manager.get_session() as db_session:
        option = (
            db_session.query(AtmOption)
            .filter_by(option_id=option_id, user_id=user.user_id)
            .one_or_none()
        )
        if option is None:
            flash('ATM option not found.', 'warning')
            return redirect(url_for('settings.index'))

        trade_count = (
            db_session.query(func.count(TradeAnnotation.annotation_id))
            .filter(
                TradeAnnotation.user_id == user.user_id,
                TradeAnnotation.atm_option_id == option_id
            )
            .scalar() or 0
        )
        if trade_count > 0:
            flash(
                f'Cannot deactivate "{option.option_name}": {trade_count} trade(s) use this option.',
                'warning'
            )
            return redirect(url_for('settings.index'))

        option.is_active = False
        db_session.commit()
        flash(f'ATM option "{option.option_name}" deactivated.', 'success')

    return redirect(url_for('settings.index'))


# ── Backtest Strategy Types ────────────────────────────────────────────────

@bp.route('/backtest-strategy-types', methods=['POST'])
@login_required
def create_bt_strategy():
    user = AuthContext.require_user()
    name = request.form.get('strategy_name', '').strip()
    if not name:
        flash('Strategy name cannot be empty.', 'danger')
        return redirect(url_for('settings.index'))

    with db_manager.get_session() as db_session:
        existing = (
            db_session.query(BacktestStrategyType)
            .filter(
                BacktestStrategyType.user_id == user.user_id,
                func.lower(BacktestStrategyType.strategy_name) == name.lower(),
            )
            .first()
        )
        if existing:
            flash(f'Strategy "{name}" already exists.', 'warning')
            return redirect(url_for('settings.index'))
        db_session.add(BacktestStrategyType(user_id=user.user_id, strategy_name=name))
        db_session.commit()
        flash(f'Strategy "{name}" created.', 'success')

    return redirect(url_for('settings.index'))


@bp.route('/backtest-strategy-types/<int:strategy_type_id>/edit', methods=['POST'])
@login_required
def edit_bt_strategy(strategy_type_id: int):
    user = AuthContext.require_user()
    new_name = request.form.get('strategy_name', '').strip()
    if not new_name:
        flash('Strategy name cannot be empty.', 'danger')
        return redirect(url_for('settings.index'))

    with db_manager.get_session() as db_session:
        row = (
            db_session.query(BacktestStrategyType)
            .filter_by(strategy_type_id=strategy_type_id, user_id=user.user_id)
            .one_or_none()
        )
        if row is None:
            flash('Strategy not found.', 'warning')
            return redirect(url_for('settings.index'))
        duplicate = (
            db_session.query(BacktestStrategyType)
            .filter(
                BacktestStrategyType.user_id == user.user_id,
                func.lower(BacktestStrategyType.strategy_name) == new_name.lower(),
                BacktestStrategyType.strategy_type_id != strategy_type_id,
            )
            .first()
        )
        if duplicate:
            flash(f'Strategy "{new_name}" already exists.', 'warning')
            return redirect(url_for('settings.index'))
        old_name = row.strategy_name
        row.strategy_name = new_name
        db_session.commit()
        flash(f'Strategy "{old_name}" renamed to "{new_name}".', 'success')

    return redirect(url_for('settings.index'))


@bp.route('/backtest-strategy-types/<int:strategy_type_id>/deactivate', methods=['POST'])
@login_required
def deactivate_bt_strategy(strategy_type_id: int):
    user = AuthContext.require_user()
    with db_manager.get_session() as db_session:
        row = (
            db_session.query(BacktestStrategyType)
            .filter_by(strategy_type_id=strategy_type_id, user_id=user.user_id)
            .one_or_none()
        )
        if row is None:
            flash('Strategy not found.', 'warning')
            return redirect(url_for('settings.index'))
        run_count = (
            db_session.query(func.count(BacktestRun.run_id))
            .filter(
                BacktestRun.user_id == user.user_id,
                BacktestRun.strategy_type_id == strategy_type_id,
            )
            .scalar() or 0
        )
        if run_count > 0:
            flash(
                f'Cannot deactivate "{row.strategy_name}": {run_count} run(s) use this strategy.',
                'warning',
            )
            return redirect(url_for('settings.index'))
        row.is_active = False
        db_session.commit()
        flash(f'Strategy "{row.strategy_name}" deactivated.', 'success')

    return redirect(url_for('settings.index'))


# ── Backtest Underlyings ───────────────────────────────────────────────────

@bp.route('/backtest-underlyings', methods=['POST'])
@login_required
def create_bt_underlying():
    user = AuthContext.require_user()
    name = request.form.get('underlying_name', '').strip()
    if not name:
        flash('Underlying name cannot be empty.', 'danger')
        return redirect(url_for('settings.index'))

    with db_manager.get_session() as db_session:
        existing = (
            db_session.query(BacktestUnderlying)
            .filter(
                BacktestUnderlying.user_id == user.user_id,
                func.lower(BacktestUnderlying.underlying_name) == name.lower(),
            )
            .first()
        )
        if existing:
            flash(f'Underlying "{name}" already exists.', 'warning')
            return redirect(url_for('settings.index'))
        db_session.add(BacktestUnderlying(user_id=user.user_id, underlying_name=name))
        db_session.commit()
        flash(f'Underlying "{name}" created.', 'success')

    return redirect(url_for('settings.index'))


@bp.route('/backtest-underlyings/<int:underlying_id>/edit', methods=['POST'])
@login_required
def edit_bt_underlying(underlying_id: int):
    user = AuthContext.require_user()
    new_name = request.form.get('underlying_name', '').strip()
    if not new_name:
        flash('Underlying name cannot be empty.', 'danger')
        return redirect(url_for('settings.index'))

    with db_manager.get_session() as db_session:
        row = (
            db_session.query(BacktestUnderlying)
            .filter_by(underlying_id=underlying_id, user_id=user.user_id)
            .one_or_none()
        )
        if row is None:
            flash('Underlying not found.', 'warning')
            return redirect(url_for('settings.index'))
        duplicate = (
            db_session.query(BacktestUnderlying)
            .filter(
                BacktestUnderlying.user_id == user.user_id,
                func.lower(BacktestUnderlying.underlying_name) == new_name.lower(),
                BacktestUnderlying.underlying_id != underlying_id,
            )
            .first()
        )
        if duplicate:
            flash(f'Underlying "{new_name}" already exists.', 'warning')
            return redirect(url_for('settings.index'))
        old_name = row.underlying_name
        row.underlying_name = new_name
        db_session.commit()
        flash(f'Underlying "{old_name}" renamed to "{new_name}".', 'success')

    return redirect(url_for('settings.index'))


@bp.route('/backtest-underlyings/<int:underlying_id>/deactivate', methods=['POST'])
@login_required
def deactivate_bt_underlying(underlying_id: int):
    user = AuthContext.require_user()
    with db_manager.get_session() as db_session:
        row = (
            db_session.query(BacktestUnderlying)
            .filter_by(underlying_id=underlying_id, user_id=user.user_id)
            .one_or_none()
        )
        if row is None:
            flash('Underlying not found.', 'warning')
            return redirect(url_for('settings.index'))
        run_count = (
            db_session.query(func.count(BacktestRun.run_id))
            .filter(
                BacktestRun.user_id == user.user_id,
                BacktestRun.underlying_id == underlying_id,
            )
            .scalar() or 0
        )
        if run_count > 0:
            flash(
                f'Cannot deactivate "{row.underlying_name}": {run_count} run(s) use this underlying.',
                'warning',
            )
            return redirect(url_for('settings.index'))
        row.is_active = False
        db_session.commit()
        flash(f'Underlying "{row.underlying_name}" deactivated.', 'success')

    return redirect(url_for('settings.index'))
