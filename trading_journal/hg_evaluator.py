"""Deterministic HG plan evaluator — Phase 3.

Reads bars from ohlcv_price_series for an already-hydrated HgMarketDataRequest,
runs the bar-scan algorithm defined in the design doc, and writes the result to
hg_analysis_results.

Public API:
    evaluate_hg_plan(request_id, analysis_version=1) -> dict
"""

import logging
from datetime import timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import text

from .database import db_manager
from .grail_connector import _grail_engine
from .models import CompletedTrade, HgAnalysisResult, HgMarketDataRequest, OhlcvPriceSeries

logger = logging.getLogger(__name__)

_ANALYSIS_VERSION = 1


def evaluate_hg_plan(request_id: int, analysis_version: int = _ANALYSIS_VERSION) -> dict:
    """
    Run the deterministic HG evaluator for an already-hydrated request.

    Loads bars from ohlcv_price_series, scans them chronologically, and writes
    an HgAnalysisResult row.  Idempotent: an existing result for the same
    (request_id, analysis_version) is returned without recomputing.

    Returns:
        {
            'status':           'ok' | 'skipped' | 'failed',
            'result_id':        int | None,
            'entry_touched':    bool,
            'entry_touch_type': str,
            'tp1_reached':      bool,
            'tp2_reached':      bool,
            'bars_scanned':     int,
            'message':          str,
        }
    """
    # 1. Load request row
    request = _load_request(request_id)
    if request is None:
        return _fail(None, f"request_id={request_id} not found")

    if request.status != "success":
        return _fail(None, f"request status is '{request.status}', expected 'success'")

    # 2. Idempotency check
    existing_result = _find_existing_result(request_id, analysis_version)
    if existing_result is not None:
        return {
            "status": "skipped",
            "result_id": existing_result.hg_analysis_result_id,
            "entry_touched": existing_result.entry_touched,
            "entry_touch_type": existing_result.entry_touch_type,
            "tp1_reached": existing_result.tp1_reached,
            "tp2_reached": existing_result.tp2_reached,
            "bars_scanned": existing_result.bars_scanned,
            "message": "result already exists",
        }

    # 3. Load grail plan parameters
    plan_params = _load_plan_params(request.grail_plan_id)
    if plan_params is None:
        return _fail(None, f"could not extract plan params from grail_plan_id={request.grail_plan_id}")

    side = plan_params["side"]
    zone_low = plan_params["zone_low"]
    zone_high = plan_params["zone_high"]
    tp1 = plan_params["tp1"]
    tp2 = plan_params["tp2"]
    stop = plan_params["stop"]
    instrument_type = plan_params["instrument_type"]

    if side is None or zone_low is None or zone_high is None:
        return _fail(None, "plan is missing side or entry zone")

    # Eval window = fetch window (v1 simplification per design doc)
    eval_start = request.fetch_start_at
    eval_end = request.fetch_end_at

    # 4. Load bars
    bars = _load_bars(request.symbol, request.timeframe, eval_start, eval_end)
    bars_scanned = len(bars)

    # 5. Run bar scan
    scan = _scan_bars(bars, side, float(zone_low), float(zone_high), tp1, tp2)

    # 6. Load linked trade comparison fields
    linked = _load_linked_trade(request.user_id, request.completed_trade_id)

    # 7. Write hg_analysis_results
    result_id = _write_result(
        request=request,
        analysis_version=analysis_version,
        side=side,
        instrument_type=instrument_type,
        zone_low=zone_low,
        zone_high=zone_high,
        tp1=tp1,
        tp2=tp2,
        stop=stop,
        eval_start=eval_start,
        eval_end=eval_end,
        bars_scanned=bars_scanned,
        scan=scan,
        linked=linked,
    )

    logger.info(
        "evaluate_hg_plan: request_id=%s result_id=%s entry_touched=%s tp1=%s tp2=%s bars=%d",
        request_id, result_id, scan["entry_touched"], scan["tp1_reached"], scan["tp2_reached"],
        bars_scanned,
    )

    return {
        "status": "ok",
        "result_id": result_id,
        "entry_touched": scan["entry_touched"],
        "entry_touch_type": scan["entry_touch_type"],
        "tp1_reached": scan["tp1_reached"],
        "tp2_reached": scan["tp2_reached"],
        "bars_scanned": bars_scanned,
        "message": f"evaluated {bars_scanned} bars",
    }


# ---------------------------------------------------------------------------
# Bar-scan algorithm
# ---------------------------------------------------------------------------

