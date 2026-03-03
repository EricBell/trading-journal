"""Positions route: /positions."""

from flask import Blueprint, render_template, request

from ..auth import login_required
from ...authorization import AuthContext
from ...database import db_manager
from ...models import Position

bp = Blueprint('positions', __name__)


@bp.route('/positions')
@login_required
def index():
    user = AuthContext.require_user()
    open_only = request.args.get('open_only') == '1'
    symbol = (request.args.get('symbol', '').strip().upper()) or None

    with db_manager.get_session() as session:
        query = session.query(Position).filter_by(user_id=user.user_id)

        if open_only:
            query = query.filter(Position.closed_at.is_(None), Position.current_qty != 0)
        if symbol:
            query = query.filter(Position.symbol == symbol)

        positions = query.order_by(Position.symbol).all()

    return render_template(
        'positions/index.html',
        positions=positions,
        user=user,
        open_only=open_only,
        symbol=symbol or '',
    )
