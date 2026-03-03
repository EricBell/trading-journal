"""Trade routes: /trades, /trades/<id>, /trades/<id>/annotate."""

from flask import Blueprint, flash, redirect, render_template, request, url_for

from ..auth import login_required
from ...authorization import AuthContext
from ...database import db_manager
from ...models import CompletedTrade, SetupPattern

bp = Blueprint('trades', __name__)


@bp.route('/trades')
@login_required
def index():
    user = AuthContext.require_user()
    symbol = request.args.get('symbol', '').strip() or None
    range_filter = request.args.get('range', '').strip() or None

    with db_manager.get_session() as session:
        query = session.query(CompletedTrade).filter_by(user_id=user.user_id)

        if symbol:
            query = query.filter(CompletedTrade.symbol == symbol.upper())

        if range_filter:
            from datetime import date, timedelta
            today = date.today()
            if range_filter.endswith('d'):
                try:
                    days = int(range_filter[:-1])
                    cutoff = today - timedelta(days=days - 1)
                    query = query.filter(CompletedTrade.closed_at >= cutoff)
                except ValueError:
                    pass

        trades = query.order_by(CompletedTrade.closed_at.desc()).all()

        # Fetch user patterns for filter dropdown
        patterns = (
            session.query(CompletedTrade.setup_pattern)
            .filter(
                CompletedTrade.user_id == user.user_id,
                CompletedTrade.setup_pattern.isnot(None),
            )
            .distinct()
            .all()
        )
        pattern_names = sorted(p[0] for p in patterns if p[0])

    return render_template(
        'trades/index.html',
        trades=trades,
        user=user,
        symbol=symbol or '',
        range_filter=range_filter or '',
        pattern_names=pattern_names,
    )


@bp.route('/trades/<int:trade_id>')
@login_required
def detail(trade_id: int):
    user = AuthContext.require_user()
    with db_manager.get_session() as session:
        trade = session.query(CompletedTrade).filter_by(
            completed_trade_id=trade_id, user_id=user.user_id
        ).one_or_none()
        if trade is None:
            flash('Trade not found.', 'warning')
            return redirect(url_for('trades.index'))

        executions = sorted(trade.executions, key=lambda e: e.exec_timestamp or '')

        patterns = (
            session.query(SetupPattern)
            .filter_by(user_id=user.user_id, is_active=True)
            .order_by(SetupPattern.pattern_name)
            .all()
        )
        pattern_names = [p.pattern_name for p in patterns]

    return render_template(
        'trades/detail.html',
        trade=trade,
        executions=executions,
        pattern_names=pattern_names,
        user=user,
    )


@bp.route('/trades/<int:trade_id>/annotate', methods=['POST'])
@login_required
def annotate(trade_id: int):
    user = AuthContext.require_user()
    with db_manager.get_session() as session:
        trade = session.query(CompletedTrade).filter_by(
            completed_trade_id=trade_id, user_id=user.user_id
        ).one_or_none()
        if trade is None:
            flash('Trade not found.', 'warning')
            return redirect(url_for('trades.index'))

        trade.setup_pattern = request.form.get('setup_pattern') or None
        trade.trade_notes = request.form.get('trade_notes') or None
        session.commit()
        flash('Trade updated.', 'success')

    return redirect(url_for('trades.detail', trade_id=trade_id))
