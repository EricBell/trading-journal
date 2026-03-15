"""Admin routes: /admin/users."""

import json
from datetime import date

from flask import Blueprint, flash, make_response, redirect, render_template, request, url_for
from sqlalchemy import func
from werkzeug.security import generate_password_hash

from ..auth import admin_required
from ...authorization import AuthContext
from ...database import db_manager
from ...models import Account, CompletedTrade, TradeAnnotation, User
from ...user_management import UserManager

bp = Blueprint('admin', __name__, url_prefix='/admin')


@bp.route('/users')
@admin_required
def users():
    with db_manager.get_session() as session:
        manager = UserManager(session)
        user_list = manager.list_users(include_inactive=True)
    return render_template('admin/users.html', users=user_list, user=AuthContext.get_current_user())


@bp.route('/users/create', methods=['POST'])
@admin_required
def create_user():
    username = request.form.get('username', '').strip()
    email = request.form.get('email', '').strip()
    is_admin = bool(request.form.get('is_admin'))
    password = request.form.get('password', '').strip()

    if not username or not email:
        flash('Username and email are required.', 'danger')
        return redirect(url_for('admin.users'))

    try:
        with db_manager.get_session() as session:
            manager = UserManager(session)
            user_obj, raw_api_key = manager.create_user(username, email, is_admin=is_admin)

            if password:
                user_obj.password_hash = generate_password_hash(password)

            session.commit()
            flash(
                f"User '{username}' created. API key: {raw_api_key} — save this now, it won't be shown again.",
                'success',
            )
    except ValueError as e:
        flash(f"Error: {e}", 'danger')
    except Exception as e:
        flash(f"Failed to create user: {e}", 'danger')

    return redirect(url_for('admin.users'))


@bp.route('/users/<int:target_user_id>/deactivate', methods=['POST'])
@admin_required
def deactivate_user(target_user_id: int):
    try:
        with db_manager.get_session() as session:
            manager = UserManager(session)
            manager.deactivate_user(target_user_id)
            session.commit()
            flash(f"User {target_user_id} deactivated.", 'success')
    except Exception as e:
        flash(f"Failed: {e}", 'danger')
    return redirect(url_for('admin.users'))


@bp.route('/users/<int:target_user_id>/reactivate', methods=['POST'])
@admin_required
def reactivate_user(target_user_id: int):
    try:
        with db_manager.get_session() as session:
            manager = UserManager(session)
            manager.reactivate_user(target_user_id)
            session.commit()
            flash(f"User {target_user_id} reactivated.", 'success')
    except Exception as e:
        flash(f"Failed: {e}", 'danger')
    return redirect(url_for('admin.users'))


@bp.route('/users/<int:target_user_id>/set-password', methods=['POST'])
@admin_required
def set_password(target_user_id: int):
    password = request.form.get('password', '').strip()
    if not password:
        flash('Password cannot be empty.', 'danger')
        return redirect(url_for('admin.users'))
    try:
        with db_manager.get_session() as session:
            user_obj = session.get(User, target_user_id)
            if user_obj is None:
                flash('User not found.', 'danger')
                return redirect(url_for('admin.users'))
            user_obj.password_hash = generate_password_hash(password)
            session.commit()
            flash(f"Password set for user {target_user_id}.", 'success')
    except Exception as e:
        flash(f"Failed: {e}", 'danger')
    return redirect(url_for('admin.users'))


_COMMON_TIMEZONES = [
    'US/Eastern', 'US/Central', 'US/Mountain', 'US/Pacific', 'UTC',
]


@bp.route('/users/<int:target_user_id>/set-timezone', methods=['POST'])
@admin_required
def set_timezone(target_user_id: int):
    tz = request.form.get('timezone', '').strip()
    if not tz:
        flash('Timezone cannot be empty.', 'danger')
        return redirect(url_for('admin.users'))
    try:
        import zoneinfo
        zoneinfo.ZoneInfo(tz)  # validates the timezone string
    except Exception:
        flash(f'Invalid timezone: {tz}', 'danger')
        return redirect(url_for('admin.users'))
    try:
        with db_manager.get_session() as session:
            user_obj = session.get(User, target_user_id)
            if user_obj is None:
                flash('User not found.', 'danger')
                return redirect(url_for('admin.users'))
            user_obj.timezone = tz
            session.commit()
            flash(f'Timezone set to {tz} for {user_obj.username}.', 'success')
    except Exception as e:
        flash(f'Failed: {e}', 'danger')
    return redirect(url_for('admin.users'))


