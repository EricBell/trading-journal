"""Read-only connector for the external grail_files database."""

import logging
from datetime import datetime, timezone

from sqlalchemy import bindparam, create_engine, text
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


def batch_grail_coverage(symbol_date_directions: list[tuple]) -> dict:
    """Batch query grail_files for a page of trades — one DB round-trip.

    Args:
        symbol_date_directions: list of (symbol, trade_date, trade_direction) tuples
            symbol:          ticker string (options should already be mapped to underlying)
            trade_date:      datetime.date in UTC
            trade_direction: "LONG", "SHORT", or None

    Returns:
        dict keyed by (symbol, trade_date) ->
            {'has_match': bool,       # direction-matching plan exists
             'has_candidates': bool}  # any plan exists on that day
        Missing keys mean grail DB was unreachable; treat as no coverage.
    """
    if not symbol_date_directions:
        return {}

    try:
        symbols = list({s for s, _, _ in symbol_date_directions})
        dates = list({d for _, d, _ in symbol_date_directions})

        engine = _grail_engine()
        with engine.connect() as conn:
            result = conn.execute(
                text(
                    "SELECT ticker, DATE(file_created_at) AS trade_date,"
                    "       json_content->'trade_plan'->'entry'->>'direction' AS direction"
                    " FROM grail_files"
                    " WHERE ticker IN :symbols"
                    "   AND DATE(file_created_at) IN :dates"
                ).bindparams(
                    bindparam("symbols", expanding=True),
                    bindparam("dates", expanding=True),
                ),
                {"symbols": symbols, "dates": dates},
            )
            rows = result.mappings().all()

        # Build (ticker, date) → [directions] index from raw results
        plan_index: dict[tuple, list[str]] = {}
        for row in rows:
            key = (row["ticker"], row["trade_date"])
            plan_index.setdefault(key, []).append((row["direction"] or "").upper())

        coverage: dict[tuple, dict] = {}
        for symbol, trade_date, trade_direction in symbol_date_directions:
            key = (symbol, trade_date)
            directions = plan_index.get(key, [])
            has_candidates = bool(directions)
            has_match = has_candidates and (
                trade_direction is None or trade_direction.upper() in directions
            )
            coverage[key] = {"has_match": has_match, "has_candidates": has_candidates}

        return coverage

    except Exception as exc:
        logger.warning("grail_files batch coverage query failed: %s", exc)
        return {}


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
