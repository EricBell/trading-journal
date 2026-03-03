"""Dashboard route: /"""

from flask import Blueprint, render_template

from ..auth import login_required
from ...authorization import AuthContext

bp = Blueprint('dashboard', __name__)


@bp.route('/')
@login_required
def index():
    user = AuthContext.get_current_user()
    return render_template('dashboard/index.html', user=user)
