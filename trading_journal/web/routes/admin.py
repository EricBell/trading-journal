"""Admin routes: /admin/users."""

import json
import logging
from datetime import date

logger = logging.getLogger(__name__)

from flask import Blueprint, Response, flash, make_response, redirect, render_template, request, stream_with_context, url_for
from sqlalchemy import func
from werkzeug.security import generate_password_hash

from ..auth import admin_required
from ...authorization import AuthContext
from ...database import db_manager
from ...models import Account, CompletedTrade, JournalNote, TradeAnnotation, User
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


_EXPLORE_ROW_LIMIT = 500

_EXPLORE_STARTER_SQL = """\
SELECT r.symbol, r.grail_plan_id, r.timeframe,
       r.fetch_start_at, r.fetch_end_at,
       COUNT(o.series_id) AS bars_cached,
       r.status
FROM hg_market_data_requests r
LEFT JOIN ohlcv_price_series o
  ON o.symbol = r.symbol
 AND o.timeframe = r.timeframe
 AND o.timestamp BETWEEN r.fetch_start_at AND r.fetch_end_at
GROUP BY r.hg_market_data_request_id, r.symbol, r.grail_plan_id,
         r.timeframe, r.fetch_start_at, r.fetch_end_at, r.status
ORDER BY r.fetch_start_at DESC"""


def _validate_select_only(sql: str):
    stripped = sql.strip().lstrip(';').strip()
    if not stripped.upper().startswith('SELECT'):
        return "Only SELECT statements are allowed."
    if ';' in stripped[:-1]:
        return "Multiple statements are not allowed."
    return None


def _get_ohlcv_summary(session):
    from sqlalchemy import func as sa_func
    from ...models import OhlcvPriceSeries

    total = session.query(sa_func.count()).select_from(OhlcvPriceSeries).scalar() or 0
    symbol_count = session.query(sa_func.count(sa_func.distinct(OhlcvPriceSeries.symbol))).scalar() or 0
    date_range = session.query(
        sa_func.min(OhlcvPriceSeries.timestamp),
        sa_func.max(OhlcvPriceSeries.timestamp),
    ).one()
    timeframe_counts = session.query(
        OhlcvPriceSeries.timeframe,
        sa_func.count(),
    ).group_by(OhlcvPriceSeries.timeframe).all()
    return {
        'total': total,
        'symbol_count': symbol_count,
        'earliest': date_range[0],
        'latest': date_range[1],
        'timeframes': dict(timeframe_counts),
    }