@bp.route('/market-data', methods=['GET', 'POST'])
@admin_required
def market_data():
    import os
    import json
    import zoneinfo
    import urllib.request
    from datetime import datetime, timezone as dt_timezone, timedelta
    import urllib.error as urllib_error

    from ...market_data import get_unenriched_option_trades

    current_user = AuthContext.get_current_user()
    api_key = os.environ.get('MASSIVE_API_KEY', '')
    user_tz_str = current_user.timezone or 'US/Eastern'
    try:
        user_tz = zoneinfo.ZoneInfo(user_tz_str)
    except Exception:
        user_tz = zoneinfo.ZoneInfo('UTC')
        user_tz_str = 'UTC'

    result = None
    error = None
    form_symbol = ''
    form_date = ''

    if request.method == 'POST':
        form_symbol = request.form.get('symbol', '').strip().upper()
        form_date = request.form.get('date', '').strip()

        if not api_key:
            error = 'MASSIVE_API_KEY is not set in the environment.'
        elif not form_symbol:
            error = 'Symbol is required.'
        elif not form_date:
            error = 'Date is required.'
        else:
            try:
                dt = datetime.strptime(form_date, '%Y-%m-%d')
                cutoff = datetime.now() - timedelta(days=730)
                if dt < cutoff:
                    error = (
                        f"{form_date} is more than 2 years ago — "
                        "the free tier only covers the last 2 years of history."
                    )
                else:
                    from_ms = int(dt.replace(hour=0, minute=0, second=0).timestamp() * 1000)
                    to_ms   = int(dt.replace(hour=23, minute=59, second=59).timestamp() * 1000)
                    url = (
                        f"https://api.polygon.io/v2/aggs/ticker/{form_symbol}"
                        f"/range/15/minute/{from_ms}/{to_ms}"
                        f"?adjusted=false&sort=asc&limit=100&apiKey={api_key}"
                    )
                    try:
                        with urllib.request.urlopen(url, timeout=15) as resp:
                            data = json.loads(resp.read().decode())
                    except urllib_error.HTTPError as exc:
                        if exc.code == 403:
                            error = (
                                "403 Forbidden — check that MASSIVE_API_KEY is correct "
                                "and that your plan covers this symbol/date."
                            )
                        elif exc.code == 429:
                            error = "429 Too Many Requests — rate limit hit, wait a minute and try again."
                        else:
                            error = str(exc)
                        data = None
                    if data is not None:
                        if data.get("results"):
                            for bar in data["results"]:
                                bar_dt = datetime.fromtimestamp(
                                    bar["t"] / 1000, tz=dt_timezone.utc
                                ).astimezone(user_tz)
                                bar["_dt"] = bar_dt.strftime("%Y-%m-%d %H:%M %Z")
                        result = data
            except Exception as exc:
                error = str(exc)

    # Load unenriched trades for the missing-data panel
    user_id = current_user.user_id
    cutoff = datetime.now(dt_timezone.utc) - timedelta(days=730)
    raw_trades = get_unenriched_option_trades(user_id)
    # Annotate each with user-tz display time and "too_old" flag
    missing_trades = []
    for t in raw_trades:
        ts = t["opened_at"]
        if ts is not None:
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=dt_timezone.utc)
            display_dt = ts.astimezone(user_tz).strftime("%Y-%m-%d %H:%M %Z")
            too_old = ts < cutoff
        else:
            display_dt = "—"
            too_old = False
        missing_trades.append({**t, "display_dt": display_dt, "too_old": too_old})

    return render_template(
        'admin/market_data.html',
        user=current_user,
        api_key_set=bool(api_key),
        user_tz=user_tz_str,
        result=result,
        error=error,
        form_symbol=form_symbol,
        form_date=form_date,
        missing_trades=missing_trades,
        max_per_fetch=4,
        active_tab='sample' if request.method == 'POST' else 'resolve',
    )


