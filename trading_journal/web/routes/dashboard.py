"""Dashboard route: /"""

from flask import Blueprint, render_template

from ..auth import login_required
from ...authorization import AuthContext
from ...database import db_manager
from ...models import Account

bp = Blueprint('dashboard', __name__)


@bp.route('/')
@login_required
def index():
    user = AuthContext.get_current_user()
    with db_manager.get_session() as db_session:
        accounts = (
            db_session.query(Account)
            .filter_by(user_id=user.user_id)
            .order_by(Account.account_name)
            .all()
        )
    return render_template('dashboard/index.html', user=user, accounts=accounts)
