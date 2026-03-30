"""On-demand HG plan bar hydration.

Phase 2 of the HG historical analysis feature.

Public API:
    hydrate_hg_plan(user_id, grail_plan_id, completed_trade_id=None, timeframe='1m') -> dict
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import text

from .database import db_manager
from .grail_connector import _grail_engine
from .market_data import MassiveClient
from .models import CompletedTrade, HgMarketDataRequest

logger = logging.getLogger(__name__)

_WINDOW_BEFORE_MINUTES = 30
_WINDOW_AFTER_MINUTES = 90


def hydrate_hg_plan(
    user_id: int,
    grail_plan_id: str,
    completed_trade_id: Optional[int] = None,
    timeframe: str = "1m",
) -> dict:
    """
    Fetch bars for the HG plan window and record the request in hg_market_data_requests.

    Fetch window:
      - Base:     grail_plan_created_at - 30m  through  grail_plan_created_at + 90m
      - Extended: if the linked trade closed after the base window end, extend to trade exit

    Idempotent: an existing successful request for the same
    (user_id, grail_plan_id, timeframe, fetch_start_at, fetch_end_at) is returned as-is.
    A failed or partial request for the same window is retried.

    Returns:
        {
            'status':        'success' | 'partial' | 'failed' | 'skipped',
            'request_id':    int | None,
            'bars_received': int,
            'message':       str,
        }
    """
    # 1. Look up grail plan
    plan = _fetch_grail_plan(grail_plan_id)
    if plan is None:
        return {
            "status": "failed",
            "request_id": None,
            "bars_received": 0,
            "message": f"grail plan id={grail_plan_id} not found in grail_files",
        }

    symbol = plan["ticker"]
    # file_created_at is stored as naive UTC in grail_files
    grail_created_at = plan["file_created_at"].replace(tzinfo=timezone.utc)

    # 2. Compute fetch window
    fetch_start = grail_created_at - timedelta(minutes=_WINDOW_BEFORE_MINUTES)
    base_end = grail_created_at + timedelta(minutes=_WINDOW_AFTER_MINUTES)
    fetch_end = base_end
    window_rule = "t-30_to_t+90"
    linked_trade_exit_at = None

    if completed_trade_id is not None:
        exit_ts = _get_trade_exit(user_id, completed_trade_id)
        if exit_ts is not None:
            if exit_ts.tzinfo is None:
                exit_ts = exit_ts.replace(tzinfo=timezone.utc)
            linked_trade_exit_at = exit_ts
            if exit_ts > base_end:
                fetch_end = exit_ts
                window_rule = "extended_to_trade_exit"

    # 3. Check for existing request with this exact window
    existing = _find_existing_request(user_id, grail_plan_id, timeframe, fetch_start, fetch_end)
    if existing is not None and existing.status == "success":
        return {
            "status": "skipped",
            "request_id": existing.hg_market_data_request_id,
            "bars_received": existing.bars_received or 0,
            "message": "already hydrated successfully",
        }

    # 4. Create or reuse request record (set to pending)
    request_id = _upsert_request(
        user_id=user_id,
        grail_plan_id=grail_plan_id,
        grail_plan_created_at=grail_created_at,
        completed_trade_id=completed_trade_id,
        symbol=symbol,
        timeframe=timeframe,
        fetch_start=fetch_start,
        fetch_end=fetch_end,
        window_rule=window_rule,
        linked_trade_exit_at=linked_trade_exit_at,
        existing=existing,
    )

    # 5. Fetch bars from Massive
    client = MassiveClient()
    if not client.enabled:
        _update_request(request_id, "failed", 0, None, None, "MASSIVE_API_KEY not set")
        return {
            "status": "failed",
            "request_id": request_id,
            "bars_received": 0,
            "message": "MASSIVE_API_KEY not set",
        }

    fetch_result = client.fetch_window_bars(symbol, fetch_start, fetch_end, timeframe)

    # 6. Update request record with outcome
    bars_received = fetch_result.get("bars_received", 0)
    error_text = fetch_result.get("error")

    if error_text:
        status = "failed"
    elif bars_received == 0:
        # API returned OK but no bars in window (e.g. non-trading hours)
        status = "partial"
    else:
        status = "success"

    _update_request(
        request_id=request_id,
        status=status,
        bars_received=bars_received,
        first_bar_at=fetch_result.get("first_bar_at"),
        last_bar_at=fetch_result.get("last_bar_at"),
        error_text=error_text,
    )

    return {
        "status": status,
        "request_id": request_id,
        "bars_received": bars_received,
        "message": error_text or f"{bars_received} bars stored",
    }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _fetch_grail_plan(grail_plan_id: str) -> Optional[dict]:
    """Return the grail_files row for grail_plan_id, or None on miss/error."""
    try:
        engine = _grail_engine()
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT id, ticker, file_created_at FROM grail_files WHERE id = :pid"),
                {"pid": int(grail_plan_id)},
            ).mappings().first()
            return dict(row) if row is not None else None
    except Exception as exc:
        logger.warning("_fetch_grail_plan failed for id=%s: %s", grail_plan_id, exc)
        return None


def _get_trade_exit(user_id: int, completed_trade_id: int) -> Optional[datetime]:
    """Return the closed_at timestamp for a completed trade, or None."""
    try:
        with db_manager.get_session() as session:
            trade = session.get(CompletedTrade, completed_trade_id)
            if trade is None or trade.user_id != user_id:
                return None
            return trade.closed_at
    except Exception as exc:
        logger.warning("_get_trade_exit failed for trade_id=%s: %s", completed_trade_id, exc)
        return None


def _find_existing_request(
    user_id: int,
    grail_plan_id: str,
    timeframe: str,
    fetch_start: datetime,
    fetch_end: datetime,
) -> Optional[HgMarketDataRequest]:
    """Return an existing HgMarketDataRequest matching the exact window, or None."""
    try:
        with db_manager.get_session() as session:
            return (
                session.query(HgMarketDataRequest)
                .filter_by(
                    user_id=user_id,
                    grail_plan_id=str(grail_plan_id),
                    timeframe=timeframe,
                    fetch_start_at=fetch_start,
                    fetch_end_at=fetch_end,
                )
                .first()
            )
    except Exception as exc:
        logger.warning("_find_existing_request failed: %s", exc)
        return None


def _upsert_request(
    *,
    user_id: int,
    grail_plan_id: str,
    grail_plan_created_at: datetime,
    completed_trade_id: Optional[int],
    symbol: str,
    timeframe: str,
    fetch_start: datetime,
    fetch_end: datetime,
    window_rule: str,
    linked_trade_exit_at: Optional[datetime],
    existing: Optional[HgMarketDataRequest],
) -> int:
    """Create a new pending request row, or reset an existing one to pending. Returns request_id."""
    try:
        with db_manager.get_session() as session:
            if existing is not None:
                req = session.get(HgMarketDataRequest, existing.hg_market_data_request_id)
                req.status = "pending"
                req.bars_expected = None
                req.bars_received = None
                req.first_bar_at = None
                req.last_bar_at = None
                req.error_text = None
                req.fetched_at = None
                session.commit()
                return req.hg_market_data_request_id

            req = HgMarketDataRequest(
                user_id=user_id,
                grail_plan_id=str(grail_plan_id),
                grail_plan_created_at=grail_plan_created_at,
                completed_trade_id=completed_trade_id,
                symbol=symbol,
                timeframe=timeframe,
                fetch_start_at=fetch_start,
                fetch_end_at=fetch_end,
                request_source="manual",
                window_rule=window_rule,
                linked_trade_exit_at=linked_trade_exit_at,
                status="pending",
                provider="massive",
                provider_request_meta={},
            )
            session.add(req)
            session.commit()
            session.refresh(req)
            return req.hg_market_data_request_id
    except Exception as exc:
        logger.error("_upsert_request failed: %s", exc)
        raise


def _update_request(
    request_id: int,
    status: str,
    bars_received: int,
    first_bar_at: Optional[datetime],
    last_bar_at: Optional[datetime],
    error_text: Optional[str],
) -> None:
    """Update an HgMarketDataRequest row with fetch outcome."""
    try:
        with db_manager.get_session() as session:
            req = session.get(HgMarketDataRequest, request_id)
            if req is None:
                logger.warning("_update_request: request_id=%s not found", request_id)
                return
            req.status = status
            req.bars_received = bars_received
            req.first_bar_at = first_bar_at
            req.last_bar_at = last_bar_at
            req.error_text = error_text
            req.fetched_at = datetime.now(tz=timezone.utc)
            session.commit()
    except Exception as exc:
        logger.warning("_update_request failed for request_id=%s: %s", request_id, exc)
