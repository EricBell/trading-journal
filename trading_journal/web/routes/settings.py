"""Settings routes: /settings — manage setup patterns and sources."""

from flask import Blueprint, flash, redirect, render_template, request, url_for
from sqlalchemy import func

from ..auth import login_required
from ...authorization import AuthContext
from ...database import db_manager
from ...models import TradeAnnotation, SetupPattern, SetupSource

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

    return render_template(
        'settings/index.html',
        user=user,
        pattern_rows=pattern_rows,
        source_rows=source_rows,
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