def _scan_bars(
    bars: list,
    side: str,
    zone_low: float,
    zone_high: float,
    tp1: Optional[float],
    tp2: Optional[float],
) -> dict:
    """
    Chronological bar scan.  Returns a dict of all evaluation result fields.

    Entry overlap condition (both long and short):
        bar.low <= zone_high  AND  bar.high >= zone_low

    Touch classification (long — price approaches from above):
        near edge = zone_high, far edge = zone_low
        top_of_zone  : bar.low > midpoint          (clipped top half only)
        in_zone      : zone_low < bar.low <= mid   (reached lower half, not far edge)
        bottom_of_zone: bar.low == zone_low         (exactly at far edge, rare)
        through_zone : bar.low < zone_low           (past far edge)

    Touch classification (short — price approaches from below):
        near edge = zone_low, far edge = zone_high
        top_of_zone  : bar.high < midpoint          (clipped bottom half only)
        in_zone      : mid <= bar.high < zone_high  (reached upper half, not far edge)
        bottom_of_zone: bar.high == zone_high        (exactly at far edge, rare)
        through_zone : bar.high > zone_high          (past far edge)

    TP evaluation uses stock_price_range[0] for both long and short:
        long  : TP reached when bar.high >= target_price
        short : TP reached when bar.low  <= target_price
        (Only checked on bars after the entry bar, not the entry bar itself.)

    MFE/MAE are computed from the entry bar onwards (inclusive).
    """
    zone_mid = (zone_low + zone_high) / 2.0

    entry_touched = False
    entry_bar_idx: Optional[int] = None
    entry_first_touch_at = None
    entry_touch_type = "never"
    entry_touch_price: Optional[float] = None
    bars_to_entry: Optional[int] = None

    tp1_reached = False
    tp1_reached_at = None
    tp2_reached = False
    tp2_reached_at = None
    bars_from_entry_to_tp1: Optional[int] = None
    bars_from_entry_to_tp2: Optional[int] = None

    mfe: Optional[float] = None
    mae: Optional[float] = None
    mfe_at = None
    mae_at = None

    for i, bar in enumerate(bars):
        bar_low = float(bar.low_price)
        bar_high = float(bar.high_price)

        # --- Entry detection ---
        if not entry_touched:
            overlaps = bar_low <= zone_high and bar_high >= zone_low
            if overlaps:
                entry_touched = True
                entry_bar_idx = i
                entry_first_touch_at = bar.timestamp
                bars_to_entry = i  # bars scanned before this one

                if side == "long":
                    entry_touch_type = _classify_touch_long(bar_low, zone_low, zone_high, zone_mid)
                    entry_touch_price = bar_low
                else:
                    entry_touch_type = _classify_touch_short(bar_high, zone_low, zone_high, zone_mid)
                    entry_touch_price = bar_high

        # --- Post-entry: MFE/MAE and TP checks ---
        if entry_touched:
            ref = entry_touch_price  # type: ignore[assignment]

            if side == "long":
                excursion_fav = bar_high - ref
                excursion_adv = ref - bar_low
            else:
                excursion_fav = ref - bar_low
                excursion_adv = bar_high - ref

            if mfe is None or excursion_fav > mfe:
                mfe = excursion_fav
                mfe_at = bar.timestamp
            if mae is None or excursion_adv > mae:
                mae = excursion_adv
                mae_at = bar.timestamp

            # TPs only on bars strictly after the entry bar
            if i > entry_bar_idx:  # type: ignore[operator]
                bars_after = i - entry_bar_idx  # type: ignore[operator]

                if not tp1_reached and tp1 is not None:
                    hit = (side == "long" and bar_high >= tp1) or \
                          (side == "short" and bar_low <= tp1)
                    if hit:
                        tp1_reached = True
                        tp1_reached_at = bar.timestamp
                        bars_from_entry_to_tp1 = bars_after

                if not tp2_reached and tp2 is not None:
                    hit = (side == "long" and bar_high >= tp2) or \
                          (side == "short" and bar_low <= tp2)
                    if hit:
                        tp2_reached = True
                        tp2_reached_at = bar.timestamp
                        bars_from_entry_to_tp2 = bars_after

    return {
        "entry_touched": entry_touched,
        "entry_first_touch_at": entry_first_touch_at,
        "entry_touch_type": entry_touch_type,
        "entry_touch_price": entry_touch_price,
        "bars_to_entry": bars_to_entry,
        "tp1_reached": tp1_reached,
        "tp1_reached_at": tp1_reached_at,
        "tp2_reached": tp2_reached,
        "tp2_reached_at": tp2_reached_at,
        "max_favorable_excursion": mfe,
        "max_adverse_excursion": mae,
        "mfe_at": mfe_at,
        "mae_at": mae_at,
        "bars_from_entry_to_tp1": bars_from_entry_to_tp1,
        "bars_from_entry_to_tp2": bars_from_entry_to_tp2,
    }