def _get_hg_coverage(session, user_id):
    from sqlalchemy import desc
    from ...models import HgAnalysisResult, HgMarketDataRequest

    rows = (
        session.query(HgMarketDataRequest, HgAnalysisResult)
        .outerjoin(
            HgAnalysisResult,
            HgAnalysisResult.hg_market_data_request_id == HgMarketDataRequest.hg_market_data_request_id,
        )
        .filter(HgMarketDataRequest.user_id == user_id)
        .order_by(desc(HgMarketDataRequest.created_at))
        .all()
    )
    return [
        {
            'request_id': r.hg_market_data_request_id,
            'grail_plan_id': r.grail_plan_id,
            'symbol': r.symbol,
            'timeframe': r.timeframe,
            'fetch_start_at': r.fetch_start_at,
            'fetch_end_at': r.fetch_end_at,
            'bars_received': r.bars_received,
            'status': r.status,
            'has_analysis': a is not None,
        }
        for r, a in rows
    ]


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
    user_id = current_user.user_id
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

    _VALID_TIMEFRAMES = {'1': 'minute', '5': 'minute', '15': 'minute'}
    form_timeframe = '5'

    # Explore tab state
    explore_sql = _EXPLORE_STARTER_SQL
    explore_columns = None
    explore_rows = None
    explore_row_count = None
    explore_capped = False
    explore_error = None
    ohlcv_summary = None
    hg_coverage = None

    action = request.form.get('action') if request.method == 'POST' else None

    if action == 'explore':
        explore_sql = request.form.get('sql', '').strip() or _EXPLORE_STARTER_SQL
        explore_error = _validate_select_only(explore_sql)
        if not explore_error:
            try:
                from sqlalchemy import text as sa_text
                with db_manager.get_session() as session:
                    result_proxy = session.execute(sa_text(explore_sql))
                    explore_columns = list(result_proxy.keys())
                    fetched = result_proxy.mappings().fetchmany(_EXPLORE_ROW_LIMIT + 1)
                    explore_capped = len(fetched) > _EXPLORE_ROW_LIMIT
                    explore_rows = [dict(r) for r in fetched[:_EXPLORE_ROW_LIMIT]]
                    explore_row_count = len(explore_rows)
            except Exception as exc:
                explore_error = str(exc)
        with db_manager.get_session() as session:
            ohlcv_summary = _get_ohlcv_summary(session)
            hg_coverage = _get_hg_coverage(session, user_id)
        active_tab = 'explore'

    elif request.method == 'POST':
        form_symbol = request.form.get('symbol', '').strip().upper()
        form_date = request.form.get('date', '').strip()
        form_timeframe = request.form.get('timeframe', '5')
        if form_timeframe not in _VALID_TIMEFRAMES:
            form_timeframe = '5'

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
                    multiplier = form_timeframe
                    timespan = _VALID_TIMEFRAMES[form_timeframe]
                    url = (
                        f"https://api.polygon.io/v2/aggs/ticker/{form_symbol}"
                        f"/range/{multiplier}/{timespan}/{from_ms}/{to_ms}"
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
        active_tab = 'sample'

    else:  # GET
        tab = request.args.get('tab', '')
        if tab == 'explore':
            active_tab = 'explore'
            with db_manager.get_session() as session:
                ohlcv_summary = _get_ohlcv_summary(session)
                hg_coverage = _get_hg_coverage(session, user_id)
        else:
            active_tab = 'resolve'

    # Load unenriched trades for the missing-data panel
    cutoff_dt = datetime.now(dt_timezone.utc) - timedelta(days=730)
    raw_trades = get_unenriched_option_trades(user_id)
    # Annotate each with user-tz display time and "too_old" flag
    missing_trades = []
    for t in raw_trades:
        ts = t["opened_at"]
        if ts is not None:
            # Timestamps are stored as naive ET (no tz in source data) but PostgreSQL
            # labels them UTC. Strip that label and display as-is in the app timezone.
            naive = ts.replace(tzinfo=None)
            display_dt = naive.strftime("%Y-%m-%d %H:%M") + f" {user_tz_str}"
            # For "too old" check, reinterpret as the app timezone to get real UTC
            ts_real_utc = naive.replace(tzinfo=user_tz).astimezone(dt_timezone.utc)
            too_old = ts_real_utc < cutoff_dt
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
        form_timeframe=form_timeframe,
        missing_trades=missing_trades,
        max_per_fetch=4,
        active_tab=active_tab,
        explore_sql=explore_sql,
        explore_columns=explore_columns,
        explore_rows=explore_rows,
        explore_row_count=explore_row_count,
        explore_capped=explore_capped,
        explore_error=explore_error,
        ohlcv_summary=ohlcv_summary,
        hg_coverage=hg_coverage,
    )


@bp.route('/market-data/enrich', methods=['POST'])
@admin_required
def market_data_enrich():
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

    try:
        result = enrich_trades_by_ids(user_id, trade_ids)
    except Exception as exc:
        flash(f"Enrichment failed: {exc}", 'danger')
        return redirect(url_for('admin.market_data'))

    if result.get('disabled'):
        flash('Enrichment is disabled — MASSIVE_API_KEY is not set.', 'warning')
    elif result.get('error'):
        flash(f"Enrichment error: {result['error']}", 'danger')
    elif result['enriched'] == 0 and result['failed'] > 0:
        flash(
            f"Enrichment failed for all {result['failed']} trade(s). "
            "The data may be too old for your API plan, or the API returned no price data.",
            'danger',
        )
    elif result['failed'] > 0:
        flash(
            f"Enriched {result['enriched']} trade(s). "
            f"{result['failed']} failed (no price data returned).",
            'warning',
        )
    elif result['unavailable'] > 0 and result['enriched'] == 0:
        flash(
            f"{result['unavailable']} trade(s) could not be enriched — "
            "data is too old for your API plan (free tier covers ~2 years).",
            'warning',
        )
    else:
        flash(
            f"✅ Enriched {result['enriched']} trade(s)."
            + (f" {result['unavailable']} too old for free tier." if result['unavailable'] else ""),
            'success',
        )

    return redirect(url_for('admin.market_data'))


