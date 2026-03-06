"""Positions route: /positions."""

from flask import Blueprint, render_template, request, session
from sqlalchemy import asc, desc
from sqlalchemy.orm import joinedload

from ..auth import login_required
from ...authorization import AuthContext
from ...database import db_manager
from ...models import Account, Position

bp = Blueprint('positions', __name__)

SORT_COLUMNS = {
    'symbol':   Position.symbol,
    'type':     Position.instrument_type,
    'qty':      Position.current_qty,
    'avg_cost': Position.avg_cost_basis,
    'pnl':      Position.realized_pnl,
    'opened':   Position.opened_at,
    'status':   Position.closed_at,
}
DEFAULT_SORT, DEFAULT_DIR = 'symbol', 'asc'
PER_PAGE_OPTIONS = [10, 25, 50, 100]


@bp.route('/positions')
@login_required
def index():
    user = AuthContext.require_user()
    open_only = request.args.get('open_only') == '1'
    symbol = (request.args.get('symbol', '').strip().upper()) or None
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
                session['positions_per_page'] = per_page
        except ValueError:
            pass
    per_page = session.get('positions_per_page', 25)

    try:
        page = max(1, int(request.args.get('page', 1)))
    except ValueError:
        page = 1

    with db_manager.get_session() as db_session:
        query = db_session.query(Position).filter_by(user_id=user.user_id)

        if open_only:
            query = query.filter(Position.closed_at.is_(None), Position.current_qty != 0)
        if symbol:
            query = query.filter(Position.symbol == symbol)
        if account_filter:
            try:
                query = query.filter(Position.account_id == int(account_filter))
            except ValueError:
                pass

        col = SORT_COLUMNS[sort_col]
        order_fn = asc if sort_dir == 'asc' else desc
        query = query.order_by(order_fn(col))

        total = query.count()
        total_pages = max(1, (total + per_page - 1) // per_page)
        page = min(page, total_pages)
        positions = query.options(joinedload(Position.account)).offset((page - 1) * per_page).limit(per_page).all()

        accounts = (
            db_session.query(Account)
            .filter_by(user_id=user.user_id)
            .order_by(Account.account_name)
            .all()
        )

    return render_template(
        'positions/index.html',
        positions=positions,
        user=user,
        open_only=open_only,
        symbol=symbol or '',
        account_filter=account_filter or '',
        accounts=accounts,
        sort_col=sort_col,
        sort_dir=sort_dir,
        page=page,
        per_page=per_page,
        total=total,
        total_pages=total_pages,
        per_page_options=PER_PAGE_OPTIONS,
    )