def _classify_touch_long(bar_low: float, zone_low: float, zone_high: float, zone_mid: float) -> str:
    """Classify how deeply price entered the zone for a long setup (price from above)."""
    if bar_low < zone_low:
        return "through_zone"
    if bar_low == zone_low:
        return "bottom_of_zone"
    if bar_low <= zone_mid:
        return "in_zone"
    return "top_of_zone"  # zone_mid < bar_low <= zone_high


def _classify_touch_short(bar_high: float, zone_low: float, zone_high: float, zone_mid: float) -> str:
    """Classify how deeply price entered the zone for a short setup (price from below)."""
    if bar_high > zone_high:
        return "through_zone"
    if bar_high == zone_high:
        return "bottom_of_zone"
    if bar_high >= zone_mid:
        return "in_zone"
    return "top_of_zone"  # zone_low <= bar_high < zone_mid


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _load_request(request_id: int) -> Optional[HgMarketDataRequest]:
    try:
        with db_manager.get_session() as session:
            return session.get(HgMarketDataRequest, request_id)
    except Exception as exc:
        logger.warning("_load_request failed: %s", exc)
        return None


def _find_existing_result(request_id: int, analysis_version: int) -> Optional[HgAnalysisResult]:
    try:
        with db_manager.get_session() as session:
            return (
                session.query(HgAnalysisResult)
                .filter_by(
                    hg_market_data_request_id=request_id,
                    analysis_version=analysis_version,
                )
                .first()
            )
    except Exception as exc:
        logger.warning("_find_existing_result failed: %s", exc)
        return None


def _load_plan_params(grail_plan_id: str) -> Optional[dict]:
    """
    Fetch the grail plan from grail_files and extract evaluation parameters.

    All price fields use stock_price_range when available (option plans store
    option premium in price_range but underlying prices in stock_price_range).
    """
    try:
        engine = _grail_engine()
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT id, asset_type, json_content->'trade_plan' AS trade_plan "
                    "FROM grail_files WHERE id = :pid"
                ),
                {"pid": int(grail_plan_id)},
            ).mappings().first()

        if row is None:
            logger.warning("_load_plan_params: grail_plan_id=%s not found", grail_plan_id)
            return None

        trade_plan = row["trade_plan"]
        if not trade_plan or not isinstance(trade_plan, dict):
            logger.warning("_load_plan_params: no trade_plan for id=%s", grail_plan_id)
            return None

        entry = trade_plan.get("entry") or {}
        exits = trade_plan.get("exits") or {}

        # Side
        direction = (entry.get("direction") or "").upper()
        side = "long" if direction == "LONG" else "short" if direction == "SHORT" else None

        # Entry zone (always underlying prices)
        ideal_zone = entry.get("ideal_zone") or {}
        zone_low = _to_float(ideal_zone.get("low"))
        zone_high = _to_float(ideal_zone.get("high"))

        # Targets — prefer stock_price_range (underlying), fall back to price_range
        targets = exits.get("profit_targets") or []
        tp1 = _target_price(targets, 0, side)
        tp2 = _target_price(targets, 1, side)

        # Stop — prefer stock_price_range, fall back to price_range
        stop_data = exits.get("stop_loss") or {}
        stop = _stop_price(stop_data, side)

        # instrument_type for hg_analysis_results CHECK constraint
        asset_type = (row["asset_type"] or "").upper()
        instrument_type = "option" if asset_type == "OPTIONS" else "equity"

        return {
            "side": side,
            "zone_low": zone_low,
            "zone_high": zone_high,
            "tp1": tp1,
            "tp2": tp2,
            "stop": stop,
            "instrument_type": instrument_type,
        }

    except Exception as exc:
        logger.warning("_load_plan_params failed for id=%s: %s", grail_plan_id, exc)
        return None


def _target_price(targets: list, idx: int, side: Optional[str]) -> Optional[float]:
    """Return a single representative price for the target at index idx.

    Uses stock_price_range when present (option plans).  For long setups uses
    the lower (conservative) bound; for short uses the upper (conservative) bound.
    Falls back to price_range for non-option plans.
    """
    if idx >= len(targets):
        return None
    t = targets[idx]
    price_list = t.get("stock_price_range") or t.get("price_range") or []
    if not price_list:
        return None
    if side == "short":
        return _to_float(price_list[-1])  # upper/conservative for short downside targets
    return _to_float(price_list[0])       # lower/conservative for long upside targets


