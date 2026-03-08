"""Read-only connector for the external grail_files database."""

import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import make_url

from .config import db_config

logger = logging.getLogger(__name__)

_ET = ZoneInfo("US/Eastern")


def _grail_engine():
    """Build a SQLAlchemy engine pointing at the grail_files database."""
    url = make_url(db_config.url).set(database="grail_files")
    return create_engine(str(url), pool_pre_ping=True, pool_recycle=3600)


def find_grail_match(symbol: str, opened_at) -> dict | None:
    """
    Find the most recent grail record for symbol created before opened_at on the same date.

    Args:
        symbol: Ticker symbol (e.g. "AAPL")
        opened_at: datetime of trade open (may be timezone-aware or naive UTC)

    Returns:
        dict of row columns or None if no match or grail DB is unreachable.
    """
    if opened_at is None:
        return None

    try:
        # Normalize opened_at to ET naive datetime
        if isinstance(opened_at, datetime):
            if opened_at.tzinfo is not None:
                opened_at_et = opened_at.astimezone(_ET).replace(tzinfo=None)
            else:
                # Assume UTC if naive
                opened_at_et = opened_at.replace(tzinfo=timezone.utc).astimezone(_ET).replace(tzinfo=None)
        else:
            return None

        trade_date = opened_at_et.date()

        engine = _grail_engine()
        with engine.connect() as conn:
            result = conn.execute(
                text(
                    "SELECT * FROM grail_files"
                    " WHERE ticker = :symbol"
                    "   AND DATE(file_created_at) = :trade_date"
                    "   AND file_created_at < :opened_at_naive"
                    " ORDER BY file_created_at DESC"
                    " LIMIT 1"
                ),
                {"symbol": symbol, "trade_date": trade_date, "opened_at_naive": opened_at_et},
            )
            row = result.mappings().first()
            return dict(row) if row is not None else None

    except Exception as exc:
        logger.warning("grail_files DB unreachable or query failed: %s", exc)
        return None
