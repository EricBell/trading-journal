"""JSON API routes for Chart.js: /api/dashboard, /api/trades."""

from datetime import date
from flask import Blueprint, jsonify, request

from ..auth import login_required
from ...authorization import AuthContext
from ...dashboard import DashboardEngine
from ...trade_completion import TradeCompletionEngine

bp = Blueprint('api', __name__, url_prefix='/api')


@bp.route('/dashboard')
@login_required
def dashboard():
    engine = DashboardEngine()

    symbol = request.args.get('symbol') or None
    date_range_str = request.args.get('range') or None

    start_date, end_date = None, None
    if date_range_str:
        try:
            start_date, end_date = engine.parse_date_range(date_range_str)
        except ValueError as e:
            return jsonify({'error': str(e)}), 400

    data = engine.generate_dashboard(
        start_date=start_date,
        end_date=end_date,
        symbol=symbol,
    )
    return jsonify(data)


@bp.route('/trades')
@login_required
def trades():
    engine = TradeCompletionEngine()
    symbol = request.args.get('symbol') or None
    date_range_str = request.args.get('range') or None

    start_date, end_date = None, None
    if date_range_str:
        try:
            dash = DashboardEngine()
            start_date, end_date = dash.parse_date_range(date_range_str)
        except ValueError as e:
            return jsonify({'error': str(e)}), 400

    summary = engine.get_completed_trades_summary(
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
    )
    return jsonify(summary)
