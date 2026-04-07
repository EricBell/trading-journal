"""Zone-based grail plan analysis — plan-centric (not trade-linked).

Public API:
    run_grail_plan_analysis(grail_plan_id, user_id, analysis_version=1) -> dict
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import text

from .database import db_manager
from .grail_connector import _grail_engine
from .market_data import MassiveClient
from .models import GrailPlanAnalysis, OhlcvPriceSeries

logger = logging.getLogger(__name__)

_WINDOW_BEFORE_MINUTES = 90
_WINDOW_AFTER_MINUTES = 120
_ANALYSIS_VERSION = 1


def run_grail_plan_analysis(
    grail_plan_id: int,
    user_id: int,
    analysis_version: int = _ANALYSIS_VERSION,
) -> dict:
    """Fetch 1m bars for the plan window and run zone-based analysis. Idempotent.

    Fetch window: plan_created_at − 90m  through  plan_created_at + 120m

    Analysis:
    - Phase 1: scan bars for entry zone touch (entry_zone_low..entry_zone_high)
               and ideal entry touch (entry_price).
    - Phase 2: after first entry zone touch, scan for TP1 zone or stop zone hit.
               Stop has priority on bars where both are touched.

    Outcome values:
        no_entry    — entry zone never touched
        success     — entry touched, TP1 zone touched before stop zone
        failure     — entry touched, stop zone touched before TP1 zone
        inconclusive — entry touched, neither TP1 nor stop reached in window

    Returns:
        {'status': 'ok'|'skipped'|'failed', 'outcome': str|None, 'message': str}
    """
    # 1. Check idempotency
    existing = _find_existing(grail_plan_id, analysis_version)
    if existing is not None:
        return {
            "status": "skipped",
            "outcome": existing.outcome,
            "message": "analysis already exists",
        }

    # 2. Load plan from grail_files
    plan = _load_plan(grail_plan_id)
    if plan is None:
        return {"status": "failed", "outcome": None, "message": f"grail plan id={grail_plan_id} not found"}

    symbol = plan["ticker"]
    asset_type = (plan.get("asset_type") or "").upper()
    direction = (plan.get("entry_direction") or "").upper()
    side = "long" if direction == "LONG" else "short" if direction == "SHORT" else None

    entry_zone_low = _to_float(plan.get("entry_low"))
    entry_zone_high = _to_float(plan.get("entry_high"))
    entry_ideal = _to_float(plan.get("entry_price"))
    stop_zone_low = _to_float(plan.get("stop_low"))
    stop_zone_high = _to_float(plan.get("stop_high"))
    tp1_zone_low = _to_float(plan.get("tp1_low"))
    tp1_zone_high = _to_float(plan.get("tp1_high"))

    # Fall back to JSON for entry zone if pre-extracted columns are NULL
    if entry_zone_low is None or entry_zone_high is None:
        trade_plan = plan.get("json_content") or {}
        if isinstance(trade_plan, dict):
            ideal_zone = ((trade_plan.get("trade_plan") or {}).get("entry") or {}).get("ideal_zone") or {}
            entry_zone_low = entry_zone_low or _to_float(ideal_zone.get("low"))
            entry_zone_high = entry_zone_high or _to_float(ideal_zone.get("high"))
            if entry_ideal is None:
                entry_ideal = _to_float(ideal_zone.get("mid"))

    if entry_zone_low is None or entry_zone_high is None:
        return {"status": "failed", "outcome": None, "message": "plan has no entry zone (entry_low/entry_high NULL)"}

    # Symbol to fetch: for options use resolved_ticker (underlying), else use ticker
    fetch_symbol = symbol
    if asset_type == "OPTIONS":
        resolved = plan.get("resolved_ticker")
        if resolved:
            fetch_symbol = resolved
        else:
            # Best-effort: strip option suffix from ticker (e.g. "SPY241220P00580000" → "SPY")
            fetch_symbol = symbol[:3] if len(symbol) > 5 else symbol

    # 3. Compute fetch window
    plan_created_at = plan["file_created_at"]
    if plan_created_at.tzinfo is None:
        plan_created_at = plan_created_at.replace(tzinfo=timezone.utc)
    fetch_start = plan_created_at - timedelta(minutes=_WINDOW_BEFORE_MINUTES)
    fetch_end = plan_created_at + timedelta(minutes=_WINDOW_AFTER_MINUTES)

    # 4. Fetch bars (upsert into ohlcv_price_series)
    client = MassiveClient()
    fetch_status = "skipped"
    bars_fetched = 0

    if client.enabled:
        fetch_result = client.fetch_window_bars(fetch_symbol, fetch_start, fetch_end, "1m")
        bars_fetched = fetch_result.get("bars_received", 0)
        error = fetch_result.get("error")
        if error:
            fetch_status = "failed"
        elif bars_fetched == 0:
            fetch_status = "partial"
        else:
            fetch_status = "success"
    else:
        logger.warning("run_grail_plan_analysis: MASSIVE_API_KEY not set, using cached bars only")
        fetch_status = "skipped"

    # 5. Load bars from ohlcv_price_series
    bars = _load_bars(fetch_symbol, "1m", fetch_start, fetch_end)
    bars_scanned = len(bars)

    # 6. Run zone-based bar scan
    scan = _zone_scan(bars, side, entry_zone_low, entry_zone_high, entry_ideal,
                      stop_zone_low, stop_zone_high, tp1_zone_low, tp1_zone_high)

    # 7. Write result
    _write_result(
        grail_plan_id=grail_plan_id,
        user_id=user_id,
        analysis_version=analysis_version,
        symbol=symbol,
        asset_type=asset_type,
        side=side,
        entry_zone_low=entry_zone_low,
        entry_zone_high=entry_zone_high,
        entry_ideal=entry_ideal,
        stop_zone_low=stop_zone_low,
        stop_zone_high=stop_zone_high,
        tp1_zone_low=tp1_zone_low,
        tp1_zone_high=tp1_zone_high,
        fetch_start=fetch_start,
        fetch_end=fetch_end,
        bars_fetched=bars_fetched,
        fetch_status=fetch_status,
        bars_scanned=bars_scanned,
        scan=scan,
    )

    return {
        "status": "ok",
        "outcome": scan["outcome"],
        "message": f"{bars_scanned} bars scanned, outcome={scan['outcome']}",
    }


# ---------------------------------------------------------------------------
# Zone scan algorithm
# ---------------------------------------------------------------------------

def _zone_scan(
    bars: list,
    side: Optional[str],
    entry_zone_low: float,
    entry_zone_high: float,
    entry_ideal: Optional[float],
    stop_zone_low: Optional[float],
    stop_zone_high: Optional[float],
    tp1_zone_low: Optional[float],
    tp1_zone_high: Optional[float],
) -> dict:
    """
    Phase 1 — Entry scan (all bars):
      Detect first bar overlapping [entry_zone_low, entry_zone_high].
      Also track whether entry_ideal was touched.

    Phase 2 — Outcome scan (bars after entry bar):
      Stop has priority: if a bar touches stop zone, outcome = failure.
      Otherwise if it touches TP1 zone, outcome = success.
      Loop ends: outcome = inconclusive.

    Zone overlap: bar.low <= zone_high AND bar.high >= zone_low
    Ideal entry touch (long): bar.low <= entry_ideal
    Ideal entry touch (short): bar.high >= entry_ideal
    """
    entry_zone_touched = False
    entry_ideal_touched = False
    entry_first_touch_at = None
    entry_bar_idx = None
    bars_to_entry = None

    tp1_zone_touched = False
    tp1_zone_touch_at = None
    stop_zone_touched = False
    stop_zone_touch_at = None
    bars_to_outcome = None
    outcome = "no_entry"

    for i, bar in enumerate(bars):
        bar_low = float(bar.low_price)
        bar_high = float(bar.high_price)

        # Ideal entry check (throughout all bars, not just pre-entry)
        if not entry_ideal_touched and entry_ideal is not None:
            if side == "long" and bar_low <= entry_ideal:
                entry_ideal_touched = True
            elif side == "short" and bar_high >= entry_ideal:
                entry_ideal_touched = True
            elif side is None and bar_low <= entry_ideal <= bar_high:
                entry_ideal_touched = True

        if not entry_zone_touched:
            # Phase 1: look for entry zone overlap
            if bar_low <= entry_zone_high and bar_high >= entry_zone_low:
                entry_zone_touched = True
                entry_first_touch_at = bar.timestamp
                entry_bar_idx = i
                bars_to_entry = i
                outcome = "inconclusive"
        else:
            # Phase 2: bars strictly after entry bar
            if i <= entry_bar_idx:
                continue

            stop_hit = (
                stop_zone_low is not None and stop_zone_high is not None
                and bar_low <= stop_zone_high and bar_high >= stop_zone_low
            )
            tp1_hit = (
                tp1_zone_low is not None and tp1_zone_high is not None
                and bar_low <= tp1_zone_high and bar_high >= tp1_zone_low
            )

            if stop_hit:
                stop_zone_touched = True
                stop_zone_touch_at = bar.timestamp
                outcome = "failure"
                bars_to_outcome = i - entry_bar_idx
                break

            if tp1_hit:
                tp1_zone_touched = True
                tp1_zone_touch_at = bar.timestamp
                outcome = "success"
                bars_to_outcome = i - entry_bar_idx
                break

    return {
        "entry_zone_touched": entry_zone_touched,
        "entry_ideal_touched": entry_ideal_touched,
        "entry_first_touch_at": entry_first_touch_at,
        "bars_to_entry": bars_to_entry,
        "outcome": outcome,
        "tp1_zone_touched": tp1_zone_touched,
        "tp1_zone_touch_at": tp1_zone_touch_at,
        "stop_zone_touched": stop_zone_touched,
        "stop_zone_touch_at": stop_zone_touch_at,
        "bars_to_outcome": bars_to_outcome,
    }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _find_existing(grail_plan_id: int, analysis_version: int) -> Optional[GrailPlanAnalysis]:
    try:
        with db_manager.get_session() as session:
            return (
                session.query(GrailPlanAnalysis)
                .filter_by(grail_plan_id=str(grail_plan_id), analysis_version=analysis_version)
                .first()
            )
    except Exception as exc:
        logger.warning("_find_existing failed: %s", exc)
        return None


def _load_plan(grail_plan_id: int) -> Optional[dict]:
    try:
        engine = _grail_engine()
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT id, ticker, asset_type, entry_direction, file_created_at,"
                    "       entry_price, entry_low, entry_high,"
                    "       stop_low, stop_high, tp1_low, tp1_high,"
                    "       resolved_ticker, json_content->'trade_plan' AS json_content"
                    " FROM grail_files WHERE id = :pid"
                ),
                {"pid": grail_plan_id},
            ).mappings().first()
            return dict(row) if row is not None else None
    except Exception as exc:
        logger.warning("_load_plan failed for id=%s: %s", grail_plan_id, exc)
        return None


def _load_bars(symbol: str, timeframe: str, start: datetime, end: datetime) -> list:
    try:
        with db_manager.get_session() as session:
            return (
                session.query(OhlcvPriceSeries)
                .filter(
                    OhlcvPriceSeries.symbol == symbol,
                    OhlcvPriceSeries.timeframe == timeframe,
                    OhlcvPriceSeries.timestamp >= start,
                    OhlcvPriceSeries.timestamp <= end,
                    OhlcvPriceSeries.low_price.isnot(None),
                    OhlcvPriceSeries.high_price.isnot(None),
                )
                .order_by(OhlcvPriceSeries.timestamp.asc())
                .all()
            )
    except Exception as exc:
        logger.warning("_load_bars failed: %s", exc)
        return []


def _write_result(
    *,
    grail_plan_id: int,
    user_id: int,
    analysis_version: int,
    symbol: str,
    asset_type: str,
    side: Optional[str],
    entry_zone_low: float,
    entry_zone_high: float,
    entry_ideal: Optional[float],
    stop_zone_low: Optional[float],
    stop_zone_high: Optional[float],
    tp1_zone_low: Optional[float],
    tp1_zone_high: Optional[float],
    fetch_start: datetime,
    fetch_end: datetime,
    bars_fetched: int,
    fetch_status: str,
    bars_scanned: int,
    scan: dict,
) -> None:
    with db_manager.get_session() as session:
        row = GrailPlanAnalysis(
            user_id=user_id,
            grail_plan_id=str(grail_plan_id),
            symbol=symbol,
            asset_type=asset_type or None,
            side=side,
            entry_zone_low=entry_zone_low,
            entry_zone_high=entry_zone_high,
            entry_ideal=entry_ideal,
            stop_zone_low=stop_zone_low,
            stop_zone_high=stop_zone_high,
            tp1_zone_low=tp1_zone_low,
            tp1_zone_high=tp1_zone_high,
            fetch_start_at=fetch_start,
            fetch_end_at=fetch_end,
            bars_fetched=bars_fetched,
            fetch_status=fetch_status,
            analysis_version=analysis_version,
            bars_scanned=bars_scanned,
            entry_zone_touched=scan["entry_zone_touched"],
            entry_ideal_touched=scan["entry_ideal_touched"],
            entry_first_touch_at=scan["entry_first_touch_at"],
            bars_to_entry=scan["bars_to_entry"],
            outcome=scan["outcome"],
            tp1_zone_touched=scan["tp1_zone_touched"],
            tp1_zone_touch_at=scan["tp1_zone_touch_at"],
            stop_zone_touched=scan["stop_zone_touched"],
            stop_zone_touch_at=scan["stop_zone_touch_at"],
            bars_to_outcome=scan["bars_to_outcome"],
            analyzed_at=datetime.now(tz=timezone.utc),
        )
        session.add(row)
        session.commit()


def _to_float(val) -> Optional[float]:
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None
