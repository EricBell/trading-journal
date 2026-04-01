"""Read-only connector for the external grail_files database."""

import logging
from datetime import datetime, timezone

from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import make_url

from .config import db_config

logger = logging.getLogger(__name__)


def _grail_engine():
    """Build a SQLAlchemy engine pointing at the grail_files database."""
    url = make_url(db_config.url).set(database="grail_files")
    return create_engine(url, pool_pre_ping=True, pool_recycle=3600)


def _normalize_opened_at(opened_at):
    """Return (naive UTC datetime, date) or (None, None) if input is invalid."""
    if not isinstance(opened_at, datetime):
        return None, None
    if opened_at.tzinfo is not None:
        utc = opened_at.astimezone(timezone.utc).replace(tzinfo=None)
    else:
        utc = opened_at
    return utc, utc.date()


def find_grail_match(symbol: str, opened_at, trade_direction: str | None = None) -> dict | None:
    """
    Find the most recent grail record for symbol created before opened_at on the same date.

    Args:
        symbol: Ticker symbol (e.g. "AAPL")
        opened_at: datetime of trade open (may be timezone-aware or naive UTC)
        trade_direction: Optional "LONG" or "SHORT" — when provided, only plans with a
            matching direction in json_content are returned, avoiding cross-direction mismatches.

    Returns:
        dict of row columns or None if no match or grail DB is unreachable.
    """
    if opened_at is None:
        return None

    try:
        opened_at_utc, trade_date = _normalize_opened_at(opened_at)
        if opened_at_utc is None:
            return None

        params: dict = {"symbol": symbol, "trade_date": trade_date, "opened_at_utc": opened_at_utc}
        direction_clause = ""
        if trade_direction:
            direction_clause = (
                "   AND json_content->'trade_plan'->'entry'->>'direction' = :direction"
            )
            params["direction"] = trade_direction.upper()

        engine = _grail_engine()
        with engine.connect() as conn:
            result = conn.execute(
                text(
                    "SELECT * FROM grail_files"
                    " WHERE ticker = :symbol"
                    "   AND DATE(file_created_at) = :trade_date"
                    "   AND file_created_at < :opened_at_utc"
                    + direction_clause
                    + " ORDER BY file_created_at DESC"
                    " LIMIT 1"
                ),
                params,
            )
            row = result.mappings().first()
            return dict(row) if row is not None else None

    except Exception as exc:
        logger.warning("grail_files DB unreachable or query failed: %s", exc)
        return None


def fetch_grail_by_id(plan_id) -> dict | None:
    """Fetch a single grail plan by primary key.

    Returns dict of row columns, or None if not found or grail DB is unreachable.
    """
    try:
        engine = _grail_engine()
        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT * FROM grail_files WHERE id = :id"),
                {"id": plan_id},
            )
            row = result.mappings().first()
            return dict(row) if row is not None else None
    except Exception as exc:
        logger.warning("grail_files DB unreachable or query failed: %s", exc)
        return None


def list_grail_candidates(symbol: str, opened_at) -> list[dict]:
    """Return all grail plans for symbol on the same trading day as opened_at.

    Extracts direction from json_content so the UI can display LONG/SHORT without
    parsing the full JSON. Returns an empty list if grail DB is unreachable.
    """
    if opened_at is None:
        return []

    try:
        opened_at_utc, trade_date = _normalize_opened_at(opened_at)
        if opened_at_utc is None:
            return []

        engine = _grail_engine()
        with engine.connect() as conn:
            result = conn.execute(
                text(
                    "SELECT id, ticker, file_created_at, asset_type,"
                    "       json_content->'trade_plan'->'entry'->>'direction' AS direction"
                    " FROM grail_files"
                    " WHERE ticker = :symbol"
                    "   AND DATE(file_created_at) = :trade_date"
                    " ORDER BY file_created_at ASC"
                ),
                {"symbol": symbol, "trade_date": trade_date},
            )
            return [dict(row) for row in result.mappings()]
    except Exception as exc:
        logger.warning("grail_files DB unreachable or query failed: %s", exc)
        return []