_HG_BATCH_CAP = 20  # max new analyses per batch run


@bp.route('/market-data/hg-analysis')
@admin_required
def hg_analysis():
    """Show all HG analyses in the DB and batch-trigger controls."""
    from sqlalchemy import desc
    from ...models import HgAnalysisResult, HgMarketDataRequest

    current_user = AuthContext.get_current_user()
    user_id = current_user.user_id

    with db_manager.get_session() as session:
        requests = (
            session.query(HgMarketDataRequest)
            .filter_by(user_id=user_id)
            .order_by(desc(HgMarketDataRequest.created_at))
            .all()
        )
        request_ids = [r.hg_market_data_request_id for r in requests]
        analyses = (
            session.query(HgAnalysisResult)
            .filter(HgAnalysisResult.hg_market_data_request_id.in_(request_ids))
            .all()
        ) if request_ids else []

        # Build index: request_id → analysis
        analysis_by_request = {a.hg_market_data_request_id: a for a in analyses}

        rows = [
            {
                'request_id': r.hg_market_data_request_id,
                'grail_plan_id': r.grail_plan_id,
                'symbol': r.symbol,
                'timeframe': r.timeframe,
                'fetch_status': r.status,
                'bars_received': r.bars_received,
                'window_rule': r.window_rule,
                'created_at': r.created_at,
                'analysis': analysis_by_request.get(r.hg_market_data_request_id),
            }
            for r in requests
        ]

    return render_template(
        'admin/hg_analysis.html',
        user=current_user,
        rows=rows,
        batch_cap=_HG_BATCH_CAP,
    )


@bp.route('/market-data/hg-batch', methods=['POST'])
@admin_required
def hg_batch():
    """Run hydration + evaluation for all unanalyzed grail-linked trades (capped)."""
    from ...database import db_manager as _db
    from ...grail_connector import find_grail_match
    from ...hg_evaluator import evaluate_hg_plan
    from ...hg_hydration import hydrate_hg_plan
    from ...models import CompletedTrade, HgMarketDataRequest

    current_user = AuthContext.get_current_user()
    user_id = current_user.user_id

    import os
    if not os.environ.get('MASSIVE_API_KEY'):
        flash('MASSIVE_API_KEY is not set — cannot fetch bars.', 'warning')
        return redirect(url_for('admin.hg_analysis'))

    # Load all trades for this user, ordered newest first
    with _db.get_session() as session:
        trades = (
            session.query(CompletedTrade)
            .filter_by(user_id=user_id)
            .order_by(CompletedTrade.opened_at.desc())
            .all()
        )
        # Collect already-analyzed grail plan IDs to avoid re-querying
        analyzed_plan_ids = set(
            row[0]
            for row in session.query(HgMarketDataRequest.grail_plan_id)
            .filter_by(user_id=user_id, status='success')
            .all()
        )

    analyzed = 0
    skipped = 0
    failed = 0
    no_match = 0

    for trade in trades:
        if analyzed >= _HG_BATCH_CAP:
            break

        match_symbol = trade.symbol.split()[0] if trade.instrument_type == 'OPTION' else trade.symbol
        grail_record = find_grail_match(match_symbol, trade.opened_at)
        if grail_record is None:
            no_match += 1
            continue

        grail_plan_id = str(grail_record['id'])
        if grail_plan_id in analyzed_plan_ids:
            skipped += 1
            continue

        hydration = hydrate_hg_plan(user_id, grail_plan_id, completed_trade_id=trade.completed_trade_id)
        if hydration['status'] == 'failed':
            failed += 1
            continue

        evaluation = evaluate_hg_plan(hydration['request_id'])
        if evaluation['status'] not in ('ok', 'skipped'):
            failed += 1
            continue

        analyzed_plan_ids.add(grail_plan_id)
        analyzed += 1

    flash(
        f"Batch complete: {analyzed} analyzed, {skipped} already done, "
        f"{failed} failed, {no_match} trades had no grail match.",
        'success' if analyzed > 0 else 'info',
    )
    return redirect(url_for('admin.hg_analysis'))