@bp.route('/market-data/enrich', methods=['POST'])
@admin_required
def market_data_enrich():
    import threading
    from ...market_data import enrich_trades_by_ids

    current_user = AuthContext.get_current_user()
    raw_ids = request.form.getlist('trade_ids')
    trade_ids = []
    for v in raw_ids:
        try:
            trade_ids.append(int(v))
        except ValueError:
            pass

    if not trade_ids:
        flash('No trades selected.', 'warning')
        return redirect(url_for('admin.market_data'))

    user_id = current_user.user_id

    def _run():
        enrich_trades_by_ids(user_id, trade_ids)

    threading.Thread(target=_run, daemon=True).start()

    flash(
        f"Fetching underlying prices for {len(trade_ids)} trade(s) in the background — "
        "refresh this page in ~15 seconds to see results.",
        'info',
    )
    return redirect(url_for('admin.market_data'))


@bp.route('/export')
@admin_required
def export_page():
    current_user = AuthContext.get_current_user()
    with db_manager.get_session() as session:
        manager = UserManager(session)
        user_list = manager.list_users(include_inactive=False)
        counts = dict(
            session.query(TradeAnnotation.user_id, func.count())
            .group_by(TradeAnnotation.user_id)
            .all()
        )
    for u in user_list:
        u['annotation_count'] = counts.get(u['user_id'], 0)
    return render_template(
        'admin/export.html',
        users=user_list,
        user=current_user,
    )


@bp.route('/export/download', methods=['POST'])
@admin_required
def export_download():
    current_user = AuthContext.get_current_user()
    selected_user_ids = set(request.form.getlist('users'))

    with db_manager.get_session() as session:
        users_out = []

        for uid_str in selected_user_ids:
            try:
                uid = int(uid_str)
            except ValueError:
                continue

            user_obj = session.get(User, uid)
            if user_obj is None:
                continue

            annotations = (
                session.query(TradeAnnotation)
                .outerjoin(CompletedTrade, TradeAnnotation.completed_trade_id == CompletedTrade.completed_trade_id)
                .filter(TradeAnnotation.user_id == uid)
                .all()
            )

            accounts_by_id = {
                a.account_id: a
                for a in session.query(Account).filter(Account.user_id == uid).all()
            }

            buckets: dict = {}

            for ann in annotations:
                ct = ann.trade
                account_id = ct.account_id if ct else None
                bucket_key = str(account_id) if account_id is not None else 'null'

                if bucket_key not in buckets:
                    if account_id is not None and account_id in accounts_by_id:
                        acct = accounts_by_id[account_id]
                        buckets[bucket_key] = {
                            'account_id': acct.account_id,
                            'account_number': acct.account_number,
                            'account_name': acct.account_name or '',
                            'account_type': acct.account_type or '',
                            'annotations': [],
                        }
                    else:
                        buckets[bucket_key] = {
                            'account_id': None,
                            'account_number': None,
                            'account_name': 'No Account',
                            'account_type': None,
                            'annotations': [],
                        }

                pattern_name = ann.setup_pattern_rel.pattern_name if ann.setup_pattern_rel else None
                source_name = ann.setup_source_rel.source_name if ann.setup_source_rel else None

                buckets[bucket_key]['annotations'].append({
                    'annotation_id': ann.annotation_id,
                    'completed_trade_id': ann.completed_trade_id,
                    'symbol': ann.symbol,
                    'opened_at': ann.opened_at.isoformat() if ann.opened_at else None,
                    'setup_pattern': pattern_name,
                    'setup_source': source_name,
                    'stop_price': float(ann.stop_price) if ann.stop_price is not None else None,
                    'trade_notes': ann.trade_notes,
                    'strategy_category': ann.strategy_category,
                    'atm_engaged': ann.atm_engaged,
                    'exit_reason': ann.exit_reason,
                    'underlying_at_entry': float(ann.underlying_at_entry) if ann.underlying_at_entry is not None else None,
                    'created_at': ann.created_at.isoformat() if ann.created_at else None,
                    'updated_at': ann.updated_at.isoformat() if ann.updated_at else None,
                })

            users_out.append({
                'user_id': user_obj.user_id,
                'username': user_obj.username,
                'accounts': list(buckets.values()),
            })

    payload = {
        'export_metadata': {
            'exported_at': date.today().isoformat(),
            'format_version': '2.0',
            'exported_by': current_user.username,
        },
        'users': users_out,
    }

    response = make_response(json.dumps(payload, indent=2))
    filename = f"annotations_export_{date.today().isoformat()}.json"
    response.headers['Content-Disposition'] = f'attachment; filename={filename}'
    response.headers['Content-Type'] = 'application/json'
    return response
