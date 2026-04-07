"""Read-only connector for the external grail_files database."""

import logging
from datetime import date, datetime, timezone
from typing import Optional

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


def list_grail_plans(
    symbol: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    asset_type: Optional[str] = None,
    page: int = 1,
    per_page: int = 25,
) -> dict:
    """Browse grail_files with optional filters. Returns paginated rows + total count.

    Returns:
        {'rows': [dict, ...], 'total': int}
        or {'rows': [], 'total': 0, 'error': str} if grail DB is unreachable.
    """
    try:
        conditions = []
        params: dict = {}

        if symbol:
            conditions.append("ticker ILIKE :symbol")
            params["symbol"] = f"%{symbol.strip()}%"
        if date_from:
            conditions.append("DATE(file_created_at) >= :date_from")
            params["date_from"] = date_from
        if date_to:
            conditions.append("DATE(file_created_at) <= :date_to")
            params["date_to"] = date_to
        if asset_type:
            conditions.append("asset_type = :asset_type")
            params["asset_type"] = asset_type.upper()

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        engine = _grail_engine()
        with engine.connect() as conn:
            total_row = conn.execute(
                text(f"SELECT COUNT(*) FROM grail_files {where}"), params
            ).scalar()

            offset = (page - 1) * per_page
            rows = conn.execute(
                text(
                    f"SELECT id, ticker, asset_type, entry_direction,"
                    f"       file_created_at, entry_price,"
                    f"       entry_low, entry_high,"
                    f"       stop_low, stop_high,"
                    f"       tp1_low, tp1_high,"
                    f"       tp2_low, tp2_high,"
                    f"       resolved_ticker"
                    f" FROM grail_files {where}"
                    f" ORDER BY file_created_at DESC"
                    f" LIMIT :limit OFFSET :offset"
                ),
                {**params, "limit": per_page, "offset": offset},
            ).mappings().all()

        return {"rows": [dict(r) for r in rows], "total": total_row or 0}

    except Exception as exc:
        logger.warning("list_grail_plans failed: %s", exc)
        return {"rows": [], "total": 0, "error": str(exc)}


def fetch_grail_plan_full(plan_id: int) -> Optional[dict]:
    """Fetch all columns for a single grail plan by PK. Used by plan detail page."""
    try:
        engine = _grail_engine()
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT id, ticker, asset_type, entry_direction,"
                    "       file_created_at, entry_price,"
                    "       entry_low, entry_high,"
                    "       stop_low, stop_high,"
                    "       tp1_low, tp1_high,"
                    "       tp2_low, tp2_high,"
                    "       resolved_ticker, json_content"
                    " FROM grail_files WHERE id = :pid"
                ),
                {"pid": plan_id},
            ).mappings().first()
            return dict(row) if row is not None else None
    except Exception as exc:
        logger.warning("fetch_grail_plan_full failed for id=%s: %s", plan_id, exc)
        return None


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
            direction_clause = "   AND entry_direction = :direction"
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
                    "       entry_direction AS direction"
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
                    "       entry_direction AS direction, entry_low, entry_high"
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