def _stop_price(stop_data: dict, side: Optional[str]) -> Optional[float]:
    """Return a single representative stop price."""
    price_list = stop_data.get("stock_price_range") or stop_data.get("price_range") or []
    if not price_list:
        return None
    # For stops: long stop is below entry (use upper/tighter bound);
    # short stop is above entry (use lower/tighter bound).
    if side == "long":
        return _to_float(price_list[-1])
    return _to_float(price_list[0])


def _to_float(val) -> Optional[float]:
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _load_bars(symbol: str, timeframe: str, start, end) -> list:
    """Return OhlcvPriceSeries rows ordered by timestamp ascending."""
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


def _load_linked_trade(user_id: int, completed_trade_id: Optional[int]) -> dict:
    """Return trade comparison fields from completed_trades, or empty dict."""
    if completed_trade_id is None:
        return {}
    try:
        with db_manager.get_session() as session:
            trade = session.get(CompletedTrade, completed_trade_id)
            if trade is None or trade.user_id != user_id:
                return {}
            return {
                "linked_trade_opened_at": trade.opened_at,
                "linked_trade_closed_at": trade.closed_at,
                "linked_trade_entry_price": trade.entry_avg_price,
                "linked_trade_exit_price": trade.exit_avg_price,
            }
    except Exception as exc:
        logger.warning("_load_linked_trade failed: %s", exc)
        return {}


def _write_result(
    *,
    request: HgMarketDataRequest,
    analysis_version: int,
    side: str,
    instrument_type: str,
    zone_low,
    zone_high,
    tp1: Optional[float],
    tp2: Optional[float],
    stop: Optional[float],
    eval_start,
    eval_end,
    bars_scanned: int,
    scan: dict,
    linked: dict,
) -> int:
    """Insert the HgAnalysisResult row and return its PK."""
    with db_manager.get_session() as session:
        result = HgAnalysisResult(
            user_id=request.user_id,
            hg_market_data_request_id=request.hg_market_data_request_id,
            grail_plan_id=request.grail_plan_id,
            grail_plan_created_at=request.grail_plan_created_at,
            completed_trade_id=request.completed_trade_id,
            symbol=request.symbol,
            timeframe=request.timeframe,
            analysis_version=analysis_version,
            # Plan params snapshotted at eval time
            side=side,
            instrument_type=instrument_type,
            entry_zone_low=zone_low,
            entry_zone_high=zone_high,
            target_1_price=tp1,
            target_2_price=tp2,
            stop_price=stop,
            # Eval window
            eval_start_at=eval_start,
            eval_end_at=eval_end,
            bars_scanned=bars_scanned,
            # Entry behavior
            entry_touched=scan["entry_touched"],
            entry_first_touch_at=scan["entry_first_touch_at"],
            entry_touch_type=scan["entry_touch_type"],
            entry_touch_price=scan["entry_touch_price"],
            # Target behavior
            tp1_reached=scan["tp1_reached"],
            tp1_reached_at=scan["tp1_reached_at"],
            tp2_reached=scan["tp2_reached"],
            tp2_reached_at=scan["tp2_reached_at"],
            # Excursion metrics
            max_favorable_excursion=scan["max_favorable_excursion"],
            max_adverse_excursion=scan["max_adverse_excursion"],
            mfe_at=scan["mfe_at"],
            mae_at=scan["mae_at"],
            # Timing
            bars_to_entry=scan["bars_to_entry"],
            bars_from_entry_to_tp1=scan["bars_from_entry_to_tp1"],
            bars_from_entry_to_tp2=scan["bars_from_entry_to_tp2"],
            # Linked trade
            linked_trade_opened_at=linked.get("linked_trade_opened_at"),
            linked_trade_closed_at=linked.get("linked_trade_closed_at"),
            linked_trade_entry_price=linked.get("linked_trade_entry_price"),
            linked_trade_exit_price=linked.get("linked_trade_exit_price"),
            notes={},
        )
        session.add(result)
        session.commit()
        session.refresh(result)
        return result.hg_analysis_result_id


def _fail(result_id, message: str) -> dict:
    logger.warning("evaluate_hg_plan failed: %s", message)
    return {
        "status": "failed",
        "result_id": result_id,
        "entry_touched": False,
        "entry_touch_type": "never",
        "tp1_reached": False,
        "tp2_reached": False,
        "bars_scanned": 0,
        "message": message,
    }