# ---------------------------------------------------------------------------
# Grail plan browser + zone analysis
# ---------------------------------------------------------------------------

# Free-tier Massive API: 5 requests/minute.
_MASSIVE_RATE_PER_MINUTE = 5   # how many sequential API calls fit in one 60s window
_GRAIL_BATCH_DEFAULT = 4       # default plan count shown in the UI input


@bp.route('/grail-plans')
@admin_required
def grail_plans():
    """Browse grail_files plans with filters and show analysis outcomes."""
    from ...grail_connector import list_grail_plans
    from ...models import GrailPlanAnalysis

    current_user = AuthContext.get_current_user()

    symbol = request.args.get('symbol', '').strip() or None
    date_from_str = request.args.get('date_from', '')
    date_to_str = request.args.get('date_to', '')
    asset_type = request.args.get('asset_type', '') or None
    page = max(1, int(request.args.get('page', 1)))
    per_page = 25

    date_from = None
    date_to = None
    try:
        if date_from_str:
            date_from = date.fromisoformat(date_from_str)
        if date_to_str:
            date_to = date.fromisoformat(date_to_str)
    except ValueError:
        pass

    result = list_grail_plans(
        symbol=symbol,
        date_from=date_from,
        date_to=date_to,
        asset_type=asset_type,
        page=page,
        per_page=per_page,
    )
    plan_rows = result.get("rows", [])
    total = result.get("total", 0)
    total_pages = max(1, (total + per_page - 1) // per_page)

    # Overlay existing analysis outcomes
    plan_ids = [str(r["id"]) for r in plan_rows]
    analysis_by_plan: dict = {}
    if plan_ids:
        with db_manager.get_session() as session:
            analyses = (
                session.query(GrailPlanAnalysis)
                .filter(GrailPlanAnalysis.grail_plan_id.in_(plan_ids))
                .all()
            )
            analysis_by_plan = {a.grail_plan_id: a for a in analyses}

    # Aggregate stats across ALL analyzed plans (not just current page)
    stats = _grail_analysis_stats()

    return render_template(
        'admin/grail_plans.html',
        user=current_user,
        plan_rows=plan_rows,
        analysis_by_plan=analysis_by_plan,
        total=total,
        page=page,
        total_pages=total_pages,
        stats=stats,
        filters={'symbol': symbol or '', 'date_from': date_from_str, 'date_to': date_to_str, 'asset_type': asset_type or ''},
    )


@bp.route('/grail-plans/<int:plan_id>')
@admin_required
def grail_plan_detail(plan_id: int):
    """Show a single grail plan's details and analysis result."""
    from ...grail_connector import fetch_grail_plan_full
    from ...models import GrailPlanAnalysis

    current_user = AuthContext.get_current_user()

    plan = fetch_grail_plan_full(plan_id)
    if plan is None:
        flash(f"Grail plan {plan_id} not found.", 'warning')
        return redirect(url_for('admin.grail_plans'))

    with db_manager.get_session() as session:
        analysis = (
            session.query(GrailPlanAnalysis)
            .filter_by(grail_plan_id=str(plan_id))
            .order_by(GrailPlanAnalysis.analysis_version.desc())
            .first()
        )

    return render_template(
        'admin/grail_plan_detail.html',
        user=current_user,
        plan=plan,
        analysis=analysis,
    )


@bp.route('/grail-plans/<int:plan_id>/analyze', methods=['POST'])
@admin_required
def grail_plan_analyze(plan_id: int):
    """Trigger zone analysis for a single grail plan."""
    import os
    from ...grail_analyzer import run_grail_plan_analysis

    current_user = AuthContext.get_current_user()

    if not os.environ.get('MASSIVE_API_KEY'):
        flash('MASSIVE_API_KEY is not set — bar fetch is disabled; analysis will use cached bars only.', 'warning')

    force = request.form.get('force') == '1'
    result = run_grail_plan_analysis(grail_plan_id=plan_id, user_id=current_user.user_id, force=force)

    if result['status'] == 'ok':
        flash(f"Analysis complete: {result['message']}", 'success')
    elif result['status'] == 'skipped':
        flash(f"Already analyzed: outcome={result['outcome']}", 'info')
    else:
        flash(f"Analysis failed: {result['message']}", 'danger')

    redirect_to = request.referrer or url_for('admin.grail_plan_detail', plan_id=plan_id)
    return redirect(redirect_to)


@bp.route('/grail-plans/analyze-batch', methods=['POST'])
@admin_required
def grail_plans_analyze_batch():
    """Stream zone analysis progress as SSE for up to batch_count plans.

    Rate-limit strategy: execute up to _MASSIVE_RATE_PER_MINUTE calls per
    60-second window.  Measure how long each sub-batch takes, then sleep the
    remainder of 60s before starting the next sub-batch.  The client reads the
    SSE stream with fetch() and updates the UI in real time.

    SSE event shapes:
        {"done": N, "total": M, "plan_id": "...", "outcome": "...", "fetch_status": "..."}
        {"waiting": true, "wait_seconds": N, "done": N, "total": M}
        {"complete": true, "ok": N, "skipped": N, "failed": N, "message": "..."}
        {"error": "..."}
    """
    import os
    import time as _time
    from ...grail_analyzer import run_grail_plan_analysis
    from ...grail_connector import list_grail_plans
    from ...models import GrailPlanAnalysis

    current_user = AuthContext.get_current_user()
    user_id = current_user.user_id

    # Validate batch_count: positive integer only
    raw_count = request.form.get('batch_count', str(_GRAIL_BATCH_DEFAULT)).strip()
    try:
        batch_count = int(raw_count)
        if batch_count < 1:
            raise ValueError
    except (ValueError, TypeError):
        batch_count = _GRAIL_BATCH_DEFAULT

    symbol = request.form.get('symbol', '').strip() or None
    date_from_str = request.form.get('date_from', '')
    date_to_str = request.form.get('date_to', '')
    asset_type = request.form.get('asset_type', '') or None

    date_from = None
    date_to = None
    try:
        if date_from_str:
            date_from = date.fromisoformat(date_from_str)
        if date_to_str:
            date_to = date.fromisoformat(date_to_str)
    except ValueError:
        pass

    def _sse(data: dict) -> str:
        return f"data: {json.dumps(data)}\n\n"

    @stream_with_context
    def generate():
        try:
            # Resolve plan IDs — fetch enough to fill batch_count after skipping already-analyzed.
            # Exclude 'no_data' outcomes so rate-limited or subscription-gated plans can be retried.
            result = list_grail_plans(
                symbol=symbol, date_from=date_from, date_to=date_to,
                asset_type=asset_type, page=1, per_page=max(batch_count * 10, 200)
            )
            all_ids = [str(r["id"]) for r in result.get("rows", [])]

            with db_manager.get_session() as session:
                analyzed_ids = {
                    a.grail_plan_id
                    for a in session.query(GrailPlanAnalysis.grail_plan_id)
                    .filter(GrailPlanAnalysis.grail_plan_id.in_(all_ids))
                    .filter(GrailPlanAnalysis.outcome != 'no_data')
                    .all()
                }

            to_analyze = [pid for pid in all_ids if pid not in analyzed_ids][:batch_count]
            total = len(to_analyze)

            if total == 0:
                yield _sse({"complete": True, "ok": 0, "skipped": 0, "failed": 0,
                            "elapsed_secs": 0.0,
                            "message": "All matching plans already analyzed."})
                return

            logger.info("grail batch start: total=%d user_id=%s", total, user_id)

            ok = skipped = failed = done = 0
            batch_start = _time.monotonic()

            for pid in to_analyze:
                r = run_grail_plan_analysis(grail_plan_id=int(pid), user_id=user_id)
                fetch_status = r.get('fetch_status', '')

                if fetch_status == 'rate_limited':
                    # Stop this sub-batch immediately; client will wait and issue a new request.
                    logger.info("grail batch: rate_limited on plan %s, stopping sub-batch", pid)
                    break

                if r['status'] == 'skipped':
                    skipped += 1
                elif r['status'] == 'ok':
                    ok += 1
                else:
                    failed += 1
                done += 1

                yield _sse({
                    "done": done,
                    "total": total,
                    "plan_id": pid,
                    "outcome": r.get('outcome', ''),
                    "fetch_status": fetch_status,
                })
                logger.info(
                    "grail batch: plan_id=%s outcome=%s fetch_status=%s bars_scanned=%s",
                    pid, r.get('outcome', ''), fetch_status, r.get('bars_scanned', '?'),
                )

            elapsed_secs = round(_time.monotonic() - batch_start, 1)
            yield _sse({"complete": True, "ok": ok, "skipped": skipped, "failed": failed,
                        "elapsed_secs": elapsed_secs, "message": ""})
            logger.info("grail batch complete: ok=%d skipped=%d failed=%d elapsed=%.1fs",
                        ok, skipped, failed, elapsed_secs)

        except GeneratorExit:
            pass  # client disconnected — stop silently
        except Exception as exc:
            logger.exception("grail batch stream error")
            yield _sse({"error": str(exc)})

    return Response(
        generate(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',   # prevent nginx from buffering the stream
        },
    )


def _grail_analysis_stats() -> dict:
    """Return aggregate counts across all grail_plan_analyses rows."""
    try:
        from sqlalchemy import func as sqlfunc
        from ...models import GrailPlanAnalysis
        with db_manager.get_session() as session:
            total_analyzed = session.query(sqlfunc.count(GrailPlanAnalysis.grail_plan_analyses_id)).scalar() or 0
            by_outcome = dict(
                session.query(GrailPlanAnalysis.outcome, sqlfunc.count())
                .group_by(GrailPlanAnalysis.outcome)
                .all()
            )
            entry_reached = sum(
                v for k, v in by_outcome.items() if k in ('success', 'failure', 'inconclusive')
            )
        return {
            'total_analyzed': total_analyzed,
            'entry_reached': entry_reached,
            'success': by_outcome.get('success', 0),
            'failure': by_outcome.get('failure', 0),
            'inconclusive': by_outcome.get('inconclusive', 0),
            'no_entry': by_outcome.get('no_entry', 0),
        }
    except Exception as exc:
        logger.warning("_grail_analysis_stats failed: %s", exc)
        return {}


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
        note_counts = dict(
            session.query(JournalNote.user_id, func.count())
            .group_by(JournalNote.user_id)
            .all()
        )
    for u in user_list:
        u['annotation_count'] = counts.get(u['user_id'], 0)
        u['note_count'] = note_counts.get(u['user_id'], 0)
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

            journal_notes = (
                session.query(JournalNote)
                .filter(JournalNote.user_id == uid)
                .order_by(JournalNote.created_at.asc())
                .all()
            )

            users_out.append({
                'user_id': user_obj.user_id,
                'username': user_obj.username,
                'accounts': list(buckets.values()),
                'journal_notes': [
                    {
                        'note_id': n.note_id,
                        'title': n.title,
                        'body': n.body,
                        'created_at': n.created_at.isoformat() if n.created_at else None,
                        'updated_at': n.updated_at.isoformat() if n.updated_at else None,
                    }
                    for n in journal_notes
                ],
            })

    payload = {
        'export_metadata': {
            'exported_at': date.today().isoformat(),
            'format_version': '3.0',
            'exported_by': current_user.username,
            'schema': {
                'description': 'Complete export of all manually entered data. Suitable for re-import.',
                'trade_annotation_natural_key': ['username', 'symbol', 'opened_at'],
                'journal_note_natural_key': ['username', 'created_at'],
            },
        },
        'users': users_out,
    }

    response = make_response(json.dumps(payload, indent=2))
    filename = f"annotations_export_{date.today().isoformat()}.json"
    response.headers['Content-Disposition'] = f'attachment; filename={filename}'
    response.headers['Content-Type'] = 'application/json'
    return response
